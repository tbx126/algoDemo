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
from dehaze_registry import (
    DEHAZE_ALGOS,
    DEHAZE_DATA_DIR,
    DEHAZE_MODELS_DIR,
    DEHAZE_STATE_PATH,
    evaluate_dehaze_on_test,
    infer_dehaze_bytes,
)
from custom_registry import (
    CUSTOM_DATA_ROOT,
    CUSTOM_MODELS_ROOT,
    _CUSTOM_LOCK,
    build_template_algorithm_zip,
    build_template_dataset_zip,
    build_template_evaluator_py,
    create_custom_benchmark,
    infer_custom_algorithm,
    load_custom_state,
    read_custom_dataset_rows,
    run_unified_evaluation,
    safe_slug,
    save_custom_algorithm,
    save_custom_dataset_part,
    save_custom_state,
    validate_algorithm_package,
    validate_dataset_zip,
)
from studio_engine import (
    generate_pipeline_predictor_code,
    publish_studio_pipeline,
    run_studio_batch_eval,
    run_studio_sample,
)

STATE_FILE = ROOT / "state" / "real_state.json"
META_FILE = DATA_DIR / "meta.json"
DEHAZE_META_FILE = DEHAZE_DATA_DIR / "meta.json"
OCR_DATA_DIR = ROOT / "data" / "sroie-ocr-dataset"
OCR_META_FILE = OCR_DATA_DIR / "meta.json"
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
        "tags": ["真实部署", "基线算法"],
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
        "description": f"基于真实数据集 Admin/cat-dog-dataset 测试集 v1.0（{te['files']} 张真实猫狗照片），执行真实 PyTorch 推理并计算准确率与 Macro F1。",
        "task": "image-classification",
        "datasetId": "Admin/cat-dog-dataset",
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": "pytorch-cls-evaluator",
        "evaluatorVersion": "v1.2.0",
        "metrics": [
            {"key": "top1", "label": "准确率", "higherIsBetter": True, "unit": "%", "primary": True},
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
        "tags": ["基线算法"],
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


def load_dehaze_state() -> dict | None:
    if not DEHAZE_STATE_PATH.exists():
        return None
    return json.loads(DEHAZE_STATE_PATH.read_text(encoding="utf-8"))


def save_dehaze_state(state: dict) -> None:
    DEHAZE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEHAZE_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_dehaze_meta() -> dict | None:
    if not DEHAZE_META_FILE.exists():
        return None
    return json.loads(DEHAZE_META_FILE.read_text(encoding="utf-8"))


def read_dehaze_part_rows(part: Literal["train", "test"], limit: int | None = None) -> list[dict]:
    csv_path = DEHAZE_DATA_DIR / part / "labels.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"去雾数据集 {part} 不存在")
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn = row["file_name"]
            short = fn.split("/")[-1]
            beta = float(row.get("beta", 1.5))
            fog_level = "轻雾" if beta < 1.35 else ("中雾" if beta < 1.75 else "浓雾")
            rows.append({
                "file_name": fn,
                "label": f"{fog_level} (β={row.get('beta', '-')}, A={row.get('airlight', '-')})",
                "url": f"/real-api/datasets/Admin/dehaze-dataset/files/{part}/{short}",
                "row": [fn, row["clear_file"], row.get("beta", ""), row.get("airlight", "")],
            })
            if limit is not None and len(rows) >= limit:
                break
    return rows


def build_dehaze_algorithms(dstate: dict, dmeta: dict | None = None) -> list[dict]:
    algo_versions_map = dstate.get("algorithms", {})
    all_evals = dstate.get("evals", [])
    test_rows = read_dehaze_part_rows("test", limit=12)
    ver_tag = (dmeta or {}).get("test", {}).get("contentHash", "")[7:15]
    suffix = f"?v={ver_tag}" if ver_tag else ""
    sample_images = [f"{r['url']}{suffix}" for r in test_rows[:3]]

    results: list[dict] = []
    for algo_id, spec in DEHAZE_ALGOS.items():
        versions = algo_versions_map.get(algo_id, [])
        if not versions:
            continue
        evals = [e for e in all_evals if e["algorithmId"] == algo_id and e["status"] == "succeeded"]

        files = [
            {"path": "backend/dehaze_registry.py", "size": (ROOT / "dehaze_registry.py").stat().st_size, "kind": "code"},
            {"path": "backend/train_dehaze.py", "size": (ROOT / "train_dehaze.py").stat().st_size, "kind": "code"},
        ]
        if spec.weight_file:
            wf = DEHAZE_MODELS_DIR / spec.weight_file
            files.append({
                "path": f"weights/dehaze/{spec.weight_file}",
                "size": wf.stat().st_size if wf.exists() else versions[0]["weightsSize"],
                "kind": "weights",
            })

        hw_desc = "纯 CPU（NumPy + 积分图导向滤波，0 GB 显存）" if spec.arch == "dcp" else f"{hardware_label()}（声明显存 {spec.gpu_mem} GB）"
        weight_line = f"  v1.0.0: weights/dehaze/{spec.weight_file}" if spec.weight_file else "  v1.0.0: none (CPU physical prior)"
        readme = f"""# {spec.display_name}（{algo_id}）

{spec.summary}

## 算法与论文信息

- **技术路线**：{spec.title}
- **代表论文**：{spec.paper}
- **推理框架**：{spec.framework}
- **运行设备**：{hw_desc}
- **训练集 / 评测基准**：`Admin/dehaze-dataset@v1.0` / `dehaze-bench`（PSNR & SSIM）

## 在线推理接口

- 路由：`POST /real-api/algorithms/{algo_id}/infer`（`multipart/form-data`）
- 参数：`version`（`v1.0.0`）、`file`（JPG / PNG 雾天图片）
- 返回：真实去雾后图像（`outputImage` Base64 Data URL）、耗时与设备信息
"""

        results.append({
            "id": algo_id,
            "org": "Admin",
            "name": spec.name,
            "displayName": spec.display_name,
            "task": "image-dehazing",
            "business": "other",
            "framework": spec.framework,
            "tags": list(spec.tags),
            "summary": spec.summary,
            "readme": readme,
            "likes": 12 if spec.arch == "deanet" else (9 if spec.arch == "ffanet" else 7),
            "evalCount": len(evals),
            "updatedAt": spec.created_at,
            "versions": versions,
            "files": files,
            "algoYaml": f"""name: {spec.name}
version: {spec.version}
task: image-dehazing
business: other
framework: {spec.framework}
entry: backend/dehaze_registry.py:{spec.arch}
versions:
{weight_line}
""",
            "labels": ["轻雾", "中雾", "浓雾"],
            "sampleImages": sample_images,
        })
    return results


def build_dehaze_dataset(dmeta: dict) -> dict:
    tr = dmeta["train"]
    te = dmeta["test"]
    train_rows = read_dehaze_part_rows("train", limit=6)
    test_rows = read_dehaze_part_rows("test", limit=6)

    readme = f"""# dehaze-dataset（真实场景配对图像去雾数据集）

基于真实自然与城市摄影图像（Pillow 完整性校验 + SHA-256 去重，训练/测试零重叠），按 RESIDE 标准大气散射物理模型：

$$I(x) = J(x) e^{{-\\beta d(x)}} + A \\left(1 - e^{{-\\beta d(x)}}\\right)$$

结合平滑空间景深场 $d(x, y)$ 生成多浓度（轻雾 / 中雾 / 浓雾）有雾-清晰配对图。

## 组成

| 部分 | 配对数 | 大小 | 说明 |
| --- | --- | --- | --- |
| 训练集 | {tr["files"]} 对 | {tr["sizeBytes"] / (1024 * 1024):.2f} MB | 所有账号可在线浏览与真实打包下载 |
| 测试集 | {te["files"]} 对 | {te["sizeBytes"] / (1024 * 1024):.2f} MB | **仅管理员可查看与下载**，用于 PSNR/SSIM 真实评测 |

## labels.csv

```
file_name,clear_file,beta,airlight
```
"""

    return {
        "id": "Admin/dehaze-dataset",
        "org": "Admin",
        "name": "dehaze-dataset",
        "task": "image-dehazing",
        "tags": ["图像去雾", "配对数据集", "PSNR/SSIM", "真实数据集"],
        "summary": f"真实配对图像去雾数据集（训练集 {tr['files']} 对 + 测试集 {te['files']} 对，384×256 RGB），含大气散射系数 β 与大气光 A 标注，支持实时预览与 ZIP 下载。",
        "readme": readme,
        "classes": ["轻雾", "中雾", "浓雾"],
        "train": {
            "name": "train",
            "columns": ["file_name", "clear_file", "beta", "airlight"],
            "versions": [
                {
                    "version": "v1.0",
                    "createdAt": "2026-11-20T10:00:00+08:00",
                    "createdBy": "admin",
                    "contentHash": tr["contentHash"],
                    "sizeBytes": tr["sizeBytes"],
                    "note": f"真实配对图像去雾训练集（{tr['files']} 对有雾/清晰图）",
                    "files": tr["files"],
                    "rows": tr["rows"],
                }
            ],
            "classCounts": tr.get("classCounts", {}),
        },
        "test": {
            "name": "test",
            "columns": ["file_name", "clear_file", "beta", "airlight"],
            "versions": [
                {
                    "version": "v1.0",
                    "createdAt": "2026-11-20T10:05:00+08:00",
                    "createdBy": "admin",
                    "contentHash": te["contentHash"],
                    "sizeBytes": te["sizeBytes"],
                    "note": f"真实配对图像去雾测试集（{te['files']} 对有雾/清晰图，与训练集零重叠）",
                    "files": te["files"],
                    "rows": te["rows"],
                }
            ],
            "classCounts": te.get("classCounts", {}),
        },
        "likes": 9,
        "downloads": 18,
        "updatedAt": "2026-11-20T10:05:00+08:00",
        "previewSeed": 2000,
        "realPreview": {
            "train": train_rows[:6],
            "test": test_rows[:6],
        },
    }


def build_dehaze_benchmark(dmeta: dict) -> dict:
    te = dmeta["test"]
    return {
        "id": "dehaze-bench",
        "name": "dehaze-bench",
        "displayName": "图像去雾标准评测基准（PSNR / SSIM）",
        "description": f"基于真实配对数据集 Admin/dehaze-dataset 测试集 v1.0（{te['files']} 对轻/中/浓雾真实场景图），逐张执行真实去雾推理并计算峰值信噪比（PSNR）与结构相似度（SSIM）。",
        "task": "image-dehazing",
        "datasetId": "Admin/dehaze-dataset",
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": "dehaze-psnr-ssim-evaluator",
        "evaluatorVersion": "v1.0.0",
        "metrics": [
            {"key": "psnr", "label": "PSNR", "higherIsBetter": True, "unit": "dB", "primary": True},
            {"key": "ssim", "label": "SSIM", "higherIsBetter": True, "unit": ""},
        ],
        "createdAt": "2026-11-20T10:10:00+08:00",
        "org": "Admin",
    }


def load_ocr_meta() -> dict | None:
    if not OCR_META_FILE.exists():
        return None
    return json.loads(OCR_META_FILE.read_text(encoding="utf-8"))


def read_ocr_part_rows(part: Literal["train", "test"], limit: int | None = None) -> list[dict]:
    csv_path = OCR_DATA_DIR / part / "labels.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=404, detail=f"OCR 数据集 {part} 不存在")
    rows: list[dict] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fn = row["file_name"]
            short = fn.split("/")[-1]
            text_gt = row["text"]
            cat = row.get("category", "")
            src_receipt = row.get("source_receipt", "")
            rows.append({
                "file_name": fn,
                "label": text_gt,
                "url": f"/real-api/datasets/Admin/sroie-ocr-dataset/files/{part}/{short}",
                "row": [fn, text_gt, cat, src_receipt],
            })
            if limit is not None and len(rows) >= limit:
                break
    return rows


def build_ocr_dataset(ometa: dict) -> dict:
    tr = ometa["train"]
    te = ometa["test"]
    total_imgs = tr["files"] + te["files"]
    total_receipts = tr.get("receipts", 0) + te.get("receipts", 0)
    train_pool = read_ocr_part_rows("train", limit=60)
    test_pool = read_ocr_part_rows("test", limit=30)

    # 挑选文字清晰、长度适中且覆盖多种语义类别的样本作为首屏预览
    def pick_preview(pool: list[dict], k: int = 6) -> list[dict]:
        chosen: list[dict] = []
        seen_cats: set[str] = set()
        for r in pool:
            txt = r["label"]
            cat = r["row"][2] if len(r.get("row", [])) > 2 else ""
            if 4 <= len(txt) <= 24 and cat not in seen_cats:
                chosen.append(r)
                seen_cats.add(cat)
                if len(chosen) >= k:
                    return chosen
        for r in pool:
            if r not in chosen and 3 <= len(r["label"]) <= 28:
                chosen.append(r)
                if len(chosen) >= k:
                    return chosen
        return pool[:k]

    train_preview = pick_preview(train_pool, 6)
    test_preview = pick_preview(test_pool, 6)

    readme = f"""# sroie-ocr-dataset（ICDAR-2019 SROIE 真实票据 OCR 文本行数据集）

来源于官方 **ICDAR-2019 SROIE**（Scanned Receipts OCR and Information Extraction）公开竞赛真实扫描票据集（共 {total_receipts} 张高分辨率扫描票据）。逐行按人工标注四点坐标裁剪出真实文本行图像（含 2px 上下文留白），经 Pillow 完整性校验、极小噪点过滤与图片 SHA-256 严格去重后，共保留 **{total_imgs:,} 张真实 OCR 文本行图片及其精确 Ground Truth 文字标注**。

训练与测试分片严格按**整张票据维度 80% / 20% 切分**，确保同一张票据不会同时出现在训练集与测试集中，零数据泄漏。

## 组成

| 部分 | 图片数 | 原始票据数 | 大小 | 说明 |
| --- | --- | --- | --- | --- |
| 训练集 (`train`) | {tr["files"]:,} | {tr.get("receipts", "-")} | {tr["sizeBytes"] / (1024 * 1024):.2f} MB | 所有账号可在线浏览与真实打包下载 |
| 测试集 (`test`) | {te["files"]:,} | {te.get("receipts", "-")} | {te["sizeBytes"] / (1024 * 1024):.2f} MB | **仅管理员可查看与下载**，用于 OCR 算法真实评测（CER / 整行准确率） |

## 文件结构

```
train/
├── images/          # 真实裁剪票据文本行 JPEG 图片
└── labels.csv       # file_name,text,category,source_receipt
test/
├── images/          # 真实裁剪票据文本行 JPEG 图片
└── labels.csv       # file_name,text,category,source_receipt
```

## labels.csv

一张裁剪文本行图片一行，`text` 为人工精标文字真值（Ground Truth），`category` 按文本内容分为 `数字与金额`、`日期与编号`、`文本与抬头` 三类，`source_receipt` 记录所属原始扫描票据编号。

```
file_name,text,category,source_receipt
```
"""

    return {
        "id": "Admin/sroie-ocr-dataset",
        "org": "Admin",
        "name": "sroie-ocr-dataset",
        "task": "ocr",
        "tags": ["OCR", "ICDAR-2019", "票据识别", "真实数据集"],
        "summary": f"ICDAR-2019 SROIE 真实扫描票据 OCR 文本行数据集（训练集 {tr['files']:,} 张 + 测试集 {te['files']:,} 张），含人工精标文字真值，支持在线预览与 ZIP 下载。",
        "readme": readme,
        "classes": ["数字与金额", "日期与编号", "文本与抬头"],
        "train": {
            "name": "train",
            "columns": ["file_name", "text", "category", "source_receipt"],
            "versions": [
                {
                    "version": "v1.0",
                    "createdAt": "2026-11-22T23:35:00+08:00",
                    "createdBy": "admin",
                    "contentHash": tr["contentHash"],
                    "sizeBytes": tr["sizeBytes"],
                    "note": f"ICDAR-2019 SROIE 真实文本行训练集（{tr['files']:,} 张，来自 {tr.get('receipts', 0)} 张扫描票据）",
                    "files": tr["files"],
                    "rows": tr["rows"],
                }
            ],
            "classCounts": tr.get("classCounts", {}),
        },
        "test": {
            "name": "test",
            "columns": ["file_name", "text", "category", "source_receipt"],
            "versions": [
                {
                    "version": "v1.0",
                    "createdAt": "2026-11-22T23:36:00+08:00",
                    "createdBy": "admin",
                    "contentHash": te["contentHash"],
                    "sizeBytes": te["sizeBytes"],
                    "note": f"ICDAR-2019 SROIE 真实文本行测试集（{te['files']:,} 张，按票据维度与训练集零重叠）",
                    "files": te["files"],
                    "rows": te["rows"],
                }
            ],
            "classCounts": te.get("classCounts", {}),
        },
        "likes": 11,
        "downloads": 15,
        "updatedAt": "2026-11-22T23:36:00+08:00",
        "previewSeed": 3000,
        "realPreview": {
            "train": train_preview,
            "test": test_preview,
        },
    }


@app.get("/real-api/bootstrap")
def bootstrap():
    with _STATE_LOCK:
        state = load_state()
        dstate = load_dehaze_state()
    meta = load_dataset_meta()
    dmeta = load_dehaze_meta()
    ometa = load_ocr_meta()
    cat_dog = build_real_algorithm(state)
    rand_algo = build_random_algorithm(state)
    cat_dog_ds = build_real_dataset(meta)
    cat_dog_bench = build_real_benchmark(meta)

    algorithms = [cat_dog]
    datasets = [cat_dog_ds]
    benchmarks = [cat_dog_bench]
    evals = list(state["evals"])

    if dstate and dmeta:
        algorithms.extend(build_dehaze_algorithms(dstate, dmeta))
        datasets.append(build_dehaze_dataset(dmeta))
        benchmarks.append(build_dehaze_benchmark(dmeta))
        evals.extend(dstate["evals"])

    if ometa:
        datasets.append(build_ocr_dataset(ometa))

    algorithms.append(rand_algo)

    with _CUSTOM_LOCK:
        cstate = load_custom_state()
    algorithms = list(cstate["algorithms"]) + algorithms
    datasets = list(cstate["datasets"]) + datasets
    benchmarks = list(cstate["benchmarks"]) + benchmarks
    evals = list(cstate["evals"]) + evals

    return {
        "algorithm": cat_dog,
        "algorithms": algorithms,
        "dataset": cat_dog_ds,
        "datasets": datasets,
        "benchmark": cat_dog_bench,
        "benchmarks": benchmarks,
        "evals": evals,
        "realAlgoIds": [a["id"] for a in algorithms],
        "realDatasetIds": [d["id"] for d in datasets],
        "realBenchmarkIds": [b["id"] for b in benchmarks],
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


@app.get("/real-api/datasets/Admin/dehaze-dataset/part/{part}")
def get_dehaze_dataset_part(part: Literal["train", "test"], limit: int = 200):
    dmeta = load_dehaze_meta()
    if not dmeta:
        raise HTTPException(status_code=503, detail="去雾数据集尚未初始化")
    rows = read_dehaze_part_rows(part, limit=max(1, min(limit, 500)))
    return {
        "part": part,
        "columns": ["file_name", "clear_file", "beta", "airlight"],
        "total": dmeta[part]["files"],
        "rows": rows,
    }


@app.get("/real-api/datasets/Admin/dehaze-dataset/files/{part}/{filename}")
def get_dehaze_dataset_file(part: Literal["train", "test"], filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = DEHAZE_DATA_DIR / part / "images" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/real-api/datasets/Admin/dehaze-dataset/clear/{part}/{filename}")
def get_dehaze_clear_file(part: Literal["train", "test"], filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = DEHAZE_DATA_DIR / part / "clear" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="清晰真值图不存在")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/real-api/datasets/Admin/dehaze-dataset/download/{part}")
def download_dehaze_dataset_part(part: Literal["train", "test"]):
    part_dir = DEHAZE_DATA_DIR / part
    if not part_dir.exists():
        raise HTTPException(status_code=404, detail="去雾数据集分片不存在")
    zip_path = DEHAZE_DATA_DIR / f"dehaze-dataset-{part}-v1.0.zip"
    if not zip_path.exists():
        tmp = zip_path.with_suffix(".zip.tmp")
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zf:
            csv_path = part_dir / "labels.csv"
            if csv_path.exists():
                zf.write(csv_path, arcname=f"{part}/labels.csv")
            for sub in ("images", "clear"):
                for img in sorted((part_dir / sub).glob("*.jpg")):
                    zf.write(img, arcname=f"{part}/{sub}/{img.name}")
        tmp.replace(zip_path)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"dehaze-dataset-{part}-v1.0.zip",
    )


@app.get("/real-api/datasets/Admin/sroie-ocr-dataset/part/{part}")
def get_ocr_dataset_part(part: Literal["train", "test"], limit: int = 200):
    ometa = load_ocr_meta()
    if not ometa:
        raise HTTPException(status_code=503, detail="OCR 数据集尚未初始化，请先运行 prepare_ocr_dataset.py")
    rows = read_ocr_part_rows(part, limit=max(1, min(limit, 500)))
    return {
        "part": part,
        "columns": ["file_name", "text", "category", "source_receipt"],
        "total": ometa[part]["files"],
        "rows": rows,
    }


@app.get("/real-api/datasets/Admin/sroie-ocr-dataset/files/{part}/{filename}")
def get_ocr_dataset_file(part: Literal["train", "test"], filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    path = OCR_DATA_DIR / part / "images" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/real-api/datasets/Admin/sroie-ocr-dataset/download/{part}")
def download_ocr_dataset_part(part: Literal["train", "test"]):
    part_dir = OCR_DATA_DIR / part
    if not part_dir.exists():
        raise HTTPException(status_code=404, detail="OCR 数据集分片不存在")
    zip_path = OCR_DATA_DIR / f"sroie-ocr-dataset-{part}-v1.0.zip"
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
        filename=f"sroie-ocr-dataset-{part}-v1.0.zip",
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


@app.post("/real-api/algorithms/Admin/{algo_name}/infer")
async def infer_dehaze_algo(
    algo_name: str,
    version: str = Form("v1.0.0"),
    file: UploadFile | None = File(None),
    sample_path: str | None = Form(None),
):
    algo_id = f"Admin/{algo_name}"
    if algo_id not in DEHAZE_ALGOS:
        return await infer_custom_algorithm_endpoint("Admin", algo_name, version=version, file=file, sample_path=sample_path)
    if file is not None:
        raw = await file.read()
    elif sample_path:
        clean_path = sample_path.split("?", 1)[0]
        parts = clean_path.strip("/").split("/")
        if len(parts) >= 2 and parts[-2] in ("train", "test"):
            p = DEHAZE_DATA_DIR / parts[-2] / "images" / parts[-1]
            if not p.exists():
                raise HTTPException(status_code=404, detail="示例雾图不存在")
            raw = p.read_bytes()
        else:
            raise HTTPException(status_code=400, detail="无效的示例图片路径")
    else:
        raise HTTPException(status_code=400, detail="请上传有雾图片或选择示例图片")

    try:
        return infer_dehaze_bytes(algo_id, raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"去雾推理失败：{exc}")


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


def _run_dehaze_eval_bg(eval_id: str, algo_id: str):
    def on_progress(pct: int, msg: str | None):
        with _STATE_LOCK:
            st = load_dehaze_state()
            if not st:
                return
            run = next((r for r in st["evals"] if r["id"] == eval_id), None)
            if not run:
                return
            run["progress"] = pct
            if msg:
                run["logs"].append(msg)
            save_dehaze_state(st)

    try:
        spec = DEHAZE_ALGOS[algo_id]
        with _STATE_LOCK:
            st = load_dehaze_state()
            if st:
                run = next((r for r in st["evals"] if r["id"] == eval_id), None)
                if run:
                    run["status"] = "running"
                    run["startedAt"] = iso_now()
                    hw = "CPU (NumPy + Pillow)" if spec.arch == "dcp" else hardware_label()
                    run["logs"].append(f"[scheduler] 开始在 {hw} 上执行真实去雾评测（{spec.title}）")
                    save_dehaze_state(st)

        res = evaluate_dehaze_on_test(algo_id, on_progress=on_progress)

        with _STATE_LOCK:
            st = load_dehaze_state()
            if st:
                run = next((r for r in st["evals"] if r["id"] == eval_id), None)
                if run:
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
                    run["isLatestValid"] = True
                    run["perClass"] = res["perClass"]
                    run["errorSamples"] = res["errorSamples"]
                    run["logs"].append(
                        f"[done] 真实评测完成：PSNR={res['metrics']['psnr']:.2f} dB，SSIM={res['metrics']['ssim']:.4f}，平均单图 {res['latencyMs']} ms，已更新排行榜"
                    )
                    save_dehaze_state(st)
    except Exception as exc:
        with _STATE_LOCK:
            st = load_dehaze_state()
            if st:
                run = next((r for r in st["evals"] if r["id"] == eval_id), None)
                if run:
                    run["status"] = "failed"
                    run["finishedAt"] = iso_now()
                    run["error"] = str(exc)
                    run["logs"].append(f"[error] 评测失败：{exc}")
                    save_dehaze_state(st)


@app.post("/real-api/evals")
def trigger_real_eval(req: EvalRequest):
    if req.algorithmId in DEHAZE_ALGOS and req.benchmarkId == "dehaze-bench":
        with _STATE_LOCK:
            dst = load_dehaze_state()
            if not dst:
                raise HTTPException(status_code=503, detail="去雾模型尚未初始化")
            versions = dst.get("algorithms", {}).get(req.algorithmId, [])
            vrec = next((v for v in versions if v["version"] == req.algoVersion), None)
            if not vrec:
                raise HTTPException(status_code=404, detail="版本不存在")
            spec = DEHAZE_ALGOS[req.algorithmId]
            eval_id = f"ev-dehaze-{1001 + len(dst['evals'])}"
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
                "evaluatorVersion": "v1.0.0",
                "params": {"tile_size": 0, "amp_fp16": spec.arch != "dcp"},
                "hardware": "CPU (NumPy + Pillow)" if spec.arch == "dcp" else hardware_label(),
                "isLatestValid": False,
                "logs": [f"[scheduler] 真实去雾评测任务 {eval_id} 已入队，目标 {req.algorithmId} {req.algoVersion}（{spec.title}）"],
            }
            dst["evals"].insert(0, run)
            save_dehaze_state(dst)
        threading.Thread(target=_run_dehaze_eval_bg, args=(eval_id, req.algorithmId), daemon=True).start()
        return run

    if req.algorithmId in ("Admin/cat-dog-classifier", "Admin/random") and req.benchmarkId == "cat-dog-cls-bench":
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

    # 统一真实评测通道：支持任意内置/用户上传算法 × 任意内置/用户创建评测基准
    return _trigger_unified_eval(req)


def _find_any_benchmark(bench_id: str) -> dict | None:
    if bench_id == "cat-dog-cls-bench":
        return build_real_benchmark(load_dataset_meta())
    if bench_id == "dehaze-bench":
        dm = load_dehaze_meta()
        return build_dehaze_benchmark(dm) if dm else None
    with _CUSTOM_LOCK:
        cst = load_custom_state()
    return next((b for b in cst["benchmarks"] if b["id"] == bench_id), None)


def _find_any_algo_version(algo_id: str, version: str) -> tuple[dict | None, dict | None]:
    if algo_id == "Admin/cat-dog-classifier":
        st = load_state()
        return {"id": algo_id, "task": "image-classification"}, next((v for v in st["versions"] if v["version"] == version), None)
    if algo_id == "Admin/random":
        return {"id": algo_id, "task": "custom"}, {
            "version": version,
            "imageDigest": "sha256:random0000000000000000000000000000000000000000000000000000000001",
            "weightsHash": "sha256:none000000000000000000000000000000000000000000000000000000000000",
        }
    if algo_id in DEHAZE_ALGOS:
        dst = load_dehaze_state()
        vers = (dst or {}).get("algorithms", {}).get(algo_id, [])
        return {"id": algo_id, "task": "image-dehazing"}, next((v for v in vers if v["version"] == version), None)
    with _CUSTOM_LOCK:
        cst = load_custom_state()
    algo = next((a for a in cst["algorithms"] if a["id"] == algo_id), None)
    if not algo:
        return None, None
    return algo, next((v for v in algo["versions"] if v["version"] == version), None)


def _run_unified_eval_bg(eval_id: str, algorithm_id: str, version: str, bench: dict, params: dict):
    def on_progress(pct: int, msg: str | None):
        with _CUSTOM_LOCK:
            cst = load_custom_state()
            run = next((r for r in cst["evals"] if r["id"] == eval_id), None)
            if not run:
                return
            run["progress"] = pct
            if msg:
                run["logs"].append(msg)
            save_custom_state(cst)

    try:
        with _CUSTOM_LOCK:
            cst = load_custom_state()
            run = next((r for r in cst["evals"] if r["id"] == eval_id), None)
            if run:
                run["status"] = "running"
                run["startedAt"] = iso_now()
                run["logs"].append(f"[scheduler] 开始在 {hardware_label()} 上执行标准化真实评测")
                save_custom_state(cst)

        res = run_unified_evaluation(algorithm_id, version, bench, params, on_progress=on_progress)

        with _CUSTOM_LOCK:
            cst = load_custom_state()
            run = next((r for r in cst["evals"] if r["id"] == eval_id), None)
            if run:
                for other in cst["evals"]:
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
                run["logs"].append(f"[done] 真实评测完成（{res['totalSamples']} 条样本，均耗 {res['latencyMs']} ms），已更新排行榜")
                # 更新自定义算法 evalCount
                ca = next((a for a in cst["algorithms"] if a["id"] == algorithm_id), None)
                if ca:
                    ca["evalCount"] = len([e for e in cst["evals"] if e["algorithmId"] == algorithm_id and e["status"] == "succeeded"])
                save_custom_state(cst)
    except Exception as exc:
        with _CUSTOM_LOCK:
            cst = load_custom_state()
            run = next((r for r in cst["evals"] if r["id"] == eval_id), None)
            if run:
                run["status"] = "failed"
                run["finishedAt"] = iso_now()
                run["error"] = str(exc)
                run["logs"].append(f"[error] 评测失败：{exc}")
                save_custom_state(cst)


def _trigger_unified_eval(req: EvalRequest) -> dict:
    bench = _find_any_benchmark(req.benchmarkId)
    if not bench:
        raise HTTPException(status_code=404, detail=f"真实评测基准不存在：{req.benchmarkId}")
    algo, vrec = _find_any_algo_version(req.algorithmId, req.algoVersion)
    if not algo or not vrec:
        raise HTTPException(status_code=404, detail=f"真实算法或版本不存在：{req.algorithmId}@{req.algoVersion}")

    with _CUSTOM_LOCK:
        cst = load_custom_state()
        eval_id = f"ev-custom-{1001 + len(cst['evals'])}"
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
            "imageDigest": vrec.get("imageDigest", ""),
            "weightsHash": vrec.get("weightsHash", ""),
            "evaluatorVersion": bench.get("evaluatorVersion", "v1.0.0"),
            "params": {},
            "hardware": hardware_label(),
            "isLatestValid": False,
            "logs": [f"[scheduler] 标准化真实评测任务 {eval_id} 已入队：{req.algorithmId} {req.algoVersion} × {req.benchmarkId}"],
        }
        cst["evals"].insert(0, run)
        save_custom_state(cst)

    threading.Thread(
        target=_run_unified_eval_bg,
        args=(eval_id, req.algorithmId, req.algoVersion, bench, {}),
        daemon=True,
    ).start()
    return run


@app.get("/real-api/evals")
def list_real_evals():
    with _STATE_LOCK:
        evals = list(load_state()["evals"])
        dst = load_dehaze_state()
        if dst:
            evals.extend(dst["evals"])
    with _CUSTOM_LOCK:
        evals = list(load_custom_state()["evals"]) + evals
    return evals


@app.get("/real-api/evals/{eval_id}")
def get_real_eval(eval_id: str):
    with _CUSTOM_LOCK:
        cst = load_custom_state()
    run = next((r for r in cst["evals"] if r["id"] == eval_id), None)
    if run:
        return run
    with _STATE_LOCK:
        st = load_state()
        dst = load_dehaze_state()
    run = next((r for r in st["evals"] if r["id"] == eval_id), None)
    if not run and dst:
        run = next((r for r in dst["evals"] if r["id"] == eval_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="评测记录不存在")
    return run


# ==================== 标准化模板下载 & 自助上传接口 ====================
@app.get("/real-api/templates/dataset/{task}")
def download_dataset_template(task: str, part: Literal["train", "test"] = "train"):
    data = build_template_dataset_zip(task, part=part)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="template-{task}-{part}.zip"'},
    )


@app.get("/real-api/templates/algorithm/{task}")
def download_algorithm_template(task: str):
    data = build_template_algorithm_zip(task)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="template-algo-{task}.zip"'},
    )


