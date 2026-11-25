"""
构建新能源场站短期功率预测仿真数据集（Admin/wind-solar-power-dataset）—— 符合 power_forecast_std 标准

  注意：本数据集由气象与功率曲线规律仿真生成，不是真实采集数据。

  - 6 座典型风电 / 光伏场站（装机 100 MW），每座场站连续仿真约 255 天的逐小时实况
  - 每条样本是一次「日前预测」：00:00 发布，输入前一天 24h 实测遥测 + 次日 24h NWP 数值天气预报，预测次日 24h 功率
      series/*.csv：24 行，第 h 行 = 前一天 h 时实测 + 次日 h 时 NWP 预报（两者同一时刻，相差 24h）
  - NWP 预报由独立的「预报过程」生成，而不是在真实未来天气上加小噪声：
      * 只预报天气背景（不含阵风、云团过境等小尺度过程）
      * 每天有整体偏差（风速 ±0.8 m/s、云量 ±0.1）
      * 天气过程的时间偏差（提前 / 推迟 0~3h）
      * 随提前期增大的相关误差（风速 σ 约 1.0 → 2.0 m/s，云量 σ 约 0.08 → 0.18）
  - 时间切分：前 200 天为训练集，之后空出 48h 隔离带（训练窗口最后时刻与测试窗口最早时刻相隔 ≥ 48h），再取 50 天为测试集
  - 训练集 1,200 条 / 测试集 300 条（6 场站 × 200 / 50 天）
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import power_forecast_std as pstd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "wind-solar-power-dataset"

TRAIN_DAYS = 200
TEST_DAYS = 50
GAP_HOURS = 48  # 训练窗口最后一个小时与测试窗口第一个小时之间的最小间隔

STATIONS = [
    {"id": "HZ-W01", "name": "华中风电一号", "kind": "wind", "capacity_mw": 100.0, "wind_base": 7.6, "cloud_base": 0.34, "temp_base": 17.5},
    {"id": "XB-S02", "name": "西北光伏二号", "kind": "solar", "capacity_mw": 100.0, "wind_base": 4.2, "cloud_base": 0.20, "temp_base": 19.0},
    {"id": "HD-W03", "name": "华东海上风电", "kind": "wind", "capacity_mw": 100.0, "wind_base": 9.1, "cloud_base": 0.38, "temp_base": 18.5},
    {"id": "XN-S04", "name": "西南山地光伏", "kind": "solar", "capacity_mw": 100.0, "wind_base": 3.5, "cloud_base": 0.42, "temp_base": 20.5},
    {"id": "NM-W05", "name": "内蒙戈壁风电", "kind": "wind", "capacity_mw": 100.0, "wind_base": 8.4, "cloud_base": 0.18, "temp_base": 11.5},
    {"id": "QH-S06", "name": "青海高原光伏", "kind": "solar", "capacity_mw": 100.0, "wind_base": 5.0, "cloud_base": 0.15, "temp_base": 10.0},
]


def _clear_sky(hour: int, season: float) -> float:
    if not 6 <= hour <= 19:
        return 0.0
    return 990.0 * (max(0.0, math.sin(math.pi * (hour - 6) / 13.0)) ** 1.12) * (1.0 + 0.12 * season)


def _simulate_station(station: dict, total_hours: int, seed: int) -> list[dict]:
    """逐小时实况。除公开列外，另记录天气背景（_wind_bg / _cloud_bg），只供 NWP 预报过程使用，不写入数据集"""
    rng = random.Random(seed)
    cap = station["capacity_mw"]
    rows: list[dict] = []
    bg_wind, cloud, pressure = station["wind_base"], station["cloud_base"], 1012.0
    gust_left, gust_amp, burst_left = 0, 0.0, 0

    for t in range(total_hours):
        hour, day = t % 24, t // 24
        season = math.sin(2 * math.pi * day / 365.0)
        bg_wind = max(1.0, min(18.5, 0.91 * bg_wind + 0.09 * (station["wind_base"] + 1.8 * season) + rng.gauss(0, 0.72)))
        cloud = max(0.0, min(0.95, 0.87 * cloud + 0.13 * station["cloud_base"] + rng.gauss(0, 0.09)))
        pressure = max(990.0, min(1035.0, 0.94 * pressure + 0.06 * 1012.0 + rng.gauss(0, 0.8)))

        # 小尺度过程：阵风、云团过境（NWP 不会预报）
        if gust_left <= 0 and rng.random() < 0.03:
            gust_left, gust_amp = rng.randint(2, 5), rng.uniform(1.8, 4.0) * (1 if rng.random() > 0.35 else -1)
        if gust_left > 0:
            gust_left -= 1
        else:
            gust_amp *= 0.5
        if burst_left <= 0 and rng.random() < 0.04:
            burst_left = rng.randint(2, 6)
        eff_cloud = min(0.96, cloud + (0.35 if burst_left > 0 else 0.0))
        burst_left = max(0, burst_left - 1)

        diurnal_wind = 1.3 * math.sin(2 * math.pi * (hour - 14) / 24.0)
        wind_bg = bg_wind + diurnal_wind
        wind = max(0.3, wind_bg + gust_amp + rng.gauss(0, 0.42))
        clear = _clear_sky(hour, season)
        irr = max(0.0, clear * (1.0 - 0.74 * eff_cloud) + rng.gauss(0, 16.0)) if clear > 0 else 0.0
        temp = station["temp_base"] + 7.5 * season + 5.8 * math.sin(2 * math.pi * (hour - 9) / 24.0) - 3.2 * eff_cloud + rng.gauss(0, 0.55)
        hum = max(12.0, min(98.0, 44.0 + 36.0 * eff_cloud - 12.0 * math.sin(2 * math.pi * (hour - 9) / 24.0) + rng.gauss(0, 2.2)))

        if station["kind"] == "wind":
            if wind < 3.0 or wind > 22.0:
                p = 0.0
            elif wind < 12.2:
                p = cap * ((wind - 3.0) / 9.2) ** 2.45
            else:
                p = cap * 0.98
            power = max(0.0, min(cap, p + rng.gauss(0, 1.9)))
        else:
            p = cap * (irr / 920.0) * max(0.84, 1.0 - 0.0038 * max(0.0, temp - 25.0))
            power = max(0.0, min(cap, p + (rng.gauss(0, 1.5) if irr > 5 else 0.0)))

        weather = "大风" if wind >= 10.5 else "晴" if eff_cloud < 0.25 else "多云" if eff_cloud < 0.58 else "阴"
        rows.append({
            "hour": hour, "wind_speed_ms": wind, "irradiance_wm2": irr, "temp_c": temp, "humidity_pct": hum,
            "pressure_hpa": pressure, "power_mw": power, "weather": weather,
            "_wind_bg": wind_bg, "_cloud_bg": cloud, "_clear": clear,
        })
    return rows


def _nwp_forecast(timeline: list[dict], start: int, rng: random.Random) -> tuple[list[float], list[float]]:
    """次日 24h 的 NWP 预报：基于天气背景，含整日偏差、时间偏移与随提前期增大的相关误差"""
    shift = rng.choice([-3, -2, -1, -1, 0, 0, 0, 1, 1, 2, 3])
    w_bias, c_bias = rng.gauss(0, 0.8), rng.gauss(0, 0.1)
    ew = ec = 0.0
    winds, irrs = [], []
    for h in range(24):
        lead = h / 23.0
        ew = 0.75 * ew + rng.gauss(0, (1.0 + 1.0 * lead) * math.sqrt(1 - 0.75 ** 2))
        ec = 0.75 * ec + rng.gauss(0, (0.08 + 0.10 * lead) * math.sqrt(1 - 0.75 ** 2))
        src = timeline[min(len(timeline) - 1, max(0, start + h + shift))]
        winds.append(max(0.3, src["_wind_bg"] + w_bias + ew))
        cloud_fc = min(0.95, max(0.0, src["_cloud_bg"] + c_bias + ec))
        clear = timeline[start + h]["_clear"]  # 晴空辐照按天文时刻计算，不受天气过程时间偏差影响
        irrs.append(max(0.0, clear * (1.0 - 0.74 * cloud_fc)) if clear > 0 else 0.0)
    return winds, irrs


def build_dataset() -> dict:
    for split in ("train", "test"):
        sdir = DATA_DIR / split / "series"
        sdir.mkdir(parents=True, exist_ok=True)
        for old in sdir.glob("*.csv"):
            old.unlink()

    # 窗口 d：历史 = 第 d 天，预测 = 第 d+1 天。训练窗口 d ∈ [0, TRAIN_DAYS)，最后一个小时为 (TRAIN_DAYS + 1) * 24 - 1
    test_first_day = TRAIN_DAYS + 1 + math.ceil(GAP_HOURS / 24)
    total_hours = (test_first_day + TEST_DAYS + 2) * 24
    records: dict[str, list[dict]] = {"train": [], "test": []}
    counts: dict[str, dict[str, int]] = {"train": {}, "test": {}}

    for s_idx, st in enumerate(STATIONS):
        timeline = _simulate_station(st, total_hours, seed=20261125 + s_idx * 173)
        nwp_rng = random.Random(9100 + s_idx)
        for split, days in (("train", range(TRAIN_DAYS)), ("test", range(test_first_day, test_first_day + TEST_DAYS))):
            for n, d in enumerate(days, 1):
                t0 = d * 24
                hist, fut = timeline[t0 : t0 + 24], timeline[t0 + 24 : t0 + 48]
                nwp_w, nwp_irr = _nwp_forecast(timeline, t0 + 24, nwp_rng)
                rows = [{**hist[h], "nwp_wind_ms": nwp_w[h], "nwp_irr_wm2": nwp_irr[h]} for h in range(24)]
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
    assert first_test_hour - last_train_hour - 1 >= GAP_HOURS
    meta = pstd.write_meta(
        DATA_DIR,
        {
            "id": "Admin/wind-solar-power-dataset",
            "name": "wind-solar-power-dataset",
            "displayName": "新能源场站短期功率时序数据集（仿真）",
            "summary": f"【仿真】6 座风电 / 光伏场站日前功率预测：前一天 24h 实测 + 次日 24h NWP 预报 → 次日 24h 逐小时功率。按时间切分，训练 {TRAIN_DAYS} 天、测试 {TEST_DAYS} 天，中间隔离 {first_test_hour - last_train_hour - 1}h。",
            "tags": ["仿真数据", "新能源场站", "NWP气象", "时序预测"],
            "stations": {s["name"]: {"id": s["id"], "kind": s["kind"], "capacity_mw": s["capacity_mw"]} for s in STATIONS},
            "split": {"trainDays": TRAIN_DAYS, "testDays": TEST_DAYS, "lastTrainHour": last_train_hour, "firstTestHour": first_test_hour, "gapHours": first_test_hour - last_train_hour - 1},
            "createdAt": "2026-11-25T16:00:00+08:00",
            "benchmark": {"id": "power-forecast-bench", "displayName": "新能源场站短期功率预测评测基准（仿真数据）"},
        },
        records,
        counts,
    )
    (DATA_DIR / "README.md").write_text(README.format(gap=meta["split"]["gapHours"]), encoding="utf-8")
    print(f"[power] 已生成 Admin/wind-solar-power-dataset：train={meta['train']['files']} 条，test={meta['test']['files']} 条，隔离 {meta['split']['gapHours']}h")
    return meta


README = """# wind-solar-power-dataset（新能源场站短期功率预测 · 仿真数据集）

