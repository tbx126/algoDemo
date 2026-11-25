"""
新能源场站短期功率预测标准（task = "power-forecast"）—— 与 server_fault_std 同样的「标准 + 统一评测器」模式

一、数据集标准（backend/data/<name>/）
  meta.json                  task = "power-forecast"，stations（场站 -> kind / capacity_mw），benchmark
  {train,test}/series/*.csv  24 行，第 h 行 = 前一天 h 时实测 + 次日 h 时 NWP 预报：
      hour, wind_speed_ms, irradiance_wm2, temp_c, humidity_pct, pressure_hpa, nwp_wind_ms, nwp_irr_wm2, power_mw
  {train,test}/labels.csv    file_name, value, station, kind, weather, peak_mw, t0, target_24h

二、算法接口
  predict_batch(raw: [N, 24, 9] 原始单位（CHANNELS 顺序）, specs: [{"kind": "wind"|"solar", "capacity_mw": float}] * N)
      -> [N, 24] 次日逐小时功率（MW）
  算法只拿到输入与场站规格，拿不到真值；真值由评测器自己读取。

三、统一评测（evaluate）
  考核时段：风电全天 24h；光伏只计 6:00–19:00（夜间出力恒为 0，计入会抬高准确率）
  accuracy_rate   考核准确率 = (1 − NRMSE) × 100%（主指标，按装机容量归一化，只计考核时段）
  nrmse / nmae    归一化 RMSE / MAE（%）
  r2              决定系数 R²（%，各场站分别计算后取平均，避免场站差异与昼夜变化虚高）
  peak_err_mw     日最大出力误差（MW）
  qualified_rate  单日准确率 ≥ 85% 的天数占比（%）
  skill           相对「NWP + 名义功率曲线」基线的 RMSE 降低比例（%，≤ 0 表示不如基线）
  night_mw        光伏夜间平均预测出力（MW，应接近 0）
  另给出两个参照基线：持续法（次日 = 前一天）与 NWP + 名义功率曲线（不训练、不看历史）
"""
from __future__ import annotations

import csv
import hashlib
import json
import time
import zipfile
from pathlib import Path
from typing import Callable

import numpy as np

TASK = "power-forecast"
LOOKBACK = 24
HORIZON = 24
DEFAULT_CAPACITY_MW = 100.0
SOLAR_EVAL_HOURS = range(6, 20)  # 光伏考核时段 6:00–19:00
QUALIFIED_ACC = 85.0

CHANNELS = ["hour", "wind_speed_ms", "irradiance_wm2", "temp_c", "humidity_pct", "pressure_hpa", "nwp_wind_ms", "nwp_irr_wm2", "power_mw"]
CHANNEL_DIGITS = [0, 2, 1, 1, 1, 1, 2, 1, 2]
LABEL_COLUMNS = ["file_name", "value", "station", "kind", "weather", "peak_mw", "t0", "target_24h"]
KINDS = ("wind", "solar")

METRICS = [
    {"key": "accuracy_rate", "label": "考核准确率", "higherIsBetter": True, "unit": "%", "primary": True},
    {"key": "nrmse", "label": "归一化 RMSE", "higherIsBetter": False, "unit": "%"},
    {"key": "nmae", "label": "归一化 MAE", "higherIsBetter": False, "unit": "%"},
    {"key": "r2", "label": "决定系数 R²", "higherIsBetter": True, "unit": "%"},
    {"key": "peak_err_mw", "label": "日峰值误差", "higherIsBetter": False, "unit": "MW"},
    {"key": "qualified_rate", "label": "单日合格率", "higherIsBetter": True, "unit": "%"},
    {"key": "skill", "label": "相对 NWP 基线提升", "higherIsBetter": True, "unit": "%"},
    {"key": "night_mw", "label": "光伏夜间误报出力", "higherIsBetter": False, "unit": "MW"},
]


# ================================================================== 文件读写
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def write_series_csv(path: Path, rows: list[dict]) -> None:
    if len(rows) != LOOKBACK:
        raise ValueError(f"{path.name}: 需要 {LOOKBACK} 行，实际 {len(rows)} 行")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CHANNELS)
        for r in rows:
            w.writerow([int(r["hour"]) if c == "hour" else round(float(r[c]), k) for c, k in zip(CHANNELS, CHANNEL_DIGITS)])


