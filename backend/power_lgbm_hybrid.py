"""
新能源短期功率预测算法（Admin/power-lgbm-hybrid）—— 物理功率曲线先验 + LightGBM 残差纠偏（Huber 鲁棒损失）

  - 核心思想：先通过物理名义功率曲线计算基础出力 p_nom，再用风/光双 LightGBM 学习残差 Δp = y - p_nom，
              专门纠正 NWP 预报系统偏差、天气过程相位偏移（h-2..h+2 窗口）与空气密度/温度效率折损
  - 鲁棒性：采用 Huber 损失抑制阵风/云团突变的极端离群梯度；光伏夜间零辐照时段严格置零
  - 接口：实现 power_forecast_std 标准 predict_batch(raw [N, 24, 9], specs) -> [N, 24] MW
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np

import power_forecast_std as pstd

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data"
MODEL_DIR = ROOT / "models" / "power-forecast"
STATE_PATH = ROOT / "state" / "power_lgbm_hybrid_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_power_lgbm_hybrid.lgb.json"
CODE_PATH = Path(__file__).resolve()

ALGO_ID = "Admin/power-lgbm-hybrid"
VAL_DAYS = 20
PURGE_DAYS = 2

LGB_PARAMS = {
    "objective": "huber",
    "alpha": 0.08,
    "metric": "rmse",
    "boosting_type": "gbdt",
    "num_leaves": 47,
    "learning_rate": 0.035,
    "feature_fraction": 0.85,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_data_in_leaf": 24,
    "reg_alpha": 0.2,
    "reg_lambda": 1.0,
    "verbose": -1,
    "seed": 2025,
    "n_jobs": 4,
}
NUM_BOOST_ROUND = 3000  # 上限足够大，由验证集 early stopping 决定实际轮数

CARD = {
    "name": "power-lgbm-hybrid",
    "displayName": "新能源功率预测（物理先验 + LightGBM 残差）",
    "framework": "LightGBM",
    "runtime": "Python 3.12 · LightGBM 4.x · NumPy",
    "gpuMem": 0.0,
    "summary": "物理名义功率曲线叠加风/光双 LightGBM 残差纠偏：5 小时 NWP 相位窗口 + 空气密度/结温修正 + 光伏夜间硬约束。",
    "tags": ["LightGBM", "物理混合", "NWP纠偏"],
    "business": "production",
    "codeFile": "power_lgbm_hybrid.py",
    "likes": 18,
    "downloads": 35,
    "changelog": "在 LightGBM 基础上引入物理功率曲线先验、5 小时 NWP 相位上下文、空气密度/温度修正特征与 Huber 鲁棒损失；轮数由验证集 early stopping 决定。",
    "readme": """# power-lgbm-hybrid（新能源功率预测 · 物理先验 + LightGBM 残差）

在压缩包 LightGBM 方案的基础上，结合新能源调度工程常用的**物理模型 + 机器学习残差纠偏（Physics-Guided Residual GBDT）**范式构建的进阶功率预测模型。

## 核心机制

1. **物理基线先验**：先基于 NWP 风速 / 辐照度计算名义功率曲线 `p_nom`，模型只需学习与名义曲线的偏差。
2. **残差学习（Δp = y - p_nom）**：风电 / 光伏两个 LightGBM 模型专门拟合真实出力与物理基线的偏差，重点吸收：
   - **±2 小时 NWP 相位窗口**（`h-2, h-1, h, h+1, h+2` 及其爬坡率），平滑 NWP 天气系统提前/滞后误差；
   - **场站历史偏差代理**：前一日实测出力与实测气象物理名义值之差，自动自适应不同场站的机组效率与地形折减；
   - **空气密度与结温代理**：结合气压与气温构造 `P / (T + 273.15)` 空气密度项与光伏温度折损项。
