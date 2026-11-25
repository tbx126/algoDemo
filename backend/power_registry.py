"""
新能源短期功率预测算法（Admin/power-dlinear）—— 实现 power_forecast_std 的算法接口

  - 模型：PowerDLinearNet = 历史功率趋势-季节分解（DLinear）+ 逐小时 NWP / 历史多变量 1D-CNN + 全局门控
  - 接口：predict_batch(raw [N, 24, 9], specs) -> [N, 24] MW；只使用输入与场站规格（类型、装机容量），拿不到真值
  - 训练：只读各标准数据集的训练集（联合训练）；按时间切分验证集（最后 20 天，并剔除与验证集时间重叠的 2 个窗口），保存验证集最优的一轮
  - 权重：backend/models/power-forecast/v1.0.0_power_dlinear.pt；训练记录：backend/state/power_state.json
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

import power_forecast_std as pstd

ROOT = Path(__file__).resolve().parent
TRAIN_DATA_DIR = ROOT / "data" / "wind-solar-power-dataset"
MODEL_DIR = ROOT / "models" / "power-forecast"
STATE_PATH = ROOT / "state" / "power_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_power_dlinear.pt"
CODE_PATH = Path(__file__).resolve()

ALGO_ID = "Admin/power-dlinear"
IN_FEATURES = 14  # sin_h, cos_h, wind, irr, temp, hum, pres, nwp_w, nwp_irr, pwr, dpwr, dwind, dirr, is_solar
VAL_DAYS = 20
PURGE_DAYS = 2

CARD = {
    "name": "power-dlinear",
    "displayName": "新能源短期功率时序预测（DLinear-NWP）",
    "summary": "根据前一天 24h 实测与次日 24h NWP 气象预报，预测风电 / 光伏场站次日逐小时功率。",
    "tags": ["新能源场站", "实时推理", "NWP气象"],
    "business": "production",
    "codeFile": "power_registry.py",
    "likes": 16,
    "downloads": 42,
    "changelog": "在 Admin/wind-solar-power-dataset（仿真）训练集上真实训练 PowerDLinearNet（SmoothL1），按时间切分验证集，实现功率预测标准接口。",
    "readme": """# power-dlinear（新能源短期功率预测 · DLinear-NWP）

输入**前一天 24 小时实测**与**次日 24 小时 NWP 数值天气预报**，输出次日 24 个逐小时功率（MW）。本算法实现平台**新能源功率预测标准**接口，可以在任何符合标准的数据集上评测或推理。

## 使用方法

上传 24 行标准 CSV（第 h 行 = 前一天 h 时实测 + 次日 h 时 NWP 预报），并选择场站类型（风电 / 光伏）与装机容量：

```
hour,wind_speed_ms,irradiance_wm2,temp_c,humidity_pct,pressure_hpa,nwp_wind_ms,nwp_irr_wm2,power_mw
```

## 模型结构

- **DLinear 分支**：前一天功率做滑动平均分解，趋势与季节两部分各用一个线性层外推次日曲线
- **NWP 分支**：逐小时 NWP 预报与历史多变量（含一阶差分、场站类型）经 1D-CNN 输出逐小时修正
- **全局门控**：池化全天特征，学习场站整体出力水平
- 输出按装机容量归一化到 0–1 后再乘回容量

## 训练方式

