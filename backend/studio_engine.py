"""
低代码可视化编排实验室后端引擎（backend/studio_engine.py）：
支持将前端拖拽连接的 DAG 节点图（数据集 → 预处理 → 已有算法 → 后处理/融合 → 评测指标）
在真实图片与真实测试集上执行单图试跑、批量评测对比，并支持将优化后的流水线
编译为标准 predictor.py 一键发布为平台新算法。
"""
from __future__ import annotations

import base64
import csv
import io
import json
import time
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from custom_registry import (
    _decode_data_url_rgb,
    _resolve_dataset_test_dir,
    _run_any_algo_on_bytes,
    save_custom_algorithm,
)
from dehaze_registry import compute_psnr, compute_ssim


def _rgb_bytes_from_pil(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _data_url_from_bytes(raw: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def _img_shape(raw: bytes) -> str:
    try:
        with Image.open(io.BytesIO(raw)) as im:
            return f"{im.width}×{im.height} {im.mode}"
    except Exception:
        return "RGB"


def apply_preprocess(image_bytes: bytes, cfg: dict[str, Any]) -> bytes:
    """真实图像预处理（Pillow + NumPy）"""
    with Image.open(io.BytesIO(image_bytes)) as im:
        rgb = im.convert("RGB")
        max_side = int(cfg.get("maxSide") or 0)
        if max_side >= 128 and max(rgb.size) > max_side:
            rgb.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        if cfg.get("denoise"):
            rgb = rgb.filter(ImageFilter.MedianFilter(size=3))
        contrast = float(cfg.get("contrast", 1.0))
        if abs(contrast - 1.0) > 1e-3:
            rgb = ImageEnhance.Contrast(rgb).enhance(contrast)
        gamma = float(cfg.get("gamma", 1.0))
        if abs(gamma - 1.0) > 1e-3:
            arr = np.asarray(rgb, dtype=np.float32) / 255.0
            arr = np.power(np.clip(arr, 0.0, 1.0), gamma)
            rgb = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8))
        sharpen = float(cfg.get("sharpen", 0.0))
        if sharpen > 1e-3:
            rgb = ImageEnhance.Sharpness(rgb).enhance(1.0 + sharpen)
        return _rgb_bytes_from_pil(rgb)


def apply_postprocess(image_bytes: bytes, cfg: dict[str, Any], orig_bytes: bytes | None = None) -> bytes:
    """真实图像后处理与残差融合优化"""
    with Image.open(io.BytesIO(image_bytes)) as im:
        rgb = im.convert("RGB")
        if cfg.get("autoContrast"):
            arr = np.asarray(rgb, dtype=np.float32) / 255.0
            lo = np.percentile(arr, 1, axis=(0, 1), keepdims=True)
            hi = np.percentile(arr, 99, axis=(0, 1), keepdims=True)
            arr = np.clip((arr - lo) / np.maximum(hi - lo, 1e-3), 0.0, 1.0)
            rgb = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8))
        gamma = float(cfg.get("gamma", 1.0))
        if abs(gamma - 1.0) > 1e-3:
            arr = np.asarray(rgb, dtype=np.float32) / 255.0
            arr = np.power(np.clip(arr, 0.0, 1.0), gamma)
            rgb = Image.fromarray(np.clip(arr * 255.0, 0, 255).astype(np.uint8))
        sat = float(cfg.get("saturation", 1.0))
        if abs(sat - 1.0) > 1e-3:
            rgb = ImageEnhance.Color(rgb).enhance(sat)
        sharpen = float(cfg.get("sharpen", 0.0))
        if sharpen > 1e-3:
            rgb = ImageEnhance.Sharpness(rgb).enhance(1.0 + sharpen)

        blend = float(cfg.get("blendOriginal", 0.0))
        if blend > 1e-3 and orig_bytes is not None:
            with Image.open(io.BytesIO(orig_bytes)) as im_o:
                o_rgb = im_o.convert("RGB").resize(rgb.size, Image.Resampling.BILINEAR)
            a1 = np.asarray(rgb, dtype=np.float32)
            a0 = np.asarray(o_rgb, dtype=np.float32)
            mixed = np.clip(a1 * (1.0 - blend) + a0 * blend, 0, 255).astype(np.uint8)
            rgb = Image.fromarray(mixed)
        return _rgb_bytes_from_pil(rgb)


