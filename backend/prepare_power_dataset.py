"""
构建新能源场站短期功率时序预测数据集（Admin/wind-solar-power-dataset）—— 对标 0x07 标准：
  - 覆盖 6 座典型风电/光伏场站（装机容量 100 MW）：
      华中风电一号、西北光伏二号、华东海上风电、西南山地光伏、内蒙戈壁风电、青海高原光伏
  - 每条样本为 24 小时历史遥测 + 未来 24 小时 NWP 数值天气预报（9 列 CSV）：
      hour, wind_speed_ms, irradiance_wm2, temp_c, humidity_pct, pressure_hpa, nwp_wind_ms, nwp_irr_wm2, power_mw
  - 真实感细节：
      * AR(1) 气象演化 + 阵风/云团过境骤降 + 限电/切出保护 + 传感器轻微噪声
      * NWP 气象预报随提前期（+1h -> +24h）误差自然增大，真实反映短期功率预测难度梯度
  - 训练集 1,200 条 + 测试集 300 条（与 0x07 同规模，按时间顺序切分并留 48h 隔离带防泄露）
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import power_forecast_std as pstd

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "wind-solar-power-dataset"

STATIONS = [
    {"id": "HZ-W01", "name": "华中风电一号", "kind": "wind", "capacity": 100.0, "wind_base": 7.6, "cloud_base": 0.34, "temp_base": 17.5},
    {"id": "XB-S02", "name": "西北光伏二号", "kind": "solar", "capacity": 100.0, "wind_base": 4.2, "cloud_base": 0.20, "temp_base": 19.0},
    {"id": "HD-W03", "name": "华东海上风电", "kind": "wind", "capacity": 100.0, "wind_base": 9.1, "cloud_base": 0.38, "temp_base": 18.5},
    {"id": "XN-S04", "name": "西南山地光伏", "kind": "solar", "capacity": 100.0, "wind_base": 3.5, "cloud_base": 0.42, "temp_base": 20.5},
    {"id": "NM-W05", "name": "内蒙戈壁风电", "kind": "wind", "capacity": 100.0, "wind_base": 8.4, "cloud_base": 0.18, "temp_base": 11.5},
    {"id": "QH-S06", "name": "青海高原光伏", "kind": "solar", "capacity": 100.0, "wind_base": 5.0, "cloud_base": 0.15, "temp_base": 10.0},
]


def _simulate_station_timeline(station: dict, total_hours: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    kind = station["kind"]
    cap = station["capacity"]
    rows: list[dict] = []

    bg_wind = station["wind_base"]
    cloud = station["cloud_base"]
    pressure = 1012.0
    gust_left = 0
    gust_amp = 0.0
    cloud_burst_left = 0

    for t in range(total_hours):
        hour = t % 24
        day = t // 24
        season = math.sin(2 * math.pi * day / 365.0)

        bg_wind = max(1.0, min(18.5, 0.91 * bg_wind + 0.09 * (station["wind_base"] + 1.8 * season) + rng.gauss(0, 0.72)))
        cloud = max(0.0, min(0.95, 0.87 * cloud + 0.13 * station["cloud_base"] + rng.gauss(0, 0.09)))
        pressure = max(990.0, min(1035.0, 0.94 * pressure + 0.06 * 1012.0 + rng.gauss(0, 0.8)))

        # 偶发阵风与云团过境骤降（增加真实预测难度）
        if gust_left <= 0 and rng.random() < 0.03:
            gust_left = rng.randint(2, 5)
            gust_amp = rng.uniform(1.8, 4.0) * (1 if rng.random() > 0.35 else -1)
        if gust_left > 0:
            gust_left -= 1
        else:
            gust_amp *= 0.5

        if cloud_burst_left <= 0 and rng.random() < 0.04:
            cloud_burst_left = rng.randint(2, 6)
        eff_cloud = min(0.96, cloud + (0.35 if cloud_burst_left > 0 else 0.0))
        if cloud_burst_left > 0:
            cloud_burst_left -= 1

        diurnal_wind = 1.3 * math.sin(2 * math.pi * (hour - 14) / 24.0)
        wind_speed = max(0.3, bg_wind + diurnal_wind + gust_amp + rng.gauss(0, 0.42))

        if 6 <= hour <= 19:
            solar_angle = max(0.0, math.sin(math.pi * (hour - 6) / 13.0))
            clear_sky = 990.0 * (solar_angle ** 1.12) * (1.0 + 0.12 * season)
            irradiance = max(0.0, clear_sky * (1.0 - 0.74 * eff_cloud) + rng.gauss(0, 16.0))
        else:
            irradiance = 0.0

        temp_c = station["temp_base"] + 7.5 * season + 5.8 * math.sin(2 * math.pi * (hour - 9) / 24.0) - 3.2 * eff_cloud + rng.gauss(0, 0.55)
        humidity = max(12.0, min(98.0, 44.0 + 36.0 * eff_cloud - 12.0 * math.sin(2 * math.pi * (hour - 9) / 24.0) + rng.gauss(0, 2.2)))

        if kind == "wind":
            if wind_speed < 3.0:
                p = 0.0
            elif wind_speed < 12.2:
                p = cap * ((wind_speed - 3.0) / 9.2) ** 2.45
            elif wind_speed <= 22.0:
                p = cap * 0.98
            else:
                p = 0.0
            power = max(0.0, min(cap, p + rng.gauss(0, 1.9)))
        else:
            temp_eff = max(0.84, 1.0 - 0.0038 * max(0.0, temp_c - 25.0))
            p = cap * (irradiance / 920.0) * temp_eff
            power = max(0.0, min(cap, p + (rng.gauss(0, 1.5) if irradiance > 5 else 0.0)))

        if wind_speed >= 10.5:
            weather = "大风"
        elif eff_cloud < 0.25:
            weather = "晴"
        elif eff_cloud < 0.58:
            weather = "多云"
        else:
            weather = "阴"

        rows.append({
            "hour": hour,
            "wind_speed_ms": round(wind_speed, 2),
            "irradiance_wm2": round(irradiance, 1),
            "temp_c": round(temp_c, 1),
            "humidity_pct": round(humidity, 1),
            "pressure_hpa": round(pressure, 1),
            "power_mw": round(power, 2),
            "weather": weather,
        })
    return rows


def build_dataset() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for split in ("train", "test"):
        sdir = DATA_DIR / split / "series"
        sdir.mkdir(parents=True, exist_ok=True)
        for old in sdir.glob("*.csv"):
            old.unlink()

    # 6 座场站 × (200 训练 + 50 测试) = 1,200 训练 + 300 测试（与 0x07 同规模）
    train_per_st = 200
    test_per_st = 50
    stride = 5
    gap_hours = 48

    split_records: dict[str, list[dict]] = {"train": [], "test": []}
    class_counts: dict[str, dict[str, int]] = {"train": {}, "test": {}}
    nwp_rng = random.Random(20261125)

    for s_idx, st in enumerate(STATIONS):
        total_needed = (train_per_st + test_per_st) * stride + gap_hours + 64
        timeline = _simulate_station_timeline(st, total_needed, seed=20261125 + s_idx * 173)

        def write_window(split: str, start_idx: int, sample_no: int):
            hist = timeline[start_idx : start_idx + 24]
            fut = timeline[start_idx + 24 : start_idx + 48]
            # 未来 24h NWP 预报（误差随提前期 +1h..+24h 线性增长，贴合真实气象局预报特性）
            series_rows: list[dict] = []
            for h in range(24):
                lead_scale = 0.45 + 0.95 * (h / 23.0)
                nwp_w = max(0.3, fut[h]["wind_speed_ms"] + nwp_rng.gauss(0, 0.52 * lead_scale))
                nwp_irr = max(0.0, fut[h]["irradiance_wm2"] + (nwp_rng.gauss(0, 42.0 * lead_scale) if fut[h]["irradiance_wm2"] > 0 else 0.0))
                series_rows.append({
                    **hist[h],
                    "nwp_wind_ms": round(nwp_w, 2),
                    "nwp_irr_wm2": round(nwp_irr, 1),
                })

            fname = f"{split}_{st['id'].lower()}_{sample_no:04d}.csv"
            rel_path = f"series/{fname}"
            pstd.write_series_csv(DATA_DIR / split / rel_path, series_rows)

            fut_powers = [r["power_mw"] for r in fut]
            mean_val = round(sum(fut_powers) / len(fut_powers), 2)
            peak_val = round(max(fut_powers), 2)
            weather = fut[12]["weather"]
            split_records[split].append({
                "file_name": rel_path,
                "value": f"{mean_val:.2f}",
                "station": st["name"],
                "kind": st["kind"],
                "weather": weather,
                "peak_mw": f"{peak_val:.2f}",
                "target_24h": json.dumps(fut_powers, separators=(",", ":")),
            })
            class_counts[split][st["name"]] = class_counts[split].get(st["name"], 0) + 1

        for i in range(train_per_st):
            write_window("train", i * stride, i + 1)
        test_base = train_per_st * stride + gap_hours
        for j in range(test_per_st):
            write_window("test", test_base + j * stride, j + 1)

    meta: dict = {
        "id": "Admin/wind-solar-power-dataset",
        "name": "wind-solar-power-dataset",
        "task": pstd.TASK,
        "capacity_mw": pstd.CAPACITY_MW,
        "horizon_hours": pstd.HORIZON,
        "lookback_hours": pstd.LOOKBACK,
        "stations": [s["name"] for s in STATIONS],
        "columns": ["file_name", "value", "station", "weather", "peak_mw"],
    }

    for split in ("train", "test"):
        pstd.write_labels(DATA_DIR / split / "labels.csv", split_records[split])
        zip_size, sha = pstd.pack_zip(DATA_DIR, split)
        meta[split] = {
            "files": len(split_records[split]),
            "rows": len(split_records[split]),
            "sizeBytes": zip_size,
            "contentHash": sha,
            "classCounts": class_counts[split],
        }

    (DATA_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[power] 已生成 Admin/wind-solar-power-dataset：train={meta['train']['files']} 条，test={meta['test']['files']} 条（6 座场站，含 NWP 通道）")
    return meta


if __name__ == "__main__":
    build_dataset()
