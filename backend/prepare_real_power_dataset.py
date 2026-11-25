"""
基于真实气象再分析（ERA5，经 Open-Meteo Historical Weather API 获取）构建符合 power_forecast_std 标准的
中国六大新能源基地功率预测数据集（Admin/china-meteo-power-dataset）—— 半仿真数据集

  - 实况气象：ERA5 逐小时 100m 风速、短波辐照、气温、相对湿度、地表气压（真实再分析数据）
  - 场站出力：由 ERA5 实况经物理发电模型换算（风电：空气密度修正功率曲线；光伏：NOCT 结温 + 系统效率），不是真实场站出力
  - 次日 NWP：由 ERA5 实况经独立的「预报误差过程」生成（仿真），参照常见日前数值预报的误差量级：
      * 只保留天气背景（3 小时滑动平滑，去掉小尺度起伏）
      * 每天有整体偏差（风速 σ≈0.8 m/s，晴空指数 σ≈0.08）
      * 天气过程提前 / 推迟 0~3 小时
      * 随提前期增大的相关误差（风速 σ≈1.0 → 2.0 m/s，晴空指数 σ≈0.08 → 0.18）
    （早期版本直接使用 Open-Meteo Historical Forecast API，取回的数值与 ERA5 实况逐小时完全相同，等于把次日实况交给模型，已废弃）

时间切分（严格零泄露）：
  - 采集时段：2024-01-01 至 2024-10-25（共 299 天，每座场站 7,176 小时）
  - 训练集：前 240 天（6 场站 × 240 = 1,440 个日前预测窗口）
  - 隔离带：中间空出 72 小时（≥ 48h，杜绝相邻窗口重叠）
  - 测试集：后 50 天（6 场站 × 50 = 300 个日前预测窗口）

数据署名：Contains modified Copernicus Climate Change Service information 2024（ERA5）；Weather data by Open-Meteo.com（CC BY 4.0）。
"""
from __future__ import annotations

import json
import math
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

import power_forecast_std as pstd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "china-meteo-power-dataset"
RAW_CACHE_DIR = DATA_DIR / "_raw_openmeteo"

START_DATE = "2024-01-01"
END_DATE = "2024-10-25"
TRAIN_DAYS = 240
TEST_DAYS = 50
GAP_DAYS = 3  # 72h 隔离带

STATIONS = [
    {"id": "GS-W01", "name": "甘肃酒泉风电基地", "kind": "wind", "capacity_mw": 150.0, "lat": 39.73, "lon": 98.49, "region": "甘肃河西", "cut_in": 3.0, "rated": 11.8, "cut_out": 24.0},
    {"id": "GS-S02", "name": "甘肃敦煌光伏基地", "kind": "solar", "capacity_mw": 120.0, "lat": 40.14, "lon": 94.66, "region": "甘肃河西", "pr": 0.84, "temp_coeff": -0.0038},
    {"id": "SX-S03", "name": "山西大同光伏基地", "kind": "solar", "capacity_mw": 100.0, "lat": 40.08, "lon": 113.30, "region": "晋北高原", "pr": 0.82, "temp_coeff": -0.0040},
    {"id": "NM-W04", "name": "内蒙锡林郭勒风电", "kind": "wind", "capacity_mw": 200.0, "lat": 43.93, "lon": 116.09, "region": "蒙东草原", "cut_in": 3.2, "rated": 12.2, "cut_out": 25.0},
    {"id": "JS-W05", "name": "江苏如东海上风电", "kind": "wind", "capacity_mw": 180.0, "lat": 32.55, "lon": 121.35, "region": "黄海近海", "cut_in": 2.8, "rated": 11.2, "cut_out": 25.0},
    {"id": "QH-S06", "name": "青海共和高原光伏", "kind": "solar", "capacity_mw": 160.0, "lat": 36.28, "lon": 100.62, "region": "青藏高原", "pr": 0.86, "temp_coeff": -0.0035},
]


def _fetch_json(url: str, retries: int = 3) -> dict:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AlgoHub-PowerForecast/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 {url}: {last_err}")


def _fetch_station_obs(st: dict) -> dict:
    """ERA5 实况（优先读本地缓存，缓存缺失时才联网获取）"""
    RAW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    obs_cache = RAW_CACHE_DIR / f"{st['id'].lower()}_obs.json"
    if obs_cache.exists():
        return json.loads(obs_cache.read_text(encoding="utf-8"))
    qs = urllib.parse.urlencode({
        "latitude": st["lat"],
        "longitude": st["lon"],
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure,wind_speed_100m,shortwave_radiation",
        "wind_speed_unit": "ms",
        "timezone": "Asia/Shanghai",
    })
    obs = _fetch_json(f"https://archive-api.open-meteo.com/v1/archive?{qs}")
    obs_cache.write_text(json.dumps(obs), encoding="utf-8")
    time.sleep(0.4)
    return obs


