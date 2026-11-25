"""
新能源场站短期功率时序预测算法注册与推理/评测模块（Admin/power-dlinear）—— 对标 0x07 标准：
  - 模型结构：PowerDLinearNet（趋势-季节分解 + 历史一阶差分 + 未来 24h NWP 气象 1D-CNN 融合）
  - 严格 90% 训练 / 10% 验证切分，测试集零参与训练，保存最优验证集权重
  - 统一通过 power_forecast_std.evaluate_predictions 输出 6 项工业考核指标与 5 维折线图可视化数据
"""
from __future__ import annotations

import csv
import io
import json
import math
import time
from pathlib import Path
from typing import Callable

import numpy as np
import torch
import torch.nn as nn

import power_forecast_std as pstd

ROOT = Path(__file__).resolve().parent
POWER_DATA_DIR = ROOT / "data" / "wind-solar-power-dataset"
POWER_MODEL_DIR = ROOT / "models" / "power-forecast"
POWER_STATE_PATH = ROOT / "state" / "power_state.json"

POWER_ALGO_ID = "Admin/power-dlinear"
POWER_DATASET_ID = "Admin/wind-solar-power-dataset"
POWER_BENCH_ID = "power-forecast-bench"
WEIGHT_PATH = POWER_MODEL_DIR / "v1.0.0_power_dlinear.pt"

IN_FEATURES = 13  # sin_h, cos_h, wind, irr, temp, hum, pres, nwp_w, nwp_irr, pwr, dpwr, dwind, dirr


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
    """趋势-季节分解 + 历史一阶差分 + 未来 NWP 气象时序融合网络"""

    def __init__(self, seq_len: int = pstd.LOOKBACK, pred_len: int = pstd.HORIZON, in_features: int = IN_FEATURES):
        super().__init__()
        self.decomp = MovingAvg(kernel_size=5)
        self.linear_trend = nn.Linear(seq_len, pred_len)
        self.linear_seasonal = nn.Linear(seq_len, pred_len)
        # 逐小时 NWP + 历史多变量残差 1D-CNN
        self.meteo_net = nn.Sequential(
            nn.Conv1d(in_features, 48, kernel_size=3, padding=1),
            nn.GroupNorm(8, 48),
            nn.GELU(),
            nn.Conv1d(48, 48, kernel_size=3, padding=1),
            nn.GroupNorm(8, 48),
            nn.GELU(),
            nn.Conv1d(48, 1, kernel_size=1),
        )
        # 全局场站特性门控（区分风电 vs 光伏响应模式）
        self.global_head = nn.Sequential(
            nn.AdaptiveAvgPool1d(4),
            nn.Flatten(),
            nn.Linear(in_features * 4, 48),
            nn.GELU(),
            nn.Linear(48, pred_len),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, 24, 13], channel 9 = norm power
        pwr = x[:, :, 9:10]
        trend = self.decomp(pwr).squeeze(-1)
        seasonal = pwr.squeeze(-1) - trend
        base = self.linear_trend(trend) + self.linear_seasonal(seasonal)
        xt = x.permute(0, 2, 1)
        local_nwp = self.meteo_net(xt).squeeze(1)
        glob_res = self.global_head(xt)
        return torch.clamp(base * 0.25 + local_nwp + 0.2 * glob_res, 0.0, 1.0)


def encode_raw_batch(raw: np.ndarray) -> np.ndarray:
    """raw: [N, 24, 9] (pstd.CHANNELS) -> [N, 24, 13] 归一化特征 + 一阶差分"""
    raw = np.asarray(raw, dtype=np.float32)
    single = raw.ndim == 2
    if single:
        raw = raw[None, ...]
    hour = raw[:, :, 0]
    wind = raw[:, :, 1] / 15.0
    irr = raw[:, :, 2] / 1000.0
    temp = raw[:, :, 3] / 40.0
    hum = raw[:, :, 4] / 100.0
    pres = (raw[:, :, 5] - 1000.0) / 30.0
    nwp_w = raw[:, :, 6] / 15.0
    nwp_irr = raw[:, :, 7] / 1000.0
    pwr = raw[:, :, 8] / pstd.CAPACITY_MW

    # 一阶差分（反映爬坡趋势）
    dpwr = np.diff(pwr, axis=1, prepend=pwr[:, :1])
    dwind = np.diff(wind, axis=1, prepend=wind[:, :1])
    dirr = np.diff(irr, axis=1, prepend=irr[:, :1])

    feats = np.stack(
        [
            np.sin(2.0 * math.pi * hour / 24.0),
            np.cos(2.0 * math.pi * hour / 24.0),
            wind,
            irr,
            temp,
            hum,
            pres,
            nwp_w,
            nwp_irr,
            pwr,
            dpwr,
            dwind,
            dirr,
        ],
        axis=-1,
    ).astype(np.float32)
    return feats[0] if single else feats


