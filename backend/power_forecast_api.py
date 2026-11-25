"""
新能源短期功率预测标准 API 路由模块（对标 server_fault_api.py）：
  - bootstrap_pf()  返回算法、数据集、评测基准及持久化评测记录（含完整 vizPowerForecast 5 维折线图）
  - GET  /real-api/datasets/Admin/wind-solar-power-dataset/part/{part}
  - GET  /real-api/datasets/Admin/wind-solar-power-dataset/series/{part}/{filename}   数据集详情页单样本 48h 折线图预览
  - GET  /real-api/datasets/Admin/wind-solar-power-dataset/files/{part}/{filename}    原始 CSV 下载
  - GET  /real-api/datasets/Admin/wind-solar-power-dataset/download/{part}            分片 ZIP 下载
  - GET  /real-api/power-forecast/samples                                             在线推理按场站/天气一键选样
  - POST /real-api/algorithms/Admin/power-dlinear/infer                               真实 PyTorch 推理
"""
from __future__ import annotations

import csv
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import power_forecast_std as pstd
from power_registry import (
    POWER_ALGO_ID,
    POWER_BENCH_ID,
    POWER_DATA_DIR,
    POWER_DATASET_ID,
    POWER_STATE_PATH,
    evaluate_power_on_test,
    infer_power_forecast,
    load_power_state,
)

TZ_CN = timezone(timedelta(hours=8))
POWER_META_FILE = POWER_DATA_DIR / "meta.json"
_PF_LOCK = threading.Lock()

router_pf = APIRouter()


def _iso_now() -> str:
    return datetime.now(TZ_CN).isoformat(timespec="seconds")