def _smooth3(vals: list[float]) -> list[float]:
    n = len(vals)
    return [sum(vals[max(0, t - 1) : min(n, t + 2)]) / (min(n, t + 2) - max(0, t - 1)) for t in range(n)]


def _clear_sky_envelope(irrs: list[float], half_days: int = 7) -> list[float]:
    """晴空辐照包络：同一时刻前后 ±half_days 天的最大值（用于计算晴空指数）"""
    n = len(irrs)
    out = []
    for t in range(n):
        vals = [irrs[t + 24 * k] for k in range(-half_days, half_days + 1) if 0 <= t + 24 * k < n]
        out.append(max(vals) if vals else 0.0)
    return out


def _nwp_day(winds_s: list[float], kt_s: list[float], clear: list[float], start: int, rng: random.Random) -> tuple[list[float], list[float]]:
    """次日 24h 仿真 NWP：天气背景 + 整日偏差 + 0~3h 相位偏移 + 随提前期增大的 AR(1) 误差"""
    n = len(winds_s)
    shift = rng.choice([-3, -2, -1, -1, 0, 0, 0, 1, 1, 2, 3])
    w_bias, k_bias = rng.gauss(0, 0.8), rng.gauss(0, 0.08)
    ew = ek = 0.0
    winds, irrs = [], []
    for h in range(24):
        lead = h / 23.0
        ew = 0.75 * ew + rng.gauss(0, (1.0 + 1.0 * lead) * math.sqrt(1 - 0.75 ** 2))
        ek = 0.75 * ek + rng.gauss(0, (0.08 + 0.10 * lead) * math.sqrt(1 - 0.75 ** 2))
        src = min(n - 1, max(0, start + h + shift))
        winds.append(max(0.3, winds_s[src] + w_bias + ew))
        c = clear[start + h]  # 晴空包络按天文时刻，不受相位偏移影响
        irrs.append(max(0.0, c * min(1.05, max(0.0, kt_s[src] + k_bias + ek))) if c > 5.0 else 0.0)
    return winds, irrs


def _clean_series(vals: list, default: float = 0.0) -> list[float]:
    out: list[float] = []
    prev = default
    for v in vals:
        if v is None or (isinstance(v, float) and not math.isfinite(v)):
            out.append(prev)
        else:
            prev = float(v)
            out.append(prev)
    return out


def _physical_power(st: dict, wind: float, irr: float, temp: float, pressure: float, rng: random.Random) -> float:
    """基于实况气象的物理场站出力模型（含空气密度/结温修正与微小机组波动）"""
    cap = st["capacity_mw"]
    if st["kind"] == "wind":
        # 空气密度修正有效风速：v_eff = v * (rho / rho_0)^(1/3)
        rho = (pressure * 100.0) / (287.05 * (temp + 273.15))
        v_eff = wind * ((max(0.7, min(1.3, rho / 1.225))) ** (1.0 / 3.0))
        v_in, v_rated, v_out = st["cut_in"], st["rated"], st["cut_out"]
        if v_eff < v_in or v_eff > v_out:
            p = 0.0
        elif v_eff < v_rated:
            norm = (v_eff - v_in) / (v_rated - v_in)
            p = cap * (0.04 * norm + 0.96 * (norm ** 2.65))
        else:
            p = cap * 0.985
        noise = rng.gauss(0, cap * 0.012) if p > 0 else 0.0
        return max(0.0, min(cap, p + noise))
    else:
        if irr <= 3.0:
            return 0.0
        # NOCT 电池结温模型：T_cell = T_amb + (NOCT - 20) / 800 * G
        t_cell = temp + 0.031 * irr
        temp_factor = max(0.76, min(1.08, 1.0 + st["temp_coeff"] * (t_cell - 25.0)))
        # 弱光效率衰减 + 逆变器限幅
        low_light = min(1.0, (irr / 80.0) ** 0.25) if irr < 80.0 else 1.0
        p = cap * (irr / 1000.0) * st["pr"] * temp_factor * low_light
        noise = rng.gauss(0, cap * 0.008)
        return max(0.0, min(cap, p + noise))


def _weather_tag(wind: float, irr: float, hour: int) -> str:
    if wind >= 10.5:
        return "大风"
    if 8 <= hour <= 16:
        if irr >= 520:
            return "晴"
        if irr >= 240:
            return "多云"
        return "阴"
    return "微风" if wind < 4.5 else "和风"