@app.get("/real-api/templates/evaluator")
def download_evaluator_template():
    data = build_template_evaluator_py()
    return Response(
        content=data,
        media_type="text/x-python",
        headers={"Content-Disposition": 'attachment; filename="evaluator_template.py"'},
    )


@app.post("/real-api/datasets/validate")
async def validate_custom_dataset_endpoint(
    zip_file: UploadFile = File(...),
    task: str = Form(...),
    part: Literal["train", "test"] = Form("train"),
    classes_json: str = Form("[]"),
    dataset_id: str | None = Form(None),
):
    raw = await zip_file.read()
    try:
        classes = json.loads(classes_json) if classes_json else []
    except Exception:
        classes = []
    expected_cols = None
    if dataset_id:
        with _CUSTOM_LOCK:
            cst = load_custom_state()
        ex = next((d for d in cst["datasets"] if d["id"] == dataset_id), None)
        if ex:
            other = ex["test"] if part == "train" else ex["train"]
            if other:
                expected_cols = other["columns"]
    return validate_dataset_zip(raw, task, part, classes or None, expected_cols)


@app.post("/real-api/datasets")
async def create_custom_dataset_endpoint(
    org: str = Form(...),
    name: str = Form(...),
    task: str = Form(...),
    summary: str = Form(...),
    classes_json: str = Form("[]"),
    note: str = Form("首个版本"),
    created_by: str = Form("admin"),
    zip_file: UploadFile = File(...),
):
    raw = await zip_file.read()
    try:
        classes = json.loads(classes_json) if classes_json else []
        return save_custom_dataset_part(
            org=org,
            name=name,
            task=task,
            part="train",
            zip_bytes=raw,
            note=note,
            created_by=created_by,
            summary=summary,
            classes=classes,
            is_new=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/real-api/datasets/{org}/{name}/{part}")
async def upload_custom_dataset_part_endpoint(
    org: str,
    name: str,
    part: Literal["train", "test"],
    note: str = Form("增量更新"),
    created_by: str = Form("admin"),
    zip_file: UploadFile = File(...),
):
    raw = await zip_file.read()
    try:
        return save_custom_dataset_part(
            org=org,
            name=name,
            task="",
            part=part,
            zip_bytes=raw,
            note=note,
            created_by=created_by,
            is_new=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/real-api/datasets/{org}/{name}/part/{part}")
def get_custom_dataset_part_endpoint(org: str, name: str, part: Literal["train", "test"], limit: int = 200):
    ds_id = f"{org}/{name}"
    with _CUSTOM_LOCK:
        cst = load_custom_state()
    ds = next((d for d in cst["datasets"] if d["id"] == ds_id), None)
    if not ds or not ds.get(part):
        raise HTTPException(status_code=404, detail="数据集或分片不存在")
    rows = read_custom_dataset_rows(org, name, part, limit=max(1, min(limit, 500)))
    return {
        "part": part,
        "columns": ds[part]["columns"],
        "total": ds[part]["versions"][0]["files"],
        "rows": rows,
    }


@app.get("/real-api/datasets/{org}/{name}/files/{part}/{filename}")
def get_custom_dataset_file_endpoint(org: str, name: str, part: Literal["train", "test"], filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    part_dir = CUSTOM_DATA_ROOT / safe_slug(org, name) / part
    for candidate in (part_dir / "images" / filename, part_dir / filename):
        if candidate.exists():
            return FileResponse(candidate, headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404, detail="文件不存在")


@app.get("/real-api/datasets/{org}/{name}/download/{part}")
def download_custom_dataset_part_endpoint(org: str, name: str, part: Literal["train", "test"]):
    ds_root = CUSTOM_DATA_ROOT / safe_slug(org, name)
    latest_zip = ds_root / f"{name}-{part}-latest.zip"
    if not latest_zip.exists():
        raise HTTPException(status_code=404, detail="压缩包不存在")
    return FileResponse(latest_zip, media_type="application/zip", filename=f"{name}-{part}.zip")


@app.delete("/real-api/datasets/{org}/{name}")
def delete_custom_dataset_endpoint(org: str, name: str):
    ds_id = f"{org}/{name}"
    with _CUSTOM_LOCK:
        cst = load_custom_state()
        cst["datasets"] = [d for d in cst["datasets"] if d["id"] != ds_id]
        removed_benches = {b["id"] for b in cst["benchmarks"] if b["datasetId"] == ds_id}
        cst["benchmarks"] = [b for b in cst["benchmarks"] if b["datasetId"] != ds_id]
        cst["evals"] = [e for e in cst["evals"] if e["benchmarkId"] not in removed_benches]
        save_custom_state(cst)
    return {"ok": True}


@app.post("/real-api/algorithms/validate")
async def validate_custom_algorithm_endpoint(
    task: str = Form(...),
    package_file: UploadFile = File(...),
):
    raw = await package_file.read()
    return validate_algorithm_package(package_file.filename or "predictor.py", raw, task)


@app.post("/real-api/algorithms")
async def create_custom_algorithm_endpoint(
    metadata_json: str = Form(...),
    created_by: str = Form("admin"),
    role: str = Form("admin"),
    package_file: UploadFile = File(...),
):
    try:
        meta = json.loads(metadata_json)
        raw = await package_file.read()
        return save_custom_algorithm(meta, package_file.filename or "predictor.py", raw, created_by=created_by, role=role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/real-api/algorithms/{org}/{name}/approve")
def approve_custom_algorithm_endpoint(org: str, name: str, version: str = Form(...)):
    algo_id = f"{org}/{name}"
    with _CUSTOM_LOCK:
        cst = load_custom_state()
        algo = next((a for a in cst["algorithms"] if a["id"] == algo_id), None)
        if not algo:
            raise HTTPException(status_code=404, detail="算法不存在")
        ver = next((v for v in algo["versions"] if v["version"] == version), None)
        if not ver:
            raise HTTPException(status_code=404, detail="版本不存在")
        ver["status"] = "ready"
        ver["buildLog"].append("[review] 管理员审核通过，版本已就绪")
        save_custom_state(cst)
        return ver


@app.delete("/real-api/algorithms/{org}/{name}")
def delete_custom_algorithm_endpoint(org: str, name: str):
    algo_id = f"{org}/{name}"
    with _CUSTOM_LOCK:
        cst = load_custom_state()
        cst["algorithms"] = [a for a in cst["algorithms"] if a["id"] != algo_id]
        cst["evals"] = [e for e in cst["evals"] if e["algorithmId"] != algo_id]
        save_custom_state(cst)
    return {"ok": True}


@app.post("/real-api/algorithms/{org}/{name}/infer")
async def infer_custom_algorithm_endpoint(
    org: str,
    name: str,
    version: str = Form("v1.0.0"),
    file: UploadFile | None = File(None),
    sample_path: str | None = Form(None),
):
    algo_id = f"{org}/{name}"
    if file is not None:
        raw = await file.read()
    elif sample_path:
        clean = sample_path.split("?", 1)[0].strip("/")
        # 支持 /real-api/datasets/{ds_org}/{ds_name}/files/{part}/{filename}
        parts = clean.split("/")
        if len(parts) >= 7 and parts[0] == "real-api" and parts[1] == "datasets" and parts[4] == "files":
            ds_org, ds_name, part, fname = parts[2], parts[3], parts[5], parts[6]
            if f"{ds_org}/{ds_name}" == "Admin/cat-dog-dataset":
                p = DATA_DIR / part / "images" / fname
            elif f"{ds_org}/{ds_name}" == "Admin/dehaze-dataset":
                p = DEHAZE_DATA_DIR / part / "images" / fname
            elif f"{ds_org}/{ds_name}" == "Admin/sroie-ocr-dataset":
                p = OCR_DATA_DIR / part / "images" / fname
            else:
                p = CUSTOM_DATA_ROOT / safe_slug(ds_org, ds_name) / part / "images" / fname
            if not p.exists():
                raise HTTPException(status_code=404, detail="示例图片不存在")
            raw = p.read_bytes()
        else:
            raise HTTPException(status_code=400, detail="无效的示例图片路径")
    else:
        raise HTTPException(status_code=400, detail="请上传图片或选择示例图片")

    try:
        return infer_custom_algorithm(algo_id, version, raw)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"自定义算法推理失败：{exc}")


@app.post("/real-api/benchmarks")
async def create_custom_benchmark_endpoint(
    metadata_json: str = Form(...),
    evaluator_script: UploadFile | None = File(None),
):
    try:
        meta = json.loads(metadata_json)
        script_bytes = await evaluator_script.read() if evaluator_script is not None else None
        return create_custom_benchmark(meta, evaluator_script_bytes=script_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ==================== 低代码可视化编排实验室（实验性） ====================
class StudioGraphReq(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    sampleIndex: int | None = None
    sampleCount: int = 12


class StudioPublishReq(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    meta: dict
    createdBy: str = "admin"
    role: str = "admin"


@app.post("/real-api/studio/run-sample")
def studio_run_sample_endpoint(req: StudioGraphReq):
    try:
        return run_studio_sample(req.nodes, req.edges, sample_index=req.sampleIndex)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/real-api/studio/run-eval")
def studio_run_eval_endpoint(req: StudioGraphReq):
    try:
        return run_studio_batch_eval(req.nodes, req.edges, sample_count=req.sampleCount)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/real-api/studio/preview-code")
def studio_preview_code_endpoint(req: StudioPublishReq):
    try:
        code, base_id = generate_pipeline_predictor_code(req.nodes, req.edges, req.meta.get("task", "image-dehazing"))
        return {"code": code, "baseAlgorithmId": base_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/real-api/studio/publish")
def studio_publish_endpoint(req: StudioPublishReq):
    try:
        return publish_studio_pipeline(req.nodes, req.edges, req.meta, created_by=req.createdBy, role=req.role)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
