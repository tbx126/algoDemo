"""
服务器运行故障检测算法（Admin/server-fault-tcn）—— 实现「服务器故障检测标准」（server_fault_std）的算法接口

  - 模型：ServerFaultTCN = 因果膨胀 TCN（只看过去，不偷看未来）+ 单向 GRU + 双头输出
      * 状态头：逐分钟输出标准状态码 0~5（正常 / CPU过载 / 内存泄漏 / GPU过热 / 磁盘IO饱和 / 网络异常）
      * 预警头：逐分钟「未来 10 分钟内将发生故障」概率
  - 标准输出：fault_prob = 1 − P(正常)，state = argmax 状态码，warn_prob = 预警概率
  - 训练数据：Admin/server-telemetry-sim 训练集（90% 训练 / 10% 验证）
  - 权重：backend/models/server-fault-tcn/v1.0.0_server_fault_tcn.pt；训练记录：backend/state/server_fault_tcn_state.json
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
TRAIN_DATA_DIR = ROOT / "data" / "server-telemetry-sim"
MODEL_DIR = ROOT / "models" / "server-fault-tcn"
STATE_PATH = ROOT / "state" / "server_fault_tcn_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_server_fault_tcn.pt"

ALGO_ID = "Admin/server-fault-tcn"
# 模型可输出的标准状态码（0 ~ 5）
OUTPUT_STATES = std.STATES[:6]
N_OUT = len(OUTPUT_STATES)
# 输入特征（每路通道 3 个，共 24 维）：
#   1. 按机器容量换算的相对值 std.to_relative（磁盘 / 网络除以该机器上限，不同硬件可比）
#   2. 一阶差分（变化速度）
#   3. 偏离自身近期均值的程度（因果滑动均值，只用过去数据），学的是「和这台机器平时比」而不是绝对水平
IN_FEATURES = len(std.CHANNELS) * 3
BASELINE_SPAN = 15  # 近期均值的窗口长度（分钟）
SATURATION_FROM = 0.6  # 磁盘 / 网络利用率超过该比例才开始计入「接近上限程度」
_THROUGHPUT = [std.CHANNELS.index("disk_io_mbps"), std.CHANNELS.index("net_mbps")]

CARD = {
    "name": "server-fault-tcn",
    "displayName": "服务器运行故障检测（因果 TCN-GRU）",
    "summary": "根据 CPU、GPU、内存、磁盘、网络等运行遥测，逐分钟判断服务器运行状态（6 类），并给出未来 10 分钟故障预警。",
    "tags": ["服务器运维", "实时推理"],
    "business": "other",
    "codeFile": "server_fault_tcn.py",
    "gpuMem": 0.2,
    "likes": 4,
    "downloads": 6,
    "changelog": "在 Admin/server-telemetry-sim（仿真）训练集上真实训练 ServerFaultTCN（加权交叉熵 + 预警 BCE），实现服务器故障检测标准接口。",
    "readme": """# server-fault-tcn（服务器运行故障检测 · 因果 TCN-GRU）

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

- **输入编码**：8 路遥测先按机器容量换算成相对值（磁盘、网络除以该机器上限），再拼接一阶差分与「偏离自身近期 15 分钟均值」两组特征，共 24 维，使模型学的是相对变化而不是某种硬件上的绝对读数
- **模型选择**：训练时保存验证集 Macro-F1 最高的一轮（相同时取验证损失更低的），而不是最后一轮
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
        # 逐分钟 LayerNorm（只在通道维上归一化）。不能用 GroupNorm / BatchNorm 按时间维统计：
        # 那样每一分钟的输出都会受到同一窗口里未来分钟的影响，等于偷看未来
        self.norm = nn.LayerNorm(ch)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        y = F.gelu(self.conv1(F.pad(x, (self.pad, 0))))
        y = self.conv2(F.pad(y, (self.pad, 0)))
        return F.gelu(self.norm((x + y).transpose(1, 2)).transpose(1, 2))


class ServerFaultTCN(nn.Module):
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


