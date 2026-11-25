"""
服务器运行故障时序检测算法（Admin/0x6E）—— 实现「服务器故障检测标准」（server_fault_std）的算法接口

  - 模型结构：ServerFaultNet0x6E（多尺度 1D-CNN + 双向 GRU + 逐时间步故障风险预测头）
  - 输入：标准 8 通道遥测 [N, 60, 8]（std.CHANNELS 顺序、原始单位），按量程归一化
  - 标准输出：
      fault_prob  逐分钟故障概率（模型输出）
      state       逐分钟状态码：概率 >= 0.5 的分钟按窗口级根因规则归入 CPU过载 / 显存泄漏 / 内存IO雪崩 / 其他异常
  - 训练数据：Admin/0x6E-server-telemetry 训练集（90% 训练 / 10% 验证）
  - 权重：backend/models/0x6e/v1.0.0_0x6e_faultnet.pt；训练记录：backend/state/0x6e_state.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

import server_fault_std as std

ROOT = Path(__file__).resolve().parent
TRAIN_DATA_DIR = ROOT / "data" / "0x6e-server-telemetry"
MODEL_DIR = ROOT / "models" / "0x6e"
STATE_PATH = ROOT / "state" / "0x6e_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_0x6e_faultnet.pt"

ALGO_ID = "Admin/0x6E"
IN_CHANNELS = len(std.CHANNELS)
SCALES = np.asarray([100, 100, 100, 100, 100, 100, 1000, 1000], dtype=np.float32)  # 与 std.CHANNELS 顺序一致
_CH = {c: i for i, c in enumerate(std.CHANNELS)}

CARD = {
    "name": "0x6E",
    "displayName": "服务器运行故障时序检测（0x6E）",
    "summary": "基于多尺度 1D-CNN 与 BiGRU 的服务器多维时序故障检测算法（0x6E），输出逐分钟故障风险曲线，并按硬件遥测归因故障类型。",
    "tags": ["0x6E", "时序故障检测", "服务器监控"],
    "business": "inspection",
    "codeFile": "fault_0x6e_registry.py",
    "imageDigest": "sha256:0x6efaultnet01000000000000000000000000000000000000000000000006e1",
    "weightsHash": "sha256:0x6efaultnetw100",
    "gpuMem": 0.1,
    "likes": 18,
    "downloads": 42,
    "changelog": "0x6E：基于 SMD + GPU 集群遥测训练集真实训练 ServerFaultNet0x6E（BCEWithLogitsLoss），输入改为服务器故障检测标准 8 通道。",
    "readme": """# 0x6E（服务器运行故障时序检测 · ServerFaultNet-0x6E）

面向服务器集群的多维时序运行状态与故障检测算法（PyTorch 真实训练权重）。本算法实现平台**服务器故障检测标准**的算法接口，可以直接在任何符合标准的数据集上评测或推理。

## 模型架构（0x6E）
1. **多尺度时序卷积**：并行 `Conv1d(k=3)` 捕捉瞬时毛刺（CPU 尖峰 / IO 抖动）与 `Conv1d(k=7)` 捕捉中长期爬坡（显存泄漏 / 内存缓慢耗尽）。
2. **双向 GRU 上下文聚合**：在 60 分钟窗口内建模跨通道耦合，逐分钟输出连续故障风险概率（0–100%）。
3. **根因归类**：风险 ≥ 50% 的分钟按窗口内硬件读数归入 显存泄漏（显存 ≥ 82%）/ 内存IO雪崩（磁盘 ≥ 400 MB/s）/ CPU过载（CPU ≥ 80%）/ 其他异常。

## 输入