3. **工程硬约束**：采用 Huber 鲁棒损失抑制阵风/云团瞬变噪声；光伏夜间无辐照时段严格置零（`night_mw ≈ 0 MW`）。
""",
}

_MODEL_CACHE: dict[str, lgb.Booster] | None = None


def device_label() -> str:
    return "CPU (LightGBM 4.x)"


def load_state() -> dict | None:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _shift_24(arr: np.ndarray, delta: int) -> np.ndarray:
    """沿 24h 轴平移，边缘采用边界值复制填充"""
    if delta == 0:
        return arr
    if delta > 0:
        return np.concatenate([np.repeat(arr[:, :1], delta, axis=1), arr[:, :-delta]], axis=1)
    k = -delta
    return np.concatenate([arr[:, k:], np.repeat(arr[:, -1:], k, axis=1)], axis=1)


def _hist_nominal(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """用前一日实测风速/辐照度计算名义出力（归一化 0-1），用于估计场站系统效率偏差"""
    out = np.zeros(raw.shape[:2], dtype=np.float32)
    for i, sp in enumerate(specs):
        if sp["kind"] == "wind":
            v = raw[i, :, 1]
            out[i] = np.where((v < 3) | (v > 25), 0.0, np.where(v >= 12, 1.0, ((np.clip(v, 3, 12) - 3) / 9.0) ** 3))
        else:
            out[i] = np.clip(raw[i, :, 2] / 1000.0 * 0.9, 0.0, 1.0)
    return out


def _build_features(raw: np.ndarray, specs: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """返回 (特征 [N, 24, F], 归一化物理先验 p_nom [N, 24])"""
    raw = np.asarray(raw, dtype=np.float32)
    N, H, _ = raw.shape
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
    p_nom = (pstd.nominal_power(raw, specs) / cap).astype(np.float32)
    h_nom = _hist_nominal(raw, specs)

    hour = raw[:, :, 0]
    w_hist = raw[:, :, 1]
    i_hist = raw[:, :, 2]
    temp = raw[:, :, 3]
    hum = raw[:, :, 4]
    pres = raw[:, :, 5]
    nwp_w = raw[:, :, 6]
    nwp_i = raw[:, :, 7]
    pwr = raw[:, :, 8] / cap

    # 历史场站效率偏差（实测功率 - 实测名义曲线），可无监督识别场站折减系数与地形差异
    hist_bias = pwr - h_nom
    hist_bias_mean = np.broadcast_to(hist_bias.mean(axis=1, keepdims=True), (N, H))
    hist_bias_day = np.broadcast_to(
        np.where(h_nom > 0.05, hist_bias, 0.0).sum(axis=1, keepdims=True) / np.maximum(1.0, (h_nom > 0.05).sum(axis=1, keepdims=True)),
        (N, H),
    )

    # 空气密度代理（kg/m³ 近似）与光伏结温代理
    air_density = (pres * 100.0) / (287.05 * (temp + 273.15))
    t_cell_proxy = temp + 0.031 * nwp_i

    # 5 小时 NWP 相位窗口与名义曲线平滑窗口
    nw_m2, nw_m1, nw_p1, nw_p2 = _shift_24(nwp_w, 2), _shift_24(nwp_w, 1), _shift_24(nwp_w, -1), _shift_24(nwp_w, -2)
    ni_m2, ni_m1, ni_p1, ni_p2 = _shift_24(nwp_i, 2), _shift_24(nwp_i, 1), _shift_24(nwp_i, -1), _shift_24(nwp_i, -2)
    pn_m2, pn_m1, pn_p1, pn_p2 = _shift_24(p_nom, 2), _shift_24(p_nom, 1), _shift_24(p_nom, -1), _shift_24(p_nom, -2)
    pn_smooth = 0.1 * pn_m2 + 0.2 * pn_m1 + 0.4 * p_nom + 0.2 * pn_p1 + 0.1 * pn_p2

    # 日尺度天气变化（次日 NWP 均值 - 前一日实测均值）
    dw_day = np.broadcast_to((nwp_w.mean(axis=1, keepdims=True) - w_hist.mean(axis=1, keepdims=True)), (N, H))
    di_day = np.broadcast_to((nwp_i.mean(axis=1, keepdims=True) - i_hist.mean(axis=1, keepdims=True)), (N, H))
    last1 = np.broadcast_to(pwr[:, 23:24], (N, H))
    pwr_mean = np.broadcast_to(pwr.mean(axis=1, keepdims=True), (N, H))

    feats = [
        hour,
        np.sin(2 * math.pi * hour / 24.0),
        np.cos(2 * math.pi * hour / 24.0),
        np.sin(4 * math.pi * hour / 24.0),
        np.cos(4 * math.pi * hour / 24.0),
        p_nom,
        pn_smooth,
        pn_m2,
        pn_m1,
        pn_p1,
        pn_p2,
        p_nom - pn_m1,
        pn_p1 - p_nom,
        nwp_w,
        nw_m2,
        nw_m1,
        nw_p1,
        nw_p2,
        nwp_w - nw_m1,
        nwp_i,
        ni_m2,
        ni_m1,
        ni_p1,
        ni_p2,
        nwp_i - ni_m1,
        dw_day,
        di_day,
        air_density,
        t_cell_proxy,
        temp,
        hum,
        pres,
        pwr,
        last1,
        pwr_mean,
        hist_bias,
        hist_bias_mean,
        hist_bias_day,
    ]
    return np.stack(feats, axis=-1).astype(np.float32), p_nom


def _apply_solar_night_mask(pred_norm: np.ndarray, raw: np.ndarray, kinds: np.ndarray) -> np.ndarray:
    """光伏夜间无辐照时段严格置零"""
    hours = np.rint(raw[:, :, 0]).astype(int) % 24
    solar = (kinds == "solar")[:, None]
    night = solar & (~np.isin(hours, list(pstd.SOLAR_EVAL_HOURS))) & (raw[:, :, 7] <= 2.0)
    out = pred_norm.copy()
    out[night] = 0.0
    return out


def _discover_train_dirs() -> list[Path]:
    dirs = []
    if DATA_ROOT.exists():
        for d in sorted(DATA_ROOT.iterdir()):
            if d.is_dir() and pstd.read_meta(d) is not None:
                dirs.append(d)
    return dirs


def train(data_dirs: list[Path] | None = None) -> dict:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dirs = data_dirs or _discover_train_dirs()
    if not dirs:
        raise RuntimeError("未发现任何符合 power-forecast 标准的训练数据集")

    X_tr_l, r_tr_l, k_tr_l = [], [], []
    X_va_l, r_va_l, p_va_l, y_va_l, raw_va_l, k_va_l, m_va_l = [], [], [], [], [], [], []
    tr_wins = va_wins = 0

    for d in dirs:
        raw, y_mw, metas, specs = pstd.load_split(d, "train")
        X, p_nom = _build_features(raw, specs)
        cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
        Y = (y_mw / cap).astype(np.float32)
        resid = (Y - p_nom).astype(np.float32)
        kinds = np.array([s["kind"] for s in specs])
        mask = pstd.eval_mask(raw, specs)

        t0 = np.array([int(m["t0"]) for m in metas])
        val_start = t0.max() - (VAL_DAYS - 1) * 24
        val_idx = np.where(t0 >= val_start)[0]
        tr_idx = np.where(t0 < val_start - PURGE_DAYS * 24)[0]
        tr_wins += len(tr_idx)
        va_wins += len(val_idx)

        X_tr_l.append(X[tr_idx]); r_tr_l.append(resid[tr_idx]); k_tr_l.append(kinds[tr_idx])
        X_va_l.append(X[val_idx]); r_va_l.append(resid[val_idx]); p_va_l.append(p_nom[val_idx])
        y_va_l.append(Y[val_idx]); raw_va_l.append(raw[val_idx]); k_va_l.append(kinds[val_idx]); m_va_l.append(mask[val_idx])

    X_tr = np.concatenate(X_tr_l); r_tr = np.concatenate(r_tr_l); k_tr = np.concatenate(k_tr_l)
    X_va = np.concatenate(X_va_l); r_va = np.concatenate(r_va_l); p_va = np.concatenate(p_va_l)
    y_va = np.concatenate(y_va_l); raw_va = np.concatenate(raw_va_l); k_va = np.concatenate(k_va_l); m_va = np.concatenate(m_va_l)

    t_start = time.perf_counter()
    models: dict[str, lgb.Booster] = {}
    evals_res: dict[str, dict] = {}
    best_iters: dict[str, int] = {}

    for kind in pstd.KINDS:
        tr_sel = k_tr == kind
        va_sel = k_va == kind
        dtrain = lgb.Dataset(X_tr[tr_sel].reshape(-1, X_tr.shape[-1]), label=r_tr[tr_sel].reshape(-1))
        dval = lgb.Dataset(X_va[va_sel].reshape(-1, X_va.shape[-1]), label=r_va[va_sel].reshape(-1), reference=dtrain)
        rec: dict = {}
        booster = lgb.train(
            dict(LGB_PARAMS),
            dtrain,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[dtrain, dval],
            valid_names=["train", "val"],
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.record_evaluation(rec)],
        )
        models[kind] = booster
        evals_res[kind] = rec
        best_iters[kind] = int(booster.best_iteration or NUM_BOOST_ROUND)

    max_len = max(len(evals_res[k]["val"]["rmse"]) for k in pstd.KINDS)
    history: list[dict] = []
    for step in range(0, max_len, max(1, max_len // 40)):
        tr_vals = [evals_res[k]["train"]["rmse"][min(step, len(evals_res[k]["train"]["rmse"]) - 1)] for k in pstd.KINDS]
        va_vals = [evals_res[k]["val"]["rmse"][min(step, len(evals_res[k]["val"]["rmse"]) - 1)] for k in pstd.KINDS]
        v_rmse = float(np.mean(va_vals))
        history.append({
            "epoch": step + 1,
            "train_loss": round(float(np.mean(tr_vals)), 5),
            "val_loss": round(v_rmse, 5),
            "val_acc": round(max(0.0, (1.0 - v_rmse) * 100.0), 2),
        })

    vp = np.zeros_like(y_va)
    for kind in pstd.KINDS:
        sel = k_va == kind
        if sel.any():
            dr = models[kind].predict(X_va[sel].reshape(-1, X_va.shape[-1]), num_iteration=models[kind].best_iteration)
            vp[sel] = np.clip(p_va[sel] + dr.reshape(-1, pstd.HORIZON), 0.0, 1.0)
    vp = _apply_solar_night_mask(vp, raw_va, k_va)
    val_nrmse = float(np.sqrt(np.mean((vp - y_va)[m_va] ** 2)))
    val_acc = round(max(0.0, (1.0 - val_nrmse) * 100.0), 2)

    payload = {
        "algorithm_id": ALGO_ID,
        "version": "v1.0.0",
        "num_features": int(X_tr.shape[-1]),
        "best_iterations": best_iters,
        "models": {k: models[k].model_to_string() for k in pstd.KINDS},
    }
    WEIGHT_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    global _MODEL_CACHE
    _MODEL_CACHE = models

    state = {
        "algorithm_id": ALGO_ID,
        "version": "v1.0.0",
        "weight_file": WEIGHT_PATH.name,
        "weight_bytes": WEIGHT_PATH.stat().st_size,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "train_seconds": round(time.perf_counter() - t_start, 2),
        "device": device_label(),
        "train_datasets": [d.name for d in dirs],
        "best_epoch": int(round(np.mean(list(best_iters.values())))),
        "best_iterations": best_iters,
        "val_acc": val_acc,
        "split": {"train_windows": int(tr_wins), "val_windows": int(va_wins), "val_days": VAL_DAYS, "purge_days": PURGE_DAYS},
        "history": history,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[power-lgbm-hybrid] 训练完成：训练 {tr_wins} / 验证 {va_wins} 窗口，验证准确率 {val_acc:.2f}%，迭代 {best_iters}，用时 {state['train_seconds']}s")
    return state


def _models() -> dict[str, lgb.Booster]:
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        if not WEIGHT_PATH.exists():
            train()
        else:
            payload = json.loads(WEIGHT_PATH.read_text(encoding="utf-8"))
            _MODEL_CACHE = {k: lgb.Booster(model_str=payload["models"][k]) for k in pstd.KINDS}
    assert _MODEL_CACHE is not None
    return _MODEL_CACHE


def predict_batch(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    models = _models()
    raw = np.asarray(raw, dtype=np.float32)
    X, p_nom = _build_features(raw, specs)
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
    kinds = np.array([s["kind"] for s in specs])
    out = np.zeros((len(raw), pstd.HORIZON), dtype=np.float32)

    for kind in pstd.KINDS:
        sel = kinds == kind
        if not sel.any():
            continue
        dr = models[kind].predict(X[sel].reshape(-1, X.shape[-1]))
        out[sel] = np.clip(p_nom[sel] + dr.reshape(-1, pstd.HORIZON), 0.0, 1.0)
    out = _apply_solar_night_mask(out, raw, kinds)
    return out * cap


if __name__ == "__main__":
    train()
