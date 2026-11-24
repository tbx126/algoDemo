"""
服务器运行故障时序检测算法模块（Admin/0x6E）：
  - 模型结构：ServerFaultNet0x6E（多尺度 1D-CNN + 双向 GRU + 逐时间步故障风险预测头）
  - 输入通道（6 维服务器状态时序，60 分钟窗口）：
      cpu_pct, gpu_util_pct, gpu_mem_pct, mem_pct, disk_io_mbps, gpu_temp_c
  - 输出：逐时间步连续故障概率曲线 pred_prob[0..59] ∈ [0, 1] 与服务器运行状态诊断
  - 权重文件：backend/models/0x6e/v1.0.0_0x6e_faultnet.pt
  - 状态文件：backend/state/0x6e_state.json
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

ROOT = Path(__file__).resolve().parent
DATA_0X6E_DIR = ROOT / "data" / "0x6e-server-telemetry"
MODEL_0X6E_DIR = ROOT / "models" / "0x6e"
STATE_0X6E_PATH = ROOT / "state" / "0x6e_state.json"

ALGO_0X6E_ID = "Admin/0x6E"
DATASET_0X6E_ID = "Admin/0x6E-server-telemetry"
BENCH_0X6E_ID = "0x6E-server-fault-bench"
WEIGHT_0X6E_PATH = MODEL_0X6E_DIR / "v1.0.0_0x6e_faultnet.pt"

WINDOW_LEN = 60
IN_CHANNELS = 6  # cpu, gpu_util, gpu_mem, mem, disk_io, gpu_temp


class ServerFaultNet0x6E(nn.Module):
    """
    多尺度时序卷积 + 双向 GRU 服务器故障检测网络（0x6E）：
      - 分支 1：kernel=3 捕捉突发毛刺（CPU 尖峰 / IO 抖动）
      - 分支 2：kernel=7 捕捉中长期爬坡（显存泄漏 / 内存缓慢耗尽）
      - BiGRU 聚合 60 分钟上下文并输出逐时间步故障概率 logit
    """

    def __init__(self, in_ch: int = IN_CHANNELS):
        super().__init__()
        self.conv_short = nn.Sequential(
            nn.Conv1d(in_ch, 24, kernel_size=3, padding=1),
            nn.BatchNorm1d(24),
            nn.GELU(),
        )
        self.conv_long = nn.Sequential(
            nn.Conv1d(in_ch, 24, kernel_size=7, padding=3),
            nn.BatchNorm1d(24),
            nn.GELU(),
        )
        self.gru = nn.GRU(input_size=48, hidden_size=32, num_layers=1, batch_first=True, bidirectional=True)
        self.head = nn.Sequential(
            nn.Linear(64, 32),
            nn.GELU(),
            nn.Linear(32, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, T, 6]
        xt = x.permute(0, 2, 1)  # [B, 6, T]
        feat = torch.cat([self.conv_short(xt), self.conv_long(xt)], dim=1).permute(0, 2, 1)  # [B, T, 48]
        out, _ = self.gru(feat)  # [B, T, 64]
        return self.head(out).squeeze(-1)  # [B, T] logits


def _encode_rows(rows: list[dict]) -> tuple[np.ndarray, dict[str, list[float]], list[int] | None]:
    feats: list[list[float]] = []
    channels: dict[str, list[float]] = {
        "cpu_pct": [],
        "gpu_util_pct": [],
        "gpu_mem_pct": [],
        "mem_pct": [],
        "disk_io_mbps": [],
        "gpu_temp_c": [],
    }
    gt_list: list[int] = []
    has_gt = False

    for r in rows[-WINDOW_LEN:]:
        cpu = float(r.get("cpu_pct", 35.0))
        gpu_u = float(r.get("gpu_util_pct", 40.0))
        gpu_m = float(r.get("gpu_mem_pct", 42.0))
        mem = float(r.get("mem_pct", 48.0))
        disk = float(r.get("disk_io_mbps", 80.0))
        temp = float(r.get("gpu_temp_c", 56.0))
        channels["cpu_pct"].append(round(cpu, 2))
        channels["gpu_util_pct"].append(round(gpu_u, 2))
        channels["gpu_mem_pct"].append(round(gpu_m, 2))
        channels["mem_pct"].append(round(mem, 2))
        channels["disk_io_mbps"].append(round(disk, 2))
        channels["gpu_temp_c"].append(round(temp, 2))
        feats.append([cpu / 100.0, gpu_u / 100.0, gpu_m / 100.0, mem / 100.0, disk / 1000.0, temp / 100.0])
        if "gt_fault" in r and str(r["gt_fault"]).strip() != "":
            has_gt = True
            gt_list.append(1 if int(float(r["gt_fault"])) > 0 else 0)

    while len(feats) < WINDOW_LEN:
        pad_f = feats[0] if feats else [0.3, 0.3, 0.3, 0.4, 0.05, 0.5]
        feats.insert(0, pad_f)
        for k in channels:
            channels[k].insert(0, channels[k][0] if channels[k] else 0.0)
        if has_gt:
            gt_list.insert(0, gt_list[0] if gt_list else 0)

    return np.asarray(feats, dtype=np.float32), channels, (gt_list if has_gt else None)


def _load_split(split: str) -> tuple[np.ndarray, np.ndarray, list[dict], list[dict[str, list[float]]]]:
    split_dir = DATA_0X6E_DIR / split
    lbl_path = split_dir / "labels.csv"
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    metas: list[dict] = []
    all_channels: list[dict[str, list[float]]] = []
    with lbl_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            p = split_dir / row["file_name"]
            with p.open("r", encoding="utf-8") as sf:
                srows = list(csv.DictReader(sf))
            feat, ch, _ = _encode_rows(srows)
            gt = np.asarray(json.loads(row["gt_seq"]), dtype=np.float32)
            xs.append(feat)
            ys.append(gt)
            metas.append(row)
            all_channels.append(ch)
    return np.stack(xs, axis=0), np.stack(ys, axis=0), metas, all_channels


def _binary_metrics(y_true: np.ndarray, y_prob: np.ndarray, thresh: float = 0.5) -> dict[str, float]:
    yt = y_true.reshape(-1) > 0.5
    yp = y_prob.reshape(-1) >= thresh
    tp = int(np.sum(yt & yp))
    fp = int(np.sum((~yt) & yp))
    fn = int(np.sum(yt & (~yp)))
    tn = int(np.sum((~yt) & (~yp)))
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    acc = (tp + tn) / max(1, tp + tn + fp + fn)
    return {
        "f1": round(f1 * 100.0, 2),
        "accuracy": round(acc * 100.0, 2),
        "precision": round(prec * 100.0, 2),
        "recall": round(rec * 100.0, 2),
    }


def _roc_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    yt = (y_true.reshape(-1) > 0.5).astype(np.int32)
    yp = y_prob.reshape(-1)
    pos = int(np.sum(yt == 1))
    neg = int(np.sum(yt == 0))
    if pos == 0 or neg == 0:
        return 100.0
    order = np.argsort(yp)
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, len(yp) + 1)
    sum_pos_ranks = float(np.sum(ranks[yt == 1]))
    auc = (sum_pos_ranks - pos * (pos + 1) / 2.0) / (pos * neg)
    return round(max(0.0, min(1.0, auc)) * 100.0, 2)


_MODEL_CACHE: ServerFaultNet0x6E | None = None
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_device_label() -> str:
    if torch.cuda.is_available():
        return f"GPU ({torch.cuda.get_device_name(0)})"
    return "CPU (PyTorch)"


def train_0x6e_model(epochs: int = 36) -> dict:
    """在真实训练集上训练 ServerFaultNet0x6E，记录真实训练曲线并保存权重"""
    MODEL_0X6E_DIR.mkdir(parents=True, exist_ok=True)
    STATE_0X6E_PATH.parent.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(0x6E)
    np.random.seed(0x6E)

    X_train, y_train, _, _ = _load_split("train")
    X_test, y_test, _, _ = _load_split("test")

    model = ServerFaultNet0x6E().to(_DEVICE)
    pos_ratio = float(np.mean(y_train))
    pos_weight = torch.tensor([(1.0 - pos_ratio) / max(0.05, pos_ratio)], device=_DEVICE)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    xt = torch.from_numpy(X_train).to(_DEVICE)
    yt = torch.from_numpy(y_train).to(_DEVICE)
    xv = torch.from_numpy(X_test).to(_DEVICE)
    batch_size = 64
    n = xt.shape[0]
    training_curve: list[dict] = []

    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(n, device=_DEVICE)
        ep_loss = 0.0
        steps = 0
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            opt.zero_grad()
            logits = model(xt[idx])
            loss = loss_fn(logits, yt[idx])
            loss.backward()
            opt.step()
            ep_loss += float(loss.item())
            steps += 1
        sched.step()

        if ep == 1 or ep % 3 == 0 or ep == epochs:
            model.eval()
            with torch.no_grad():
                val_prob = torch.sigmoid(model(xv)).cpu().numpy()
            vm = _binary_metrics(y_test, val_prob, 0.5)
            training_curve.append({
                "epoch": ep,
                "loss": round(ep_loss / max(1, steps), 4),
                "val_f1": vm["f1"],
            })

    model.eval()
    torch.save({"state_dict": model.state_dict(), "window_len": WINDOW_LEN, "in_channels": IN_CHANNELS}, WEIGHT_0X6E_PATH)
    global _MODEL_CACHE
    _MODEL_CACHE = model

    eval_res = evaluate_0x6e_on_test(training_curve=training_curve)
    state = {
        "algorithm_id": ALGO_0X6E_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_0X6E_PATH.name,
        "weight_bytes": WEIGHT_0X6E_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "device": get_device_label(),
        "trainingCurve": training_curve,
        "eval": eval_res,
    }
    STATE_0X6E_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    m = eval_res["metrics"]
    print(
        f"[0x6E] ServerFaultNet0x6E 训练完成 -> {WEIGHT_0X6E_PATH.name} ({state['weight_bytes']:,} B) | "
        f"F1={m['f1']}% Acc={m['accuracy']}% Prec={m['precision']}% Rec={m['recall']}% AUC={m['auc']}%"
    )
    return state


def load_0x6e_model() -> ServerFaultNet0x6E:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if not WEIGHT_0X6E_PATH.exists():
        train_0x6e_model()
        assert _MODEL_CACHE is not None
        return _MODEL_CACHE
    ckpt = torch.load(WEIGHT_0X6E_PATH, map_location=_DEVICE, weights_only=True)
    model = ServerFaultNet0x6E().to(_DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _MODEL_CACHE = model
    return model


def load_0x6e_state() -> dict | None:
    if STATE_0X6E_PATH.exists():
        try:
            return json.loads(STATE_0X6E_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def evaluate_0x6e_on_test(
    on_progress: Callable[[int, str | None], None] | None = None,
    training_curve: list[dict] | None = None,
) -> dict:
    """在 Admin/0x6E-server-telemetry@v1.0/test（200 条 60 分钟窗口）上运行真实评测并生成多折线图可视化数据"""
    t0 = time.perf_counter()
    if on_progress:
        on_progress(15, f"[0x6E] 加载 {ALGO_0X6E_ID}@v1.0.0 ({get_device_label()})")
    model = load_0x6e_model()
    X_test, y_test, metas, all_channels = _load_split("test")
    if on_progress:
        on_progress(50, f"[0x6E] 挂载 {DATASET_0X6E_ID}@v1.0/test（{len(metas)} 条窗口 × 60 步 = {len(metas)*WINDOW_LEN:,} 时间步）")

    with torch.no_grad():
        probs = torch.sigmoid(model(torch.from_numpy(X_test).to(_DEVICE))).cpu().numpy()

    m = _binary_metrics(y_test, probs, 0.5)
    m["auc"] = _roc_auc(y_test, probs)

    # 分故障类型准确率 / F1
    by_fault: dict[str, list[int]] = {}
    for idx, meta in enumerate(metas):
        by_fault.setdefault(meta["fault_type"], []).append(idx)

    per_class = []
    for ftype, idxs in by_fault.items():
        sub_m = _binary_metrics(y_test[idxs], probs[idxs], 0.5)
        score = sub_m["accuracy"] if ftype == "正常" else sub_m["f1"]
        per_class.append({
            "label": ftype,
            "value": score,
            "accuracy": sub_m["accuracy"],
            "f1": sub_m["f1"],
            "support": len(idxs),
        })

    # 阈值灵敏度折线图（0.10 -> 0.90，共 17 个阈值点）
    threshold_curve = []
    for th_int in range(10, 95, 5):
        th = round(th_int / 100.0, 2)
        tm = _binary_metrics(y_test, probs, th)
        threshold_curve.append({
            "threshold": th,
            "f1": tm["f1"],
            "precision": tm["precision"],
            "recall": tm["recall"],
        })

    # 挑选每类故障各 1 条典型测试样本用于前端「预测概率 vs Ground Truth + 硬件指标」同步折线图展示
    picked_cases = []
    for target_type in ("显存泄漏", "CPU过载", "内存IO雪崩", "正常"):
        cand = by_fault.get(target_type, [])
        if not cand:
            continue
        # 故障类选故障步数较清晰的代表样本
        best_idx = max(cand, key=lambda i: int(np.sum(y_test[i]))) if target_type != "正常" else cand[0]
        pred_seq = [round(float(v) * 100.0, 1) for v in probs[best_idx]]
        gt_seq = [int(v) * 100 for v in y_test[best_idx]]
        cm = _binary_metrics(y_test[best_idx], probs[best_idx], 0.5)
        picked_cases.append({
            "id": metas[best_idx]["file_name"],
            "node": metas[best_idx]["node"],
            "faultType": target_type,
            "accuracy": cm["accuracy"],
            "f1": cm["f1"] if target_type != "正常" else cm["accuracy"],
            "predProb": pred_seq,
            "gtFault": gt_seq,
            "telemetry": all_channels[best_idx],
        })

    if training_curve is None:
        st = load_0x6e_state()
        training_curve = (st or {}).get("trainingCurve", [])

    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "metrics": m,
        "perClass": per_class,
        "visual0x6E": {
            "tag": "0x6E",
            "windowLen": WINDOW_LEN,
            "cases": picked_cases,
            "thresholdCurve": threshold_curve,
            "trainingCurve": training_curve,
        },
        "samples": len(metas),
        "durationSec": max(0.2, elapsed),
        "device": get_device_label(),
    }


def _diagnose_status(pred_prob: list[float], telemetry: dict[str, list[float]]) -> tuple[str, str]:
    peak_p = max(pred_prob) if pred_prob else 0.0
    fault_steps = sum(1 for p in pred_prob if p >= 50.0)
    if peak_p < 50.0 or fault_steps < 2:
        return "正常", "服务器各项硬件指标平稳，未检测到故障风险。"
    max_gmem = max(telemetry["gpu_mem_pct"])
    max_cpu = max(telemetry["cpu_pct"])
    max_disk = max(telemetry["disk_io_mbps"])
    if max_gmem >= 82.0:
        return "显存泄漏", f"检测到 GPU 显存持续攀升至 {max_gmem:.1f}%，存在 OOM 故障风险。"
    if max_disk >= 400.0:
        return "内存IO雪崩", f"检测到磁盘 IO 飙升至 {max_disk:.0f} MB/s 且内存承压，存在雪崩风险。"
    if max_cpu >= 80.0:
        return "CPU过载", f"检测到 CPU 负载冲高至 {max_cpu:.1f}%，持续 {fault_steps} 分钟触发过载告警。"
    return "运行异常", f"时序风险概率峰值达 {peak_p:.1f}%，建议核查节点负载。"


def infer_0x6e_fault(csv_bytes: bytes | None = None, filename: str = "server_0x6e_sample.csv") -> dict:
    """运行真实 PyTorch 0x6E 服务器故障检测推理，返回预测概率曲线、GT（若有）及全套多维硬件遥测"""
    t0 = time.perf_counter()
    model = load_0x6e_model()
    rows: list[dict] = []
    source_file = filename

    if csv_bytes:
        try:
            text = csv_bytes.decode("utf-8-sig", errors="ignore")
            rows = list(csv.DictReader(io.StringIO(text)))
        except Exception:
            rows = []

    if not rows:
        # 自动从测试集挑选一条含典型故障的真实遥测样本
        lbl_path = DATA_0X6E_DIR / "test" / "labels.csv"
        picked_path: Path | None = None
        if lbl_path.exists():
            with lbl_path.open("r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row["fault_type"] == "显存泄漏":
                        picked_path = DATA_0X6E_DIR / "test" / row["file_name"]
                        source_file = Path(row["file_name"]).name
                        break
        if picked_path and picked_path.exists():
            with picked_path.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

    feat, telemetry, gt_list = _encode_rows(rows)
    with torch.no_grad():
        x = torch.from_numpy(feat).unsqueeze(0).to(_DEVICE)
        prob = torch.sigmoid(model(x)).squeeze(0).cpu().numpy()

    pred_prob = [round(float(v) * 100.0, 1) for v in prob]
    gt_fault = [int(v) * 100 for v in gt_list] if gt_list is not None else None
    status, reason = _diagnose_status(pred_prob, telemetry)
    fault_steps = sum(1 for p in pred_prob if p >= 50.0)
    latency_ms = max(0.4, round((time.perf_counter() - t0) * 1000, 2))

    return {
        "device": get_device_label(),
        "latencyMs": latency_ms,
        "queuedMs": 0,
        "raw": {
            "algorithm": ALGO_0X6E_ID,
            "tag": "0x6E",
            "version": "v1.0.0",
            "task": "power-forecast",
            "source_file": source_file,
            "status": status,
            "diagnosis": reason,
            "peak_risk_pct": round(max(pred_prob), 1),
            "mean_risk_pct": round(sum(pred_prob) / len(pred_prob), 1),
            "fault_minutes": fault_steps,
            "window_len": WINDOW_LEN,
            "predProb": pred_prob,
            "gtFault": gt_fault,
            "telemetry": telemetry,
        },
    }


if __name__ == "__main__":
    train_0x6e_model()