def build_dataset() -> dict:
    for split in ("train", "test"):
        sdir = DATA_DIR / split / "series"
        sdir.mkdir(parents=True, exist_ok=True)
        for old in sdir.glob("*.csv"):
            old.unlink()

    records: dict[str, list[dict]] = {"train": [], "test": []}
    counts: dict[str, dict[str, int]] = {"train": {}, "test": {}}
    test_first_day = TRAIN_DAYS + 1 + GAP_DAYS  # 训练最后一天用 d+1，再空出 GAP_DAYS 天

    for s_idx, st in enumerate(STATIONS):
        print(f"[china-meteo] 采集 {st['name']}（{st['lat']}°N, {st['lon']}°E）ERA5 实况（本地缓存优先），生成仿真 NWP…")
        obs = _fetch_station_obs(st)
        oh = obs["hourly"]

        times = oh["time"]
        n_total = len(times)
        temps = _clean_series(oh["temperature_2m"][:n_total], 15.0)
        hums = _clean_series(oh["relative_humidity_2m"][:n_total], 50.0)
        press = _clean_series(oh["surface_pressure"][:n_total], 1010.0)
        winds = _clean_series(oh["wind_speed_100m"][:n_total], 5.0)
        irrs = _clean_series(oh["shortwave_radiation"][:n_total], 0.0)
        # NWP 误差过程的输入：平滑后的天气背景与晴空指数
        winds_s = _smooth3([max(0.0, v) for v in winds])
        clear = _clear_sky_envelope([max(0.0, v) for v in irrs])
        kt_s = _smooth3([min(1.05, max(0.0, irrs[t]) / clear[t]) if clear[t] > 5.0 else 0.0 for t in range(n_total)])
        nwp_rng = random.Random(77000 + s_idx)

        rng = random.Random(20261125 + s_idx * 97)
        timeline = []
        for t in range(n_total):
            hour = int(times[t][11:13])
            w = max(0.0, winds[t])
            ir = max(0.0, irrs[t])
            pw = _physical_power(st, w, ir, temps[t], press[t], rng)
            timeline.append({
                "hour": hour,
                "wind_speed_ms": w,
                "irradiance_wm2": ir,
                "temp_c": temps[t],
                "humidity_pct": max(0.0, min(100.0, hums[t])),
                "pressure_hpa": press[t],
                "power_mw": pw,
                "weather": _weather_tag(w, ir, hour),
            })

        avail_days = n_total // 24
        assert test_first_day + TEST_DAYS + 1 <= avail_days, f"可用天数 {avail_days} 不足"

        for split, days in (("train", range(TRAIN_DAYS)), ("test", range(test_first_day, test_first_day + TEST_DAYS))):
            for n, d in enumerate(days, 1):
                t0 = d * 24
                hist = timeline[t0 : t0 + 24]
                fut = timeline[t0 + 24 : t0 + 48]
                nwp_w, nwp_i = _nwp_day(winds_s, kt_s, clear, t0 + 24, nwp_rng)
                rows = [
                    {
                        "hour": hist[h]["hour"],
                        "wind_speed_ms": hist[h]["wind_speed_ms"],
                        "irradiance_wm2": hist[h]["irradiance_wm2"],
                        "temp_c": hist[h]["temp_c"],
                        "humidity_pct": hist[h]["humidity_pct"],
                        "pressure_hpa": hist[h]["pressure_hpa"],
                        "nwp_wind_ms": nwp_w[h],
                        "nwp_irr_wm2": nwp_i[h],
                        "power_mw": hist[h]["power_mw"],
                    }
                    for h in range(24)
                ]
                fname = f"{split}_{st['id'].lower()}_{n:04d}.csv"
                pstd.write_series_csv(DATA_DIR / split / "series" / fname, rows)
                target = [round(r["power_mw"], 2) for r in fut]
                records[split].append({
                    "file_name": f"series/{fname}",
                    "value": f"{sum(target) / 24:.2f}",
                    "station": st["name"],
                    "kind": st["kind"],
                    "weather": fut[12]["weather"],
                    "peak_mw": f"{max(target):.2f}",
                    "t0": t0,
                    "target_24h": json.dumps(target, separators=(",", ":")),
                })
                counts[split][st["name"]] = counts[split].get(st["name"], 0) + 1

    last_train_hour = (TRAIN_DAYS - 1) * 24 + 47
    first_test_hour = test_first_day * 24
    gap_hours = first_test_hour - last_train_hour - 1
    assert gap_hours >= 48

    meta = pstd.write_meta(
        DATA_DIR,
        {
            "id": "Admin/china-meteo-power-dataset",
            "name": "china-meteo-power-dataset",
            "displayName": "中国六大新能源基地功率数据集（ERA5 实况 + 仿真 NWP 误差）",
            "summary": f"【半仿真】2024 年 ERA5 真实逐小时气象实况；场站出力由物理模型换算，次日 NWP 由仿真预报误差过程生成。覆盖甘肃酒泉/敦煌、山西大同、内蒙锡林郭勒、江苏如东海上、青海共和 6 座 100–200 MW 场站（训练 {TRAIN_DAYS} 天 / 测试 {TEST_DAYS} 天，隔离 {gap_hours}h）。",
            "tags": ["半仿真", "ERA5再分析", "NWP气象", "新能源场站", "时序预测"],
            "stations": {
                s["name"]: {"id": s["id"], "kind": s["kind"], "capacity_mw": s["capacity_mw"], "lat": s["lat"], "lon": s["lon"], "region": s["region"]}
                for s in STATIONS
            },
            "split": {"trainDays": TRAIN_DAYS, "testDays": TEST_DAYS, "lastTrainHour": last_train_hour, "firstTestHour": first_test_hour, "gapHours": gap_hours},
            "createdAt": "2026-11-25T18:45:00+08:00",
            "benchmark": {
                "id": "china-meteo-power-bench",
                "displayName": "中国六大新能源基地功率预测评测基准（ERA5 + 仿真 NWP）",
            },
        },
        records,
        counts,
    )
    (DATA_DIR / "README.md").write_text(README.format(gap=gap_hours), encoding="utf-8")
    print(f"[china-meteo] 构建完成：train={meta['train']['files']} 条，test={meta['test']['files']} 条，隔离 {gap_hours}h")
    return meta


