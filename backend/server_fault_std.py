"""
服务器运行故障检测标准（task = "server-fault"）

所有「服务器故障检测」数据集和算法都遵守同一份标准，因此任意算法都能直接在任意数据集上评测，
不需要任何格式转换或输出映射。

一、数据集标准（backend/data/<dir>/）
  meta.json                         task = "server-fault"，含 id / displayName / summary / tags / benchmark，
                                    以及 machines：{server: 机器规格}，每台机器至少含 MACHINE_SPEC_REQUIRED 中的容量字段
  README.md                         数据集卡片
  {train,test}/series/*.csv         每个文件 60 行，表头固定为 SERIES_COLUMNS（原始物理单位）
  {train,test}/labels.csv           表头固定为 LABEL_COLUMNS
      state_seq  60 个逐分钟状态码（JSON 数组，取值见 STATES）
      warn_seq   60 个逐分钟预警真值（1 = 当前正常且未来 WARN_HORIZON 分钟内会出现故障）
  数据集只能通过本模块的 write_series_csv / write_labels / write_meta / pack_zip 写出，保证格式一致。

二、算法标准（backend/<module>.py）
  ALGO_ID: str
  predict_batch(raw: np.ndarray[N, 60, 8], specs: list[dict]) -> dict
      raw 为 CHANNELS 顺序、原始物理单位的遥测；specs 为每个窗口所在机器的规格（见 MACHINE_SPEC_REQUIRED），
      算法可用 to_relative(raw, specs) 按容量换算成相对值（不同硬件可比），归一化方式由算法自己决定
      必须返回 "fault_prob": [N, 60]，逐分钟故障概率（0~1）
      可选返回 "state":      [N, 60]，逐分钟状态码（取值见 STATES）
      可选返回 "warn_prob":  [N, 60]，逐分钟「未来 10 分钟内发生故障」概率
  load_state() -> dict | None       训练记录，history = [{epoch, train_loss, val_loss, val_f1}]
  CARD: dict                        平台算法卡片信息
  可选 diagnose(raw_window[60, 8], pred: dict) -> str   推理时的文字诊断

三、评测标准：evaluate() 对所有算法 × 所有数据集使用同一套指标与可视化数据。
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

TASK = "server-fault"
WINDOW = 60
WARN_HORIZON = 10
MIN_FAULT_RUN = 3  # 窗口判定：连续 >= 3 分钟判为故障，抑制孤立毛刺

CHANNELS = ["cpu_pct", "cpu_temp_c", "mem_pct", "gpu_pct", "gpu_temp_c", "gpu_mem_pct", "disk_io_mbps", "net_mbps"]
CHANNEL_UNITS = {"cpu_pct": "%", "cpu_temp_c": "℃", "mem_pct": "%", "gpu_pct": "%", "gpu_temp_c": "℃", "gpu_mem_pct": "%", "disk_io_mbps": "MB/s", "net_mbps": "Mbps"}
SERIES_COLUMNS = ["minute", *CHANNELS]
LABEL_COLUMNS = ["file_name", "label", "server", "role", "onset_min", "state_seq", "warn_seq"]

# 机器规格：磁盘与网络吞吐是绝对值，必须结合容量才能判断「是否打满」；百分比与温度通道本身已可跨硬件比较
MACHINE_SPEC_REQUIRED = ["disk_max_mbps", "net_max_mbps"]
MACHINE_SPEC_OPTIONAL = ["cpu_cores", "mem_gb", "gpu"]
DEFAULT_SPEC = {"disk_max_mbps": 500.0, "net_max_mbps": 1000.0}  # 未提供规格时（如上传 CSV 未填写）使用的参考容量

# 统一状态码表：任何数据集 / 算法都只能使用这些编码（新增状态只能追加，不能改已有编码）
STATES = ["正常", "CPU过载", "内存泄漏", "GPU过热", "磁盘IO饱和", "网络异常", "显存泄漏", "内存IO雪崩", "其他异常"]
STATE_CODE = {s: i for i, s in enumerate(STATES)}


# ================================================================== 写入（数据集生成脚本共用）
def derive_warn(states_ext: list[int], horizon: int = WARN_HORIZON) -> list[int]:
    """由（可向窗口后延伸的）状态序列推出前 WINDOW 分钟的预警真值"""
    return [1 if states_ext[t] == 0 and any(s > 0 for s in states_ext[t + 1 : t + 1 + horizon]) else 0 for t in range(WINDOW)]


def window_label(states: list[int]) -> str:
    faults = [s for s in states if s > 0]
    return STATES[max(set(faults), key=faults.count)] if faults else STATES[0]


def write_series_csv(path: Path, rows: list[dict]) -> None:
    if len(rows) != WINDOW:
        raise ValueError(f"{path.name}: 需要 {WINDOW} 行，实际 {len(rows)} 行")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(SERIES_COLUMNS)
        for t, r in enumerate(rows):
            w.writerow([t, *[round(float(r[c]), 1) for c in CHANNELS]])


def make_label_record(file_name: str, server: str, role: str, states: list[int], warn: list[int], onset: int | None = None) -> dict:
    """onset 默认取窗口内第一个故障分钟（无故障为 -1）；故障发生在窗口之后时可传入 >= 60 的真实起点"""
    if len(states) != WINDOW or len(warn) != WINDOW:
        raise ValueError(f"{file_name}: state_seq / warn_seq 长度必须为 {WINDOW}")
    if any(s < 0 or s >= len(STATES) for s in states):
        raise ValueError(f"{file_name}: state_seq 含未知状态码")
    first = next((t for t, s in enumerate(states) if s > 0), -1)
    onset = first if first >= 0 or onset is None or onset < WINDOW else onset
    return {
        "file_name": file_name,
        "label": window_label(states),
        "server": server,
        "role": role,
        "onset_min": onset,
        "state_seq": json.dumps(states, separators=(",", ":")),
        "warn_seq": json.dumps(warn, separators=(",", ":")),
    }


def write_labels(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_COLUMNS)
        w.writeheader()
        w.writerows(records)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def pack_zip(data_dir: Path, split: str) -> tuple[int, str]:
    zip_path = data_dir / f"{data_dir.name}-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(data_dir / split / "labels.csv", arcname=f"{split}/labels.csv")
        for f in sorted((data_dir / split / "series").glob("*.csv")):
            zf.write(f, arcname=f"{split}/series/{f.name}")
    return zip_path.stat().st_size, _sha256_file(zip_path)


def write_meta(data_dir: Path, info: dict, split_records: dict[str, list[dict]]) -> dict:
    """info 需含 id / displayName / summary / tags / benchmark{id, displayName} / machines{server: spec}；统计字段由本函数计算"""
    machines = info.get("machines") or {}
    for split, recs in split_records.items():
        for r in recs:
            spec = machines.get(r["server"])
            if not spec or any(k not in spec for k in MACHINE_SPEC_REQUIRED):
                raise ValueError(f"meta.machines 缺少机器 {r['server']} 的规格（需要 {MACHINE_SPEC_REQUIRED}）")
    meta = {**info, "task": TASK, "window_minutes": WINDOW, "warn_horizon_minutes": WARN_HORIZON, "channels": CHANNELS, "states": STATES}
    for split, recs in split_records.items():
        size, sha = pack_zip(data_dir, split)
        counts: dict[str, int] = {}
        fault_min = 0
        for r in recs:
            counts[r["label"]] = counts.get(r["label"], 0) + 1
            fault_min += sum(1 for s in json.loads(r["state_seq"]) if s > 0)
        meta[split] = {"files": len(recs), "rows": len(recs), "sizeBytes": size, "contentHash": sha, "classCounts": counts, "faultMinuteRatio": round(fault_min / max(1, len(recs) * WINDOW), 4)}
    (data_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    validate_dataset(data_dir)
    return meta


# ================================================================== 读取（评测 / 训练 / 推理共用）
def parse_series(rows: list[dict], source: str = "") -> np.ndarray:
    """标准 CSV 行 -> [60, 8]；缺列直接报错，多于 60 行取最后 60 行，不足则用首行向前补齐"""
    if not rows:
        raise ValueError(f"{source} 为空")
    missing = [c for c in CHANNELS if c not in rows[0]]
    if missing:
        raise ValueError(f"{source} 不符合服务器故障检测标准，缺少列：{', '.join(missing)}（需要：{', '.join(SERIES_COLUMNS)}）")
    vals = [[float(r[c] or 0.0) for c in CHANNELS] for r in rows[-WINDOW:]]
    while len(vals) < WINDOW:
        vals.insert(0, vals[0])
    return np.asarray(vals, dtype=np.float32)


def read_series(path: Path) -> np.ndarray:
    with path.open("r", encoding="utf-8-sig") as f:
        return parse_series(list(csv.DictReader(f)), path.name)


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


def load_split(data_dir: Path, split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """返回 (原始遥测 [N,60,8], 状态真值 [N,60], 预警真值 [N,60], 元数据)"""
    raws, ys, ws, metas = [], [], [], []
    for row in read_labels(data_dir, split):
        raws.append(read_series(data_dir / split / row["file_name"]))
        ys.append(json.loads(row["state_seq"]))
        ws.append(json.loads(row["warn_seq"]))
        metas.append({k: row[k] for k in ("file_name", "label", "server", "role", "onset_min")})
    return np.stack(raws), np.asarray(ys, dtype=np.int64), np.asarray(ws, dtype=np.float32), metas


def load_specs(data_dir: Path, metas: list[dict]) -> list[dict]:
    """每个窗口所在机器的规格（来自 meta.json 的 machines）"""
    machines = (read_meta(data_dir) or {}).get("machines", {})
    return [machines.get(m["server"], DEFAULT_SPEC) for m in metas]


def to_relative(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """[N, 60, 8] 原始遥测 -> 按容量换算的相对值（约 0~1）：百分比 /100、温度 /100、磁盘 / 磁盘上限、网络 / 网络上限"""
    raw = np.asarray(raw, dtype=np.float32)
    if len(specs) != len(raw):
        raise ValueError("specs 数量必须与窗口数一致")
    scale = np.ones((len(raw), 1, len(CHANNELS)), dtype=np.float32) * 100.0
    for i, sp in enumerate(specs):
        scale[i, 0, CHANNELS.index("disk_io_mbps")] = float(sp.get("disk_max_mbps") or DEFAULT_SPEC["disk_max_mbps"])
        scale[i, 0, CHANNELS.index("net_mbps")] = float(sp.get("net_max_mbps") or DEFAULT_SPEC["net_max_mbps"])
    return np.clip(raw / scale, 0.0, 1.5).astype(np.float32)


def validate_dataset(data_dir: Path) -> None:
    meta = read_meta(data_dir)
    if not meta:
        raise ValueError(f"{data_dir.name}: meta.json 缺失或 task 不是 {TASK}")
    for server, spec in (meta.get("machines") or {}).items():
        if any(k not in spec for k in MACHINE_SPEC_REQUIRED):
            raise ValueError(f"{data_dir.name}: 机器 {server} 的规格缺少 {MACHINE_SPEC_REQUIRED}")
    if not meta.get("machines"):
        raise ValueError(f"{data_dir.name}: meta.json 缺少 machines 机器规格")
    for split in ("train", "test"):
        with (data_dir / split / "labels.csv").open("r", encoding="utf-8") as f:
            header = next(csv.reader(f))
        if header != LABEL_COLUMNS:
            raise ValueError(f"{data_dir.name}/{split}/labels.csv 表头应为 {LABEL_COLUMNS}，实际 {header}")
        first = read_labels(data_dir, split)[0]
        with (data_dir / split / first["file_name"]).open("r", encoding="utf-8") as f:
            sheader = next(csv.reader(f))
        if sheader != SERIES_COLUMNS:
            raise ValueError(f"{data_dir.name}/{split}/{first['file_name']} 表头应为 {SERIES_COLUMNS}，实际 {sheader}")


def run_label(pred_state: np.ndarray | None, fault_prob: np.ndarray) -> int:
    """窗口判定：最长的连续故障段 >= MIN_FAULT_RUN 分钟才算故障。有状态输出时返回该段状态码，否则返回 8（其他异常）"""
    seq = pred_state.tolist() if pred_state is not None else [8 if p >= 0.5 else 0 for p in fault_prob.tolist()]
    best, best_len, run_c, run_len = 0, 0, -1, 0
    for c in seq:
        run_len = run_len + 1 if c == run_c else 1
        run_c = c
        if c > 0 and run_len > best_len:
            best, best_len = c, run_len
    return best if best_len >= MIN_FAULT_RUN else 0


# ================================================================== 评测
def _auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    pos = labels > 0.5
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _prf(flag: np.ndarray, truth: np.ndarray) -> tuple[float, float, float]:
    tp = int(np.sum(flag & truth))
    fp = int(np.sum(flag & ~truth))
    fn = int(np.sum(~flag & truth))
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


METRICS = [
    {"key": "fault_f1", "label": "逐分钟故障检测 F1", "higherIsBetter": True, "unit": "%", "primary": True},
    {"key": "fault_auc", "label": "故障检测 AUC", "higherIsBetter": True, "unit": "%"},
    {"key": "state_macro_f1", "label": "故障类型 Macro-F1", "higherIsBetter": True, "unit": "%"},
    {"key": "event_recall", "label": "故障事件检出率", "higherIsBetter": True, "unit": "%"},
    {"key": "false_alarm_rate", "label": "正常窗口误报率", "higherIsBetter": False, "unit": "%"},
    {"key": "detect_delay_min", "label": "平均检测时延", "higherIsBetter": False, "unit": "分钟"},
    {"key": "warn_auc", "label": "10 分钟预警 AUC", "higherIsBetter": True, "unit": "%"},
]


CAUSAL_CUTS = (15, 30, 45)
CAUSAL_TOL = 1e-3


def check_causal(predict_batch: Callable[[np.ndarray, list[dict]], dict], raw: np.ndarray, specs: list[dict], n: int = 32) -> None:
    """因果性检查：把第 t 分钟之后的数据换成另一个窗口的数据，第 0~t 分钟的输出必须不变。
    逐分钟输出代表「此刻能给出的判断」，只允许使用当前及过去的数据；不满足即视为偷看未来，评测失败。"""
    k = min(n, len(raw))
    if k < 2:
        return
    sel = np.linspace(0, len(raw) - 1, k).astype(int)
    donor = np.roll(sel, 1)
    # 用同一批样本、同样批大小重新推理一次作为对照，排除 GPU 上批大小不同带来的浮点误差
    base = predict_batch(raw[sel].copy(), [specs[i] for i in sel])
    for t in CAUSAL_CUTS:
        mixed = raw[sel].copy()
        mixed[:, t + 1 :] = raw[donor, t + 1 :]
        out = predict_batch(mixed, [specs[i] for i in sel])
        for key in ("fault_prob", "warn_prob", "state"):
            if base.get(key) is None or out.get(key) is None:
                continue
            a = np.asarray(base[key], dtype=np.float64)[:, : t + 1]
            b = np.asarray(out[key], dtype=np.float64)[:, : t + 1]
            diff = float(np.abs(a - b).max())
            if diff > (0.0 if key == "state" else CAUSAL_TOL):
                raise ValueError(f"因果性检查未通过：改动第 {t + 1} 分钟之后的数据，第 0~{t} 分钟的 {key} 输出变化了 {diff:.4f}（算法使用了未来数据）")


def evaluate(
    predict_batch: Callable[[np.ndarray, list[dict]], dict],
    data_dir: Path,
    history: list[dict] | None = None,
    say: Callable[[int, str], None] | None = None,
) -> dict:
    """统一评测器：任意符合标准的算法 × 任意符合标准的数据集测试集"""
    say = say or (lambda p, m: None)
    t0 = time.perf_counter()
    RAW, Y, WG, metas = load_split(data_dir, "test")
    specs = load_specs(data_dir, metas)
    say(30, f"[runner] 挂载 {data_dir.name}@v1.0/test：{len(metas)} 个 60 分钟 × 8 通道窗口（标准 {TASK}），共 {Y.size:,} 个逐分钟真值")

    t_inf = time.perf_counter()
    out = predict_batch(RAW, specs)
    infer_ms = (time.perf_counter() - t_inf) * 1000
    P = np.asarray(out["fault_prob"], dtype=np.float64)
    S = np.asarray(out["state"], dtype=np.int64) if out.get("state") is not None else None
    W = np.asarray(out["warn_prob"], dtype=np.float64) if out.get("warn_prob") is not None else None
    if P.shape != Y.shape or (S is not None and S.shape != Y.shape) or (W is not None and W.shape != Y.shape):
        raise ValueError(f"算法输出形状不符合标准：需要 {Y.shape}")
    caps = "故障概率" + (" + 状态码" if S is not None else "") + (" + 预警概率" if W is not None else "")
    say(55, f"[runner] 推理完成：{len(RAW)} 个窗口用时 {infer_ms:.1f} ms，算法输出 {caps}")
    check_causal(predict_batch, RAW, specs)
    say(60, f"[runner] 因果性检查通过：替换第 {', '.join(str(t + 1) for t in CAUSAL_CUTS)} 分钟之后的数据，之前各分钟输出不变（未使用未来数据）")

    is_fault = Y > 0
    flag = P >= 0.5
    _, _, fault_f1 = _prf(flag, is_fault)
    fault_auc = _auc(P.ravel(), is_fault.ravel().astype(np.float64))

    present = sorted(set(Y.ravel().tolist()))
    per_class, state_f1s = [], []
    for c in present:
        sel = Y == c
        # 各类检出率：故障类 = 该类故障分钟被判为故障的比例；正常类 = 正常分钟未被误报的比例
        det = float(np.mean(~flag[sel])) if c == 0 else float(np.mean(flag[sel]))
        item = {"label": STATES[c], "value": round(det * 100, 2), "support": int(sel.sum())}
        if S is not None:
            _, _, f1c = _prf(S == c, sel)
            state_f1s.append(f1c)
            item["stateF1"] = round(f1c * 100, 2)
        per_class.append(item)

    delays, n_events, detected = [], 0, 0
    win_true = [int(np.any(y > 0)) for y in Y]
    for i in range(len(Y)):
        faults = np.where(Y[i] > 0)[0]
        if len(faults) == 0 or faults[0] == 0:
            continue
        n_events += 1
        onset = int(faults[0])
        end = int(faults[-1])
        hit = np.where(flag[i, onset : end + 1])[0]
        if len(hit):
            detected += 1
            delays.append(int(hit[0]))
    win_pred = [run_label(S[i] if S is not None else None, P[i]) > 0 for i in range(len(Y))]
    normals = [i for i in range(len(Y)) if not win_true[i]]
    false_alarm = sum(1 for i in normals if win_pred[i]) / max(1, len(normals))

    warn_auc = None
    if W is not None:
        mask = Y == 0
        warn_auc = _auc(W[mask], WG[mask])

    metrics: dict[str, float] = {
        "fault_f1": round(fault_f1 * 100, 2),
        "event_recall": round(detected / max(1, n_events) * 100, 2),
        "false_alarm_rate": round(false_alarm * 100, 2),
        "detect_delay_min": round(float(np.mean(delays)) if delays else 0.0, 2),
    }
    if fault_auc is not None:
        metrics["fault_auc"] = round(fault_auc * 100, 2)
    if S is not None:
        metrics["state_macro_f1"] = round(float(np.mean(state_f1s)) * 100, 2)
    if warn_auc is not None:
        metrics["warn_auc"] = round(warn_auc * 100, 2)
    say(80, "[runner] 生成可视化数据：典型样本、故障起点对齐、阈值扫描、检测时延分布、训练曲线")

    threshold_curve = []
    for th in np.round(np.arange(0.05, 0.96, 0.05), 2):
        f = P >= th
        p, r, f1 = _prf(f, is_fault)
        fpr = int(np.sum(f & ~is_fault)) / max(1, int(np.sum(~is_fault)))
        threshold_curve.append({"threshold": float(th), "precision": round(p * 100, 2), "recall": round(r * 100, 2), "f1": round(f1 * 100, 2), "fpr": round(fpr * 100, 2)})
    delay_cdf = [{"minute": d, "detected": round(100 * sum(1 for x in delays if x <= d) / max(1, n_events), 2)} for d in range(0, 16)]

    aligned = []
    onsets = [(i, int(np.where(Y[i] > 0)[0][0])) for i in range(len(Y)) if np.any(Y[i] > 0) and Y[i, 0] == 0]
    for off in range(-20, 21):
        pts = [(i, o + off) for i, o in onsets if 0 <= o + off < WINDOW]
        if not pts:
            continue
        aligned.append({
            "offset": off,
            "anomaly": round(float(np.mean([P[i, t] for i, t in pts])) * 100, 2),
            "warn": round(float(np.mean([W[i, t] for i, t in pts])) * 100, 2) if W is not None else None,
            "gtFault": round(float(np.mean([1.0 if Y[i, t] > 0 else 0.0 for i, t in pts])) * 100, 2),
            "n": len(pts),
        })

    def case(i: int) -> dict:
        onset = int(np.where(Y[i] > 0)[0][0]) if np.any(Y[i] > 0) else (int(metas[i]["onset_min"]) if int(metas[i]["onset_min"]) >= WINDOW else -1)
        return {
            "file": Path(metas[i]["file_name"]).name,
            "server": metas[i]["server"],
            "role": metas[i]["role"],
            "spec": specs[i],
            "label": metas[i]["label"],
            "predLabel": STATES[run_label(S[i] if S is not None else None, P[i])],
            "onset": onset,
            "channels": {c: [round(float(v), 1) for v in RAW[i, :, k]] for k, c in enumerate(CHANNELS)},
            "gt": Y[i].astype(int).tolist(),
            "pred": S[i].astype(int).tolist() if S is not None else None,
            "anomaly": [round(float(v), 4) for v in P[i]],
            "warn": [round(float(v), 4) for v in W[i]] if W is not None else None,
            "warnGt": WG[i].astype(int).tolist(),
        }

    cases, picked = [], set()
    for c in present:
        if c == 0:
            continue
        cand = [i for i, m in enumerate(metas) if Y[i, 0] == 0 and STATE_CODE.get(m["label"]) == c]
        cand.sort(key=lambda i: abs(int(np.where(Y[i] > 0)[0][0]) - 30))
        if cand:
            cases.append(case(cand[0]))
            picked.add(cand[0])
    pre = next((i for i, m in enumerate(metas) if not np.any(Y[i] > 0) and np.any(WG[i] > 0)), None)
    if pre is not None:
        cases.append(case(pre))
    norm = next((i for i, m in enumerate(metas) if not np.any(Y[i] > 0) and not np.any(WG[i] > 0)), None)
    if norm is not None:
        cases.append(case(norm))

    elapsed = round(time.perf_counter() - t0, 2)
    say(95, f"[runner] 指标汇总完成，用时 {elapsed}s")
    return {
        "metrics": metrics,
        "perClass": per_class,
        "perClassLabel": "各类别故障检出率（正常类为未误报率）",
        "samples": len(metas),
        "durationSec": max(0.2, elapsed),
        "latencyMs": round(infer_ms / len(RAW), 3),
        "vizServerFault": {
            "states": STATES,
            "channels": CHANNELS,
            "capabilities": {"state": S is not None, "warn": W is not None},
            "history": history or [],
            "thresholdCurve": threshold_curve,
            "delayCdf": delay_cdf,
            "onsetAligned": aligned,
            "cases": cases,
        },
    }
