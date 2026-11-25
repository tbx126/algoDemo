"""
新能源短期功率预测算法（Admin/power-lgbm-direct）—— 源自压缩包 province_45_power_forecast.py 的 LightGBM 分时直推架构

  - 模型：风电 / 光伏双 LightGBM GBDT 回归模型（model_to_string UTF-8 落盘，兼容 Windows 任意路径）
  - 特征：周期时间正余弦编码 + 次日 NWP 气象（含相邻时段上下文与风速三次方代理）+ 历史实测滞后与统计特征
  - 改进：修复原脚本历史风速由功率反推导致的数据泄露问题，严格按时间切分训练/验证集（隔离 2 天）
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
STATE_PATH = ROOT / "state" / "power_lgbm_direct_state.json"
WEIGHT_PATH = MODEL_DIR / "v1.0.0_power_lgbm_direct.lgb.json"
CODE_PATH = Path(__file__).resolve()

ALGO_ID = "Admin/power-lgbm-direct"
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
    "name": "power-lgbm-direct",
    "displayName": "新能源功率预测（LightGBM 分时直推）",
    "framework": "LightGBM",
    "runtime": "Python 3.12 · LightGBM 4.x · NumPy",
    "gpuMem": 0.0,
    "summary": "基于中电建 LightGBM 方案改造的风/光双模型分时直推算法：周期时间编码 + NWP 气象上下文 + 历史功率滞后特征。",
    "tags": ["LightGBM", "新能源场站", "NWP气象", "实时推理"],
    "business": "production",
    "codeFile": "power_lgbm_direct.py",
    "likes": 11,
    "downloads": 28,
    "changelog": "基于 province_45_power_forecast.py 的 LightGBM 回归与周期时间编码改造，修复目标泄露，适配平台 power-forecast 标准接口并在双数据集训练集上联合训练。",
    "readme": """# power-lgbm-direct（新能源功率预测 · LightGBM 分时直推）

源自压缩包 `province_45_power_forecast.py` 的 LightGBM 梯度提升树方案，针对平台**新能源短期功率预测标准**（24h 日前逐小时）进行无泄露改造与分时直推封装。

## 特征与模型设计

- **风电 / 光伏双模型**：遵循原脚本 `lgb_wind_model` / `lgb_solar_model` 分离建模思路，分别拟合风电非线性功率曲线与光伏昼夜辐射响应。
- **周期时间编码**：保留原脚本的 `sin/cos` 周期编码（1 倍频 + 2 倍频小时相位），刻画日内出力节律。
- **NWP 气象与物理代理**：使用次日目标时刻 `h` 及相邻 `h-1 / h+1` 的 NWP 风速、辐照度、风速三次方 `v³` 与全天 NWP 均值/峰值。
- **历史滞后与实况背景**：融合前一天同时刻功率（`t-24h`）、发布前最近 3 小时功率、历史日均值/标准差以及前一日温湿压实况。

## 相对原脚本的修复

1. 移除「由历史真实功率反推风速」的训练目标泄露；
2. 严格按时间切分验证集（尾部 20 天，隔离 2 天），以验证集 RMSE 早停选优；
3. 光伏夜间（考核时段外且 NWP 辐照度 ≈ 0）出力置零；
4. 权重通过 `model_to_string()` 统一保存为 UTF-8 JSON，实现秒级加载与纯 CPU 毫秒级批量推理。
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


