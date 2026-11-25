"""
[0x07] 服务器运行故障检测算法（Admin/0x07）—— 实现「服务器故障检测标准」（server_fault_std）的算法接口

  - 模型：Fault0x07Net = 因果膨胀 TCN（只看过去，不偷看未来）+ 单向 GRU + 双头输出
      * 状态头：逐分钟输出标准状态码 0~5（正常 / CPU过载 / 内存泄漏 / GPU过热 / 磁盘IO饱和 / 网络异常）
      * 预警头：逐分钟「未来 10 分钟内将发生故障」概率
  - 标准输出：fault_prob = 1 − P(正常)，state = argmax 状态码，warn_prob = 预警概率
  - 训练数据：Admin/0x07-server-telemetry-dataset 训练集（90% 训练 / 10% 验证）
  - 权重：backend/models/0x07/v1.0.0_fault0x07.pt；训练记录：backend/state/fault0x07_state.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

import server_fault_std as std

ROOT = Path(__file__).resolve().parent
TRAIN_DATA_DIR = ROOT / "data" / "0x07-server-telemetry-dataset"
MODEL_DIR = ROOT / "models" / "0x07"
STATE_PATH = ROOT / "state" / "fault0x07_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_fault0x07.pt"

ALGO_ID = "Admin/0x07"
# 模型可输出的标准状态码（0 ~ 5）
OUTPUT_STATES = std.STATES[:6]
N_OUT = len(OUTPUT_STATES)
SCALES = np.asarray([100, 100, 100, 100, 100, 100, 500, 1000], dtype=np.float32)  # 与 std.CHANNELS 顺序一致
IN_FEATURES = len(std.CHANNELS) * 2  # 归一化值 + 一阶差分

CARD = {
    "name": "0x07",
    "displayName": "[0x07] 服务器运行故障检测（因果 TCN-GRU）",
    "summary": "[0x07] 根据 CPU、GPU、内存、磁盘、网络等运行遥测，逐分钟判断服务器运行状态（6 类），并给出未来 10 分钟故障预警。",
    "tags": ["0x07", "服务器运维", "实时推理"],
    "business": "other",
    "codeFile": "fault0x07_registry.py",
    "imageDigest": "sha256:0x07fa017de7ec70000000000000000000000000000000000000000000000000107",
    "weightsHash": "sha256:0x07fault0weights1",
    "gpuMem": 0.2,
    "likes": 4,
    "downloads": 6,
    "changelog": "[0x07] 在 Admin/0x07-server-telemetry-dataset 训练集上真实训练 Fault0x07Net（加权交叉熵 + 预警 BCE），实现服务器故障检测标准接口。",
    "readme": """# 0x07（服务器运行故障检测 · 因果 TCN-GRU）

输入服务器最近 **60 分钟**的 8 路标准遥测，逐分钟输出：

1. **当前运行状态**（标准状态码 0–5）：正常 / CPU过载 / 内存泄漏 / GPU过热 / 磁盘IO饱和 / 网络异常
2. **故障概率**：1 − P(正常)
3. **故障预警概率**：未来 10 分钟内发生故障的概率

本算法实现平台**服务器故障检测标准**的算法接口，可以直接在任何符合标准的数据集上评测或推理。

## 使用方法

上传一个 60 行的标准 CSV（多于 60 行时取最后 60 行），表头为：

```
minute,cpu_pct,cpu_temp_c,mem_pct,gpu_pct,gpu_temp_c,gpu_mem_pct,disk_io_mbps,net_mbps
```

## 模型结构

