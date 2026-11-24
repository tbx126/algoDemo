"""
[0x07] 服务器运行故障检测时序算法（Admin/0x07）：训练、评测与推理

  - 模型：Fault0x07Net = 因果膨胀 TCN（只看过去，不偷看未来）+ 单向 GRU + 双头输出
      * 状态头：逐分钟 6 类运行状态（正常 / CPU过载 / 内存泄漏 / GPU过热 / 磁盘IO饱和 / 网络异常）
      * 预警头：逐分钟「未来 10 分钟内将发生故障」概率
  - 数据集：Admin/0x07-server-telemetry-dataset（60 分钟 × 8 通道遥测窗口，逐分钟真值）
  - 权重：backend/models/0x07/v1.0.0_fault0x07.pt
  - 状态：backend/state/fault0x07_state.json（训练曲线、评测记录与可视化数据）
"""
from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path
from typing import Callable

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent
DATA_0X07_DIR = ROOT / "data" / "0x07-server-telemetry-dataset"
MODEL_0X07_DIR = ROOT / "models" / "0x07"
STATE_0X07_PATH = ROOT / "state" / "fault0x07_state.json"
WEIGHT_0X07_PATH = MODEL_0X07_DIR / "v1.0.0_fault0x07.pt"

ALGO_0X07_ID = "Admin/0x07"
DATASET_0X07_ID = "Admin/0x07-server-telemetry-dataset"
BENCH_0X07_ID = "0x07-server-fault-bench"
TASK_0X07 = "server-fault-0x07"

WINDOW = 60
WARN_HORIZON = 10
CHANNELS = ["cpu_pct", "cpu_temp_c", "mem_pct", "gpu_pct", "gpu_temp_c", "gpu_mem_pct", "disk_io_mbps", "net_mbps"]
SCALES = np.asarray([100, 100, 100, 100, 100, 100, 500, 1000], dtype=np.float32)
STATES = ["正常", "CPU过载", "内存泄漏", "GPU过热", "磁盘IO饱和", "网络异常"]
N_STATES = len(STATES)
IN_FEATURES = len(CHANNELS) * 2  # 归一化值 + 一阶差分