README = """# china-meteo-power-dataset（中国六大新能源基地功率数据集 · ERA5 实况 + 仿真 NWP 误差）

> **半仿真数据集**：气象实况为真实 ERA5 再分析数据；场站出力由物理发电模型换算，次日 NWP 由仿真预报误差过程生成，均不是真实采集数据。

符合平台**新能源功率预测标准**（`task = power-forecast`）的日前功率预测数据集，覆盖中国 6 个典型新能源基地（装机 100–200 MW）。

## 数据构成

- **实况气象（真实）**：ERA5 再分析（2024-01-01 至 2024-10-25），100m 风速、短波辐照度、2m 气温、相对湿度、地表气压，经 Open-Meteo Historical Weather API 获取。
- **场站出力（换算）**：由 ERA5 实况经物理发电模型换算（风电：空气密度修正功率曲线；光伏：NOCT 电池结温 + 系统效率）。
- **次日 NWP（仿真）**：以 ERA5 实况为基础，叠加参照常见日前数值预报误差量级的误差过程：只保留天气背景（去掉小尺度起伏）、每天整体偏差、天气过程提前 / 推迟 0–3 小时、随提前期增大的相关误差（风速约 1–2 m/s，晴空指数约 0.08–0.18）。

## 覆盖场站（6 座，异构装机容量）

| 场站名称 | 编号 | 类型 | 装机容量 | 地理位置 |
| --- | --- | --- | --- | --- |
| 甘肃酒泉风电基地 | GS-W01 | 风电 | 150 MW | 39.73°N, 98.49°E |
| 甘肃敦煌光伏基地 | GS-S02 | 光伏 | 120 MW | 40.14°N, 94.66°E |
| 山西大同光伏基地 | SX-S03 | 光伏 | 100 MW | 40.08°N, 113.30°E |
| 内蒙锡林郭勒风电 | NM-W04 | 风电 | 200 MW | 43.93°N, 116.09°E |
| 江苏如东海上风电 | JS-W05 | 风电 | 180 MW | 32.55°N, 121.35°E |
| 青海共和高原光伏 | QH-S06 | 光伏 | 160 MW | 36.28°N, 100.62°E |

## 时间切分（防泄露）

| 部分 | 样本数 | 时段 |
| --- | --- | --- |
| 训练集 | 1,440 | 2024 年前 240 天（每场站 240 个日前窗口） |
| 隔离带 | — | 中间空出 {gap}h，训练与测试窗口无时间重叠 |
| 测试集 | 300 | 随后 50 天（每场站 50 个日前窗口，仅评测器读取真值） |

## 数据署名与许可

- Contains modified Copernicus Climate Change Service information 2024（ERA5，Hersbach et al. 2023）。
- Weather data by [Open-Meteo.com](https://open-meteo.com/)，CC BY 4.0。Open-Meteo 免费 API 仅限非商业用途，商业使用需另行获得授权。
"""


if __name__ == "__main__":
    build_dataset()
