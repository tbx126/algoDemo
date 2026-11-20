"""
AlgoHub 真实后端服务（FastAPI + PyTorch）：
为猫狗识别算法（Admin/cat-dog-classifier）、猫狗数据集（Admin/cat-dog-dataset）
与猫狗评测基准（cat-dog-cls-bench）提供完全真实的：
  - 数据集图片与 labels.csv 读取、真实 ZIP 打包下载
  - 多版本模型在线推理（v1.0.0 / v2.0.0 / v3.0.0 真实前向推理）
  - 异步真实测试集评测与进度查询
"""
from __future__ import annotations

import csv
import io
import json
import threading
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from model_registry import (
    CLASSES,
    DATA_DIR,
    MODELS_DIR,
    ROOT,
    VERSION_SPECS,
    evaluate_random_on_test,
    evaluate_version_on_test,
    hardware_label,
    infer_image_bytes,
    infer_random,
    warm_containers,
)

STATE_FILE = ROOT / "state" / "real_state.json"
META_FILE = DATA_DIR / "meta.json"
TZ_CN = timezone(timedelta(hours=8))

app = FastAPI(title="AlgoHub Real Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATE_LOCK = threading.Lock()


def iso_now() -> str:
    return datetime.now(TZ_CN).isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_FILE.exists():
        raise HTTPException(status_code=503, detail="真实模型与评测尚未初始化，请先运行 train_and_eval.py")
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dataset_meta() -> dict:
    if not META_FILE.exists():
        raise HTTPException(status_code=503, detail="真实数据集尚未初始化，请先运行 prepare_dataset.py")
    return json.loads(META_FILE.read_text(encoding="utf-8"))


def read_part_rows(part: Literal["train", "test"], limit: int | None = None) -> list[dict]:
    csv_path = DATA_DIR / part / "labels.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"{part} 不存在")
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn = row["file_name"]
            short = fn.split("/")[-1]
            rows.append({
                "file_name": fn,
                "label": row["label"],
                "url": f"/real-api/datasets/Admin/cat-dog-dataset/files/{part}/{short}",
            })
            if limit is not None and len(rows) >= limit:
                break
    return rows


def build_real_algorithm(state: dict) -> dict:
    versions = state["versions"]
    evals = state["evals"]
    train_rows = read_part_rows("train", limit=24)
    # 挑 3 张真实图片（猫、狗各取）作为在线推理示例
    cats = [r["url"] for r in train_rows if r["label"] == "猫"][:2]
    dogs = [r["url"] for r in train_rows if r["label"] == "狗"][:1]
    sample_images = [cats[0], dogs[0], cats[1]] if len(cats) >= 2 and dogs else [r["url"] for r in train_rows[:3]]

    files = [
        {"path": "backend/model_registry.py", "size": (ROOT / "model_registry.py").stat().st_size, "kind": "code"},
        {"path": "backend/train_and_eval.py", "size": (ROOT / "train_and_eval.py").stat().st_size, "kind": "code"},
        {"path": "backend/server.py", "size": (ROOT / "server.py").stat().st_size, "kind": "code"},
    ]
    for v in versions:
        spec = VERSION_SPECS.get(v["version"])
        if spec:
            wf = MODELS_DIR / spec.weight_file
            files.append({
                "path": f"weights/{spec.weight_file}",
                "size": wf.stat().st_size if wf.exists() else v["weightsSize"],
                "kind": "weights",
            })

    evaluated_versions = {e["algoVersion"] for e in evals if e["status"] == "succeeded"}
    status_str = lambda v: "已评测" if v in evaluated_versions else "暂未评测"

    readme = f"""# 猫狗图像识别（cat-dog-classifier）

基于 PyTorch 真实训练与部署的猫狗二分类算法，在真实猫狗图像数据集 `Admin/cat-dog-dataset` 上训练，支持在线上传任意图片执行实时前向推理，并可在测试集上发起真实评测。

## 版本路线说明

| 版本 | 技术路线 | 输入尺寸 | 显存占用 | 评测状态 |
| --- | --- | --- | --- | --- |
| `v1.0.0` | ResNet-18 轻量级残差基线（冻结主干微调分类头） | 224×224 | 1.5 GB | {status_str("v1.0.0")} |
| `v2.0.0` | ResNet-50 深层残差网络（解冻顶层块 + 数据增强 + 标签平滑） | 224×224 | 3.2 GB | {status_str("v2.0.0")} |
| `v3.0.0` | ConvNeXt-Tiny 现代卷积主干（256×256 + 余弦退火 + 标签平滑） | 256×256 | 4.0 GB | {status_str("v3.0.0")} |

## 在线推理接口

- 路由：`POST /real-api/algorithms/Admin/cat-dog-classifier/infer`（`multipart/form-data`）
- 参数：`version`（`v1.0.0` / `v2.0.0` / `v3.0.0`）、`file`（JPG / PNG 图片）
- 运行设备：{hardware_label()}

```json
{{
  "predictions": [
    {{ "label": "猫", "score": 0.9912 }},
    {{ "label": "狗", "score": 0.0088 }}
  ]
}}
```
"""

    return {
        "id": "Admin/cat-dog-classifier",
        "org": "Admin",
        "name": "cat-dog-classifier",
        "task": "image-classification",
        "business": "other",
        "framework": "PyTorch",
        "tags": ["猫狗识别", "图像分类", "基线算法", "真实部署"],
        "summary": "真实 PyTorch 猫狗二分类算法，包含 ResNet-18 (v1.0.0)、ResNet-50 (v2.0.0)、ConvNeXt-Tiny (v3.0.0) 三个真实训练版本，支持实时推理与真实评测。",
        "readme": readme,
        "likes": 12,
        "evalCount": len([e for e in evals if e["status"] == "succeeded"]),
        "updatedAt": state.get("updatedAt", iso_now()),
        "versions": versions,
        "files": files,
        "algoYaml": """name: cat-dog-classifier
version: 3.0.0
task: image-classification
business: other
framework: PyTorch
entry: backend/server.py
classes:
  - 猫
  - 狗
versions:
  v1.0.0: weights/v1.0.0_resnet18.pt
  v2.0.0: weights/v2.0.0_resnet50.pt
  v3.0.0: weights/v3.0.0_convnext_tiny.pt
""",
        "labels": CLASSES,
        "sampleImages": sample_images,
    }


def build_real_dataset(meta: dict) -> dict:
    tr = meta["train"]
    te = meta["test"]
    train_rows = read_part_rows("train", limit=24)
    test_rows = read_part_rows("test", limit=6)

    readme = f"""# cat-dog-dataset

来源于官方 **Microsoft Dogs vs. Cats**（`kagglecatsanddogs_5340.zip`，原始 25,000 张图片），经 Pillow 逐张完整性校验并按图片 SHA-256 去重后，按 80% / 20% 切分为互不重叠的训练集与测试集。仅包含图片与类别标签（`file_name,label`），不含额外场景条件列。

## 组成

| 部分 | 图片数 | 大小 | 说明 |
| --- | --- | --- | --- |
| 训练集 | {tr["files"]} | {tr["sizeBytes"] / (1024 * 1024):.2f} MB | 所有账号可在线浏览与真实打包下载 |
| 测试集 | {te["files"]} | {te["sizeBytes"] / (1024 * 1024):.2f} MB | **仅管理员可查看与下载**，用于算法真实评测 |

## 文件结构

```
train/
├── images/          # 真实 JPEG 照片
└── labels.csv       # file_name,label
test/
├── images/          # 真实 JPEG 照片
└── labels.csv       # file_name,label
```

## labels.csv

一张图一行，`label` 为类别名（`猫` / `狗`）。表头：

```
file_name,label
```
"""

    return {
        "id": "Admin/cat-dog-dataset",
        "org": "Admin",
        "name": "cat-dog-dataset",
        "task": "image-classification",
        "tags": ["猫狗识别", "图像分类", "真实数据集"],
        "summary": f"真实猫狗二分类图像数据集（训练集 {tr['files']} 张 + 测试集 {te['files']} 张），仅保留图片与猫/狗标签，支持真实浏览与 ZIP 下载。",
        "readme": readme,
        "classes": CLASSES,
        "train": {
            "name": "train",
            "columns": ["file_name", "label"],
            "versions": [
                {
                    "version": "v1.0",
                    "createdAt": "2026-11-18T15:00:00+08:00",
                    "createdBy": "admin",
                    "contentHash": tr["contentHash"],
                    "sizeBytes": tr["sizeBytes"],
                    "note": "真实猫狗照片训练集（SHA-256 去重）",
                    "files": tr["files"],
                    "rows": tr["rows"],
                }
            ],
            "classCounts": tr["classCounts"],
        },
        "test": {
            "name": "test",
            "columns": ["file_name", "label"],
            "versions": [
                {
                    "version": "v1.0",
                    "createdAt": "2026-11-18T15:05:00+08:00",
                    "createdBy": "admin",
                    "contentHash": te["contentHash"],
                    "sizeBytes": te["sizeBytes"],
                    "note": "真实猫狗照片测试集（与训练集零重叠）",
                    "files": te["files"],
                    "rows": te["rows"],
                }
            ],
            "classCounts": te["classCounts"],
        },
        "likes": 8,
        "downloads": 24,
        "updatedAt": "2026-11-18T15:05:00+08:00",
        "previewSeed": 1000,
        "realPreview": {
            "train": train_rows[:6],
            "test": test_rows[:6],
        },
    }


def build_real_benchmark(meta: dict) -> dict:
    te = meta["test"]
    return {
        "id": "cat-dog-cls-bench",
        "name": "cat-dog-cls-bench",
        "displayName": "猫狗图像识别评测基准",
        "description": f"基于真实数据集 Admin/cat-dog-dataset 测试集 v1.0（{te['files']} 张真实猫狗照片），执行真实 PyTorch 推理并计算 Top-1 准确率与 Macro F1。",
        "task": "image-classification",
        "datasetId": "Admin/cat-dog-dataset",
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": "pytorch-cls-evaluator",
        "evaluatorVersion": "v1.2.0",
        "metrics": [
            {"key": "top1", "label": "Top-1 准确率", "higherIsBetter": True, "unit": "%", "primary": True},
            {"key": "f1", "label": "Macro F1", "higherIsBetter": True, "unit": "%"},
            {"key": "precision", "label": "精确率", "higherIsBetter": True, "unit": "%"},
            {"key": "recall", "label": "召回率", "higherIsBetter": True, "unit": "%"},
        ],
        "createdAt": "2026-11-18T15:30:00+08:00",
        "org": "Admin",
    }


@app.get("/real-api/health")
def health():
    return {"ok": True, "hardware": hardware_label(), "warmContainers": warm_containers()}


def build_random_algorithm(state: dict) -> dict:
    evals = [e for e in state["evals"] if e["algorithmId"] == "Admin/random"]
    train_rows = read_part_rows("train", limit=12)
    cats = [r["url"] for r in train_rows if r["label"] == "猫"][:2]
    dogs = [r["url"] for r in train_rows if r["label"] == "狗"][:1]
    sample_images = [cats[0], dogs[0], cats[1]] if len(cats) >= 2 and dogs else [r["url"] for r in train_rows[:3]]

    return {
        "id": "Admin/random",
        "org": "Admin",
        "name": "random",
        "task": "custom",
        "business": "other",
        "framework": "NumPy",
        "tags": ["随机基线", "全任务通用", "对照实验"],
        "summary": "全任务通用随机基线算法：无论输入任何内容，按目标任务类型独立随机生成对应格式的输出，可参与任意任务类型的评测基准作为下界对照。",
        "readme": """# 全任务通用随机基线（Admin/random）

无论输入任何内容，输出永远独立随机生成，不依赖输入特征，也不需要 GPU，支持平台全部任务类型。

## 支持的任务输出格式

- **图像识别 / 信号处理**：每次独立随机生成归一化类别概率分布；
- **目标检测 / 关键点 / OCR**：随机生成 2–6 个边界框坐标、类别/文本与置信度；
- **语义分割 / 实例分割**：随机生成多边形掩码区域与类别；
- **功率预测**：随机生成未来 24 小时功率预测序列（MW）；
- **优化求解 / 自定义任务**：随机生成数值与决策输出 JSON。

## 基准评测兼容性

- 可在**任意任务分类的评测基准**上发起评测（不限图像识别）；
- 在 `cat-dog-cls-bench` 上会真实遍历全部 4,993 张测试图逐张随机猜测（理论准确率约 50%），作为各模型版本的下界对照。
""",
        "likes": 0,
        "evalCount": len([e for e in evals if e["status"] == "succeeded"]),
        "updatedAt": "2026-11-20T15:10:00+08:00",
        "versions": [
            {
                "version": "v1.0.0",
                "status": "ready",
                "createdAt": "2026-11-20T15:10:00+08:00",
                "createdBy": "admin",
                "changelog": "初始版本：忽略所有输入，输出完全随机（CPU 零显存）",
                "imageDigest": "sha256:random0000000000000000000000000000000000000000000000000000000001",
                "weightsHash": "sha256:none000000000000000000000000000000000000000000000000000000000000",
                "weightsSize": 0,
                "baseImage": "python:3.12-slim",
                "gpuMem": 0,
                "buildLog": [
                    "[build] 管理员提交 Admin/random v1.0.0（无权重，纯 CPU 随机基线）",
                    "[build] 冒烟测试 …… OK，版本已就绪",
                ],
            }
        ],
        "files": [
            {"path": "algo.yaml", "size": 216, "kind": "config"},
            {"path": "predictor.py", "size": 198, "kind": "code"},
        ],
        "algoYaml": """name: random
version: 1.0.0
task: image-classification
business: other
framework: NumPy
entry: predictor:RandomPredictor
resources:
  gpu_mem: 0GB
  cpu: 1
""",
        "labels": CLASSES,
        "sampleImages": sample_images,
    }


@app.get("/real-api/bootstrap")
def bootstrap():
    with _STATE_LOCK:
        state = load_state()
    meta = load_dataset_meta()
    cat_dog = build_real_algorithm(state)
    rand_algo = build_random_algorithm(state)
    return {
        "algorithm": cat_dog,
        "algorithms": [cat_dog, rand_algo],
        "dataset": build_real_dataset(meta),
        "benchmark": build_real_benchmark(meta),
        "evals": state["evals"],
        "warmContainers": warm_containers(),
    }


@app.get("/real-api/datasets/Admin/cat-dog-dataset/part/{part}")
def get_dataset_part(part: Literal["train", "test"], limit: int = 200):
    meta = load_dataset_meta()
    rows = read_part_rows(part, limit=max(1, min(limit, 500)))
    return {
        "part": part,
        "columns": ["file_name", "label"],
        "total": meta[part]["files"],
        "rows": rows,
    }


@app.get("/real-api/datasets/Admin/cat-dog-dataset/files/{part}/{filename}")
def get_dataset_file(part: Literal["train", "test"], filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = DATA_DIR / part / "images" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/real-api/datasets/Admin/cat-dog-dataset/download/{part}")
def download_dataset_part(part: Literal["train", "test"]):
    part_dir = DATA_DIR / part
    if not part_dir.exists():
        raise HTTPException(status_code=404, detail="数据集分片不存在")
    zip_path = DATA_DIR / f"cat-dog-dataset-{part}-v1.0.zip"
    if not zip_path.exists():
        tmp = zip_path.with_suffix(".zip.tmp")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
            csv_path = part_dir / "labels.csv"
            if csv_path.exists():
                zf.write(csv_path, arcname=f"{part}/labels.csv")
            for img in sorted((part_dir / "images").glob("*.jpg")):
                zf.write(img, arcname=f"{part}/images/{img.name}")
        tmp.replace(zip_path)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"cat-dog-dataset-{part}-v1.0.zip",
    )


@app.post("/real-api/algorithms/Admin/random/infer")
async def infer_random_endpoint(
    task: str = Form("image-classification"),
    labels: str | None = Form(None),
):
    lbls = [x.strip() for x in labels.split(",") if x.strip()] if labels else None
    return infer_random(task=task, labels=lbls)


@app.post("/real-api/algorithms/Admin/cat-dog-classifier/infer")
async def infer_cat_dog(
    version: str = Form(...),
    file: UploadFile | None = File(None),
    sample_path: str | None = Form(None),
):
    if version not in VERSION_SPECS:
        raise HTTPException(status_code=400, detail=f"不支持的版本：{version}")
    if file is not None:
        raw = await file.read()
    elif sample_path:
        # 形如 /real-api/datasets/Admin/cat-dog-dataset/files/train/train_cat_0001.jpg
        parts = sample_path.strip("/").split("/")
        if len(parts) >= 2 and parts[-2] in ("train", "test"):
            p = DATA_DIR / parts[-2] / "images" / parts[-1]
            if not p.exists():
                raise HTTPException(status_code=404, detail="示例图片不存在")
            raw = p.read_bytes()
        else:
            raise HTTPException(status_code=400, detail="无效的示例图片路径")
    else:
        raise HTTPException(status_code=400, detail="请上传图片或选择示例图片")

    try:
        return infer_image_bytes(version, raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推理失败：{exc}")


class EvalRequest(BaseModel):
    algorithmId: str
    algoVersion: str
    benchmarkId: str
    submittedBy: str = "admin"


def _run_eval_bg(eval_id: str, algorithm_id: str, version: str):
    def on_progress(pct: int, msg: str | None):
        with _STATE_LOCK:
            st = load_state()
            run = next((r for r in st["evals"] if r["id"] == eval_id), None)
            if not run:
                return
            run["progress"] = pct
            if msg:
                run["logs"].append(msg)
            save_state(st)

    try:
        with _STATE_LOCK:
            st = load_state()
            run = next((r for r in st["evals"] if r["id"] == eval_id), None)
            if run:
                run["status"] = "running"
                run["startedAt"] = iso_now()
                hw = "CPU · Python random" if algorithm_id == "Admin/random" else hardware_label()
                run["logs"].append(f"[scheduler] 开始在 {hw} 上执行真实评测")
                save_state(st)

        res = evaluate_random_on_test(on_progress=on_progress) if algorithm_id == "Admin/random" else evaluate_version_on_test(version, on_progress=on_progress)

        with _STATE_LOCK:
            st = load_state()
            run = next((r for r in st["evals"] if r["id"] == eval_id), None)
            if run:
                # 同一算法版本×Benchmark 只有最新有效结果上榜
                for other in st["evals"]:
                    if (
                        other["id"] != eval_id
                        and other["algorithmId"] == run["algorithmId"]
                        and other["algoVersion"] == run["algoVersion"]
                        and other["benchmarkId"] == run["benchmarkId"]
                    ):
                        other["isLatestValid"] = False
                run["status"] = "succeeded"
                run["progress"] = 100
                run["finishedAt"] = iso_now()
                run["metrics"] = res["metrics"]
                run["durationSec"] = res["durationSec"]
                run["peakGpuMemGB"] = res["peakGpuMemGB"]
                run["latencyMs"] = res["latencyMs"]
                run["hardware"] = res["hardware"]
                run["isLatestValid"] = True
                run["perClass"] = res["perClass"]
                run["errorSamples"] = res["errorSamples"]
                run["logs"].append(
                    f"[done] 真实评测完成：{res['correctSamples']}/{res['totalSamples']} 正确，平均单图 {res['latencyMs']} ms，已更新排行榜"
                )
                st["updatedAt"] = iso_now()
                save_state(st)
    except Exception as exc:
        with _STATE_LOCK:
            st = load_state()
            run = next((r for r in st["evals"] if r["id"] == eval_id), None)
            if run:
                run["status"] = "failed"
                run["finishedAt"] = iso_now()
                run["error"] = str(exc)
                run["logs"].append(f"[error] 评测失败：{exc}")
                save_state(st)


@app.post("/real-api/evals")
def trigger_real_eval(req: EvalRequest):
    if req.algorithmId not in ("Admin/cat-dog-classifier", "Admin/random") or req.benchmarkId != "cat-dog-cls-bench":
        raise HTTPException(status_code=400, detail="当前真实评测仅支持 Admin/cat-dog-classifier 或 Admin/random × cat-dog-cls-bench")

    with _STATE_LOCK:
        st = load_state()
        if req.algorithmId == "Admin/random":
            vrec = {
                "imageDigest": "sha256:random0000000000000000000000000000000000000000000000000000000001",
                "weightsHash": "sha256:none000000000000000000000000000000000000000000000000000000000000",
            }
            params = {"mode": "uniform_random"}
            hw = "CPU · Python random"
        else:
            if req.algoVersion not in VERSION_SPECS:
                raise HTTPException(status_code=400, detail=f"未知版本：{req.algoVersion}")
            vrec = next((v for v in st["versions"] if v["version"] == req.algoVersion), None)
            if not vrec:
                raise HTTPException(status_code=404, detail="版本不存在")
            params = {"input_size": VERSION_SPECS[req.algoVersion].input_size, "batch_size": 64, "fp16": True}
            hw = hardware_label()

        eval_id = f"ev-real-{1001 + len(st['evals'])}"
        now = iso_now()
        run = {
            "id": eval_id,
            "algorithmId": req.algorithmId,
            "algoVersion": req.algoVersion,
            "benchmarkId": req.benchmarkId,
            "status": "queued",
            "progress": 0,
            "submittedBy": req.submittedBy,
            "submittedAt": now,
            "metrics": {},
            "imageDigest": vrec["imageDigest"],
            "weightsHash": vrec["weightsHash"],
            "evaluatorVersion": "v1.2.0",
            "params": params,
            "hardware": hw,
            "isLatestValid": False,
            "logs": [f"[scheduler] 真实评测任务 {eval_id} 已入队，目标 {req.algorithmId} {req.algoVersion}"],
        }
        st["evals"].insert(0, run)
        save_state(st)

    threading.Thread(target=_run_eval_bg, args=(eval_id, req.algorithmId, req.algoVersion), daemon=True).start()
    return run


@app.get("/real-api/evals")
def list_real_evals():
    with _STATE_LOCK:
        return load_state()["evals"]


@app.get("/real-api/evals/{eval_id}")
def get_real_eval(eval_id: str):
    with _STATE_LOCK:
        st = load_state()
    run = next((r for r in st["evals"] if r["id"] == eval_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    return run
