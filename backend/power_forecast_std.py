"""
新能源场站短期功率预测标准（task = "power-forecast"）—— 对标 server_fault_std.py

一、数据集标准（backend/data/wind-solar-power-dataset/）：
  meta.json                  元信息（含 6 座场站、分片统计与哈希）
  {train,test}/series/*.csv  每个文件 24 行（过去 24h 历史遥测 + 未来 24h NWP 气象预报）
      hour, wind_speed_ms, irradiance_wm2, temp_c, humidity_pct, pressure_hpa, nwp_wind_ms, nwp_irr_wm2, power_mw
  {train,test}/labels.csv    表头：file_name, value, station, kind, weather, peak_mw, target_24h

二、统一评测标准（evaluate_power）：
  - 核心 6 项考核指标：
      accuracy_rate  考核准确率（(1 - NRMSE) × 100%，主指标）
      nrmse          归一化 RMSE（%）
      nmae           归一化 MAE（%）
      r2             决定系数 R²（%）
      peak_err_mw    峰值功率误差（MW）
      qualified_rate 单日合格率（%，单窗口准确率 ≥ 85%）
  - 统一折线图可视化数据 vizPowerForecast：
      cases          各场站典型测试窗口（历史 24h + 未来 24h GT vs 预测 + 气象通道）
      horizonCurve   提前期 +1h..+24h 的 NRMSE / NMAE 增长曲线
      diurnalCurve   按 0..23 时对齐的平均实测 vs 平均预测日内曲线
      errorCdf       绝对误差（MW）累计分布 CDF 曲线
      history        训练/验证收敛曲线（90/10 严格切分，测试集零参与）
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
import zipfile
from pathlib import Path

import numpy as np

TASK = "power-forecast"
LOOKBACK = 24
HORIZON = 24
CAPACITY_MW = 100.0

CHANNELS = [
    "hour",
    "wind_speed_ms",
    "irradiance_wm2",
    "temp_c",
    "humidity_pct",
    "pressure_hpa",
    "nwp_wind_ms",
    "nwp_irr_wm2",
    "power_mw",
]
LABEL_COLUMNS = ["file_name", "value", "station", "kind", "weather", "peak_mw", "target_24h"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def write_series_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CHANNELS)
        for r in rows:
            w.writerow([
                int(r["hour"]),
                round(float(r["wind_speed_ms"]), 2),
                round(float(r["irradiance_wm2"]), 1),
                round(float(r["temp_c"]), 1),
                round(float(r["humidity_pct"]), 1),
                round(float(r["pressure_hpa"]), 1),
                round(float(r["nwp_wind_ms"]), 2),
                round(float(r["nwp_irr_wm2"]), 1),
                round(float(r["power_mw"]), 2),
            ])


def write_labels(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(records)


def pack_zip(data_dir: Path, split: str) -> tuple[int, str]:
    split_dir = data_dir / split
    zip_path = data_dir / f"{data_dir.name}-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(split_dir / "labels.csv", arcname=f"{split}/labels.csv")
        for f in sorted((split_dir / "series").glob("*.csv")):
            zf.write(f, arcname=f"{split}/series/{f.name}")
    return zip_path.stat().st_size, sha256_file(zip_path)


def parse_series_rows(rows: list[dict]) -> np.ndarray:
    """将 24 行 CSV 字典解析为 [24, 9] 原始浮点数组（CHANNELS 顺序）"""
    arr: list[list[float]] = []
    for i, r in enumerate(rows[-LOOKBACK:]):
        wind = float(r.get("wind_speed_ms") or 5.0)
        irr = float(r.get("irradiance_wm2") or 0.0)
        arr.append([
            float(r.get("hour", i % 24)),
            wind,
            irr,
            float(r.get("temp_c") or 20.0),
            float(r.get("humidity_pct") or 55.0),
            float(r.get("pressure_hpa") or 1012.0),
            float(r.get("nwp_wind_ms") if r.get("nwp_wind_ms") not in (None, "") else wind),
            float(r.get("nwp_irr_wm2") if r.get("nwp_irr_wm2") not in (None, "") else irr),
            float(r.get("power_mw") or r.get("value") or 30.0),
        ])
    if not arr:
        arr = [[0.0, 5.0, 0.0, 20.0, 55.0, 1012.0, 5.0, 0.0, 25.0]]
    while len(arr) < LOOKBACK:
        arr.insert(0, arr[0])
    return np.asarray(arr, dtype=np.float32)


def load_split(data_dir: Path, split: str) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    split_dir = data_dir / split
    lbl_path = split_dir / "labels.csv"
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    metas: list[dict] = []
    with lbl_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            with (split_dir / row["file_name"]).open("r", encoding="utf-8") as sf:
                srows = list(csv.DictReader(sf))
            xs.append(parse_series_rows(srows))
            ys.append(np.asarray(json.loads(row["target_24h"]), dtype=np.float32))
            metas.append(row)
    return np.stack(xs, axis=0), np.stack(ys, axis=0), metas


def build_case_payload(raw: np.ndarray, gt_24h: np.ndarray | None, pred_24h: np.ndarray | None, meta: dict) -> dict:
    """构建单个 24h 历史 + 24h 未来窗口的前端折线图数据结构"""
    hist_power = [round(float(v), 2) for v in raw[:, 8]]
    start_hour = int(round(float(raw[0, 0])))
    hours_48 = [f"{(start_hour + i) % 24:02d}:00" for i in range(LOOKBACK + HORIZON)]
    out: dict = {
        "file": Path(meta.get("file_name", "sample.csv")).name,
        "station": meta.get("station", "新能源场站"),
        "kind": meta.get("kind", "wind"),
        "weather": meta.get("weather", "晴"),
        "startHour": start_hour,
        "hours48": hours_48,
        "history": hist_power,
        "channels": {
            "wind_speed_ms": [round(float(v), 2) for v in raw[:, 1]],
            "irradiance_wm2": [round(float(v), 1) for v in raw[:, 2]],
            "nwp_wind_ms": [round(float(v), 2) for v in raw[:, 6]],
            "nwp_irr_wm2": [round(float(v), 1) for v in raw[:, 7]],
            "temp_c": [round(float(v), 1) for v in raw[:, 3]],
        },
        "gt": [round(float(v), 2) for v in gt_24h] if gt_24h is not None else None,
        "pred": [round(float(v), 2) for v in pred_24h] if pred_24h is not None else None,
    }
    if gt_24h is not None and pred_24h is not None:
        diff = pred_24h - gt_24h
        nrmse = float(np.sqrt(np.mean((diff / CAPACITY_MW) ** 2)))
        nmae = float(np.mean(np.abs(diff) / CAPACITY_MW))
        out["accuracy"] = round(max(0.0, (1.0 - nrmse) * 100.0), 2)
        out["nrmse"] = round(nrmse * 100.0, 2)
        out["nmae"] = round(nmae * 100.0, 2)
        out["peakErrMw"] = round(abs(float(np.max(pred_24h)) - float(np.max(gt_24h))), 2)
    return out


def evaluate_predictions(
    raw_test: np.ndarray,
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metas: list[dict],
    history: list[dict] | None = None,
    device: str = "CPU (PyTorch)",
    elapsed_sec: float = 0.3,
) -> dict:
    """统一功率预测评测器：计算 6 项工业考核指标 + 分场站指标 + 5 维折线图可视化"""
    diff = y_pred - y_true  # [N, 24] MW
    nrmse = float(np.sqrt(np.mean((diff / CAPACITY_MW) ** 2)))
    nmae = float(np.mean(np.abs(diff) / CAPACITY_MW))
    acc_rate = max(0.0, (1.0 - nrmse) * 100.0)

    ss_res = float(np.sum(diff ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = max(0.0, (1.0 - ss_res / max(1e-6, ss_tot)) * 100.0)

    peak_errs = np.abs(np.max(y_pred, axis=1) - np.max(y_true, axis=1))
    peak_err_mw = float(np.mean(peak_errs))

    win_nrmse = np.sqrt(np.mean((diff / CAPACITY_MW) ** 2, axis=1))
    win_acc = np.maximum(0.0, (1.0 - win_nrmse) * 100.0)
    qualified_rate = float(np.mean(win_acc >= 85.0) * 100.0)

    metrics = {
        "accuracy_rate": round(acc_rate, 2),
        "nrmse": round(nrmse * 100.0, 2),
        "nmae": round(nmae * 100.0, 2),
        "r2": round(r2, 2),
        "peak_err_mw": round(peak_err_mw, 2),
        "qualified_rate": round(qualified_rate, 2),
    }

    # 分场站准确率统计
    by_station: dict[str, list[int]] = {}
    for idx, m in enumerate(metas):
        by_station.setdefault(m["station"], []).append(idx)

    per_class = []
    for st_name, idxs in by_station.items():
        d_sub = diff[idxs]
        st_nrmse = float(np.sqrt(np.mean((d_sub / CAPACITY_MW) ** 2)))
        st_nmae = float(np.mean(np.abs(d_sub) / CAPACITY_MW))
        per_class.append({
            "label": st_name,
            "value": round(max(0.0, (1.0 - st_nrmse) * 100.0), 2),
            "nrmse": round(st_nrmse * 100.0, 2),
            "nmae": round(st_nmae * 100.0, 2),
            "support": len(idxs),
        })

    # 折线图 1：每个场站挑选 1 条代表性测试样本（含历史 24h + 未来 24h GT vs 预测 + 气象通道）
    cases = []
    for st_name, idxs in by_station.items():
        # 选功率起伏较明显、展示效果最直观的中位数表现样本
        ranked = sorted(idxs, key=lambda i: float(np.std(y_true[i])), reverse=True)
        pick = ranked[min(2, len(ranked) - 1)]
        cases.append(build_case_payload(raw_test[pick], y_true[pick], y_pred[pick], metas[pick]))

    # 折线图 2：提前期（+1h .. +24h）NRMSE & NMAE 误差增长曲线
    horizon_curve = []
    for h in range(HORIZON):
        dh = diff[:, h] / CAPACITY_MW
        horizon_curve.append({
            "hour": h + 1,
            "nrmse": round(float(np.sqrt(np.mean(dh ** 2))) * 100.0, 2),
            "nmae": round(float(np.mean(np.abs(dh))) * 100.0, 2),
        })

    # 折线图 3：24h 日内时刻对齐曲线（0:00 .. 23:00 平均实测 vs 平均预测）
    diurnal_gt = [[] for _ in range(24)]
    diurnal_pred = [[] for _ in range(24)]
    for i in range(len(metas)):
        sh = int(round(float(raw_test[i, 0, 0])))
        for h in range(HORIZON):
            tod = (sh + LOOKBACK + h) % 24
            diurnal_gt[tod].append(float(y_true[i, h]))
            diurnal_pred[tod].append(float(y_pred[i, h]))
    diurnal_curve = [
        {
            "hour": tod,
            "gt": round(float(np.mean(diurnal_gt[tod])) if diurnal_gt[tod] else 0.0, 2),
            "pred": round(float(np.mean(diurnal_pred[tod])) if diurnal_pred[tod] else 0.0, 2),
        }
        for tod in range(24)
    ]

    # 折线图 4：绝对误差累计分布 CDF（0 MW -> 20 MW）
    abs_err = np.abs(diff).reshape(-1)
    error_cdf = [
        {"mw": mw, "pct": round(float(np.mean(abs_err <= mw)) * 100.0, 2)}
        for mw in range(0, 21, 1)
    ]

    return {
        "metrics": metrics,
        "perClass": per_class,
        "perClassLabel": "各场站预测准确率（%）",
        "vizPowerForecast": {
            "capacityMw": CAPACITY_MW,
            "lookback": LOOKBACK,
            "horizon": HORIZON,
            "cases": cases,
            "horizonCurve": horizon_curve,
            "diurnalCurve": diurnal_curve,
            "errorCdf": error_cdf,
            "history": history or [],
        },
        "samples": len(metas),
        "durationSec": max(0.2, round(elapsed_sec, 2)),
        "device": device,
    }