标准 8 通道 CSV：`minute,cpu_pct,cpu_temp_c,mem_pct,gpu_pct,gpu_temp_c,gpu_mem_pct,disk_io_mbps,net_mbps`
""",
}


class ServerFaultNet0x6E(nn.Module):
    """多尺度时序卷积 + 双向 GRU 服务器故障检测网络（0x6E）"""

    def __init__(self, in_ch: int = IN_CHANNELS):
        super().__init__()
        self.conv_short = nn.Sequential(nn.Conv1d(in_ch, 24, kernel_size=3, padding=1), nn.BatchNorm1d(24), nn.GELU())
        self.conv_long = nn.Sequential(nn.Conv1d(in_ch, 24, kernel_size=7, padding=3), nn.BatchNorm1d(24), nn.GELU())
        self.gru = nn.GRU(input_size=48, hidden_size=32, num_layers=1, batch_first=True, bidirectional=True)
        self.head = nn.Sequential(nn.Linear(64, 32), nn.GELU(), nn.Linear(32, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        xt = x.permute(0, 2, 1)
        feat = torch.cat([self.conv_short(xt), self.conv_long(xt)], dim=1).permute(0, 2, 1)
        out, _ = self.gru(feat)
        return self.head(out).squeeze(-1)


_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_CACHE: ServerFaultNet0x6E | None = None


def device_label() -> str:
    return f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU (PyTorch)"


def load_state() -> dict | None:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _encode(raw: np.ndarray) -> np.ndarray:
    return (np.asarray(raw, dtype=np.float32) / SCALES).astype(np.float32)


def _f1(y: np.ndarray, p: np.ndarray) -> float:
    tp = int(np.sum(p & y))
    fp = int(np.sum(p & ~y))
    fn = int(np.sum(~p & y))
    return 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0


def train(epochs: int = 36) -> dict:
    """在训练集上训练（10% 留作验证，测试集不参与训练过程）"""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0x6E)
    np.random.seed(0x6E)

    RAW, Y, _, _ = std.load_split(TRAIN_DATA_DIR, "train")
    X = _encode(RAW)
    T = (Y > 0).astype(np.float32)
    idx = np.random.permutation(len(X))
    n_val = len(X) // 10
    val_idx, tr_idx = idx[:n_val], idx[n_val:]
    xt, yt = torch.from_numpy(X[tr_idx]).to(_DEVICE), torch.from_numpy(T[tr_idx]).to(_DEVICE)
    xv, yv = torch.from_numpy(X[val_idx]).to(_DEVICE), torch.from_numpy(T[val_idx]).to(_DEVICE)

    model = ServerFaultNet0x6E().to(_DEVICE)
    pos_ratio = float(np.mean(T[tr_idx]))
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([(1.0 - pos_ratio) / max(0.05, pos_ratio)], device=_DEVICE))
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    history = []
    t0 = time.perf_counter()
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(xt), device=_DEVICE)
        total, nb = 0.0, 0
        for i in range(0, len(xt), 64):
            b = perm[i : i + 64]
            opt.zero_grad()
            loss = loss_fn(model(xt[b]), yt[b])
            loss.backward()
            opt.step()
            total += float(loss)
            nb += 1
        sched.step()
        model.eval()
        with torch.no_grad():
            vlog = model(xv)
            vloss = float(loss_fn(vlog, yv))
            vpred = (torch.sigmoid(vlog) >= 0.5).cpu().numpy()
        history.append({"epoch": ep, "train_loss": round(total / nb, 4), "val_loss": round(vloss, 4), "val_f1": round(_f1(T[val_idx] > 0.5, vpred) * 100, 2)})

    torch.save({"state_dict": model.state_dict(), "channels": std.CHANNELS}, WEIGHT_PATH)
    global _MODEL_CACHE
    _MODEL_CACHE = model
    state = {
        "algorithm_id": ALGO_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_PATH.name,
        "weight_bytes": WEIGHT_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "train_seconds": round(time.perf_counter() - t0, 1),
        "device": device_label(),
        "epochs": epochs,
        "history": history,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[0x6E] 训练完成 -> {WEIGHT_PATH.name}，用时 {state['train_seconds']}s，最终验证 F1 {history[-1]['val_f1']}%")
    return state


def _model() -> ServerFaultNet0x6E:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not WEIGHT_PATH.exists():
            train()
        else:
            ckpt = torch.load(WEIGHT_PATH, map_location=_DEVICE, weights_only=True)
            m = ServerFaultNet0x6E().to(_DEVICE)
            m.load_state_dict(ckpt["state_dict"])
            m.eval()
            _MODEL_CACHE = m
    assert _MODEL_CACHE is not None
    return _MODEL_CACHE


def _root_cause(raw_window: np.ndarray) -> int:
    """窗口级根因规则 -> 标准状态码"""
    if raw_window[:, _CH["gpu_mem_pct"]].max() >= 82.0:
        return std.STATE_CODE["显存泄漏"]
    if raw_window[:, _CH["disk_io_mbps"]].max() >= 400.0:
        return std.STATE_CODE["内存IO雪崩"]
    if raw_window[:, _CH["cpu_pct"]].max() >= 80.0:
        return std.STATE_CODE["CPU过载"]
    return std.STATE_CODE["其他异常"]


def predict_batch(raw: np.ndarray) -> dict:
    """服务器故障检测标准接口：raw [N, 60, 8]（std.CHANNELS 顺序、原始单位）"""
    raw = np.asarray(raw, dtype=np.float32)
    model = _model()
    X = _encode(raw)
    probs = []
    with torch.no_grad():
        for i in range(0, len(X), 256):
            probs.append(torch.sigmoid(model(torch.from_numpy(X[i : i + 256]).to(_DEVICE))).cpu().numpy())
    P = np.concatenate(probs)
    S = np.zeros(P.shape, dtype=np.int64)
    for i in range(len(P)):
        on = P[i] >= 0.5
        if on.any():
            S[i, on] = _root_cause(raw[i])
    return {"fault_prob": P, "state": S}


def diagnose(raw_window: np.ndarray, pred: dict) -> str:
    """推理时的文字诊断"""
    p = np.asarray(pred["fault_prob"]) * 100
    n = int(np.sum(p >= 50))
    if p.max() < 50 or n < 2:
        return "服务器各项硬件指标平稳，未检测到故障风险。"
    code = _root_cause(raw_window)
    if code == std.STATE_CODE["显存泄漏"]:
        return f"检测到 GPU 显存持续攀升至 {raw_window[:, _CH['gpu_mem_pct']].max():.1f}%，存在 OOM 故障风险。"
    if code == std.STATE_CODE["内存IO雪崩"]:
        return f"检测到磁盘 IO 飙升至 {raw_window[:, _CH['disk_io_mbps']].max():.0f} MB/s 且内存承压，存在雪崩风险。"
    if code == std.STATE_CODE["CPU过载"]:
        return f"检测到 CPU 负载冲高至 {raw_window[:, _CH['cpu_pct']].max():.1f}%，持续 {n} 分钟触发过载告警。"
    return f"时序风险概率峰值达 {p.max():.1f}%，建议核查节点负载。"


if __name__ == "__main__":
    train()