def _encode(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """[N, 60, 8] 原始标准遥测 + 机器规格 -> [N, 60, 24]"""
    rel = std.to_relative(raw, specs)
    diff = np.diff(rel, axis=1, prepend=rel[:, :1])
    csum = np.cumsum(rel, axis=1)
    lagged = np.concatenate([np.zeros_like(csum[:, :1]), csum[:, :-BASELINE_SPAN]], axis=1) if rel.shape[1] > BASELINE_SPAN else np.zeros_like(csum[:, :1])
    n = np.minimum(np.arange(1, rel.shape[1] + 1), BASELINE_SPAN).reshape(1, -1, 1).astype(np.float32)
    head = csum[:, :BASELINE_SPAN]
    tail = csum[:, BASELINE_SPAN:] - lagged[:, 1 : rel.shape[1] - BASELINE_SPAN + 1] if rel.shape[1] > BASELINE_SPAN else csum[:, :0]
    run_mean = np.concatenate([head, tail], axis=1) / n
    level = rel.copy()
    dev = (rel - run_mean) * 2.0
    # 磁盘 / 网络吞吐：不同机器的正常利用率水平差别很大（高配机器带宽大、利用率自然低），
    # 不直接使用水平值，改用「接近上限程度」（判断打满）与「相对自身近期均值的对数比」（判断骤降 / 暴涨），与平时水平高低无关
    for c in _THROUGHPUT:
        level[..., c] = np.clip((rel[..., c] - SATURATION_FROM) / (1.0 - SATURATION_FROM), 0.0, 1.5)
        dev[..., c] = np.clip(np.log((rel[..., c] + 0.01) / (run_mean[..., c] + 0.01)), -3.0, 3.0) / 3.0
    return np.concatenate([level, diff * 4.0, dev], axis=2).astype(np.float32)


_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_CACHE: ServerFaultTCN | None = None


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

    RAW, Y, W, metas = std.load_split(TRAIN_DATA_DIR, "train")
    X = _encode(RAW, std.load_specs(TRAIN_DATA_DIR, metas))
    idx = np.random.permutation(len(X))
    n_val = len(X) // 10
    val_idx, tr_idx = idx[:n_val], idx[n_val:]
    xt, yt, wt = (torch.from_numpy(a[tr_idx]).to(_DEVICE) for a in (X, Y, W))
    xv, yv, wv = (torch.from_numpy(a[val_idx]).to(_DEVICE) for a in (X, Y, W))

    counts = np.bincount(Y[tr_idx].ravel(), minlength=N_OUT).astype(np.float32)
    cls_w = torch.from_numpy((counts.sum() / (N_OUT * np.maximum(counts, 1))) ** 0.5).to(_DEVICE)
    pos_w = torch.tensor(float((W[tr_idx] == 0).sum() / max(1, (W[tr_idx] == 1).sum())) ** 0.5, device=_DEVICE)

    model = ServerFaultTCN().to(_DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=epochs * ((len(tr_idx) + 63) // 64))

    def loss_of(xb, yb, wb):
        logits, wlog = model(xb)
        ce = F.cross_entropy(logits.reshape(-1, N_OUT), yb.reshape(-1), weight=cls_w)
        return ce + 0.5 * F.binary_cross_entropy_with_logits(wlog, wb, pos_weight=pos_w)

    history = []
    best: dict | None = None
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
        vf1 = _macro_f1(Y[val_idx].ravel(), vpred.ravel())
        history.append({"epoch": ep, "train_loss": round(total / nb, 4), "val_loss": round(vloss, 4), "val_f1": round(vf1 * 100, 2)})
        # 保存验证集上最好的一轮：先比验证 Macro-F1，相同时取验证损失更低的
        if best is None or (vf1, -vloss) > (best["f1"], -best["loss"]):
            best = {"epoch": ep, "f1": vf1, "loss": vloss, "state": {k: v.detach().clone() for k, v in model.state_dict().items()}}

    assert best is not None
    model.load_state_dict(best["state"])
    model.eval()

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
        "best_epoch": best["epoch"],
        "history": history,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[server-fault-tcn] 训练完成 -> {WEIGHT_PATH.name}，用时 {state['train_seconds']}s，保存第 {best['epoch']} 轮（验证 Macro-F1 {best['f1'] * 100:.2f}%，验证损失 {best['loss']:.4f}）")
    return state


def _model() -> ServerFaultTCN:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not WEIGHT_PATH.exists():
            train()
        else:
            ckpt = torch.load(WEIGHT_PATH, map_location=_DEVICE, weights_only=True)
            m = ServerFaultTCN().to(_DEVICE)
            m.load_state_dict(ckpt["state_dict"])
            m.eval()
            _MODEL_CACHE = m
    assert _MODEL_CACHE is not None
    return _MODEL_CACHE


# ------------------------------------------------------------------ 标准接口
def predict_batch(raw: np.ndarray, specs: list[dict]) -> dict:
    """服务器故障检测标准接口：raw [N, 60, 8]（std.CHANNELS 顺序、原始单位）"""
    model = _model()
    X = _encode(np.asarray(raw, dtype=np.float32), specs)
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
