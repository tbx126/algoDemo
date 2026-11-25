"""
新能源短期功率预测算法（Admin/power-lgbm-autoreg）—— 忠实复现压缩包 province_45_power_forecast.py 的自回归滚动 LightGBM

  - 核心机制：维护尾部滞后队列 tail，按 lag_steps = [1, 2, 3, 6, 12, 24] 逐步自回归滚动预测未来 24 小时
  - 模型：风电 / 光伏双 LightGBM GBDT 单步回归器（与原脚本相同的逐步推进结构）
  - 改进：消除原脚本历史风速由功率反推的目标泄露，按时间严格切分验证集并早停
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
STATE_PATH = ROOT / "state" / "power_lgbm_autoreg_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_power_lgbm_autoreg.lgb.json"
CODE_PATH = Path(__file__).resolve()

ALGO_ID = "Admin/power-lgbm-autoreg"
LAG_STEPS = (1, 2, 3, 6, 12, 24)
VAL_DAYS = 20
PURGE_DAYS = 2

LGB_PARAMS = {
    "objective": "regression",
    "metric": "rmse",
    "boosting_type": "gbdt",
    "num_leaves": 31,
    "learning_rate": 0.05,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_data_in_leaf": 20,
    "verbose": -1,
    "seed": 2025,
    "n_jobs": 4,
}
NUM_BOOST_ROUND = 300

CARD = {
    "name": "power-lgbm-autoreg",
    "displayName": "新能源功率预测（LightGBM 自回归滚动）",
    "framework": "LightGBM",
    "runtime": "Python 3.12 · LightGBM 4.x · NumPy",
    "gpuMem": 0.0,
    "summary": "忠实复现中电建原脚本自回归滚动策略（tail 滞后队列 + 风/光双 LightGBM），逐步递推未来 24 小时功率曲线。",
    "tags": ["LightGBM", "自回归滚动", "新能源场站", "NWP气象"],
    "business": "production",
    "codeFile": "power_lgbm_autoreg.py",
    "likes": 9,
    "downloads": 21,
    "changelog": "忠实复现 province_45_power_forecast.py 的 lag_steps 自回归滚动推理与风/光双 LightGBM 模型，修复数据泄露并接入平台统一评测。",
    "readme": """# power-lgbm-autoreg（新能源功率预测 · LightGBM 自回归滚动）

忠实保留压缩包 `province_45_power_forecast.py` 的**自回归滚动预测（Autoregressive Rolling）**架构：以历史 24 小时实测作为初始尾部队列 `tail`，逐步向后滚动预测次日第 `1..24` 小时，并将每一步的预测功率写回 `tail` 供后续步的滞后特征使用。

## 算法设计

- **滞后步长**：`lag_steps = [1, 2, 3, 6, 12, 24]`（对应原脚本 15 分钟尺度的 `[1, 2, 4, 8, 96]` 换算到小时尺度）。
- **单步特征**：目标时刻 `h` 的周期正余弦编码 + 次日 NWP 风速/辐照度 + 历史日气象背景 + 动态滚动滞后功率 `[t-1, t-2, t-3, t-6, t-12, t-24]`。
- **对比价值**：与「LightGBM 分时直推」同源同参，可直接在平台评测的**提前期误差曲线（Horizon Curve）**中观察自回归误差累积与分时直推的差异。
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


def _step_features(raw: np.ndarray, tail: np.ndarray, h: int) -> np.ndarray:
    """
    构造第 h 步（0..23）的单步特征 [N, F]
    tail: [N, 24 + h] 归一化功率序列（前 24 列为历史实测，后 h 列为已推进步的功率）
    """
    hour = raw[:, h, 0]
    nwp_w = raw[:, h, 6]
    nwp_i = raw[:, h, 7]
    temp_mean = raw[:, :, 3].mean(axis=1)
    hum_mean = raw[:, :, 4].mean(axis=1)
    pres_mean = raw[:, :, 5].mean(axis=1)
    w_hist = raw[:, h, 1]
    i_hist = raw[:, h, 2]

    lags = [tail[:, -s] for s in LAG_STEPS]
    feats = [
        hour,
        np.sin(2 * math.pi * hour / 24.0),
        np.cos(2 * math.pi * hour / 24.0),
        np.sin(4 * math.pi * hour / 24.0),
        np.cos(4 * math.pi * hour / 24.0),
        nwp_w,
        nwp_w ** 2,
        nwp_i,
        w_hist,
        i_hist,
        temp_mean,
        hum_mean,
        pres_mean,
        *lags,
    ]
    return np.stack(feats, axis=-1).astype(np.float32)


