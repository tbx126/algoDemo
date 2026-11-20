"""
猫狗识别算法（Admin/cat-dog-classifier）三个真实版本的模型定义、推理与评测引擎。
  - v1.0.0: ResNet-18 轻量级残差基线 (224x224)
  - v2.0.0: ResNet-50 深层残差网络 + 数据增强 (224x224)
  - v3.0.0: ConvNeXt-Tiny 现代纯卷积主干 + 余弦退火与标签平滑 (256x256)
"""
from __future__ import annotations

import csv
import hashlib
import io
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "cat-dog-dataset"
MODELS_DIR = ROOT / "models" / "cat-dog-classifier"

CLASSES = ["猫", "狗"]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}


@dataclass(frozen=True)
class VersionSpec:
    version: str
    arch: str
    weight_file: str
    input_size: int
    gpu_mem: float
    changelog: str
    created_at: str
    epochs: int
    lr: float
    label_smoothing: float = 0.0
    strong_aug: bool = False


VERSION_SPECS: dict[str, VersionSpec] = {
    "v1.0.0": VersionSpec(
        version="v1.0.0",
        arch="resnet18",
        weight_file="v1.0.0_resnet18.pt",
        input_size=224,
        gpu_mem=1.5,
        changelog="初始基线版本：ResNet-18 轻量级残差网络，冻结特征层仅微调分类头，主打低显存与高速推理",
        created_at="2026-11-18T16:00:00+08:00",
        epochs=2,
        lr=1.5e-3,
        strong_aug=False,
    ),
    "v2.0.0": VersionSpec(
        version="v2.0.0",
        arch="resnet50",
        weight_file="v2.0.0_resnet50.pt",
        input_size=224,
        gpu_mem=3.2,
        changelog="深层残差改进版：升级为 ResNet-50 主干并解冻顶层残差块，加入随机裁剪与颜色抖动增强，显著提升复杂背景精度",
        created_at="2026-11-19T14:20:00+08:00",
        epochs=2,
        lr=4e-4,
        label_smoothing=0.05,
        strong_aug=True,
    ),
    "v3.0.0": VersionSpec(
        version="v3.0.0",
        arch="convnext_tiny",
        weight_file="v3.0.0_convnext_tiny.pt",
        input_size=256,
        gpu_mem=4.0,
        changelog="现代卷积新路线：切换至 ConvNeXt-Tiny（256×256 输入），配合余弦退火调度与标签平滑（暂未评测）",
        created_at="2026-11-20T09:30:00+08:00",
        epochs=2,
        lr=3e-4,
        label_smoothing=0.08,
        strong_aug=True,
    ),
}


def get_device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def hardware_label() -> str:
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        mem = round(torch.cuda.get_device_properties(0).total_memory / (1024 ** 3))
        return f"{name} ({mem}GB) · PyTorch {torch.__version__} · CUDA {torch.version.cuda}"
    return f"CPU · PyTorch {torch.__version__}"


def device_label() -> str:
    if torch.cuda.is_available():
        return f"cuda:0 ({torch.cuda.get_device_name(0)})"
    return "CPU"


def build_model(arch: str, pretrained: bool = False) -> nn.Module:
    if arch == "resnet18":
        m = models.resnet18(weights=models.ResNet18_Weights.DEFAULT if pretrained else None)
        m.fc = nn.Linear(m.fc.in_features, len(CLASSES))
        return m
    if arch == "resnet50":
        m = models.resnet50(weights=models.ResNet50_Weights.DEFAULT if pretrained else None)
        m.fc = nn.Linear(m.fc.in_features, len(CLASSES))
        return m
    if arch == "convnext_tiny":
        m = models.convnext_tiny(weights=models.ConvNeXt_Tiny_Weights.DEFAULT if pretrained else None)
        m.classifier[2] = nn.Linear(m.classifier[2].in_features, len(CLASSES))
        return m
    raise ValueError(f"Unknown arch: {arch}")