def write_labels(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(records)


def pack_zip(data_dir: Path, split: str) -> tuple[int, str]:
    zip_path = data_dir / f"{data_dir.name}-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(data_dir / split / "labels.csv", arcname=f"{split}/labels.csv")
        for f in sorted((data_dir / split / "series").glob("*.csv")):
            zf.write(f, arcname=f"{split}/series/{f.name}")
    return zip_path.stat().st_size, sha256_file(zip_path)


def write_meta(data_dir: Path, info: dict, records: dict[str, list[dict]], counts: dict[str, dict[str, int]]) -> dict:
    for name, sp in (info.get("stations") or {}).items():
        if sp.get("kind") not in KINDS or not sp.get("capacity_mw"):
            raise ValueError(f"场站 {name} 缺少 kind（wind / solar）或 capacity_mw")
    meta = {**info, "task": TASK, "lookback_hours": LOOKBACK, "horizon_hours": HORIZON, "channels": CHANNELS}
    for split in ("train", "test"):
        write_labels(data_dir / split / "labels.csv", records[split])
        size, sha = pack_zip(data_dir, split)
        meta[split] = {"files": len(records[split]), "rows": len(records[split]), "sizeBytes": size, "contentHash": sha, "classCounts": counts[split]}
    (data_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def read_meta(data_dir: Path) -> dict | None:
    p = data_dir / "meta.json"
    if not p.exists():
        return None
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    return meta if meta.get("task") == TASK else None


def read_labels(data_dir: Path, split: str) -> list[dict]:
    with (data_dir / split / "labels.csv").open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_series_rows(rows: list[dict], source: str = "") -> np.ndarray:
    """标准 CSV 行 -> [24, 9]；缺列、行数不足或含非数值时直接报错（不做静默补值）"""
    if not rows:
        raise ValueError(f"{source} 为空")
    missing = [c for c in CHANNELS if c not in rows[0]]
    if missing:
        raise ValueError(f"{source} 不符合功率预测标准，缺少列：{', '.join(missing)}（需要：{', '.join(CHANNELS)}）")
    if len(rows) < LOOKBACK:
        raise ValueError(f"{source} 需要 {LOOKBACK} 行（前一天 24h 实测 + 次日 24h NWP），实际 {len(rows)} 行")
    try:
        arr = np.asarray([[float(r[c]) for c in CHANNELS] for r in rows[-LOOKBACK:]], dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source} 含空值或非数值：{exc}") from exc
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{source} 含非有限数值")
    return arr


def read_series(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8-sig") as f:
        return parse_series_rows(list(csv.DictReader(f)), path.name)


def station_spec(meta: dict | None, station: str, kind: str | None = None) -> dict:
    sp = (meta or {}).get("stations", {}).get(station) if isinstance((meta or {}).get("stations"), dict) else None
    if sp:
        return {"kind": sp["kind"], "capacity_mw": float(sp["capacity_mw"])}
    return {"kind": kind if kind in KINDS else "wind", "capacity_mw": DEFAULT_CAPACITY_MW}


def load_split(data_dir: Path, split: str) -> tuple[np.ndarray, np.ndarray, list[dict], list[dict]]:
    """返回 (输入 [N, 24, 9], 真值 [N, 24] MW, 元数据, 场站规格)"""
    meta = read_meta(data_dir)
    xs, ys, metas, specs = [], [], [], []
    for row in read_labels(data_dir, split):
        xs.append(read_series(data_dir / split / row["file_name"]))
        ys.append(json.loads(row["target_24h"]))
        metas.append(row)
        specs.append(station_spec(meta, row["station"], row.get("kind")))
    return np.stack(xs), np.asarray(ys, dtype=np.float32), metas, specs


# ================================================================== 基线
def nominal_power(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """NWP + 名义功率曲线（通用风机功率曲线 / 光伏 1000 W/m² 标准条件 × 0.9 系统效率），不训练、不看历史功率"""
    out = np.zeros(raw.shape[:2], dtype=np.float32)
    for i, sp in enumerate(specs):
        cap = sp["capacity_mw"]
        if sp["kind"] == "wind":
            v = raw[i, :, 6]
            p = np.where((v < 3) | (v > 25), 0.0, np.where(v >= 12, 1.0, ((np.clip(v, 3, 12) - 3) / 9.0) ** 3))
        else:
            p = np.clip(raw[i, :, 7] / 1000.0 * 0.9, 0, 1)
        out[i] = cap * p
    return out


def persistence(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """持续法：次日 h 时功率 = 前一天 h 时实测功率"""
    return raw[:, :, 8].astype(np.float32).copy()


# ================================================================== 评测
def eval_mask(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """[N, 24] 考核时段：风电全天，光伏 6:00–19:00（第 h 行的 hour 即预测时刻）"""
    hours = np.rint(raw[:, :, 0]).astype(int) % 24
    solar = np.array([sp["kind"] == "solar" for sp in specs])[:, None]
    return ~solar | np.isin(hours, list(SOLAR_EVAL_HOURS))


def _scores(pred: np.ndarray, y: np.ndarray, cap: np.ndarray, mask: np.ndarray) -> tuple[float, float]:
    d = ((pred - y) / cap)[mask]
    return float(np.sqrt(np.mean(d ** 2))), float(np.mean(np.abs(d)))


def _acc(nrmse: float) -> float:
    return round(max(0.0, (1.0 - nrmse) * 100.0), 2)


def build_case_payload(raw: np.ndarray, spec: dict, meta: dict, gt: np.ndarray | None, pred: np.ndarray | None) -> dict:
    cap = spec["capacity_mw"]
    nominal = nominal_power(raw[None], [spec])[0]
    out: dict = {
        "file": Path(meta.get("file_name", "sample.csv")).name,
        "station": meta.get("station", "自定义场站"),
        "kind": spec["kind"],
        "capacityMw": cap,
        "weather": meta.get("weather", ""),
        "startHour": int(round(float(raw[0, 0]))),
        "history": [round(float(v), 2) for v in raw[:, 8]],
        "channels": {c: [round(float(v), 2) for v in raw[:, k]] for k, c in enumerate(CHANNELS) if c not in ("hour", "power_mw")},
        "gt": [round(float(v), 2) for v in gt] if gt is not None else None,
        "pred": [round(float(v), 2) for v in pred] if pred is not None else None,
        "nominal": [round(float(v), 2) for v in nominal],
    }
    if gt is not None and pred is not None:
        m = eval_mask(raw[None], [spec])[0]
        nr, na = _scores(pred[None], gt[None], np.float32(cap), m[None])
        out.update({"accuracy": _acc(nr), "nrmse": round(nr * 100, 2), "nmae": round(na * 100, 2), "peakErrMw": round(abs(float(pred.max()) - float(gt.max())), 2)})
    return out


def evaluate(
    predict_batch: Callable[[np.ndarray, list[dict]], np.ndarray],
    data_dir: Path,
    history: list[dict] | None = None,
    say: Callable[[int, str], None] | None = None,
) -> dict:
    """统一评测器：任意符合标准的算法 × 任意符合标准的数据集测试集。真值只在这里读取，不交给算法"""
    say = say or (lambda p, m: None)
    t0 = time.perf_counter()
    raw, y, metas, specs = load_split(data_dir, "test")
    say(30, f"[runner] 挂载 {data_dir.name}@v1.0/test：{len(metas)} 个日前预测窗口（标准 {TASK}），共 {y.size:,} 个逐小时真值；算法只接收输入与场站规格")

    t_inf = time.perf_counter()
    pred = np.asarray(predict_batch(raw.copy(), [dict(s) for s in specs]), dtype=np.float64)
    infer_ms = (time.perf_counter() - t_inf) * 1000
    if pred.shape != y.shape:
        raise ValueError(f"算法输出形状不符合标准：需要 {y.shape}，实际 {pred.shape}")
    if not np.all(np.isfinite(pred)):
        raise ValueError("算法输出含 NaN / Inf")
    say(60, f"[runner] 推理完成：{len(raw)} 个窗口用时 {infer_ms:.1f} ms")

    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float64)[:, None]
    mask = eval_mask(raw, specs)
    solar = np.array([s["kind"] == "solar" for s in specs])
    nrmse, nmae = _scores(pred, y, cap, mask)

    stations: dict[str, list[int]] = {}
    for i, m in enumerate(metas):
        stations.setdefault(m["station"], []).append(i)
    r2s, per_class = [], []
    for st, idx in stations.items():
        mk = mask[idx]
        yt, yp = y[idx][mk], pred[idx][mk]
        r2s.append(1.0 - float(np.sum((yp - yt) ** 2)) / max(1e-6, float(np.sum((yt - yt.mean()) ** 2))))
        s_nr, s_na = _scores(pred[idx], y[idx], cap[idx], mk)
        per_class.append({"label": st, "value": _acc(s_nr), "nrmse": round(s_nr * 100, 2), "nmae": round(s_na * 100, 2), "support": len(idx)})

    win_acc = np.array([_acc(_scores(pred[i : i + 1], y[i : i + 1], cap[i : i + 1], mask[i : i + 1])[0]) for i in range(len(y))])
    base_nom, base_per = nominal_power(raw, specs), persistence(raw, specs)
    nom_nrmse, _ = _scores(base_nom, y, cap, mask)
    per_nrmse, _ = _scores(base_per, y, cap, mask)
    night = solar[:, None] & ~mask

    metrics = {
        "accuracy_rate": _acc(nrmse),
        "nrmse": round(nrmse * 100, 2),
        "nmae": round(nmae * 100, 2),
        "r2": round(max(0.0, float(np.mean(r2s))) * 100, 2),
        "peak_err_mw": round(float(np.mean(np.abs(pred.max(1) - y.max(1)))), 2),
        "qualified_rate": round(float(np.mean(win_acc >= QUALIFIED_ACC)) * 100, 2),
        "skill": round((1.0 - nrmse / max(1e-9, nom_nrmse)) * 100, 2),
        "night_mw": round(float(np.mean(np.abs(pred[night]))) if night.any() else 0.0, 2),
    }
    say(80, "[runner] 生成可视化数据：典型样本、提前期误差（含基线）、日内曲线、误差分布、训练曲线")

    cases = []
    for st, idx in stations.items():
        pick = sorted(idx, key=lambda i: float(np.std(y[i])), reverse=True)[min(2, len(idx) - 1)]
        cases.append(build_case_payload(raw[pick], specs[pick], metas[pick], y[pick], pred[pick]))

    def lead_curve(p: np.ndarray) -> list[float]:
        return [round(_scores(p[:, h : h + 1], y[:, h : h + 1], cap, mask[:, h : h + 1])[0] * 100, 2) for h in range(HORIZON)]

    model_lead, nom_lead, per_lead = lead_curve(pred), lead_curve(base_nom), lead_curve(base_per)
    horizon_curve = [
        {"hour": h + 1, "nrmse": model_lead[h], "nominal": nom_lead[h], "persistence": per_lead[h],
         "nmae": round(_scores(pred[:, h : h + 1], y[:, h : h + 1], cap, mask[:, h : h + 1])[1] * 100, 2)}
        for h in range(HORIZON)
    ]
    hours = np.rint(raw[:, :, 0]).astype(int) % 24
    diurnal = [{"hour": t, "gt": round(float(y[hours == t].mean()), 2), "pred": round(float(pred[hours == t].mean()), 2)} for t in range(24)]
    abs_err = np.abs(pred - y)[mask]
    error_cdf = [{"mw": mw, "pct": round(float(np.mean(abs_err <= mw)) * 100, 2)} for mw in range(0, 31)]

    return {
        "metrics": metrics,
        "perClass": per_class,
        "perClassLabel": "各场站考核准确率（%）",
        "latencyMs": round(infer_ms / max(1, len(raw)), 3),
        "durationSec": round(time.perf_counter() - t0, 2),
        "vizPowerForecast": {
            "lookback": LOOKBACK,
            "horizon": HORIZON,
            "solarEvalHours": [SOLAR_EVAL_HOURS.start, SOLAR_EVAL_HOURS.stop - 1],
            "evalHours": int(mask.sum()),
            "baselines": [
                {"key": "nominal", "name": "NWP + 名义功率曲线", "accuracy": _acc(nom_nrmse), "nrmse": round(nom_nrmse * 100, 2)},
                {"key": "persistence", "name": "持续法（次日 = 前一天）", "accuracy": _acc(per_nrmse), "nrmse": round(per_nrmse * 100, 2)},
            ],
            "cases": cases,
            "horizonCurve": horizon_curve,
            "diurnalCurve": diurnal,
            "errorCdf": error_cdf,
            "history": history or [],
        },
    }