def _build_supervised(raw: np.ndarray, y_norm: np.ndarray, cap: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """用 teacher-forcing 沿 24h 轨迹构造单步监督样本（仅使用严格早于当前步的滞后）"""
    hist_pwr = raw[:, :, 8] / cap  # [N, 24]
    full_seq = np.concatenate([hist_pwr, y_norm], axis=1)  # [N, 48]
    xs, ys = [], []
    for h in range(pstd.HORIZON):
        tail = full_seq[:, : 24 + h]
        xs.append(_step_features(raw, tail, h))
        ys.append(y_norm[:, h])
    return np.concatenate(xs, axis=0), np.concatenate(ys, axis=0)


def _rollout_predict(booster: lgb.Booster, raw: np.ndarray, cap: np.ndarray) -> np.ndarray:
    """自回归滚动 24 步：每步将预测结果追加至 tail，完全不访问未来真值"""
    tail = (raw[:, :, 8] / cap).astype(np.float32)  # [N, 24]
    preds = []
    for h in range(pstd.HORIZON):
        xf = _step_features(raw, tail, h)
        p = np.clip(booster.predict(xf, num_iteration=booster.best_iteration), 0.0, 1.0).astype(np.float32)
        preds.append(p)
        tail = np.concatenate([tail, p[:, None]], axis=1)
    return np.stack(preds, axis=1)


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

    raw_tr_l, y_tr_l, cap_tr_l, k_tr_l = [], [], [], []
    raw_va_l, y_va_l, cap_va_l, k_va_l, m_va_l = [], [], [], [], []

    for d in dirs:
        raw, y_mw, metas, specs = pstd.load_split(d, "train")
        cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
        Y = (y_mw / cap).astype(np.float32)
        kinds = np.array([s["kind"] for s in specs])
        mask = pstd.eval_mask(raw, specs)

        t0 = np.array([int(m["t0"]) for m in metas])
        val_start = t0.max() - (VAL_DAYS - 1) * 24
        val_idx = np.where(t0 >= val_start)[0]
        tr_idx = np.where(t0 < val_start - PURGE_DAYS * 24)[0]

        raw_tr_l.append(raw[tr_idx]); y_tr_l.append(Y[tr_idx]); cap_tr_l.append(cap[tr_idx]); k_tr_l.append(kinds[tr_idx])
        raw_va_l.append(raw[val_idx]); y_va_l.append(Y[val_idx]); cap_va_l.append(cap[val_idx]); k_va_l.append(kinds[val_idx]); m_va_l.append(mask[val_idx])

    raw_tr = np.concatenate(raw_tr_l); y_tr = np.concatenate(y_tr_l); cap_tr = np.concatenate(cap_tr_l); k_tr = np.concatenate(k_tr_l)
    raw_va = np.concatenate(raw_va_l); y_va = np.concatenate(y_va_l); cap_va = np.concatenate(cap_va_l); k_va = np.concatenate(k_va_l); m_va = np.concatenate(m_va_l)

    t_start = time.perf_counter()
    models: dict[str, lgb.Booster] = {}
    evals_res: dict[str, dict] = {}
    best_iters: dict[str, int] = {}

    for kind in pstd.KINDS:
        tr_sel = k_tr == kind
        va_sel = k_va == kind
        X_t, y_t = _build_supervised(raw_tr[tr_sel], y_tr[tr_sel], cap_tr[tr_sel])
        X_v, y_v = _build_supervised(raw_va[va_sel], y_va[va_sel], cap_va[va_sel])
        dtrain = lgb.Dataset(X_t, label=y_t)
        dval = lgb.Dataset(X_v, label=y_v, reference=dtrain)
        rec: dict = {}
        booster = lgb.train(
            dict(LGB_PARAMS),
            dtrain,
            num_boost_round=NUM_BOOST_ROUND,
            valid_sets=[dtrain, dval],
            valid_names=["train", "val"],
            callbacks=[lgb.early_stopping(30, verbose=False), lgb.record_evaluation(rec)],
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

    # 验证集真实自回归滚动评估
    vp = np.zeros_like(y_va)
    for kind in pstd.KINDS:
        sel = k_va == kind
        if sel.any():
            vp[sel] = _rollout_predict(models[kind], raw_va[sel], cap_va[sel])
    val_nrmse = float(np.sqrt(np.mean((vp - y_va)[m_va] ** 2)))
    val_acc = round(max(0.0, (1.0 - val_nrmse) * 100.0), 2)

    payload = {
        "algorithm_id": ALGO_ID,
        "version": "v1.0.0",
        "lag_steps": list(LAG_STEPS),
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
        "split": {"train_windows": int(len(raw_tr)), "val_windows": int(len(raw_va)), "val_days": VAL_DAYS, "purge_days": PURGE_DAYS},
        "history": history,
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[power-lgbm-autoreg] 训练完成：训练 {len(raw_tr)} / 验证 {len(raw_va)} 窗口，滚动验证准确率 {val_acc:.2f}%，迭代 {best_iters}，用时 {state['train_seconds']}s")
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
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
    kinds = np.array([s["kind"] for s in specs])
    out = np.zeros((len(raw), pstd.HORIZON), dtype=np.float32)

    for kind in pstd.KINDS:
        sel = kinds == kind
        if not sel.any():
            continue
        out[sel] = _rollout_predict(models[kind], raw[sel], cap[sel])
    return out * cap


if __name__ == "__main__":
    train()