# ------------------------------------------------------------------ 模型
class _CausalBlock(nn.Module):
    def __init__(self, ch: int, dilation: int):
        super().__init__()
        self.pad = 2 * dilation
        self.conv1 = nn.Conv1d(ch, ch, kernel_size=3, dilation=dilation)
        self.conv2 = nn.Conv1d(ch, ch, kernel_size=3, dilation=dilation)
        self.norm = nn.GroupNorm(8, ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.gelu(self.conv1(F.pad(x, (self.pad, 0))))
        y = self.conv2(F.pad(y, (self.pad, 0)))
        return F.gelu(self.norm(x + y))


class Fault0x07Net(nn.Module):
    """因果 TCN + GRU 逐分钟故障状态识别与预警网络"""

    def __init__(self, in_features: int = IN_FEATURES, hidden: int = 64):
        super().__init__()
        self.inp = nn.Conv1d(in_features, hidden, kernel_size=1)
        self.tcn = nn.Sequential(*[_CausalBlock(hidden, d) for d in (1, 2, 4, 8)])
        self.gru = nn.GRU(hidden, hidden, batch_first=True)
        self.state_head = nn.Linear(hidden, N_STATES)
        self.warn_head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # x: [B, T, F]
        h = self.tcn(self.inp(x.permute(0, 2, 1))).permute(0, 2, 1)
        h, _ = self.gru(h)
        return self.state_head(h), self.warn_head(h).squeeze(-1)


# ------------------------------------------------------------------ 数据
def _rows_to_raw(rows: list[dict]) -> np.ndarray:
    """CSV 行 -> [60, 8] 原始数值（多于 60 行取最后 60 行，不足则用首行向前补齐）"""
    vals = []
    for r in rows[-WINDOW:]:
        vals.append([float(r.get(c) or 0.0) for c in CHANNELS])
    if not vals:
        vals = [[0.0] * len(CHANNELS)]
    while len(vals) < WINDOW:
        vals.insert(0, vals[0])
    return np.asarray(vals, dtype=np.float32)


def _encode(raw: np.ndarray) -> np.ndarray:
    norm = raw / SCALES
    diff = np.diff(norm, axis=0, prepend=norm[:1])
    return np.concatenate([norm, diff * 4.0], axis=1).astype(np.float32)


def _read_series(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_split_0x07(split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """返回 (编码特征 [N,60,16], 原始数值 [N,60,8], 状态真值 [N,60], 预警真值 [N,60], 元数据)"""
    split_dir = DATA_0X07_DIR / split
    xs, raws, ys, ws, metas = [], [], [], [], []
    with (split_dir / "labels.csv").open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = _rows_to_raw(_read_series(split_dir / row["file_name"]))
            raws.append(raw)
            xs.append(_encode(raw))
            ys.append(json.loads(row["state_seq"]))
            ws.append(json.loads(row["warn_seq"]))
            metas.append({k: row[k] for k in ("file_name", "label", "server", "role", "onset_min")})
    return (
        np.stack(xs),
        np.stack(raws),
        np.asarray(ys, dtype=np.int64),
        np.asarray(ws, dtype=np.float32),
        metas,
    )


# ------------------------------------------------------------------ 设备与缓存
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_CACHE: Fault0x07Net | None = None


def device_label_0x07() -> str:
    if torch.cuda.is_available():
        return f"GPU ({torch.cuda.get_device_name(0)})"
    return "CPU (PyTorch)"


def load_state_0x07() -> dict | None:
    if STATE_0X07_PATH.exists():
        try:
            return json.loads(STATE_0X07_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_state_0x07(state: dict) -> None:
    STATE_0X07_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_0X07_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_0X07_PATH)


# ------------------------------------------------------------------ 指标
def _macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[float, list[dict]]:
    per = []
    f1s = []
    for c in range(N_STATES):
        tp = int(np.sum((y_pred == c) & (y_true == c)))
        fp = int(np.sum((y_pred == c) & (y_true != c)))
        fn = int(np.sum((y_pred != c) & (y_true == c)))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        f1s.append(f1)
        per.append({"label": STATES[c], "value": round(f1 * 100, 2), "precision": round(p * 100, 2), "recall": round(r * 100, 2), "support": tp + fn})
    return float(np.mean(f1s)), per


def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    pos = labels > 0.5
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return 0.0
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    ranks[order] = np.arange(1, len(scores) + 1)
    return float((ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def _window_label(pred_seq: np.ndarray) -> int:
    """窗口判定：某一故障类连续出现 >= 3 分钟才判为该故障，避免孤立毛刺误报"""
    best, best_len = 0, 0
    run_c, run_len = -1, 0
    for c in pred_seq.tolist():
        run_len = run_len + 1 if c == run_c else 1
        run_c = c
        if c > 0 and run_len > best_len:
            best, best_len = c, run_len
    return best if best_len >= 3 else 0


def _predict(model: Fault0x07Net, x: np.ndarray, batch: int = 256) -> tuple[np.ndarray, np.ndarray]:
    probs, warns = [], []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(x), batch):
            logits, wlog = model(torch.from_numpy(x[i : i + batch]).to(_DEVICE))
            probs.append(torch.softmax(logits, dim=-1).cpu().numpy())
            warns.append(torch.sigmoid(wlog).cpu().numpy())
    return np.concatenate(probs), np.concatenate(warns)


# ------------------------------------------------------------------ 训练
def train_0x07(epochs: int = 60) -> dict:
    MODEL_0X07_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(7)
    np.random.seed(7)

    X, _, Y, W, _ = load_split_0x07("train")
    idx = np.random.permutation(len(X))
    n_val = len(X) // 10
    val_idx, tr_idx = idx[:n_val], idx[n_val:]

    xt = torch.from_numpy(X[tr_idx]).to(_DEVICE)
    yt = torch.from_numpy(Y[tr_idx]).to(_DEVICE)
    wt = torch.from_numpy(W[tr_idx]).to(_DEVICE)
    xv = torch.from_numpy(X[val_idx]).to(_DEVICE)
    yv = torch.from_numpy(Y[val_idx]).to(_DEVICE)
    wv = torch.from_numpy(W[val_idx]).to(_DEVICE)

    counts = np.bincount(Y[tr_idx].ravel(), minlength=N_STATES).astype(np.float32)
    cls_w = torch.from_numpy((counts.sum() / (N_STATES * np.maximum(counts, 1))) ** 0.5).to(_DEVICE)
    pos_w = torch.tensor(float((W[tr_idx] == 0).sum() / max(1, (W[tr_idx] == 1).sum())) ** 0.5, device=_DEVICE)

    model = Fault0x07Net().to(_DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=epochs * ((len(tr_idx) + 63) // 64))

    def loss_of(xb, yb, wb):
        logits, wlog = model(xb)
        ce = F.cross_entropy(logits.reshape(-1, N_STATES), yb.reshape(-1), weight=cls_w)
        bce = F.binary_cross_entropy_with_logits(wlog, wb, pos_weight=pos_w)
        return ce + 0.5 * bce

    history = []
    t0 = time.perf_counter()
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(xt), device=_DEVICE)
        total, nb = 0.0, 0
        for i in range(0, len(xt), 64):
            b = perm[i : i + 64]
            opt.zero_grad()
            loss = loss_of(xt[b], yt[b], wt[b])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            total += float(loss)
            nb += 1
        model.eval()
        with torch.no_grad():
            vloss = float(loss_of(xv, yv, wv))
            vpred = model(xv)[0].argmax(-1).cpu().numpy()
        vf1, _ = _macro_f1(Y[val_idx].ravel(), vpred.ravel())
        history.append({"epoch": ep, "train_loss": round(total / nb, 4), "val_loss": round(vloss, 4), "val_f1": round(vf1 * 100, 2)})
        if ep % 10 == 0 or ep == 1:
            print(f"[0x07] epoch {ep:3d} train_loss={total / nb:.4f} val_loss={vloss:.4f} val_macroF1={vf1 * 100:.2f}%")

    torch.save({"state_dict": model.state_dict(), "channels": CHANNELS, "states": STATES, "window": WINDOW}, WEIGHT_0X07_PATH)
    global _MODEL_CACHE
    _MODEL_CACHE = model

    state = load_state_0x07() or {}
    state.update({
        "algorithm_id": ALGO_0X07_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_0X07_PATH.name,
        "weight_bytes": WEIGHT_0X07_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "train_seconds": round(time.perf_counter() - t0, 1),
        "device": device_label_0x07(),
        "epochs": epochs,
        "history": history,
    })
    state.setdefault("evals", [])
    save_state_0x07(state)
    print(f"[0x07] 训练完成 -> {WEIGHT_0X07_PATH.name} ({state['weight_bytes']:,} B)，用时 {state['train_seconds']}s")
    return state


def load_model_0x07() -> Fault0x07Net:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if not WEIGHT_0X07_PATH.exists():
        train_0x07()
        assert _MODEL_CACHE is not None
        return _MODEL_CACHE
    ckpt = torch.load(WEIGHT_0X07_PATH, map_location=_DEVICE, weights_only=True)
    model = Fault0x07Net().to(_DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _MODEL_CACHE = model
    return model


# ------------------------------------------------------------------ 评测
def _case(meta: dict, raw: np.ndarray, gt: np.ndarray, prob: np.ndarray, warn: np.ndarray, warn_gt: np.ndarray) -> dict:
    pred = prob.argmax(-1)
    return {
        "file": Path(meta["file_name"]).name,
        "server": meta["server"],
        "role": meta["role"],
        "label": meta["label"],
        "predLabel": STATES[_window_label(pred)],
        "onset": int(meta["onset_min"]),
        "channels": {c: [round(float(v), 1) for v in raw[:, i]] for i, c in enumerate(CHANNELS)},
        "gt": gt.astype(int).tolist(),
        "pred": pred.astype(int).tolist(),
        "anomaly": [round(float(1 - p), 4) for p in prob[:, 0]],
        "warn": [round(float(w), 4) for w in warn],
        "warnGt": warn_gt.astype(int).tolist(),
    }


def evaluate_0x07(on_progress: Callable[[int, str], None] | None = None) -> dict:
    """在 Admin/0x07-server-telemetry-dataset@v1.0/test 上运行真实评测，返回指标与折线图可视化数据"""
    t0 = time.perf_counter()
    say = on_progress or (lambda p, m: None)
    say(10, f"[runner] 加载 {ALGO_0X07_ID}@v1.0.0 权重 {WEIGHT_0X07_PATH.name}（{device_label_0x07()}）")
    model = load_model_0x07()
    X, RAW, Y, WG, metas = load_split_0x07("test")
    say(30, f"[runner] 挂载 {DATASET_0X07_ID}@v1.0/test：{len(metas)} 个 60 分钟 × 8 通道遥测窗口，共 {Y.size:,} 个逐分钟真值")

    t_inf = time.perf_counter()
    P, WP = _predict(model, X)
    infer_ms = (time.perf_counter() - t_inf) * 1000
    pred = P.argmax(-1)
    say(60, f"[runner] 推理完成：{len(X)} 个窗口用时 {infer_ms:.1f} ms，开始计算逐分钟 Macro-F1、窗口准确率与检测时延")

    macro_f1, per_class = _macro_f1(Y.ravel(), pred.ravel())
    win_true = np.asarray([int(max(r)) if r.max() > 0 else 0 for r in Y])
    win_pred = np.asarray([_window_label(p) for p in pred])
    window_acc = float(np.mean(win_true == win_pred))

    # 事件级：窗口内发生的故障是否被正确类别检出，以及检出时延
    delays, n_events, detected = [], 0, 0
    for i, m in enumerate(metas):
        onset = int(m["onset_min"])
        if 0 <= onset < WINDOW and win_true[i] > 0:
            n_events += 1
            hit = np.where((pred[i, onset:] == win_true[i]))[0]
            if len(hit):
                detected += 1
                delays.append(int(hit[0]))
    event_recall = detected / max(1, n_events)
    normal_wins = win_true == 0
    false_alarm = float(np.mean(win_pred[normal_wins] > 0)) if normal_wins.any() else 0.0
    mean_delay = float(np.mean(delays)) if delays else 0.0

    warn_mask = Y == 0  # 预警只在「当前仍正常」的分钟上有意义
    warn_auc = _auc(WP[warn_mask], WG[warn_mask])
    say(80, "[runner] 生成可视化数据：训练曲线、阈值扫描、检测时延累计分布、故障起点对齐曲线与典型样本")

    # 阈值扫描：异常分数 = 1 - P(正常)
    score = 1 - P[..., 0]
    is_fault = Y > 0
    threshold_curve = []
    for th in np.round(np.arange(0.05, 0.96, 0.05), 2):
        flag = score >= th
        tp = int(np.sum(flag & is_fault))
        fp = int(np.sum(flag & ~is_fault))
        fn = int(np.sum(~flag & is_fault))
        p = tp / (tp + fp) if tp + fp else 1.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        fpr = fp / max(1, int(np.sum(~is_fault)))
        threshold_curve.append({"threshold": float(th), "precision": round(p * 100, 2), "recall": round(r * 100, 2), "f1": round(f1 * 100, 2), "fpr": round(fpr * 100, 2)})

    delay_cdf = [{"minute": d, "detected": round(100 * sum(1 for x in delays if x <= d) / max(1, n_events), 2)} for d in range(0, 16)]

    # 以故障起始分钟对齐，统计 -20 ~ +20 分钟的平均异常分数 / 预警概率 / 真值故障占比
    aligned = []
    for off in range(-20, 21):
        sc, wp, gt = [], [], []
        for i, m in enumerate(metas):
            onset = int(m["onset_min"])
            t = onset + off
            if win_true[i] > 0 and 0 <= onset < WINDOW and 0 <= t < WINDOW:
                sc.append(score[i, t])
                wp.append(WP[i, t])
                gt.append(1.0 if Y[i, t] > 0 else 0.0)
        if sc:
            aligned.append({"offset": off, "anomaly": round(float(np.mean(sc)) * 100, 2), "warn": round(float(np.mean(wp)) * 100, 2), "gtFault": round(float(np.mean(gt)) * 100, 2), "n": len(sc)})

    # 典型样本：每类故障各取 1 个窗口内起始的样本 + 1 个仅前兆窗口 + 1 个正常窗口
    cases, picked = [], set()
    for target in STATES[1:]:
        for i, m in enumerate(metas):
            if m["label"] == target and 15 <= int(m["onset_min"]) <= 45 and i not in picked:
                cases.append(_case(m, RAW[i], Y[i], P[i], WP[i], WG[i]))
                picked.add(i)
                break
    for i, m in enumerate(metas):
        if m["label"] == "正常" and int(m["onset_min"]) >= WINDOW:
            cases.append(_case(m, RAW[i], Y[i], P[i], WP[i], WG[i]))
            break
    for i, m in enumerate(metas):
        if m["label"] == "正常" and int(m["onset_min"]) < 0:
            cases.append(_case(m, RAW[i], Y[i], P[i], WP[i], WG[i]))
            break

    state = load_state_0x07() or {}
    elapsed = round(time.perf_counter() - t0, 2)
    say(95, f"[runner] 指标汇总完成，用时 {elapsed}s")
    return {
        "metrics": {
            "macro_f1": round(macro_f1 * 100, 2),
            "window_acc": round(window_acc * 100, 2),
            "event_recall": round(event_recall * 100, 2),
            "false_alarm_rate": round(false_alarm * 100, 2),
            "detect_delay_min": round(mean_delay, 2),
            "warn_auc": round(warn_auc * 100, 2),
        },
        "perClass": per_class,
        "samples": len(metas),
        "events": n_events,
        "durationSec": max(0.2, elapsed),
        "latencyMs": round(infer_ms / len(X), 3),
        "device": device_label_0x07(),
        "viz0x07": {
            "states": STATES,
            "channels": CHANNELS,
            "history": state.get("history", []),
            "thresholdCurve": threshold_curve,
            "delayCdf": delay_cdf,
            "onsetAligned": aligned,
            "cases": cases,
        },
    }


# ------------------------------------------------------------------ 推理
def list_samples_0x07(split: str = "test") -> list[dict]:
    out = []
    with (DATA_0X07_DIR / split / "labels.csv").open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append({"file": Path(row["file_name"]).name, "label": row["label"], "server": row["server"], "onset": int(row["onset_min"])})
    return out


def infer_0x07(csv_bytes: bytes | None = None, filename: str = "", sample_file: str | None = None) -> dict:
    """真实推理：上传 60 分钟遥测 CSV，或指定数据集中的示例窗口"""
    t0 = time.perf_counter()
    model = load_model_0x07()
    rows: list[dict] = []
    gt: list[int] | None = None
    warn_gt: list[int] | None = None
    source = filename or "upload.csv"
    if csv_bytes:
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig", errors="ignore"))))
        missing = [c for c in CHANNELS if rows and c not in rows[0]]
        if not rows or missing:
            raise ValueError(f"CSV 需包含列：{', '.join(CHANNELS)}" + (f"（缺少 {', '.join(missing)}）" if missing else ""))
    if not rows:
        # 未上传：取训练集（公开）中的示例窗口，默认挑一个带故障的样本
        name = Path(sample_file).name if sample_file else None
        with (DATA_0X07_DIR / "train" / "labels.csv").open("r", encoding="utf-8") as f:
            recs = list(csv.DictReader(f))
        rec = next((r for r in recs if Path(r["file_name"]).name == name), None) if name else None
        if rec is None:
            rec = next(r for r in recs if r["label"] != "正常" and 20 <= int(r["onset_min"]) <= 40)
        rows = _read_series(DATA_0X07_DIR / "train" / rec["file_name"])
        gt = json.loads(rec["state_seq"])
        warn_gt = json.loads(rec["warn_seq"])
        source = Path(rec["file_name"]).name

    raw = _rows_to_raw(rows)
    with torch.no_grad():
        logits, wlog = model(torch.from_numpy(_encode(raw)).unsqueeze(0).to(_DEVICE))
        prob = torch.softmax(logits, -1)[0].cpu().numpy()
        warn = torch.sigmoid(wlog)[0].cpu().numpy()
    pred = prob.argmax(-1)
    win = _window_label(pred)
    first_fault = next((t for t in range(WINDOW) if pred[t] > 0), None)
    latency = max(0.3, round((time.perf_counter() - t0) * 1000, 2))
    return {
        "device": device_label_0x07(),
        "latencyMs": latency,
        "queuedMs": 0,
        "raw": {
            "algorithm": ALGO_0X07_ID,
            "version": "v1.0.0",
            "task": TASK_0X07,
            "source_file": source,
            "window_minutes": WINDOW,
            "warn_horizon_minutes": WARN_HORIZON,
            "states": STATES,
            "status": STATES[win],
            "first_fault_minute": first_fault,
            "risk_next_10min": round(float(warn[-1]) * 100, 2),
            "max_anomaly": round(float((1 - prob[:, 0]).max()) * 100, 2),
            "channels": {c: [round(float(v), 1) for v in raw[:, i]] for i, c in enumerate(CHANNELS)},
            "pred": pred.astype(int).tolist(),
            "anomaly": [round(float(1 - p), 4) for p in prob[:, 0]],
            "warn": [round(float(w), 4) for w in warn],
            "gt": gt,
            "warnGt": warn_gt,
        },
    }


if __name__ == "__main__":
    train_0x07()
    res = evaluate_0x07(lambda p, m: print(m))
    print(json.dumps(res["metrics"], ensure_ascii=False))
    print(json.dumps(res["perClass"], ensure_ascii=False))
