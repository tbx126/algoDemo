"""
新能源场站短期功率时序预测算法注册与推理/评测模块（Admin/power-dlinear）：
  - 模型结构：PowerDLinearNet（趋势-季节滑动平均分解 + 多变量气象 1D-CNN 融合 + 双线性预测头）
  - 数据集：Admin/wind-solar-power-dataset（24h 历史多变量气象与功率窗口 -> 未来 24h 功率曲线）
  - 权重文件：backend/models/power-forecast/v1.0.0_power_dlinear.pt
  - 状态文件：backend/state/power_state.json
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

ROOT = Path(__file__).resolve().parent
POWER_DATA_DIR = ROOT / "data" / "wind-solar-power-dataset"
POWER_MODEL_DIR = ROOT / "models" / "power-forecast"
POWER_STATE_PATH = ROOT / "state" / "power_state.json"

POWER_ALGO_ID = "Admin/power-dlinear"
POWER_DATASET_ID = "Admin/wind-solar-power-dataset"
POWER_BENCH_ID = "power-forecast-bench"
CAPACITY_MW = 100.0
SEQ_LEN = 24
PRED_LEN = 24
IN_FEATURES = 8  # sin_h, cos_h, wind, irr, temp, hum, pres, power

WEIGHT_PATH = POWER_MODEL_DIR / "v1.0.0_power_dlinear.pt"


class MovingAvg(nn.Module):
    """DLinear 经典滑动平均趋势提取层"""

    def __init__(self, kernel_size: int = 5):
        super().__init__()
        self.kernel_size = kernel_size
        self.avg = nn.AvgPool1d(kernel_size=kernel_size, stride=1, padding=0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, L, C]
        pad = (self.kernel_size - 1) // 2
        front = x[:, :1, :].repeat(1, pad, 1)
        end = x[:, -1:, :].repeat(1, pad, 1)
        x_pad = torch.cat([front, x, end], dim=1)
        return self.avg(x_pad.permute(0, 2, 1)).permute(0, 2, 1)


class PowerDLinearNet(nn.Module):
    """
    趋势-季节分解 + 气象多变量时序卷积融合网络（DLinear-TCN）：
      - 对历史功率通道执行 Trend/Seasonal 分解并分别以线性头外推未来 24h；
      - 同步通过轻量 1D-CNN 提取风速、辐照度、温湿度、气压与时间编码的非线性气象特征残差；
      - 输出未来 24 小时归一化功率曲线（[0, 1] -> 乘装机容量得 MW）。
    """

    def __init__(self, seq_len: int = SEQ_LEN, pred_len: int = PRED_LEN, in_features: int = IN_FEATURES):
        super().__init__()
        self.decomp = MovingAvg(kernel_size=5)
        self.linear_trend = nn.Linear(seq_len, pred_len)
        self.linear_seasonal = nn.Linear(seq_len, pred_len)
        self.meteo_conv = nn.Sequential(
            nn.Conv1d(in_features, 32, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool1d(8),
            nn.Flatten(),
            nn.Linear(32 * 8, 64),
            nn.GELU(),
            nn.Linear(64, pred_len),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: [B, 24, 8], 最后一维为归一化历史功率
        power_seq = x[:, :, -1:]  # [B, 24, 1]
        trend = self.decomp(power_seq).squeeze(-1)  # [B, 24]
        seasonal = power_seq.squeeze(-1) - trend  # [B, 24]
        base = self.linear_trend(trend) + self.linear_seasonal(seasonal)
        meteo_res = self.meteo_conv(x.permute(0, 2, 1))
        return torch.clamp(base + 0.35 * meteo_res, 0.0, 1.0)


def _encode_csv_rows(rows: list[dict]) -> tuple[np.ndarray, list[float]]:
    """将 24 行 CSV 字典编码为 [24, 8] 归一化张量并返回原始历史功率列表"""
    feats: list[list[float]] = []
    hist_power: list[float] = []
    for i, r in enumerate(rows[-SEQ_LEN:]):
        hour = float(r.get("hour", i % 24))
        wind = float(r.get("wind_speed_ms", 6.0))
        irr = float(r.get("irradiance_wm2", 0.0))
        temp = float(r.get("temp_c", 20.0))
        hum = float(r.get("humidity_pct", 55.0))
        pres = float(r.get("pressure_hpa", 1012.0))
        pwr = float(r.get("power_mw", r.get("value", 30.0)))
        hist_power.append(round(pwr, 2))
        feats.append([
            math.sin(2 * math.pi * hour / 24.0),
            math.cos(2 * math.pi * hour / 24.0),
            wind / 15.0,
            irr / 1000.0,
            temp / 40.0,
            hum / 100.0,
            (pres - 1000.0) / 30.0,
            pwr / CAPACITY_MW,
        ])
    while len(feats) < SEQ_LEN:
        feats.insert(0, feats[0] if feats else [0.0] * IN_FEATURES)
        hist_power.insert(0, hist_power[0] if hist_power else 0.0)
    return np.asarray(feats, dtype=np.float32), hist_power


def _load_split_tensors(split: str) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    split_dir = POWER_DATA_DIR / split
    lbl_path = split_dir / "labels.csv"
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    metas: list[dict] = []
    with lbl_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            series_path = split_dir / row["file_name"]
            with series_path.open("r", encoding="utf-8") as sf:
                srows = list(csv.DictReader(sf))
            feat, _ = _encode_csv_rows(srows)
            target = np.asarray(json.loads(row["target_24h"]), dtype=np.float32) / CAPACITY_MW
            xs.append(feat)
            ys.append(target)
            metas.append(row)
    return np.stack(xs, axis=0), np.stack(ys, axis=0), metas


_MODEL_CACHE: PowerDLinearNet | None = None
_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_device_label() -> str:
    if torch.cuda.is_available():
        return f"GPU ({torch.cuda.get_device_name(0)})"
    return "CPU (PyTorch)"


def train_power_model(epochs: int = 80) -> dict:
    """在真实训练集上训练 PowerDLinearNet，保存权重并在测试集完成评测"""
    POWER_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    POWER_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)

    torch.manual_seed(42)
    np.random.seed(42)

    X_train, y_train, _ = _load_split_tensors("train")
    model = PowerDLinearNet().to(_DEVICE)
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    loss_fn = nn.SmoothL1Loss(beta=0.05)

    xt = torch.from_numpy(X_train).to(_DEVICE)
    yt = torch.from_numpy(y_train).to(_DEVICE)
    batch_size = 64
    n = xt.shape[0]

    model.train()
    for _ in range(epochs):
        perm = torch.randperm(n, device=_DEVICE)
        for i in range(0, n, batch_size):
            idx = perm[i : i + batch_size]
            opt.zero_grad()
            pred = model(xt[idx])
            loss = loss_fn(pred, yt[idx])
            loss.backward()
            opt.step()
        scheduler.step()

    model.eval()
    torch.save(
        {
            "state_dict": model.state_dict(),
            "seq_len": SEQ_LEN,
            "pred_len": PRED_LEN,
            "in_features": IN_FEATURES,
            "capacity_mw": CAPACITY_MW,
        },
        WEIGHT_PATH,
    )
    global _MODEL_CACHE
    _MODEL_CACHE = model

    eval_res = evaluate_power_on_test()
    state = {
        "algorithm_id": POWER_ALGO_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_PATH.name,
        "weight_bytes": WEIGHT_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "device": get_device_label(),
        "eval": eval_res,
    }
    POWER_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"PowerDLinearNet 训练完成 -> {WEIGHT_PATH.name} ({state['weight_bytes']:,} B) | "
        f"测试集准确率={eval_res['metrics']['accuracy_rate']}% RMSE={eval_res['metrics']['rmse']}% MAE={eval_res['metrics']['mae']}%"
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
    model = PowerDLinearNet().to(_DEVICE)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    _MODEL_CACHE = model
    return model


def evaluate_power_on_test(
    on_progress: Callable[[int, str | None], None] | None = None,
) -> dict:
    """在 Admin/wind-solar-power-dataset@v1.0/test（200 条真实时序窗口）上运行评测"""
    t0 = time.perf_counter()
    if on_progress:
        on_progress(15, f"[runner] 加载 {POWER_ALGO_ID}@v1.0.0 ({get_device_label()})")
    model = load_power_model()
    X_test, y_test, metas = _load_split_tensors("test")
    if on_progress:
        on_progress(45, f"[runner] 挂载 {POWER_DATASET_ID}@v1.0/test（共 {len(metas)} 条 24h→24h 时序窗口）")

    with torch.no_grad():
        preds = model(torch.from_numpy(X_test).to(_DEVICE)).cpu().numpy()

    if on_progress:
        on_progress(80, "[runner] 按新能源场站装机容量（100 MW）计算归一化 RMSE、MAE 与考核准确率")

    # 归一化误差（已在 [0, 1] 空间，即除以 100 MW）
    diff = preds - y_test
    rmse = float(np.sqrt(np.mean(diff ** 2)))
    mae = float(np.mean(np.abs(diff)))
    acc_rate = max(0.0, (1.0 - rmse) * 100.0)

    # 分场站统计
    by_station: dict[str, list[int]] = {}
    for idx, m in enumerate(metas):
        by_station.setdefault(m["station"], []).append(idx)

    per_class = []
    for st_name, idxs in by_station.items():
        d_sub = diff[idxs]
        st_rmse = float(np.sqrt(np.mean(d_sub ** 2)))
        st_mae = float(np.mean(np.abs(d_sub)))
        acc = round(max(0.0, (1.0 - st_rmse) * 100.0), 2)
        per_class.append({
            "label": st_name,
            "value": acc,
            "rmse": round(st_rmse * 100.0, 2),
            "mae": round(st_mae * 100.0, 2),
            "support": len(idxs),
        })

    elapsed = round(time.perf_counter() - t0, 2)
    return {
        "metrics": {
            "accuracy_rate": round(acc_rate, 2),
            "rmse": round(rmse * 100.0, 2),
            "mae": round(mae * 100.0, 2),
        },
        "perClass": per_class,
        "samples": len(metas),
        "durationSec": max(0.2, elapsed),
        "device": get_device_label(),
    }


def infer_power_forecast(csv_bytes: bytes | None = None, filename: str = "station_huazhong_24h.csv") -> dict:
    """运行真实 PyTorch 短期功率预测推理，支持上传 CSV 或使用测试集示例窗口"""
    t0 = time.perf_counter()
    model = load_power_model()
    rows: list[dict] = []
    sample_source = filename

    if csv_bytes:
        try:
            text = csv_bytes.decode("utf-8-sig", errors="ignore")
            rows = list(csv.DictReader(io.StringIO(text)))
        except Exception:
            rows = []

    # 若未上传文件或 CSV 为空，则自动取测试集首条真实样本作为示例输入
    if not rows:
        test_series = sorted((POWER_DATA_DIR / "test" / "series").glob("*.csv"))
        if test_series:
            sample_file = test_series[0]
            sample_source = sample_file.name
            with sample_file.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))

    feat, hist_power = _encode_csv_rows(rows)
    with torch.no_grad():
        x = torch.from_numpy(feat).unsqueeze(0).to(_DEVICE)
        pred_norm = model(x).squeeze(0).cpu().numpy()

    forecast = [round(float(v) * CAPACITY_MW, 2) for v in pred_norm]
    latency_ms = max(0.4, round((time.perf_counter() - t0) * 1000, 2))
    return {
        "device": get_device_label(),
        "latencyMs": latency_ms,
        "queuedMs": 0,
        "raw": {
            "algorithm": POWER_ALGO_ID,
            "version": "v1.0.0",
            "task": "power-forecast",
            "source_file": sample_source,
            "unit": "MW",
            "capacity_mw": CAPACITY_MW,
            "lookback_hours": SEQ_LEN,
            "horizon_hours": PRED_LEN,
            "history": hist_power,
            "forecast": forecast,
            "mean_mw": round(sum(forecast) / len(forecast), 2),
            "peak_mw": round(max(forecast), 2),
            "min_mw": round(min(forecast), 2),
        },
    }


def load_power_state() -> dict | None:
    if POWER_STATE_PATH.exists():
        try:
            return json.loads(POWER_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


if __name__ == "__main__":
    train_power_model()
