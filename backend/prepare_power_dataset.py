"""
构建新能源场站短期功率时序预测数据集（Admin/wind-solar-power-dataset）：
  - 模拟 4 座典型风电/光伏场站（华中风电一号、西北光伏二号、华东海上风电、西南山地光伏）
  - 每条样本为 24 小时历史多变量时序窗口（1 小时粒度，24 行）：
      hour, wind_speed_ms, irradiance_wm2, temp_c, humidity_pct, pressure_hpa, power_mw
  - 预测目标：未来 24 小时目标功率曲线（labels.csv 中 value 为未来 24h 平均功率 MW，同时附带 peak_mw 与 horizon_24h JSON）
  - 训练集（800 条窗口）与测试集（200 条窗口）按时间顺序严格切分（前 80% 训练、后 20% 测试，无时间穿越泄露）
  - 输出目录：
      backend/data/wind-solar-power-dataset/{train,test}/series/*.csv
      backend/data/wind-solar-power-dataset/{train,test}/labels.csv
      backend/data/wind-solar-power-dataset/wind-solar-power-dataset-{train,test}-v1.0.zip
      backend/data/wind-solar-power-dataset/meta.json
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "wind-solar-power-dataset"

STATIONS = [
    {"id": "HZ-W01", "name": "华中风电一号", "kind": "wind", "capacity": 100.0},
    {"id": "XB-S02", "name": "西北光伏二号", "kind": "solar", "capacity": 100.0},
    {"id": "HD-W03", "name": "华东海上风电", "kind": "wind", "capacity": 100.0},
    {"id": "XN-S04", "name": "西南山地光伏", "kind": "solar", "capacity": 100.0},
]

WEATHERS = ["晴", "多云", "阴", "大风"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def _simulate_station_timeline(station: dict, total_hours: int, seed: int) -> list[dict]:
    """基于物理功率曲线 + 气象马尔可夫过程生成连续小时级时序数据"""
    rng = random.Random(seed)
    kind = station["kind"]
    cap = station["capacity"]
    rows: list[dict] = []

    # 缓慢演变的天气状态（AR(1) 气压、云量、背景风速）
    bg_wind = 7.2 if kind == "wind" else 3.8
    cloud = 0.25
    temp_base = 18.0 if kind == "wind" else 22.0
    pressure = 1012.0

    for t in range(total_hours):
        hour = t % 24
        day = t // 24

        # 季节慢变化 + 气象 AR(1) 演化
        season = math.sin(2 * math.pi * day / 365.0)
        bg_wind = max(1.0, min(18.0, 0.92 * bg_wind + 0.08 * (7.5 + 2.0 * season) + rng.gauss(0, 0.75)))
        cloud = max(0.0, min(0.95, 0.88 * cloud + 0.12 * 0.30 + rng.gauss(0, 0.09)))
        pressure = max(990.0, min(1035.0, 0.95 * pressure + 0.05 * 1012.0 + rng.gauss(0, 0.8)))

        diurnal_wind = 1.4 * math.sin(2 * math.pi * (hour - 14) / 24.0)
        wind_speed = max(0.3, bg_wind + diurnal_wind + rng.gauss(0, 0.45))

        # 太阳高度角辐照度模型
        if 6 <= hour <= 19:
            solar_angle = max(0.0, math.sin(math.pi * (hour - 6) / 13.0))
            clear_sky = 980.0 * (solar_angle ** 1.15) * (1.0 + 0.12 * season)
            irradiance = max(0.0, clear_sky * (1.0 - 0.72 * cloud) + rng.gauss(0, 18.0))
        else:
            irradiance = 0.0

        temp_c = temp_base + 7.0 * season + 5.5 * math.sin(2 * math.pi * (hour - 9) / 24.0) - 3.0 * cloud + rng.gauss(0, 0.6)
        humidity = max(15.0, min(98.0, 48.0 + 34.0 * cloud - 12.0 * math.sin(2 * math.pi * (hour - 9) / 24.0) + rng.gauss(0, 2.5)))

        # 物理功率转换曲线（风机三次方切入/额定曲线 vs 光伏辐照-温度效率曲线）
        if kind == "wind":
            if wind_speed < 3.0:
                p = 0.0
            elif wind_speed < 12.0:
                p = cap * ((wind_speed - 3.0) / 9.0) ** 2.6
            elif wind_speed <= 22.0:
                p = cap * 0.98
            else:
                p = 0.0
            power = max(0.0, min(cap, p + rng.gauss(0, 1.8)))
        else:
            temp_eff = max(0.82, 1.0 - 0.004 * max(0.0, temp_c - 25.0))
            p = cap * (irradiance / 920.0) * temp_eff
            power = max(0.0, min(cap, p + (rng.gauss(0, 1.4) if irradiance > 5 else 0.0)))

        if wind_speed >= 10.5:
            weather = "大风"
        elif cloud < 0.25:
            weather = "晴"
        elif cloud < 0.58:
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


def _pack_split_zip(split: str) -> tuple[Path, int, str]:
    split_dir = DATA_DIR / split
    zip_path = DATA_DIR / f"wind-solar-power-dataset-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(split_dir / "labels.csv", arcname=f"{split}/labels.csv")
        for f in sorted((split_dir / "series").glob("*.csv")):
            zf.write(f, arcname=f"{split}/series/{f.name}")
    return zip_path, zip_path.stat().st_size, _sha256_file(zip_path)


def build_dataset() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for split in ("train", "test"):
        (DATA_DIR / split / "series").mkdir(parents=True, exist_ok=True)

    # 每个场站生成 250 个不重叠/半重叠滑窗（前 200 训练 + 后 50 测试），共 800 训练 + 200 测试
    train_per_station = 200
    test_per_station = 50
    stride = 6  # 每 6 小时取一个 24h -> 24h 预测窗口
    gap_hours = 48  # 训练/测试间隔 48 小时防止任何数据泄露

    split_records: dict[str, list[dict]] = {"train": [], "test": []}
    class_counts: dict[str, dict[str, int]] = {"train": {}, "test": {}}

    for s_idx, st in enumerate(STATIONS):
        total_needed = (train_per_station + test_per_station) * stride + gap_hours + 64
        timeline = _simulate_station_timeline(st, total_needed, seed=20261124 + s_idx * 131)

        def write_window(split: str, start_idx: int, sample_no: int):
            hist = timeline[start_idx : start_idx + 24]
            fut = timeline[start_idx + 24 : start_idx + 48]
            fname = f"{split}_{st['id'].lower()}_{sample_no:04d}.csv"
            rel_path = f"series/{fname}"
            csv_file = DATA_DIR / split / rel_path
            with csv_file.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["hour", "wind_speed_ms", "irradiance_wm2", "temp_c", "humidity_pct", "pressure_hpa", "power_mw"])
                for r in hist:
                    w.writerow([r["hour"], r["wind_speed_ms"], r["irradiance_wm2"], r["temp_c"], r["humidity_pct"], r["pressure_hpa"], r["power_mw"]])

            fut_powers = [r["power_mw"] for r in fut]
            mean_val = round(sum(fut_powers) / len(fut_powers), 2)
            weather = hist[-1]["weather"]
            split_records[split].append({
                "file_name": rel_path,
                "value": f"{mean_val:.2f}",
                "station": st["name"],
                "weather": weather,
                "target_24h": json.dumps(fut_powers),
            })
            class_counts[split][st["name"]] = class_counts[split].get(st["name"], 0) + 1

        for i in range(train_per_station):
            write_window("train", i * stride, i + 1)
        test_base = train_per_station * stride + gap_hours
        for j in range(test_per_station):
            write_window("test", test_base + j * stride, j + 1)

    meta: dict = {
        "id": "Admin/wind-solar-power-dataset",
        "name": "wind-solar-power-dataset",
        "task": "power-forecast",
        "capacity_mw": 100.0,
        "horizon_hours": 24,
        "lookback_hours": 24,
        "stations": [s["name"] for s in STATIONS],
        "columns": ["file_name", "value", "station", "weather"],
    }

    for split in ("train", "test"):
        lbl_path = DATA_DIR / split / "labels.csv"
        with lbl_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file_name", "value", "station", "weather", "target_24h"])
            for rec in split_records[split]:
                w.writerow([rec["file_name"], rec["value"], rec["station"], rec["weather"], rec["target_24h"]])
        _, zip_size, sha = _pack_split_zip(split)
        meta[split] = {
            "files": len(split_records[split]),
            "rows": len(split_records[split]),
            "sizeBytes": zip_size,
            "contentHash": sha,
            "classCounts": class_counts[split],
        }

    (DATA_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 Admin/wind-solar-power-dataset：train={meta['train']['files']} 条，test={meta['test']['files']} 条")
    return meta


if __name__ == "__main__":
    build_dataset()