def _topo_sort(nodes: list[dict], edges: list[dict]) -> list[dict]:
    nmap = {n["id"]: n for n in nodes}
    indeg = {n["id"]: 0 for n in nodes}
    adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        s, t = e.get("source"), e.get("target")
        if s in nmap and t in nmap:
            adj[s].append(t)
            indeg[t] += 1
    q = deque([nid for nid, d in indeg.items() if d == 0])
    order: list[dict] = []
    while q:
        u = q.popleft()
        order.append(nmap[u])
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)
    if len(order) != len(nodes):
        raise ValueError("编排图中存在循环依赖，请检查节点连线")
    return order


def _load_dataset_sample(dataset_id: str, sample_index: int) -> tuple[bytes, dict]:
    test_dir, url_prefix = _resolve_dataset_test_dir(dataset_id)
    csv_path = test_dir / "labels.csv"
    with csv_path.open("r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError(f"数据集 {dataset_id} 测试集为空")
    idx = max(0, min(sample_index, len(rows) - 1))
    row = rows[idx]
    rel = row["file_name"].replace("\\", "/")
    raw = (test_dir / rel).read_bytes()
    gt_info: dict[str, Any] = {
        "fileName": rel,
        "index": idx,
        "total": len(rows),
        "url": f"{url_prefix}/{rel.split('/')[-1]}",
        "label": row.get("label"),
        "text": row.get("text"),
        "category": row.get("category"),
        "beta": row.get("beta"),
    }
    if row.get("clear_file"):
        crel = row["clear_file"].replace("\\", "/")
        gt_info["clearBytes"] = (test_dir / crel).read_bytes()
        gt_info["task"] = "image-dehazing"
    elif row.get("text"):
        gt_info["task"] = "ocr"
    elif row.get("label"):
        gt_info["task"] = "image-classification"
    else:
        gt_info["task"] = "custom"
    return raw, gt_info


def _execute_graph_on_sample(
    nodes: list[dict],
    edges: list[dict],
    sample_index: int | None = None,
    include_previews: bool = True,
) -> dict:
    order = _topo_sort(nodes, edges)
    nmap = {n["id"]: n for n in nodes}
    incoming: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("source") in incoming and e.get("target") in incoming:
            incoming[e["target"]].append(e["source"])

    # 每个节点输出上下文：{ imageBytes, origBytes, gtInfo, classification, detections, metrics, latencyMs, label }
    ctx: dict[str, dict[str, Any]] = {}
    node_results: dict[str, dict[str, Any]] = {}

    for n in order:
        nid = n["id"]
        ntype = n["type"]
        cfg = n.get("config") or {}
        parent_ids = [p for p in incoming[nid] if p in ctx]
        parents = [ctx[p] for p in parent_ids]
        t0 = time.perf_counter()

        if ntype == "dataset":
            ds_id = cfg.get("datasetId") or "Admin/dehaze-dataset"
            idx = sample_index if sample_index is not None else int(cfg.get("sampleIndex") or 0)
            raw, gt_info = _load_dataset_sample(ds_id, idx)
            lat = round((time.perf_counter() - t0) * 1000, 1)
            raw_shape = _img_shape(raw)
            raw_url = _data_url_from_bytes(raw) if include_previews else None
            gt_url = _data_url_from_bytes(gt_info["clearBytes"]) if (include_previews and gt_info.get("clearBytes")) else None
            ctx[nid] = {
                "imageBytes": raw,
                "origBytes": raw,
                "gtInfo": gt_info,
                "branchName": n.get("label") or ds_id,
                "shape": raw_shape,
            }
            outputs: list[dict[str, Any]] = [
                {
                    "name": "待测图像",
                    "kind": "image",
                    "shape": raw_shape,
                    "value": gt_info["fileName"],
                    "preview": raw_url,
                }
            ]
            if gt_info.get("clearBytes"):
                outputs.append({
                    "name": "清晰真值 GT",
                    "kind": "image",
                    "shape": _img_shape(gt_info["clearBytes"]),
                    "value": f"β={gt_info.get('beta', '-')}",
                    "preview": gt_url,
                })
            elif gt_info.get("text"):
                outputs.append({
                    "name": "文本真值 GT",
                    "kind": "text",
                    "value": gt_info["text"],
                })
            elif gt_info.get("label"):
                outputs.append({
                    "name": "类别真值 GT",
                    "kind": "label",
                    "value": gt_info["label"],
                })
            node_results[nid] = {
                "nodeId": nid,
                "type": ntype,
                "status": "ok",
                "latencyMs": lat,
                "summary": f"{gt_info['fileName']} ({idx + 1}/{gt_info['total']})",
                "previewImage": raw_url,
                "gtImage": gt_url,
                "gtLabel": gt_info.get("text") or gt_info.get("label"),
                "outputShape": raw_shape,
                "inputs": [
                    {
                        "name": "数据源配置",
                        "kind": "dataset",
                        "value": f"{ds_id} · 样本 #{idx + 1}/{gt_info['total']}",
                    }
                ],
                "outputs": outputs,
            }

        elif ntype == "preprocess":
            if not parents:
                raise ValueError(f"预处理节点「{n.get('label', nid)}」未连接上游输入")
            p = parents[0]
            p_label = nmap[parent_ids[0]].get("label", parent_ids[0])
            in_bytes = p["imageBytes"]
            in_shape = p.get("shape") or _img_shape(in_bytes)
            out_bytes = apply_preprocess(in_bytes, cfg)
            out_shape = _img_shape(out_bytes)
            lat = round((time.perf_counter() - t0) * 1000, 1)
            in_url = _data_url_from_bytes(in_bytes) if include_previews else None
            out_url = _data_url_from_bytes(out_bytes) if include_previews else None
            ctx[nid] = {
                **p,
                "imageBytes": out_bytes,
                "shape": out_shape,
                "branchName": f"{p.get('branchName', '')} → 预处理",
            }
            node_results[nid] = {
                "nodeId": nid,
                "type": ntype,
                "status": "ok",
                "latencyMs": lat,
                "summary": f"γ={cfg.get('gamma', 1.0)}, 对比度={cfg.get('contrast', 1.0)}, 锐化={cfg.get('sharpen', 0.0)}",
                "inputPreview": in_url,
                "previewImage": out_url,
                "inputShape": in_shape,
                "outputShape": out_shape,
                "inputs": [
                    {
                        "name": "输入图像",
                        "kind": "image",
                        "shape": in_shape,
                        "fromNode": p_label,
                        "preview": in_url,
                    }
                ],
                "outputs": [
                    {
                        "name": "增强图像",
                        "kind": "image",
                        "shape": out_shape,
                        "value": f"γ={cfg.get('gamma', 1.0)} · 对比={cfg.get('contrast', 1.0)} · 锐化={cfg.get('sharpen', 0.0)}",
                        "preview": out_url,
                    }
                ],
            }

        elif ntype == "algorithm":
            if not parents:
                raise ValueError(f"算法节点「{n.get('label', nid)}」未连接上游输入")
            p = parents[0]
            p_label = nmap[parent_ids[0]].get("label", parent_ids[0])
            in_bytes = p["imageBytes"]
            in_shape = p.get("shape") or _img_shape(in_bytes)
            algo_id = cfg.get("algorithmId") or "Admin/dehaze-deanet"
            ver = cfg.get("version") or "v1.0.0"
            task = p.get("gtInfo", {}).get("task") or ("image-dehazing" if "dehaze" in algo_id else "image-classification")
            res = _run_any_algo_on_bytes(algo_id, ver, task, in_bytes, {})
            lat = float(res.get("latencyMs", round((time.perf_counter() - t0) * 1000, 1)))
            out_bytes = in_bytes
            out_url = res.get("outputImage")
            if out_url:
                b64 = out_url.split(",", 1)[1] if "," in out_url else out_url
                out_bytes = base64.b64decode(b64)
            out_shape = _img_shape(out_bytes) if out_url else None
            in_url = _data_url_from_bytes(in_bytes) if include_previews else None
            ctx[nid] = {
                **p,
                "imageBytes": out_bytes,
                "shape": out_shape or in_shape,
                "classification": res.get("classification"),
                "detections": res.get("detections"),
                "text": res.get("text"),
                "branchName": n.get("label") or f"{algo_id}@{ver}",
                "algoId": algo_id,
                "algoVersion": ver,
                "algoLatencyMs": lat,
            }
            summary = f"{algo_id}@{ver}"
            algo_outputs: list[dict[str, Any]] = []
            if out_url:
                algo_outputs.append({
                    "name": "输出图像",
                    "kind": "image",
                    "shape": out_shape,
                    "value": f"{algo_id}@{ver}",
                    "preview": out_url if include_previews else None,
                })
            if res.get("classification"):
                top = res["classification"][0]
                summary = f"{top['label']} ({top['score'] * 100:.1f}%)"
                algo_outputs.append({
                    "name": "分类预测",
                    "kind": "classification",
                    "value": summary,
                    "items": res["classification"],
                })
            if isinstance(res.get("text"), str):
                summary = res["text"] or "(空)"
                algo_outputs.append({
                    "name": "识别文本",
                    "kind": "text",
                    "value": summary,
                })
            if not algo_outputs:
                algo_outputs.append({
                    "name": "推理输出",
                    "kind": "text",
                    "value": summary,
                })
            node_results[nid] = {
                "nodeId": nid,
                "type": ntype,
                "status": "ok",
                "latencyMs": round(lat, 1),
                "summary": summary,
                "inputPreview": in_url,
                "previewImage": out_url if (include_previews and out_url) else None,
                "inputShape": in_shape,
                "outputShape": out_shape,
                "classification": res.get("classification"),
                "inputs": [
                    {
                        "name": "输入图像",
                        "kind": "image",
                        "shape": in_shape,
                        "fromNode": p_label,
                        "preview": in_url,
                    }
                ],
                "outputs": algo_outputs,
            }

        elif ntype == "postprocess":
            if not parents:
                raise ValueError(f"后处理节点「{n.get('label', nid)}」未连接上游输入")
            p = parents[0]
            p_label = nmap[parent_ids[0]].get("label", parent_ids[0])
            in_bytes = p["imageBytes"]
            in_shape = p.get("shape") or _img_shape(in_bytes)
            out_bytes = apply_postprocess(in_bytes, cfg, orig_bytes=p.get("origBytes"))
            out_shape = _img_shape(out_bytes)
            lat = round((time.perf_counter() - t0) * 1000, 1)
            in_url = _data_url_from_bytes(in_bytes) if include_previews else None
            out_url = _data_url_from_bytes(out_bytes) if include_previews else None
            ctx[nid] = {
                **p,
                "imageBytes": out_bytes,
                "shape": out_shape,
                "branchName": f"{p.get('branchName', '')} + 后处理",
            }
            post_inputs: list[dict[str, Any]] = [
                {
                    "name": "上游输出图像",
                    "kind": "image",
                    "shape": in_shape,
                    "fromNode": p_label,
                    "preview": in_url,
                }
            ]
            if float(cfg.get("blendOriginal", 0.0)) > 1e-3 and p.get("origBytes"):
                post_inputs.append({
                    "name": "原始参考图",
                    "kind": "image",
                    "shape": _img_shape(p["origBytes"]),
                    "value": f"残差权重 {cfg.get('blendOriginal')}",
                    "preview": _data_url_from_bytes(p["origBytes"]) if include_previews else None,
                })
            node_results[nid] = {
                "nodeId": nid,
                "type": ntype,
                "status": "ok",
                "latencyMs": lat,
                "summary": f"融合={cfg.get('blendOriginal', 0.0)}, 锐化={cfg.get('sharpen', 0.0)}, 饱和度={cfg.get('saturation', 1.0)}",
                "inputPreview": in_url,
                "previewImage": out_url,
                "inputShape": in_shape,
                "outputShape": out_shape,
                "inputs": post_inputs,
                "outputs": [
                    {
                        "name": "融合优化图像",
                        "kind": "image",
                        "shape": out_shape,
                        "value": f"融合={cfg.get('blendOriginal', 0.0)} · 锐化={cfg.get('sharpen', 0.0)} · 饱和={cfg.get('saturation', 1.0)}",
                        "preview": out_url,
                    }
                ],
            }

        elif ntype == "evaluator":
            if not parents:
                raise ValueError(f"评测节点「{n.get('label', nid)}」未连接上游算法或后处理分支")
            branches: list[dict[str, Any]] = []
            eval_inputs: list[dict[str, Any]] = []
            gt_added = False
            for p_idx, p in enumerate(parents):
                p_label = nmap[parent_ids[p_idx]].get("label", parent_ids[p_idx])
                gt = p.get("gtInfo") or {}
                b_metrics: dict[str, Any] = {}
                br_preview = _data_url_from_bytes(p["imageBytes"]) if include_previews else None
                if gt.get("clearBytes"):
                    with Image.open(io.BytesIO(gt["clearBytes"])) as im_gt:
                        gt_rgb = im_gt.convert("RGB")
                        gt_arr = np.asarray(gt_rgb, dtype=np.float32) / 255.0
                        sz = gt_rgb.size
                    with Image.open(io.BytesIO(p["imageBytes"])) as im_pr:
                        pr_rgb = im_pr.convert("RGB").resize(sz, Image.Resampling.BILINEAR)
                        pr_arr = np.asarray(pr_rgb, dtype=np.float32) / 255.0
                    b_metrics["psnr"] = round(compute_psnr(pr_arr, gt_arr), 2)
                    b_metrics["ssim"] = round(compute_ssim(pr_arr, gt_arr), 4)
                    if not gt_added:
                        eval_inputs.append({
                            "name": "清晰真值 GT",
                            "kind": "image",
                            "shape": f"{sz[0]}×{sz[1]} RGB",
                            "preview": _data_url_from_bytes(gt["clearBytes"]) if include_previews else None,
                        })
                        gt_added = True
                elif gt.get("label") and p.get("classification"):
                    top = p["classification"][0]
                    b_metrics["top1"] = 100.0 if top["label"] == gt["label"] else 0.0
                    b_metrics["predicted"] = top["label"]
                    b_metrics["confidence"] = round(float(top["score"]) * 100.0, 2)
                    if not gt_added:
                        eval_inputs.append({
                            "name": "类别真值 GT",
                            "kind": "label",
                            "value": gt["label"],
                        })
                        gt_added = True
                eval_inputs.append({
                    "name": p.get("branchName") or p_label,
                    "kind": "classification" if p.get("classification") else "image",
                    "fromNode": p_label,
                    "value": (
                        f"{p['classification'][0]['label']} ({p['classification'][0]['score'] * 100:.1f}%)"
                        if p.get("classification")
                        else (p.get("shape") or "RGB")
                    ),
                    "preview": None if p.get("classification") else br_preview,
                })
                branches.append({
                    "branch": p.get("branchName") or "分支",
                    "metrics": b_metrics,
                    "latencyMs": round(float(p.get("algoLatencyMs", 0.0)), 1),
                    "previewImage": br_preview,
                })
            lat = round((time.perf_counter() - t0) * 1000, 1)
            ctx[nid] = {"branches": branches}
            summary = " | ".join(
                f"{b['branch']}: " + (", ".join(f"{k}={v}" for k, v in b["metrics"].items()) or "已运行")
                for b in branches
            )
            node_results[nid] = {
                "nodeId": nid,
                "type": ntype,
                "status": "ok",
                "latencyMs": lat,
                "summary": summary,
                "branches": branches,
                "inputs": eval_inputs,
                "outputs": [
                    {
                        "name": "评测指标报告",
                        "kind": "metrics",
                        "value": summary,
                        "branches": branches,
                    }
                ],
            }

    return {"nodes": node_results}


def run_studio_sample(nodes: list[dict], edges: list[dict], sample_index: int | None = None) -> dict:
    return _execute_graph_on_sample(nodes, edges, sample_index=sample_index, include_previews=True)


def run_studio_batch_eval(nodes: list[dict], edges: list[dict], sample_count: int = 12) -> dict:
    """在真实测试集多张样本上执行可视化编排图，汇总每条分支的真实指标"""
    ds_node = next((n for n in nodes if n["type"] == "dataset"), None)
    if not ds_node:
        raise ValueError("画布中缺少「数据集输入」节点")
    eval_nodes = [n for n in nodes if n["type"] == "evaluator"]
    if not eval_nodes:
        raise ValueError("画布中缺少「评测指标输出」节点")

    ds_id = (ds_node.get("config") or {}).get("datasetId") or "Admin/dehaze-dataset"
    test_dir, _ = _resolve_dataset_test_dir(ds_id)
    with (test_dir / "labels.csv").open("r", encoding="utf-8-sig") as f:
        total_avail = sum(1 for _ in csv.DictReader(f))

    n_run = max(1, min(int(sample_count), min(total_avail, 50)))
    step = max(1, total_avail // n_run)
    indices = [i * step for i in range(n_run) if i * step < total_avail]

    agg: dict[str, dict[str, list[float]]] = {}
    t0 = time.perf_counter()
    for idx in indices:
        out = _execute_graph_on_sample(nodes, edges, sample_index=idx, include_previews=False)
        for ev in eval_nodes:
            ev_res = out["nodes"].get(ev["id"], {})
            for br in ev_res.get("branches", []):
                bname = br["branch"]
                bucket = agg.setdefault(bname, {"latencyMs": []})
                bucket["latencyMs"].append(float(br.get("latencyMs", 0.0)))
                for mk, mv in br.get("metrics", {}).items():
                    if isinstance(mv, (int, float)):
                        bucket.setdefault(mk, []).append(float(mv))

    summary_rows = []
    for bname, cols in agg.items():
        m_avg = {k: round(float(np.mean(v)), 4 if k == "ssim" else 2) for k, v in cols.items() if k != "latencyMs" and v}
        summary_rows.append({
            "branch": bname,
            "samples": len(indices),
            "metrics": m_avg,
            "latencyMs": round(float(np.mean(cols["latencyMs"])), 1) if cols["latencyMs"] else 0.0,
        })

    return {
        "datasetId": ds_id,
        "samplesEvaluated": len(indices),
        "durationSec": round(time.perf_counter() - t0, 2),
        "branches": summary_rows,
    }


def generate_pipeline_predictor_code(
    nodes: list[dict],
    edges: list[dict],
    task: str,
) -> tuple[str, str]:
    """将画布中的「预处理 -> 已有算法 -> 后处理」优化链路编译为标准可执行 predictor.py"""
    order = _topo_sort(nodes, edges)
    pre_cfgs = [n.get("config") or {} for n in order if n["type"] == "preprocess"]
    algo_nodes = [n for n in order if n["type"] == "algorithm"]
    post_cfgs = [n.get("config") or {} for n in order if n["type"] == "postprocess"]
    if not algo_nodes:
        raise ValueError("发布为新算法时，画布中至少需要包含 1 个「已有算法」节点")

    base_algo = algo_nodes[0].get("config") or {}
    base_id = base_algo.get("algorithmId") or "Admin/dehaze-deanet"
    base_ver = base_algo.get("version") or "v1.0.0"

    code = f'''"""由低代码编排实验室自动生成的可执行算法（基于 {base_id}@{base_ver} 优化）"""
import base64
from custom_registry import _run_any_algo_on_bytes
from studio_engine import apply_preprocess, apply_postprocess

BASE_ALGO_ID = {json.dumps(base_id, ensure_ascii=False)}
BASE_VERSION = {json.dumps(base_ver, ensure_ascii=False)}
TASK = {json.dumps(task, ensure_ascii=False)}
PRE_CONFIGS = {json.dumps(pre_cfgs, ensure_ascii=False, indent=2)}
POST_CONFIGS = {json.dumps(post_cfgs, ensure_ascii=False, indent=2)}


class Predictor:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir

    def predict(self, image_bytes: bytes, params: dict | None = None) -> dict:
        orig_bytes = image_bytes
        cur_bytes = image_bytes
        for cfg in PRE_CONFIGS:
            cur_bytes = apply_preprocess(cur_bytes, cfg)

        res = _run_any_algo_on_bytes(BASE_ALGO_ID, BASE_VERSION, TASK, cur_bytes, params or {{}})
        out_url = res.get("outputImage")
        if out_url and POST_CONFIGS:
            b64 = out_url.split(",", 1)[1] if "," in out_url else out_url
            out_bytes = base64.b64decode(b64)
            for cfg in POST_CONFIGS:
                out_bytes = apply_postprocess(out_bytes, cfg, orig_bytes=orig_bytes)
            res["outputImage"] = "data:image/jpeg;base64," + base64.b64encode(out_bytes).decode("ascii")
        return res
'''
    return code, base_id


def publish_studio_pipeline(
    nodes: list[dict],
    edges: list[dict],
    meta: dict,
    created_by: str,
    role: str,
) -> dict:
    task = meta["task"]
    code, base_id = generate_pipeline_predictor_code(nodes, edges, task)
    meta.setdefault("summary", f"通过低代码编排实验室基于 {base_id} 优化发布的算法流水线")
    meta.setdefault("tags", ["低代码编排", "算法优化", "真实部署"])
    return save_custom_algorithm(
        meta=meta,
        filename="predictor.py",
        pkg_bytes=code.encode("utf-8"),
        created_by=created_by,
        role=role,
    )