def eval_transform(size: int) -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((size, size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def train_transform(size: int, strong: bool) -> transforms.Compose:
    if strong:
        return transforms.Compose([
            transforms.RandomResizedCrop(size, scale=(0.75, 1.0)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.15),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize((size, size)),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


# 模型缓存（单进程内预热复用）
_LOADED: dict[str, tuple[nn.Module, VersionSpec, float]] = {}


def load_version_model(version: str) -> tuple[nn.Module, VersionSpec, bool]:
    if version not in VERSION_SPECS:
        raise ValueError(f"未知版本：{version}")
    if version in _LOADED:
        m, spec, _ = _LOADED[version]
        _LOADED[version] = (m, spec, time.time())
        return m, spec, True
    spec = VERSION_SPECS[version]
    weight_path = MODELS_DIR / spec.weight_file
    if not weight_path.exists():
        raise FileNotFoundError(f"权重文件不存在：{weight_path}")
    device = get_device()
    model = build_model(spec.arch, pretrained=False)
    state = torch.load(weight_path, map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.to(device)
    model.eval()
    _LOADED[version] = (model, spec, time.time())
    return model, spec, False


def warm_containers() -> list[dict]:
    now = time.time()
    out = []
    for v, (_, spec, last_used) in _LOADED.items():
        out.append({
            "algorithmId": "Admin/cat-dog-classifier",
            "version": v,
            "memGB": spec.gpu_mem,
            "idleSec": int(now - last_used),
        })
    return out


def infer_image_bytes(version: str, image_bytes: bytes) -> dict:
    t_load0 = time.perf_counter()
    model, spec, was_warm = load_version_model(version)
    load_ms = 0 if was_warm else int((time.perf_counter() - t_load0) * 1000)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    x = eval_transform(spec.input_size)(img).unsqueeze(0).to(get_device())

    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.no_grad():
        logits = model(x)
        probs = torch.softmax(logits, dim=1)[0].cpu().tolist()
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    latency_ms = round((time.perf_counter() - t0) * 1000, 1)

    items = sorted(
        [{"label": CLASSES[i], "score": float(probs[i])} for i in range(len(CLASSES))],
        key=lambda d: d["score"],
        reverse=True,
    )
    return {
        "task": "image-classification",
        "latencyMs": latency_ms,
        "queuedMs": load_ms,
        "device": device_label(),
        "classification": items,
        "raw": {
            "version": version,
            "arch": spec.arch,
            "input_size": spec.input_size,
            "predictions": [{"label": it["label"], "score": round(it["score"], 4)} for it in items],
        },
    }


def evaluate_version_on_test(
    version: str,
    on_progress: Callable[[int, str | None], None] | None = None,
) -> dict:
    """在真实 test/images + test/labels.csv 上执行完整推理与指标计算"""
    spec = VERSION_SPECS[version]
    test_dir = DATA_DIR / "test"
    csv_path = test_dir / "labels.csv"
    rows: list[tuple[str, str]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((row["file_name"], row["label"]))

    if on_progress:
        on_progress(5, f"[runner] 加载模型 {spec.version}（{spec.arch}，权重 {spec.weight_file}）")

    device = get_device()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats(device)

    model, _, _ = load_version_model(version)
    tfm = eval_transform(spec.input_size)

    if on_progress:
        on_progress(12, f"[runner] 只读挂载 Admin/cat-dog-dataset@v1.0/test/images（共 {len(rows)} 张真实图片，batch_size=64）")

    from torch.utils.data import DataLoader, Dataset

    class _TestDS(Dataset):
        def __len__(self):
            return len(rows)

        def __getitem__(self, i):
            rel_file, label = rows[i]
            with Image.open(test_dir / rel_file) as im:
                x = tfm(im.convert("RGB"))
            return x, CLASS_TO_IDX[label]

    loader = DataLoader(_TestDS(), batch_size=64, shuffle=False, num_workers=0, pin_memory=torch.cuda.is_available())
    use_amp = torch.cuda.is_available()

    y_true: list[int] = []
    y_pred: list[int] = []
    error_samples: list[dict] = []
    t_start = time.perf_counter()
    infer_total_s = 0.0
    seen = 0
    next_report = max(64, len(rows) // 8)

    with torch.no_grad():
        for xs, ys in loader:
            xs = xs.to(device, non_blocking=True)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            ti0 = time.perf_counter()
            with torch.amp.autocast("cuda", enabled=use_amp):
                logits = model(xs)
                probs = torch.softmax(logits.float(), dim=1)
            confs, pred_t = torch.max(probs, dim=1)
            preds = pred_t.cpu().tolist()
            conf_list = confs.cpu().tolist()
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            infer_total_s += time.perf_counter() - ti0

            ys_list = ys.tolist()
            for j, (yt, yp, cf) in enumerate(zip(ys_list, preds, conf_list)):
                if yt != yp:
                    rel_file, gt_label = rows[seen + j]
                    short = rel_file.split("/")[-1]
                    error_samples.append({
                        "fileName": rel_file,
                        "url": f"/real-api/datasets/Admin/cat-dog-dataset/files/test/{short}",
                        "groundTruth": gt_label,
                        "predicted": CLASSES[yp],
                        "confidence": round(float(cf), 4),
                    })

            y_true.extend(ys_list)
            y_pred.extend(preds)
            seen += len(preds)

            if on_progress and (seen >= next_report or seen == len(rows)):
                pct = 12 + int(80 * seen / len(rows))
                on_progress(pct, f"[eval] 已完成 {seen} / {len(rows)} 张测试图片推理")
                next_report += max(64, len(rows) // 8)

    duration_sec = max(1, round(time.perf_counter() - t_start, 2))
    latency_ms = round((infer_total_s / max(1, len(rows))) * 1000, 1)
    peak_gpu_gb = (
        round(torch.cuda.max_memory_allocated(device) / (1024 ** 3), 2)
        if torch.cuda.is_available()
        else 0.0
    )

    # 计算真实 Top-1 Accuracy, Macro Precision, Macro Recall, Macro F1
    n = len(y_true)
    correct = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    top1 = round((correct / max(1, n)) * 100, 2)

    precs, recs, f1s = [], [], []
    per_class: list[dict] = []
    for c in range(len(CLASSES)):
        tp = sum(1 for a, b in zip(y_true, y_pred) if a == c and b == c)
        fp = sum(1 for a, b in zip(y_true, y_pred) if a != c and b == c)
        fn = sum(1 for a, b in zip(y_true, y_pred) if a == c and b != c)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
        precs.append(p)
        recs.append(r)
        f1s.append(f1)
        per_class.append({"label": CLASSES[c], "value": round(r * 100, 2)})

    # 按误判置信度降序取最具代表性的前 12 个真实错误样例
    error_samples.sort(key=lambda x: x["confidence"], reverse=True)

    metrics = {
        "top1": top1,
        "f1": round((sum(f1s) / len(f1s)) * 100, 2),
        "precision": round((sum(precs) / len(precs)) * 100, 2),
        "recall": round((sum(recs) / len(recs)) * 100, 2),
    }

    if on_progress:
        on_progress(
            98,
            f"[evaluator] Top-1={metrics['top1']:.2f}%  Macro F1={metrics['f1']:.2f}%  Precision={metrics['precision']:.2f}%  Recall={metrics['recall']:.2f}%",
        )

    return {
        "metrics": metrics,
        "perClass": per_class,
        "errorSamples": error_samples[:12],
        "durationSec": duration_sec,
        "latencyMs": latency_ms,
        "peakGpuMemGB": peak_gpu_gb,
        "hardware": hardware_label(),
        "totalSamples": n,
        "correctSamples": correct,
    }


RANDOM_PALETTE = ["#ef4444", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"]


def infer_random(task: str = "image-classification", labels: list[str] | None = None) -> dict:
    """Admin/random：完全忽略输入，按目标任务类型独立随机生成对应格式的输出"""
    import math

    t0 = time.perf_counter()
    pool = [x.strip() for x in (labels or []) if x.strip()] or CLASSES
    base_meta = {
        "task": task,
        "queuedMs": 0,
        "device": "CPU (Python random)",
    }

    if task in ("image-classification", "signal-processing"):
        raw_w = [random.random() + 1e-6 for _ in pool]
        s = sum(raw_w)
        items = sorted(
            [{"label": pool[i], "score": raw_w[i] / s} for i in range(len(pool))],
            key=lambda d: d["score"],
            reverse=True,
        )
        latency_ms = max(0.1, round((time.perf_counter() - t0) * 1000, 2))
        return {
            **base_meta,
            "latencyMs": latency_ms,
            "classification": items,
            "raw": {
                "algorithm": "Admin/random",
                "task": task,
                "predictions": [{"label": it["label"], "score": round(it["score"], 4)} for it in items],
            },
        }

    if task in ("object-detection", "keypoint-detection", "ocr"):
        n = random.randint(2, 6)
        dets = []
        for _ in range(n):
            w = round(random.uniform(0.08, 0.28), 4)
            h = round(random.uniform(0.08, 0.28), 4)
            x = round(random.uniform(0.02, max(0.03, 0.98 - w)), 4)
            y = round(random.uniform(0.02, max(0.03, 0.98 - h)), 4)
            lbl = str(random.randint(0, 9999)) if task == "ocr" else random.choice(pool)
            dets.append({"label": lbl, "score": round(random.uniform(0.35, 0.99), 4), "box": [x, y, w, h]})
        dets.sort(key=lambda d: d["score"], reverse=True)
        latency_ms = max(0.1, round((time.perf_counter() - t0) * 1000, 2))
        return {
            **base_meta,
            "latencyMs": latency_ms,
            "detections": dets,
            "raw": {"algorithm": "Admin/random", "task": task, "detections": dets},
        }

    if task in ("semantic-segmentation", "instance-segmentation"):
        n = random.randint(3, 7)
        segs = []
        for i in range(n):
            cx = random.uniform(0.15, 0.85)
            cy = random.uniform(0.15, 0.85)
            rad = random.uniform(0.06, 0.18)
            pts = []
            for k in range(10):
                ang = (k / 10) * math.pi * 2
                rr = rad * random.uniform(0.7, 1.25)
                pts.append([round(min(1.0, max(0.0, cx + math.cos(ang) * rr)), 3), round(min(1.0, max(0.0, cy + math.sin(ang) * rr)), 3)])
            segs.append({"label": random.choice(pool), "color": RANDOM_PALETTE[i % len(RANDOM_PALETTE)], "polygon": pts})
        latency_ms = max(0.1, round((time.perf_counter() - t0) * 1000, 2))
        return {
            **base_meta,
            "latencyMs": latency_ms,
            "segments": segs,
            "raw": {"algorithm": "Admin/random", "task": task, "segments": [{"label": s["label"], "points": len(s["polygon"])} for s in segs]},
        }

    if task == "power-forecast":
        series = [round(random.uniform(5.0, 95.0), 2) for _ in range(24)]
        latency_ms = max(0.1, round((time.perf_counter() - t0) * 1000, 2))
        return {
            **base_meta,
            "latencyMs": latency_ms,
            "raw": {
                "algorithm": "Admin/random",
                "task": task,
                "unit": "MW",
                "horizon_hours": 24,
                "forecast": series,
                "mean_mw": round(sum(series) / len(series), 2),
                "peak_mw": max(series),
            },
        }

    # optimization / custom
    latency_ms = max(0.1, round((time.perf_counter() - t0) * 1000, 2))
    return {
        **base_meta,
        "latencyMs": latency_ms,
        "raw": {
            "algorithm": "Admin/random",
            "task": task,
            "value": round(random.uniform(0, 1000), 3),
            "choice": random.choice(pool),
            "confidence": round(random.random(), 4),
        },
    }


def evaluate_random_on_test(
    on_progress: Callable[[int, str | None], None] | None = None,
) -> dict:
    """在真实测试集上运行 Admin/random 随机基线，每张图独立随机猜测"""
    test_dir = DATA_DIR / "test"
    csv_path = test_dir / "labels.csv"
    rows: list[tuple[str, str]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append((row["file_name"], row["label"]))

    if on_progress:
        on_progress(15, f"[runner] 加载 Admin/random v1.0.0（纯随机基线，无需 GPU）")
        on_progress(30, f"[runner] 挂载 Admin/cat-dog-dataset@v1.0/test（共 {len(rows)} 张真实图片）")

    t_start = time.perf_counter()
    y_true: list[int] = []
    y_pred: list[int] = []
    error_samples: list[dict] = []

    for rel_file, gt_label in rows:
        p0 = random.random()
        yp = 0 if p0 >= 0.5 else 1
        cf = p0 if yp == 0 else (1.0 - p0)
        yt = CLASS_TO_IDX[gt_label]
        y_true.append(yt)
        y_pred.append(yp)
        if yt != yp:
            short = rel_file.split("/")[-1]
            error_samples.append({
                "fileName": rel_file,
                "url": f"/real-api/datasets/Admin/cat-dog-dataset/files/test/{short}",
                "groundTruth": gt_label,
                "predicted": CLASSES[yp],
                "confidence": round(float(cf), 4),
            })

    elapsed = time.perf_counter() - t_start
    duration_sec = max(1, round(elapsed, 2))
    latency_ms = max(0.1, round((elapsed / max(1, len(rows))) * 1000, 2))

    n = len(y_true)
    correct = sum(1 for a, b in zip(y_true, y_pred) if a == b)
    top1 = round((correct / max(1, n)) * 100, 2)

    precs, recs, f1s = [], [], []
    per_class: list[dict] = []
    for c in range(len(CLASSES)):
        tp = sum(1 for a, b in zip(y_true, y_pred) if a == c and b == c)
        fp = sum(1 for a, b in zip(y_true, y_pred) if a != c and b == c)
        fn = sum(1 for a, b in zip(y_true, y_pred) if a == c and b != c)
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
        precs.append(p)
        recs.append(r)
        f1s.append(f1)
        per_class.append({"label": CLASSES[c], "value": round(r * 100, 2)})

    error_samples.sort(key=lambda x: x["confidence"], reverse=True)
    metrics = {
        "top1": top1,
        "f1": round((sum(f1s) / len(f1s)) * 100, 2),
        "precision": round((sum(precs) / len(precs)) * 100, 2),
        "recall": round((sum(recs) / len(recs)) * 100, 2),
    }

    if on_progress:
        on_progress(95, f"[evaluator] Top-1={metrics['top1']:.2f}%  Macro F1={metrics['f1']:.2f}%  Precision={metrics['precision']:.2f}%  Recall={metrics['recall']:.2f}%")

    return {
        "metrics": metrics,
        "perClass": per_class,
        "errorSamples": error_samples[:12],
        "durationSec": duration_sec,
        "latencyMs": latency_ms,
        "peakGpuMemGB": 0.0,
        "hardware": "CPU · Python random",
        "totalSamples": n,
        "correctSamples": correct,
    }