- 只使用训练集；验证集取训练时段最后 20 天，并剔除与其时间重叠的窗口，避免相邻日数据互相泄露
- 保存验证集损失最低的一轮
""",
}


# ------------------------------------------------------------------ 模型
class MovingAvg(nn.Module):
    def __init__(self, kernel_size: int = 5):
        super().__init__()
        self.kernel_size = kernel_size
        self.avg = nn.AvgPool1d(kernel_size=kernel_size, stride=1, padding=0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        pad = (self.kernel_size - 1) // 2
        front = x[:, :1, :].repeat(1, pad, 1)
        end = x[:, -1:, :].repeat(1, pad, 1)
        return self.avg(torch.cat([front, x, end], dim=1).permute(0, 2, 1)).permute(0, 2, 1)


class PowerDLinearNet(nn.Module):
    """趋势-季节分解 + 逐小时 NWP 1D-CNN + 全局门控（输入的 24 行在发布预测时都已可得，不涉及未来实测）"""

    def __init__(self, seq_len: int = pstd.LOOKBACK, pred_len: int = pstd.HORIZON, in_features: int = IN_FEATURES):
        super().__init__()
        self.decomp = MovingAvg(kernel_size=5)
        self.linear_trend = nn.Linear(seq_len, pred_len)
        self.linear_seasonal = nn.Linear(seq_len, pred_len)
        self.meteo_net = nn.Sequential(
            nn.Conv1d(in_features, 48, kernel_size=3, padding=1),
            nn.GroupNorm(8, 48),
            nn.GELU(),
            nn.Conv1d(48, 48, kernel_size=3, padding=1),
            nn.GroupNorm(8, 48),
            nn.GELU(),
            nn.Conv1d(48, 1, kernel_size=1),
        )
        self.global_head = nn.Sequential(nn.AdaptiveAvgPool1d(4), nn.Flatten(), nn.Linear(in_features * 4, 48), nn.GELU(), nn.Linear(48, pred_len))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        pwr = x[:, :, 9:10]
        trend = self.decomp(pwr).squeeze(-1)
        base = self.linear_trend(trend) + self.linear_seasonal(pwr.squeeze(-1) - trend)
        xt = x.permute(0, 2, 1)
        # 训练时不截断（clamp 会在输出越界时把梯度置零，导致模型卡死）；推理时再截断到 [0, 1]
        return base * 0.25 + self.meteo_net(xt).squeeze(1) + 0.2 * self.global_head(xt)


def _encode(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """[N, 24, 9] 原始标准输入 + 场站规格 -> [N, 24, 14]；功率按各场站装机容量归一化"""
    raw = np.asarray(raw, dtype=np.float32)
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
    solar = np.array([1.0 if s["kind"] == "solar" else 0.0 for s in specs], dtype=np.float32)[:, None]
    hour = raw[:, :, 0]
    wind, irr = raw[:, :, 1] / 15.0, raw[:, :, 2] / 1000.0
    pwr = raw[:, :, 8] / cap
    feats = [
        np.sin(2 * math.pi * hour / 24), np.cos(2 * math.pi * hour / 24), wind, irr,
        raw[:, :, 3] / 40.0, raw[:, :, 4] / 100.0, (raw[:, :, 5] - 1000.0) / 30.0,
        raw[:, :, 6] / 15.0, raw[:, :, 7] / 1000.0, pwr,
        np.diff(pwr, axis=1, prepend=pwr[:, :1]), np.diff(wind, axis=1, prepend=wind[:, :1]), np.diff(irr, axis=1, prepend=irr[:, :1]),
        np.broadcast_to(solar, hour.shape),
    ]
    return np.stack(feats, axis=-1).astype(np.float32)


_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
_MODEL_CACHE: PowerDLinearNet | None = None


def device_label() -> str:
    return f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU (PyTorch)"


def load_state() -> dict | None:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ------------------------------------------------------------------ 训练
def train(epochs: int = 80) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(42)
    np.random.seed(42)

    # 联合使用全部标准数据集的训练集（与其他功率预测算法相同，保证对比公平）；测试集不参与
    Xs, Ys, masks, tr_parts, val_parts, offset = [], [], [], [], [], 0
    train_dirs = [d for d in sorted(TRAIN_DATA_DIR.parent.iterdir()) if d.is_dir() and pstd.read_meta(d)]
    for d in train_dirs:
        raw, y_mw, metas, specs = pstd.load_split(d, "train")
        cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
        Xs.append(_encode(raw, specs))
        Ys.append((y_mw / cap).astype(np.float32))
        masks.append(pstd.eval_mask(raw, specs))
        # 每个数据集各自按时间切分：最后 VAL_DAYS 天为验证集，再往前 PURGE_DAYS 天的窗口剔除（与验证窗口有时间重叠）
        t0 = np.array([int(m["t0"]) for m in metas])
        val_start = t0.max() - (VAL_DAYS - 1) * 24
        val_parts.append(np.where(t0 >= val_start)[0] + offset)
        tr_parts.append(np.where(t0 < val_start - PURGE_DAYS * 24)[0] + offset)
        offset += len(raw)
    X, Y, mask = np.concatenate(Xs), np.concatenate(Ys), np.concatenate(masks)
    tr_idx, val_idx = np.concatenate(tr_parts), np.concatenate(val_parts)

    xt, yt = torch.from_numpy(X[tr_idx]).to(_DEVICE), torch.from_numpy(Y[tr_idx]).to(_DEVICE)
    xv, yv = torch.from_numpy(X[val_idx]).to(_DEVICE), torch.from_numpy(Y[val_idx]).to(_DEVICE)
    mv = torch.from_numpy(mask[val_idx]).to(_DEVICE)

    model = PowerDLinearNet().to(_DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = nn.SmoothL1Loss(beta=0.04)

    history: list[dict] = []
    best: dict | None = None
    t_start = time.perf_counter()
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
            vp = model(xv).clamp(0.0, 1.0)
            vloss = float(loss_fn(vp, yv))
            vacc = max(0.0, (1.0 - float(torch.sqrt(torch.mean(((vp - yv)[mv]) ** 2)))) * 100.0)
        history.append({"epoch": ep, "train_loss": round(total / nb, 5), "val_loss": round(vloss, 5), "val_acc": round(vacc, 2)})
        if best is None or vloss < best["loss"]:
            best = {"epoch": ep, "loss": vloss, "acc": vacc, "state": {k: v.detach().clone() for k, v in model.state_dict().items()}}

    assert best is not None
    model.load_state_dict(best["state"])
    model.eval()
    torch.save({"state_dict": model.state_dict(), "in_features": IN_FEATURES}, WEIGHT_PATH)
    global _MODEL_CACHE
    _MODEL_CACHE = model
    state = {
        "algorithm_id": ALGO_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_PATH.name,
        "weight_bytes": WEIGHT_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "train_seconds": round(time.perf_counter() - t_start, 1),
        "device": device_label(),
        "epochs": epochs,
        "best_epoch": best["epoch"],
        "train_datasets": [d.name for d in train_dirs],
        "split": {"train_windows": int(len(tr_idx)), "val_windows": int(len(val_idx)), "val_days": VAL_DAYS, "purge_days": PURGE_DAYS},
        "history": history,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[power-dlinear] 训练完成：训练 {len(tr_idx)} / 验证 {len(val_idx)} 窗口，保存第 {best['epoch']} 轮（验证准确率 {best['acc']:.2f}%），用时 {state['train_seconds']}s")
    return state


def _model() -> PowerDLinearNet:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        ckpt = torch.load(WEIGHT_PATH, map_location=_DEVICE, weights_only=True) if WEIGHT_PATH.exists() else None
        if not ckpt or ckpt.get("in_features") != IN_FEATURES:
            train()
        else:
            m = PowerDLinearNet().to(_DEVICE)
            m.load_state_dict(ckpt["state_dict"])
            m.eval()
            _MODEL_CACHE = m
    assert _MODEL_CACHE is not None
    return _MODEL_CACHE


# ------------------------------------------------------------------ 标准接口
def predict_batch(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """功率预测标准接口：raw [N, 24, 9]（pstd.CHANNELS 顺序、原始单位），specs 每个窗口的场站类型与装机容量 -> [N, 24] MW"""
    model = _model()
    X = _encode(raw, specs)
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
    outs = []
    with torch.no_grad():
        for i in range(0, len(X), 256):
            outs.append(model(torch.from_numpy(X[i : i + 256]).to(_DEVICE)).clamp(0.0, 1.0).cpu().numpy())
    return np.concatenate(outs) * cap


if __name__ == "__main__":
    train()