_MODEL_CACHE: PowerDLinearNet | None = None
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_device_label() -> str:
    return f"GPU ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "CPU (PyTorch)"


def train_power_model(epochs: int = 60) -> dict:
    """90% 训练 / 10% 验证严格切分训练 PowerDLinearNet，保存最优验证集权重并在测试集完成标准评测"""
    POWER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    POWER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(42)
    np.random.seed(42)

    raw_all, y_all_mw, _ = pstd.load_split(POWER_DATA_DIR, "train")
    X_all = encode_raw_batch(raw_all)
    y_all = (y_all_mw / pstd.CAPACITY_MW).astype(np.float32)

    perm = np.random.permutation(len(X_all))
    n_val = max(1, len(X_all) // 10)
    val_idx, tr_idx = perm[:n_val], perm[n_val:]

    xt = torch.from_numpy(X_all[tr_idx]).to(_DEVICE)
    yt = torch.from_numpy(y_all[tr_idx]).to(_DEVICE)
    xv = torch.from_numpy(X_all[val_idx]).to(_DEVICE)
    yv = torch.from_numpy(y_all[val_idx]).to(_DEVICE)

    model = PowerDLinearNet().to(_DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = nn.SmoothL1Loss(beta=0.04)

    history: list[dict] = []
    best_vloss = float("inf")
    best_state = None
    t0 = time.perf_counter()

    for ep in range(1, epochs + 1):
        model.train()
        p = torch.randperm(len(xt), device=_DEVICE)
        tr_sum, nb = 0.0, 0
        for i in range(0, len(xt), 64):
            b = p[i : i + 64]
            opt.zero_grad()
            loss = loss_fn(model(xt[b]), yt[b])
            loss.backward()
            opt.step()
            tr_sum += float(loss.item())
            nb += 1
        sched.step()

        model.eval()
        with torch.no_grad():
            vp = model(xv)
            vloss = float(loss_fn(vp, yv).item())
            vrmse = float(torch.sqrt(torch.mean((vp - yv) ** 2)).item())
            vacc = round(max(0.0, (1.0 - vrmse) * 100.0), 2)
        if vloss < best_vloss:
            best_vloss = vloss
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        history.append({
            "epoch": ep,
            "train_loss": round(tr_sum / max(1, nb), 5),
            "val_loss": round(vloss, 5),
            "val_acc": vacc,
        })

    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    torch.save({"state_dict": model.state_dict(), "in_features": IN_FEATURES, "capacity_mw": pstd.CAPACITY_MW}, WEIGHT_PATH)
    global _MODEL_CACHE
    _MODEL_CACHE = model

    eval_res = evaluate_power_on_test(history=history)
    state = {
        "algorithm_id": POWER_ALGO_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_PATH.name,
        "weight_bytes": WEIGHT_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "train_seconds": round(time.perf_counter() - t0, 1),
        "device": get_device_label(),
        "history": history,
        "eval": eval_res,
    }
    POWER_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    m = eval_res["metrics"]
    print(
        f"[power] PowerDLinearNet 训练完成 -> {WEIGHT_PATH.name} ({state['weight_bytes']:,} B) | "
        f"Acc={m['accuracy_rate']}% NRMSE={m['nrmse']}% NMAE={m['nmae']}% R2={m['r2']}% PeakErr={m['peak_err_mw']}MW Qual={m['qualified_rate']}%"
    )
    return state


def load_power_model() -> PowerDLinearNet:
    global _MODEL_CACHE
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE
    if not WEIGHT_PATH.exists():
        train_power_model()
        assert _MODEL_CACHE is not None
        return _MODEL_CACHE
    ckpt = torch.load(WEIGHT_PATH, map_location=_DEVICE, weights_only=True)
    if ckpt.get("in_features") != IN_FEATURES:
        train_power_model()
        assert _MODEL_CACHE is not None
        return _MODEL_CACHE
    model = PowerDLinearNet().to(_DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _MODEL_CACHE = model
    return model


def load_power_state() -> dict | None:
    if POWER_STATE_PATH.exists():
        try:
            return json.loads(POWER_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def evaluate_power_on_test(
    on_progress: Callable[[int, str | None], None] | None = None,
    history: list[dict] | None = None,
) -> dict:
    """在 Admin/wind-solar-power-dataset@v1.0/test（300 条 24h→24h 窗口）上运行标准评测"""
    t0 = time.perf_counter()
    if on_progress:
        on_progress(15, f"[power] 加载 {POWER_ALGO_ID}@v1.0.0 ({get_device_label()})")
    model = load_power_model()
    raw_test, y_true_mw, metas = pstd.load_split(POWER_DATA_DIR, "test")
    if on_progress:
        on_progress(50, f"[power] 挂载 {POWER_DATASET_ID}@v1.0/test（共 {len(metas)} 条 24h→24h 多变量窗口）")

    X_test = encode_raw_batch(raw_test)
    with torch.no_grad():
        pred_norm = model(torch.from_numpy(X_test).to(_DEVICE)).cpu().numpy()
    y_pred_mw = pred_norm * pstd.CAPACITY_MW

    if history is None:
        st = load_power_state()
        history = (st or {}).get("history", [])

    return pstd.evaluate_predictions(
        raw_test=raw_test,
        y_true=y_true_mw,
        y_pred=y_pred_mw,
        metas=metas,
        history=history,
        device=get_device_label(),
        elapsed_sec=time.perf_counter() - t0,
    )


def infer_power_forecast(
    csv_bytes: bytes | None = None,
    filename: str = "station_huazhong_24h.csv",
    sample_split: str | None = None,
) -> dict:
    """运行真实 PyTorch 短期功率预测推理，返回 48h 连续曲线（24h 历史 + 24h 预测 + 若有 GT 真值）"""
    t0 = time.perf_counter()
    model = load_power_model()
    rows: list[dict] = []
    gt_24h: np.ndarray | None = None
    meta: dict = {"file_name": filename, "station": "自定义场站", "kind": "wind", "weather": "未知"}

    # 若指定样本路径或文件名，自动匹配对应 labels.csv 中的真值与场站元信息
    def lookup_meta(split: str, fname: str):
        nonlocal gt_24h, meta
        lbl_path = POWER_DATA_DIR / split / "labels.csv"
        if not lbl_path.exists():
            return
        with lbl_path.open("r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if Path(r["file_name"]).name == fname:
                    meta = r
                    gt_24h = np.asarray(json.loads(r["target_24h"]), dtype=np.float32)
                    return

    if csv_bytes:
        try:
            rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig", errors="ignore"))))
        except Exception:
            rows = []
        if sample_split in ("train", "test"):
            lookup_meta(sample_split, Path(filename).name)
    else:
        split = sample_split if sample_split in ("train", "test") else "train"
        target_name = Path(filename).name
        p = POWER_DATA_DIR / split / "series" / target_name
        if not p.exists():
            all_csv = sorted((POWER_DATA_DIR / split / "series").glob("*.csv"))
            if all_csv:
                p = all_csv[0]
                target_name = p.name
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            lookup_meta(split, target_name)

    raw = pstd.parse_series_rows(rows)
    feat = encode_raw_batch(raw)
    with torch.no_grad():
        pred_norm = model(torch.from_numpy(feat).unsqueeze(0).to(_DEVICE)).squeeze(0).cpu().numpy()
    pred_24h = pred_norm * pstd.CAPACITY_MW

    case_data = pstd.build_case_payload(raw, gt_24h, pred_24h, meta)
    forecast = case_data["pred"]
    latency_ms = max(0.4, round((time.perf_counter() - t0) * 1000, 2))
    return {
        "device": get_device_label(),
        "latencyMs": latency_ms,
        "queuedMs": 0,
        "raw": {
            "algorithm": POWER_ALGO_ID,
            "version": "v1.0.0",
            "task": pstd.TASK,
            "unit": "MW",
            "capacity_mw": pstd.CAPACITY_MW,
            "lookback_hours": pstd.LOOKBACK,
            "horizon_hours": pstd.HORIZON,
            "source_file": case_data["file"],
            "station": case_data["station"],
            "weather": case_data["weather"],
            "history": case_data["history"],
            "forecast": forecast,
            "gt": case_data["gt"],
            "case": case_data,
            "mean_mw": round(sum(forecast) / len(forecast), 2),
            "peak_mw": round(max(forecast), 2),
            "min_mw": round(min(forecast), 2),
        },
    }


if __name__ == "__main__":
    train_power_model()