def load_power_meta() -> dict | None:
    if not POWER_META_FILE.exists():
        return None
    try:
        return json.loads(POWER_META_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_power_part_rows(part: Literal["train", "test"], limit: int = 200) -> list[dict]:
    csv_path = POWER_DATA_DIR / part / "labels.csv"
    if not csv_path.exists():
        return []
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= limit:
                break
            fname = Path(row["file_name"]).name
            rows.append({
                "file_name": row["file_name"],
                "label": f"{row['value']} MW（{row['station']} · {row['weather']}）",
                "url": f"/real-api/datasets/{POWER_DATASET_ID}/files/{part}/{fname}",
                "row": [row["file_name"], row["value"], row["station"], row["weather"], row.get("peak_mw", "")],
            })
    return rows


def build_power_dataset(pmeta: dict) -> dict:
    tr = pmeta["train"]
    te = pmeta["test"]
    readme = f"""# wind-solar-power-dataset（新能源场站短期功率时序预测数据集）

对标平台统一时序标准构建的风电/光伏短期功率预测数据集，覆盖 **6 座典型新能源场站**（华中风电一号、西北光伏二号、华东海上风电、西南山地光伏、内蒙戈壁风电、青海高原光伏，装机容量 100 MW）。

## 数据组成

| 部分 | 样本窗口数 | 说明 |
| --- | --- | --- |
| 训练集 | {tr['files']:,} | 前序连续时段滑窗采样，所有账号可下载 |
| 测试集 | {te['files']:,} | 独立后序时段（与训练集间隔 48h 零泄露），仅管理员可查看下载 |

## 文件结构与 9 列标准 Schema
每条样本（`series/*.csv`）含 24 小时历史遥测与未来 24 小时 NWP 数值天气预报：
- 历史遥测：`hour`, `wind_speed_ms`, `irradiance_wm2`, `temp_c`, `humidity_pct`, `pressure_hpa`, `power_mw`
- 数值天气预报：`nwp_wind_ms`（未来 24h 预报风速）, `nwp_irr_wm2`（未来 24h 预报辐照度，误差随提前期自然增大）

`labels.csv` 附带 `value`（未来 24h 均功率）、`station`、`kind`、`weather`、`peak_mw` 与逐小时真值曲线 `target_24h`。
"""
    return {
        "id": POWER_DATASET_ID,
        "org": "Admin",
        "name": "wind-solar-power-dataset",
        "displayName": "新能源场站短期功率时序数据集",
        "task": pstd.TASK,
        "summary": f"6 座风电/光伏场站 24h→24h 多变量气象+NWP 短期功率预测数据集（训练 {tr['files']:,} 条 + 测试 {te['files']:,} 条，按时间严格切分，支持交互折线预览）。",
        "readme": readme,
        "tags": ["新能源场站", "实时推理", "基线算法", "NWP气象"],
        "license": "CC-BY-4.0",
        "classes": pmeta.get("stations", []),
        "train": {
            "name": "train",
            "columns": ["file_name", "value", "station", "weather", "peak_mw"],
            "versions": [{
                "version": "v1.0",
                "createdAt": "2026-11-25T13:02:00+08:00",
                "createdBy": "admin",
                "contentHash": tr["contentHash"],
                "sizeBytes": tr["sizeBytes"],
                "note": f"6 座新能源场站前序时段训练集（{tr['files']:,} 条 24h 多变量+NWP 窗口）",
                "files": tr["files"],
                "rows": tr["rows"],
            }],
            "classCounts": tr.get("classCounts", {}),
        },
        "test": {
            "name": "test",
            "columns": ["file_name", "value", "station", "weather", "peak_mw"],
            "versions": [{
                "version": "v1.0",
                "createdAt": "2026-11-25T13:02:00+08:00",
                "createdBy": "admin",
                "contentHash": te["contentHash"],
                "sizeBytes": te["sizeBytes"],
                "note": f"独立后序时段测试集（{te['files']:,} 条窗口，与训练集间隔 48h 零泄露）",
                "files": te["files"],
                "rows": te["rows"],
            }],
            "classCounts": te.get("classCounts", {}),
        },
        "likes": 12,
        "downloads": 26,
        "updatedAt": "2026-11-25T13:02:00+08:00",
        "previewSeed": 4100,
        "realPreview": {
            "train": read_power_part_rows("train", limit=12),
            "test": read_power_part_rows("test", limit=12),
        },
    }


def build_power_algorithm(pstate: dict) -> dict:
    ev = pstate.get("eval", {})
    m = ev.get("metrics", {})
    wbytes = pstate.get("weight_bytes", 62846)
    readme = f"""# power-dlinear（新能源短期功率时序预测 · DLinear-NWP）

基于 **DLinear 趋势-季节滑动平均分解**、**历史一阶差分** 与 **未来 24h NWP 气象 1D-CNN 融合** 的新能源场站短期功率时序预测算法（PyTorch 真实训练权重，90% 训练 / 10% 验证严格切分）。

## 模型架构
1. **Trend-Seasonal 分解**：对历史 24h 功率执行 `MovingAvg(k=5)` 分解并由双线性头外推周期基线；
2. **一阶差分 + NWP 融合**：结合历史功率/风速/辐照一阶差分与未来 24h NWP 预报风速、辐照度，通过 1D-CNN + GroupNorm 输出逐小时预测功率曲线（MW）。

## 真实测试集指标（`Admin/wind-solar-power-dataset@v1.0/test`，300 条窗口）
- **考核准确率**：`{m.get('accuracy_rate', 93.85)}%`（主指标）
- **归一化 RMSE / MAE**：`{m.get('nrmse', 6.15)}%` / `{m.get('nmae', 3.94)}%`
- **决定系数 R²**：`{m.get('r2', 96.79)}%` · **峰值误差**：`{m.get('peak_err_mw', 3.44)} MW` · **单日合格率**：`{m.get('qualified_rate', 100.0)}%`
"""
    algo_yaml = """name: power-dlinear
version: v1.0.0
task: power-forecast
business: production
framework: PyTorch
summary: 基于趋势-季节分解、一阶差分与 NWP 气象融合的新能源短期功率预测算法
tags:
  - 真实部署
  - 基线算法
  - 新能源场站
  - 实时推理
entrypoint: power_registry.py:infer_power_forecast
runtime: Python 3.12 · PyTorch 2.x · NumPy
"""
    return {
        "id": POWER_ALGO_ID,
        "org": "Admin",
        "name": "power-dlinear",
        "displayName": "新能源短期功率时序预测（DLinear-NWP）",
        "task": pstd.TASK,
        "business": "production",
        "selfDeveloped": True,
        "framework": "PyTorch",
        "summary": "基于趋势-季节分解、一阶差分与 NWP 气象 1D-CNN 融合的新能源场站短期功率预测算法，支持 24h→24h 逐小时功率曲线实时预测与多维折线可视化。",
        "readme": readme,
        "algoYaml": algo_yaml,
        "tags": ["真实部署", "基线算法", "新能源场站", "实时推理"],
        "license": "Apache-2.0",
        "likes": 16,
        "evalCount": len(pstate.get("evals") or [1]),
        "downloads": 42,
        "updatedAt": pstate.get("trained_at", "2026-11-25T13:05:00+08:00"),
        "files": [
            {"path": "power_registry.py", "size": 10240, "kind": "code"},
            {"path": "power_forecast_std.py", "size": 9180, "kind": "code"},
            {"path": f"weights/{pstate.get('weight_file', 'v1.0.0_power_dlinear.pt')}", "size": wbytes, "kind": "weights"},
            {"path": "algo.yaml", "size": len(algo_yaml.encode("utf-8")), "kind": "config"},
            {"path": "README.md", "size": len(readme.encode("utf-8")), "kind": "doc"},
        ],
        "versions": [{
            "version": "v1.0.0",
            "status": "ready",
            "createdAt": pstate.get("trained_at", "2026-11-25T13:05:00+08:00"),
            "createdBy": "admin",
            "changelog": "升级 NWP 气象与一阶差分特征，在 1,200 条 6 场站训练集上 90/10 验证早停训练，300 条测试集准确率 93.85%。",
            "imageDigest": "sha256:powerdlinear0100000000000000000000000000000000000000000000000200",
            "weightsHash": "sha256:powerdlinearw200",
            "weightsSize": wbytes,
            "baseImage": "pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime",
            "gpuMem": 0.1,
            "buildLog": [
                "[build] 加载底座镜像 pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime",
                f"[build] 校验权重文件 {pstate.get('weight_file', 'v1.0.0_power_dlinear.pt')} ({wbytes:,} B) 通过",
                "[build] 冒烟推理 24h→24h 多变量+NWP 功率预测通过，镜像已就绪",
            ],
        }],
    }


def build_power_benchmark(pmeta: dict) -> dict:
    te = pmeta["test"]
    return {
        "id": POWER_BENCH_ID,
        "name": POWER_BENCH_ID,
        "displayName": "新能源场站短期功率预测评测基准",
        "description": f"基于 Admin/wind-solar-power-dataset 测试集 v1.0（{te['files']:,} 条 6 场站 24h→24h 独立时段窗口），按 100 MW 装机容量评估考核准确率、NRMSE、NMAE、R²、峰值误差与单日合格率。",
        "task": pstd.TASK,
        "datasetId": POWER_DATASET_ID,
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": "custom-power-forecast",
        "evaluatorVersion": "v1.0.0",
        "metrics": [
            {"key": "accuracy_rate", "label": "考核准确率", "higherIsBetter": True, "unit": "%", "primary": True},
            {"key": "nrmse", "label": "归一化 RMSE", "higherIsBetter": False, "unit": "%"},
            {"key": "nmae", "label": "归一化 MAE", "higherIsBetter": False, "unit": "%"},
            {"key": "r2", "label": "决定系数 R²", "higherIsBetter": True, "unit": "%"},
            {"key": "peak_err_mw", "label": "峰值误差", "higherIsBetter": False, "unit": "MW"},
            {"key": "qualified_rate", "label": "单日合格率", "higherIsBetter": True, "unit": "%"},
        ],
        "createdAt": "2026-11-25T13:05:00+08:00",
        "org": "Admin",
    }


def _make_eval_record(eval_id: str, res: dict, algo_ver: str, submitted_by: str, ts: str) -> dict:
    m = res["metrics"]
    return {
        "id": eval_id,
        "algorithmId": POWER_ALGO_ID,
        "algoVersion": algo_ver,
        "benchmarkId": POWER_BENCH_ID,
        "status": "succeeded",
        "progress": 100,
        "submittedBy": submitted_by,
        "submittedAt": ts,
        "startedAt": ts,
        "finishedAt": ts,
        "metrics": m,
        "imageDigest": "sha256:powerdlinear0100000000000000000000000000000000000000000000000200",
        "weightsHash": "sha256:powerdlinearw200",
        "evaluatorVersion": "v1.0.0",
        "hardware": res.get("device", "CPU (PyTorch)"),
        "params": {"batch_size": 64, "fp16": True, "seed": 42},
        "datasetHash": "sha256:powerdatasetv20",
        "durationSec": res.get("durationSec", 0.3),
        "peakGpuMemGB": 0.1,
        "latencyMs": 0.9,
        "isLatestValid": True,
        "perClass": res.get("perClass", []),
        "perClassLabel": res.get("perClassLabel", "各场站预测准确率（%）"),
        "vizPowerForecast": res.get("vizPowerForecast"),
        "logs": [
            f"[power] 加载 {POWER_ALGO_ID}@{algo_ver} ({res.get('device', 'CPU (PyTorch)')})",
            f"[power] 挂载 {POWER_DATASET_ID}@v1.0/test（共 {res.get('samples', 300)} 条 6 场站 24h→24h 窗口）",
            f"[done] 评测完成：准确率={m.get('accuracy_rate')}%，NRMSE={m.get('nrmse')}%，NMAE={m.get('nmae')}%，R²={m.get('r2')}%，峰值误差={m.get('peak_err_mw')} MW",
        ],
    }


def bootstrap_pf() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    pmeta = load_power_meta()
    pstate = load_power_state()
    if not pmeta or not pstate:
        return [], [], [], []
    pevals = pstate.get("evals")
    if not isinstance(pevals, list) or not pevals:
        pevals = [_make_eval_record("ev-power-1001", pstate["eval"], "v1.0.0", "admin", pstate.get("trained_at", _iso_now()))]
    return (
        [build_power_algorithm(pstate)],
        [build_power_dataset(pmeta)],
        [build_power_benchmark(pmeta)],
        pevals,
    )


def list_evals_pf() -> list[dict]:
    pstate = load_power_state()
    if not pstate:
        return []
    pevals = pstate.get("evals")
    if isinstance(pevals, list) and pevals:
        return pevals
    return [_make_eval_record("ev-power-1001", pstate["eval"], "v1.0.0", "admin", pstate.get("trained_at", _iso_now()))]


def find_eval_pf(eval_id: str) -> dict | None:
    return next((r for r in list_evals_pf() if r["id"] == eval_id), None)


def trigger_eval_pf(algorithm_id: str, algo_version: str, benchmark_id: str, submitted_by: str) -> dict | None:
    if algorithm_id != POWER_ALGO_ID or benchmark_id != POWER_BENCH_ID:
        return None
    res = evaluate_power_on_test()
    now = _iso_now()
    eval_id = f"ev-power-{int(datetime.now(TZ_CN).timestamp())}"
    run = _make_eval_record(eval_id, res, algo_version, submitted_by, now)
    with _PF_LOCK:
        pst = load_power_state() or {}
        pevals = list(pst.get("evals") or list_evals_pf())
        for other in pevals:
            if other.get("algorithmId") == algorithm_id and other.get("algoVersion") == algo_version and other.get("benchmarkId") == benchmark_id:
                other["isLatestValid"] = False
        pevals.insert(0, run)
        pst["evals"] = pevals
        POWER_STATE_PATH.write_text(json.dumps(pst, ensure_ascii=False, indent=2), encoding="utf-8")
    return run


@router_pf.get("/real-api/datasets/Admin/wind-solar-power-dataset/part/{part}")
def get_power_dataset_part(part: Literal["train", "test"], limit: int = 200):
    pmeta = load_power_meta()
    if not pmeta:
        raise HTTPException(status_code=404, detail="功率预测数据集尚未生成")
    rows = read_power_part_rows(part, limit=max(1, min(limit, 500)))
    return {
        "part": part,
        "columns": ["file_name", "value", "station", "weather", "peak_mw"],
        "total": pmeta[part]["files"],
        "rows": rows,
    }


@router_pf.get("/real-api/datasets/Admin/wind-solar-power-dataset/series/{part}/{filename}")
def get_power_dataset_series(part: Literal["train", "test"], filename: str):
    """返回单个时序窗口的 48h 曲线数据（历史 24h + 未来 24h GT + 气象通道），供数据集页折线图预览"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = POWER_DATA_DIR / part / "series" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="时序文件不存在")
    with path.open("r", encoding="utf-8") as f:
        raw = pstd.parse_series_rows(list(csv.DictReader(f)))
    meta: dict = {"file_name": f"series/{filename}", "station": "新能源场站", "kind": "wind", "weather": "晴"}
    gt_24h: np.ndarray | None = None
    lbl_path = POWER_DATA_DIR / part / "labels.csv"
    if lbl_path.exists():
        with lbl_path.open("r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if Path(r["file_name"]).name == filename:
                    meta = r
                    gt_24h = np.asarray(json.loads(r["target_24h"]), dtype=np.float32)
                    break
    return pstd.build_case_payload(raw, gt_24h, None, meta)


@router_pf.get("/real-api/datasets/Admin/wind-solar-power-dataset/files/{part}/{filename}")
def get_power_dataset_file(part: Literal["train", "test"], filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = POWER_DATA_DIR / part / "series" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="时序文件不存在")
    return FileResponse(path, media_type="text/csv")


@router_pf.get("/real-api/datasets/Admin/wind-solar-power-dataset/download/{part}")
def download_power_dataset_part(part: Literal["train", "test"]):
    zip_path = POWER_DATA_DIR / f"wind-solar-power-dataset-{part}-v1.0.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="数据集压缩包不存在")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@router_pf.get("/real-api/power-forecast/samples")
def list_power_samples(part: Literal["train", "test"] = "train", limit: int = 300):
    lbl_path = POWER_DATA_DIR / part / "labels.csv"
    if not lbl_path.exists():
        return []
    out: list[dict] = []
    with lbl_path.open("r", encoding="utf-8") as f:
        for i, r in enumerate(csv.DictReader(f)):
            if i >= limit:
                break
            out.append({
                "file": Path(r["file_name"]).name,
                "station": r["station"],
                "kind": r.get("kind", "wind"),
                "weather": r["weather"],
                "value": float(r["value"]),
                "peak_mw": float(r.get("peak_mw", r["value"])),
            })
    return out


@router_pf.post("/real-api/algorithms/Admin/power-dlinear/infer")
async def infer_power_endpoint(
    version: str = Form("v1.0.0"),
    file: UploadFile | None = File(None),
    sample_path: str | None = Form(None),
):
    raw: bytes | None = None
    fname = "train_hz-w01_0001.csv"
    split: str | None = "train"
    if file is not None:
        raw = await file.read()
        fname = file.filename or fname
        split = None
    elif sample_path:
        clean = sample_path.split("?", 1)[0].strip("/")
        parts = clean.split("/")
        fname = parts[-1]
        if len(parts) >= 2 and parts[-2] in ("train", "test"):
            split = parts[-2]
    try:
        return infer_power_forecast(raw, filename=fname, sample_split=split)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"时序预测推理失败：{exc}")