> 本数据集由气象与功率曲线规律**仿真生成**，用于算法开发与对照，不是真实采集数据。

符合平台**新能源功率预测标准**（task = `power-forecast`）的日前功率预测数据集：6 座风电 / 光伏场站（装机均为 100 MW），每条样本是一次 00:00 发布的日前预测。

## 数据组成

| 部分 | 样本数 | 时段 |
| --- | --- | --- |
| 训练集 | 1,200 | 每座场站第 1–200 天 |
| 测试集 | 300 | 每座场站之后的 50 天，与训练集最后时刻相隔 {gap}h |

## 文件格式

`series/*.csv`：24 行，第 h 行是**前一天 h 时的实测值**与**次日 h 时的 NWP 预报值**（同一时刻，相差 24 小时）：

```
hour,wind_speed_ms,irradiance_wm2,temp_c,humidity_pct,pressure_hpa,nwp_wind_ms,nwp_irr_wm2,power_mw
```

`labels.csv`：`file_name,value,station,kind,weather,peak_mw,t0,target_24h`

- `target_24h`：次日 24 个逐小时实际功率（MW，即 ground truth）
- `t0`：历史窗口起点（自仿真开始的小时数），可用于按时间切分验证集
- 场站类型与装机容量见 `meta.json` 的 `stations`

## NWP 预报误差

NWP 由独立的预报过程生成，误差量级参照常见的日前数值预报水平：只预报天气背景，不含阵风与云团过境；每天有整体偏差；天气过程会提前或推迟 0–3 小时；误差随提前期增大（风速约 1–2 m/s，云量约 0.08–0.18）。
"""


if __name__ == "__main__":
    build_dataset()