- **输入编码**：8 路遥测按量程归一化，并拼接一阶差分，共 16 维
- **因果膨胀 TCN**：4 个残差块，膨胀系数 1 / 2 / 4 / 8，只看当前及过去的数据，可以直接用于在线监控
- **单向 GRU**：汇总长程上下文
- **双输出头**：6 类状态 softmax 与预警 sigmoid
""",
}


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
        self.state_head = nn.Linear(hidden, N_OUT)
        self.warn_head = nn.Linear(hidden, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.tcn(self.inp(x.permute(0, 2, 1))).permute(0, 2, 1)
        h, _ = self.gru(h)
        return self.state_head(h), self.warn_head(h).squeeze(-1)


def _encode(raw: np.ndarray) -> np.ndarray:
    """[N, 60, 8] 原始标准遥测 -> [N, 60, 16]"""
    norm = raw / SCALES
    diff = np.diff(norm, axis=1, prepend=norm[:, :1])
    return np.concatenate([norm, diff * 4.0], axis=2).astype(np.float32)


_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_CACHE: Fault0x07Net | None = None


def device_label() -> str:
    return f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU (PyTorch)"


def load_state() -> dict | None:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _macro_f1(y: np.ndarray, p: np.ndarray) -> float:
    f1s = []
    for c in range(N_OUT):
        tp = int(np.sum((p == c) & (y == c)))
        fp = int(np.sum((p == c) & (y != c)))
        fn = int(np.sum((p != c) & (y == c)))
        f1s.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)
    return float(np.mean(f1s))


# ------------------------------------------------------------------ 训练
def train(epochs: int = 60) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(7)
    np.random.seed(7)

    RAW, Y, W, _ = std.load_split(TRAIN_DATA_DIR, "train")
    X = _encode(RAW)
    idx = np.random.permutation(len(X))
    n_val = len(X) // 10
    val_idx, tr_idx = idx[:n_val], idx[n_val:]
    xt, yt, wt = (torch.from_numpy(a[tr_idx]).to(_DEVICE) for a in (X, Y, W))
    xv, yv, wv = (torch.from_numpy(a[val_idx]).to(_DEVICE) for a in (X, Y, W))

    counts = np.bincount(Y[tr_idx].ravel(), minlength=N_OUT).astype(np.float32)
    cls_w = torch.from_numpy((counts.sum() / (N_OUT * np.maximum(counts, 1))) ** 0.5).to(_DEVICE)
    pos_w = torch.tensor(float((W[tr_idx] == 0).sum() / max(1, (W[tr_idx] == 1).sum())) ** 0.5, device=_DEVICE)

    model = Fault0x07Net().to(_DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=epochs * ((len(tr_idx) + 63) // 64))

    def loss_of(xb, yb, wb):
        logits, wlog = model(xb)
        ce = F.cross_entropy(logits.reshape(-1, N_OUT), yb.reshape(-1), weight=cls_w)
        return ce + 0.5 * F.binary_cross_entropy_with_logits(wlog, wb, pos_weight=pos_w)

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
        history.append({"epoch": ep, "train_loss": round(total / nb, 4), "val_loss": round(vloss, 4), "val_f1": round(_macro_f1(Y[val_idx].ravel(), vpred.ravel()) * 100, 2)})

    torch.save({"state_dict": model.state_dict(), "channels": std.CHANNELS, "states": OUTPUT_STATES}, WEIGHT_PATH)
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
    print(f"[0x07] 训练完成 -> {WEIGHT_PATH.name}，用时 {state['train_seconds']}s，最终验证 Macro-F1 {history[-1]['val_f1']}%")
    return state


def _model() -> Fault0x07Net:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not WEIGHT_PATH.exists():
            train()
        else:
            ckpt = torch.load(WEIGHT_PATH, map_location=_DEVICE, weights_only=True)
            m = Fault0x07Net().to(_DEVICE)
            m.load_state_dict(ckpt["state_dict"])
            m.eval()
            _MODEL_CACHE = m
    assert _MODEL_CACHE is not None
    return _MODEL_CACHE


# ------------------------------------------------------------------ 标准接口
def predict_batch(raw: np.ndarray) -> dict:
    """服务器故障检测标准接口：raw [N, 60, 8]（std.CHANNELS 顺序、原始单位）"""
    model = _model()
    X = _encode(np.asarray(raw, dtype=np.float32))
    probs, warns = [], []
    with torch.no_grad():
        for i in range(0, len(X), 256):
            logits, wlog = model(torch.from_numpy(X[i : i + 256]).to(_DEVICE))
            probs.append(torch.softmax(logits, -1).cpu().numpy())
            warns.append(torch.sigmoid(wlog).cpu().numpy())
    P = np.concatenate(probs)
    return {"fault_prob": 1.0 - P[..., 0], "state": P.argmax(-1), "warn_prob": np.concatenate(warns)}


if __name__ == "__main__":
    train()