def _build_features(raw: np.ndarray, specs: list[dict]) -> np.ndarray:
    """[N, 24, 9] -> [N, 24, F] 表格特征（全为预测发布时刻可得的合法特征）"""
    raw = np.asarray(raw, dtype=np.float32)
    N, H, _ = raw.shape
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]

    hour = raw[:, :, 0]
    w_hist = raw[:, :, 1]
    i_hist = raw[:, :, 2]
    temp = raw[:, :, 3]
    hum = raw[:, :, 4]
    pres = raw[:, :, 5]
    nwp_w = raw[:, :, 6]
    nwp_i = raw[:, :, 7]
    pwr = raw[:, :, 8] / cap

    # 相邻时刻 NWP 上下文（边缘复制填充）
    nwp_w_prev = np.concatenate([nwp_w[:, :1], nwp_w[:, :-1]], axis=1)
    nwp_w_next = np.concatenate([nwp_w[:, 1:], nwp_w[:, -1:]], axis=1)
    nwp_i_prev = np.concatenate([nwp_i[:, :1], nwp_i[:, :-1]], axis=1)
    nwp_i_next = np.concatenate([nwp_i[:, 1:], nwp_i[:, -1:]], axis=1)

    # 发布前最后 3 个实测时刻与全天统计（广播到 24h）
    last1 = np.broadcast_to(pwr[:, 23:24], (N, H))
    last2 = np.broadcast_to(pwr[:, 22:23], (N, H))
    last3 = np.broadcast_to(pwr[:, 21:22], (N, H))
    pwr_mean = np.broadcast_to(pwr.mean(axis=1, keepdims=True), (N, H))
    pwr_std = np.broadcast_to(pwr.std(axis=1, keepdims=True), (N, H))
    pwr_max = np.broadcast_to(pwr.max(axis=1, keepdims=True), (N, H))
    nwp_w_mean = np.broadcast_to(nwp_w.mean(axis=1, keepdims=True), (N, H))
    nwp_i_max = np.broadcast_to(nwp_i.max(axis=1, keepdims=True), (N, H))

    feats = [
        hour,
        np.sin(2 * math.pi * hour / 24.0),
        np.cos(2 * math.pi * hour / 24.0),
        np.sin(4 * math.pi * hour / 24.0),
        np.cos(4 * math.pi * hour / 24.0),
        nwp_w,
        nwp_w ** 2,
        nwp_w ** 3,
        nwp_w_prev,
        nwp_w_next,
        nwp_w - nwp_w_prev,
        nwp_w_mean,
        nwp_i,
        nwp_i_prev,
        nwp_i_next,
        nwp_i - nwp_i_prev,
        nwp_i_max,
        w_hist,
        i_hist,
        temp,
        hum,
        pres,
        pwr,
        last1,
        last2,
        last3,
        pwr_mean,
        pwr_std,
        pwr_max,
    ]
    return np.stack(feats, axis=-1).astype(np.float32)


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

    X_tr_list, y_tr_list, k_tr_list = [], [], []
    X_va_list, y_va_list, k_va_list, m_va_list, raw_va_list = [], [], [], [], []
    tr_wins = va_wins = 0

    for d in dirs:
        raw, y_mw, metas, specs = pstd.load_split(d, "train")
        X = _build_features(raw, specs)
        cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
        Y = (y_mw / cap).astype(np.float32)
        kinds = np.array([s["kind"] for s in specs])
        mask = pstd.eval_mask(raw, specs)

        t0 = np.array([int(m["t0"]) for m in metas])
        val_start = t0.max() - (VAL_DAYS - 1) * 24
        val_idx = np.where(t0 >= val_start)[0]
        tr_idx = np.where(t0 < val_start - PURGE_DAYS * 24)[0]
        tr_wins += len(tr_idx)
        va_wins += len(val_idx)

        X_tr_list.append(X[tr_idx])
        y_tr_list.append(Y[tr_idx])
        k_tr_list.append(kinds[tr_idx])

        X_va_list.append(X[val_idx])
        y_va_list.append(Y[val_idx])
        k_va_list.append(kinds[val_idx])
        m_va_list.append(mask[val_idx])
        raw_va_list.append(raw[val_idx])

    X_tr = np.concatenate(X_tr_list, axis=0)
    y_tr = np.concatenate(y_tr_list, axis=0)
    k_tr = np.concatenate(k_tr_list, axis=0)
    X_va = np.concatenate(X_va_list, axis=0)
    y_va = np.concatenate(y_va_list, axis=0)
    k_va = np.concatenate(k_va_list, axis=0)
    m_va = np.concatenate(m_va_list, axis=0)
    raw_va = np.concatenate(raw_va_list, axis=0)

    t_start = time.perf_counter()
    models: dict[str, lgb.Booster] = {}
    evals_res: dict[str, dict] = {}
    best_iters: dict[str, int] = {}

    for kind in pstd.KINDS:
        tr_sel = k_tr == kind
        va_sel = k_va == kind
        dtrain = lgb.Dataset(X_tr[tr_sel].reshape(-1, X_tr.shape[-1]), label=y_tr[tr_sel].reshape(-1))
        dval = lgb.Dataset(X_va[va_sel].reshape(-1, X_va.shape[-1]), label=y_va[va_sel].reshape(-1), reference=dtrain)
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

    # 汇总训练曲线（合并风电/光伏验证 RMSE）
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

    # 验证集综合准确率（按考核时段）
    vp = np.zeros_like(y_va)
    for kind in pstd.KINDS:
        sel = k_va == kind
        if sel.any():
            p = models[kind].predict(X_va[sel].reshape(-1, X_va.shape[-1]), num_iteration=models[kind].best_iteration)
            vp[sel] = np.clip(p.reshape(-1, pstd.HORIZON), 0.0, 1.0)
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
    print(f"[power-lgbm-direct] 训练完成：训练 {tr_wins} / 验证 {va_wins} 窗口，验证准确率 {val_acc:.2f}%，迭代 {best_iters}，用时 {state['train_seconds']}s")
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
    X = _build_features(raw, specs)
    cap = np.array([s["capacity_mw"] for s in specs], dtype=np.float32)[:, None]
    kinds = np.array([s["kind"] for s in specs])
    out = np.zeros((len(raw), pstd.HORIZON), dtype=np.float32)

    for kind in pstd.KINDS:
        sel = kinds == kind
        if not sel.any():
            continue
        p = models[kind].predict(X[sel].reshape(-1, X.shape[-1]))
        out[sel] = np.clip(p.reshape(-1, pstd.HORIZON), 0.0, 1.0)
    return _apply_solar_night_mask(out, np.asarray(raw, dtype=np.float32), kinds) * cap


def _apply_solar_night_mask(pred_norm: np.ndarray, raw: np.ndarray, kinds: np.ndarray) -> np.ndarray:
    """光伏：考核时段之外且 NWP 辐照度 ≈ 0 的夜间时刻出力置零（只依赖输入，不看真值）"""
    hours = np.rint(raw[:, :, 0]).astype(int) % 24
    night = (kinds == "solar")[:, None] & ~np.isin(hours, list(pstd.SOLAR_EVAL_HOURS)) & (raw[:, :, 7] <= 2.0)
    out = pred_norm.copy()
    out[night] = 0.0
    return out


if __name__ == "__main__":
    train()
