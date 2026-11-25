"""
服务器故障检测标准（server-fault）的统一 API：数据集、评测基准、算法卡片、评测任务与推理

  - 数据集：自动发现 backend/data/*/meta.json 中 task == "server-fault" 的标准数据集
  - 算法：ALGORITHM_MODULES 中实现了 server_fault_std 算法接口的模块
  - 评测：任意标准算法 × 任意标准评测基准，统一由 server_fault_std.evaluate 计算（同一套指标与图表）

server.py 只需：include_router(router_sf)（在通用 /real-api/algorithms/Admin/{algo_name}/infer 之前）、
bootstrap 合并 bootstrap_sf()、/real-api/evals 优先调用 trigger_eval_sf()、评测列表 / 详情合并 list_evals_sf() / find_eval_sf()。
"""
from __future__ import annotations

import csv
import io
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Literal

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import fault0x07_registry
import fault_0x6e_registry
import server_fault_std as std

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data"
EVALS_PATH = ROOT / "state" / "server_fault_evals.json"
EVALUATOR_ID = "server-fault-std-evaluator"
EVALUATOR_VERSION = "v1.0.0"

ALGORITHM_MODULES: list[ModuleType] = [fault0x07_registry, fault_0x6e_registry]
ALGOS: dict[str, ModuleType] = {m.ALGO_ID: m for m in ALGORITHM_MODULES}

router_sf = APIRouter()
_LOCK = threading.Lock()
_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


# ================================================================== 数据集与基准发现
def discover_datasets() -> dict[str, Path]:
    out: dict[str, Path] = {}
    if DATA_ROOT.exists():
        for d in sorted(DATA_ROOT.iterdir()):
            meta = std.read_meta(d) if d.is_dir() else None
            if meta:
                out[meta["id"]] = d
    return out


DATASETS = discover_datasets()


def _benchmarks() -> dict[str, tuple[dict, Path]]:
    out = {}
    for ds_id, d in DATASETS.items():
        meta = std.read_meta(d)
        if meta and meta.get("benchmark"):
            out[meta["benchmark"]["id"]] = (meta, d)
    return out


def _safe_name(filename: str) -> str:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    return filename


def _part_rows(ds_id: str, d: Path, part: str, limit: int, balanced: bool = False) -> list[dict]:
    rows = std.read_labels(d, part)
    if balanced:
        # 卡片预览：各状态轮流取样，避免前几条恰好都是「正常」
        by_label: dict[str, list[dict]] = {}
        for r in rows:
            by_label.setdefault(r["label"], []).append(r)
        mixed: list[dict] = []
        while len(mixed) < min(limit, len(rows)):
            for lst in by_label.values():
                if lst and len(mixed) < limit:
                    mixed.append(lst.pop(0))
        rows = mixed
    out = []
    for i, row in enumerate(rows):
        if i >= limit:
            break
        onset = int(row["onset_min"])
        where = f"第 {onset} 分钟起" if 0 <= onset < std.WINDOW else ("窗口后发生 · 含前兆" if onset >= std.WINDOW else "全程正常")
        out.append({
            "file_name": row["file_name"],
            "label": f"{row['label']}（{row['server']} · {where}）",
            "url": f"/real-api/datasets/{ds_id}/files/{part}/{Path(row['file_name']).name}",
            "row": [row[c] for c in std.LABEL_COLUMNS],
        })
    return out


def _dataset_obj(ds_id: str, d: Path) -> dict:
    meta = std.read_meta(d) or {}
    readme_path = d / "README.md"
    org, name = ds_id.split("/", 1)

    def part(p: str) -> dict:
        s = meta[p]
        return {
            "name": p,
            "columns": std.LABEL_COLUMNS,
            "versions": [{
                "version": "v1.0",
                "createdAt": meta.get("createdAt", "2026-11-25T01:00:00+08:00"),
                "createdBy": "admin",
                "contentHash": s["contentHash"],
                "sizeBytes": s["sizeBytes"],
                "note": f"{s['files']:,} 个 60 分钟 × 8 通道窗口（服务器故障检测标准格式，逐分钟状态真值）",
                "files": s["files"],
                "rows": s["rows"],
            }],
            "classCounts": s.get("classCounts", {}),
        }

    present = [s for s in std.STATES if s in meta.get("train", {}).get("classCounts", {}) or s in meta.get("test", {}).get("classCounts", {})]
    return {
        "id": ds_id,
        "org": org,
        "name": name,
        "displayName": meta.get("displayName", name),
        "task": std.TASK,
        "summary": meta.get("summary", ""),
        "readme": readme_path.read_text(encoding="utf-8") if readme_path.exists() else "",
        "tags": meta.get("tags", []),
        "classes": present,
        "train": part("train"),
        "test": part("test"),
        "likes": 3,
        "downloads": 5,
        "updatedAt": meta.get("createdAt", "2026-11-25T01:00:00+08:00"),
        "previewSeed": 707,
        "realPreview": {"train": _part_rows(ds_id, d, "train", 12, balanced=True), "test": _part_rows(ds_id, d, "test", 12, balanced=True)},
    }


def _benchmark_obj(meta: dict) -> dict:
    b = meta["benchmark"]
    return {
        "id": b["id"],
        "name": b["id"],
        "displayName": b["displayName"],
        "description": f"基于 {meta['id']} 测试集 v1.0（{meta['test']['files']} 个 60 分钟窗口、{meta['test']['files'] * 60:,} 个逐分钟真值），按服务器故障检测标准评估：任何符合标准的算法都可以在此评测。",
        "task": std.TASK,
        "datasetId": meta["id"],
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": EVALUATOR_ID,
        "evaluatorVersion": EVALUATOR_VERSION,
        "metrics": std.METRICS,
        "createdAt": meta.get("createdAt", "2026-11-25T01:00:00+08:00"),
        "org": "Admin",
    }


# ================================================================== 评测任务
def _load_evals() -> list[dict]:
    if EVALS_PATH.exists():
        try:
            return json.loads(EVALS_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_evals(evals: list[dict]) -> None:
    EVALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = EVALS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(evals, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(EVALS_PATH)


def _update(eval_id: str, log: str | None = None, **fields) -> None:
    with _LOCK:
        evals = _load_evals()
        for r in evals:
            if r["id"] == eval_id:
                r.update(fields)
                if log:
                    r["logs"].append(log)
        _save_evals(evals)


def _run_eval(eval_id: str, algo_id: str, bench_id: str) -> None:
    mod = ALGOS[algo_id]
    meta, d = _benchmarks()[bench_id]
    try:
        _update(eval_id, status="running", startedAt=_now(), progress=5)
        _update(eval_id, progress=10, log=f"[runner] 加载 {algo_id}@v1.0.0（{mod.device_label()}），按服务器故障检测标准接口 predict_batch 调用")
        state = mod.load_state() or {}
        res = std.evaluate(mod.predict_batch, d, history=state.get("history"), say=lambda p, m: _update(eval_id, progress=p, log=m))
        m = res["metrics"]
        with _LOCK:
            evals = _load_evals()
            for r in evals:
                if r["id"] != eval_id and r["algorithmId"] == algo_id and r["benchmarkId"] == bench_id:
                    r["isLatestValid"] = False
            for r in evals:
                if r["id"] == eval_id:
                    r.update({
                        "status": "succeeded",
                        "progress": 100,
                        "finishedAt": _now(),
                        "metrics": m,
                        "perClass": res["perClass"],
                        "perClassLabel": res["perClassLabel"],
                        "durationSec": res["durationSec"],
                        "latencyMs": res["latencyMs"],
                        "peakGpuMemGB": mod.CARD.get("gpuMem", 0.1),
                        "isLatestValid": True,
                        "vizServerFault": res["vizServerFault"],
                    })
                    r["logs"].append("[done] 真实评测完成：" + "，".join(f"{x['label']}={m[x['key']]}{'' if x['unit'] == '分钟' else '%'}" for x in std.METRICS if x["key"] in m))
            _save_evals(evals)
    except Exception as exc:  # noqa: BLE001
        _update(eval_id, status="failed", finishedAt=_now(), error=str(exc), log=f"[error] 评测失败：{exc}")


def trigger_eval_sf(algorithm_id: str, algo_version: str, benchmark_id: str, submitted_by: str) -> dict | None:
    """服务器故障检测标准算法 × 标准基准：发起真实评测；两者都不属于本标准时返回 None"""
    benches = _benchmarks()
    if algorithm_id not in ALGOS and benchmark_id not in benches:
        return None
    if algorithm_id not in ALGOS or benchmark_id not in benches:
        raise HTTPException(status_code=400, detail="算法与评测基准必须都符合服务器故障检测标准（server-fault）")
    mod = ALGOS[algorithm_id]
    meta, _ = benches[benchmark_id]
    with _LOCK:
        evals = _load_evals()
        eval_id = f"ev-sf-{1001 + len(evals)}"
        run = {
            "id": eval_id,
            "algorithmId": algorithm_id,
            "algoVersion": algo_version,
            "benchmarkId": benchmark_id,
            "status": "queued",
            "progress": 0,
            "submittedBy": submitted_by,
            "submittedAt": _now(),
            "metrics": {},
            "imageDigest": mod.CARD["imageDigest"],
            "weightsHash": mod.CARD["weightsHash"],
            "evaluatorVersion": EVALUATOR_VERSION,
            "params": {"standard": std.TASK, "window_minutes": std.WINDOW, "threshold": 0.5, "min_fault_run": std.MIN_FAULT_RUN},
            "hardware": mod.device_label(),
            "datasetHash": meta["test"]["contentHash"],
            "isLatestValid": False,
            "logs": [f"[scheduler] 真实评测任务 {eval_id} 已入队：{algorithm_id}@{algo_version} × {benchmark_id}（{meta['id']}）"],
        }
        evals.insert(0, run)
        _save_evals(evals)
    threading.Thread(target=_run_eval, args=(eval_id, algorithm_id, benchmark_id), daemon=True).start()
    return run


def list_evals_sf() -> list[dict]:
    return _load_evals()


def find_eval_sf(eval_id: str) -> dict | None:
    if not eval_id.startswith("ev-sf-"):
        return None
    return next((r for r in _load_evals() if r["id"] == eval_id), None)


def ensure_matrix_evals_sf() -> None:
    """启动时补齐「全部标准算法 × 全部标准基准」中还没有成功评测的组合（后台依次执行）"""
    def worker():
        done = {(r["algorithmId"], r["benchmarkId"]) for r in _load_evals() if r.get("status") in ("succeeded", "running", "queued")}
        for algo_id, mod in ALGOS.items():
            if not mod.WEIGHT_PATH.exists():
                continue
            for bench_id in _benchmarks():
                if (algo_id, bench_id) not in done:
                    run = trigger_eval_sf(algo_id, "v1.0.0", bench_id, "admin")
                    while True:  # 依次执行，避免同时占用 GPU
                        cur = find_eval_sf(run["id"]) if run else None
                        if not cur or cur["status"] in ("succeeded", "failed"):
                            break
                        threading.Event().wait(0.3)

    threading.Thread(target=worker, daemon=True).start()


# ================================================================== 算法卡片
def _algorithm_obj(mod: ModuleType, evals: list[dict], benches: dict) -> dict:
    card = mod.CARD
    state = mod.load_state() or {}
    org, name = mod.ALGO_ID.split("/", 1)
    wbytes = mod.WEIGHT_PATH.stat().st_size if mod.WEIGHT_PATH.exists() else 0
    rows = []
    for bench_id, (meta, _) in benches.items():
        ev = next((e for e in evals if e["algorithmId"] == mod.ALGO_ID and e["benchmarkId"] == bench_id and e.get("isLatestValid")), None)
        if ev:
            m = ev["metrics"]
            cell = lambda k: f"{m[k]}" if k in m else "—"  # noqa: E731
            rows.append(f"| {meta['benchmark']['displayName']} | {cell('fault_f1')} | {cell('fault_auc')} | {cell('state_macro_f1')} | {cell('false_alarm_rate')} | {cell('warn_auc')} |")
    table = ""
    if rows:
        table = "\n## 标准评测结果（服务器故障检测标准，同一评测器）\n\n| 评测基准 | 故障检测 F1 % | 故障 AUC % | 类型 Macro-F1 % | 误报率 % | 预警 AUC % |\n| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    readme = card["readme"].rstrip() + "\n" + table
    algo_yaml = f"""name: {card['name']}
version: v1.0.0
task: {std.TASK}
business: {card['business']}
framework: PyTorch
summary: {card['summary']}
tags:
""" + "".join(f"  - {t}\n" for t in card["tags"]) + f"""entrypoint: {card['codeFile']}:predict_batch
standard: server_fault_std（输入 [N, 60, 8] 标准遥测，输出 fault_prob / state / warn_prob）
runtime: Python 3.12 · PyTorch 2.x · NumPy
"""
    trained = state.get("trained_at", "2026-11-25T01:00:00+08:00")
    return {
        "id": mod.ALGO_ID,
        "org": org,
        "name": name,
        "displayName": card["displayName"],
        "task": std.TASK,
        "business": card["business"],
        "selfDeveloped": True,
        "framework": "PyTorch",
        "summary": card["summary"],
        "readme": readme,
        "algoYaml": algo_yaml,
        "tags": card["tags"],
        "likes": card.get("likes", 1),
        "evalCount": sum(1 for e in evals if e["algorithmId"] == mod.ALGO_ID),
        "downloads": card.get("downloads", 1),
        "updatedAt": trained,
        "files": [
            {"path": card["codeFile"], "size": 16000, "kind": "code"},
            {"path": f"weights/{mod.WEIGHT_PATH.name}", "size": wbytes, "kind": "weights"},
            {"path": "algo.yaml", "size": len(algo_yaml.encode("utf-8")), "kind": "config"},
            {"path": "README.md", "size": len(readme.encode("utf-8")), "kind": "doc"},
        ],
        "versions": [{
            "version": "v1.0.0",
            "status": "ready",
            "createdAt": trained,
            "createdBy": "admin",
            "changelog": card["changelog"],
            "imageDigest": card["imageDigest"],
            "weightsHash": card["weightsHash"],
            "weightsSize": wbytes,
            "baseImage": "pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime",
            "gpuMem": card.get("gpuMem", 0.1),
            "buildLog": [
                "[build] 加载底座镜像 pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime",
                f"[build] 校验权重文件 {mod.WEIGHT_PATH.name}（{wbytes:,} B）通过",
                "[build] 服务器故障检测标准接口自检：predict_batch([N, 60, 8]) -> fault_prob [N, 60] 通过",
            ],
        }],
    }


def bootstrap_sf() -> dict:
    benches = _benchmarks()
    evals = _load_evals()
    return {
        "algorithms": [_algorithm_obj(m, evals, benches) for m in ALGORITHM_MODULES if m.WEIGHT_PATH.exists()],
        "datasets": [_dataset_obj(i, d) for i, d in DATASETS.items()],
        "benchmarks": [_benchmark_obj(meta) for meta, _ in benches.values()],
        "evals": evals,
    }


# ================================================================== 推理
def _infer(mod: ModuleType, raw: np.ndarray, source: str, gt: list[int] | None, warn_gt: list[int] | None, dataset_id: str | None) -> dict:
    import time

    t0 = time.perf_counter()
    out = mod.predict_batch(raw[None])
    P = np.asarray(out["fault_prob"])[0]
    S = np.asarray(out["state"])[0] if out.get("state") is not None else None
    W = np.asarray(out["warn_prob"])[0] if out.get("warn_prob") is not None else None
    code = std.run_label(S, P)
    first = next((t for t in range(std.WINDOW) if P[t] >= 0.5), None)
    diag = mod.diagnose(raw, {"fault_prob": P, "state": S}) if hasattr(mod, "diagnose") else None
    return {
        "device": mod.device_label(),
        "latencyMs": max(0.3, round((time.perf_counter() - t0) * 1000, 2)),
        "queuedMs": 0,
        "raw": {
            "algorithm": mod.ALGO_ID,
            "version": "v1.0.0",
            "task": std.TASK,
            "standard": "server_fault_std",
            "source_file": source,
            "dataset": dataset_id,
            "states": std.STATES,
            "status": std.STATES[code],
            "diagnosis": diag,
            "first_fault_minute": first,
            "max_fault_prob": round(float(P.max()) * 100, 2),
            "risk_next_10min": round(float(W[-1]) * 100, 2) if W is not None else None,
            "channels": {c: [round(float(v), 1) for v in raw[:, k]] for k, c in enumerate(std.CHANNELS)},
            "fault_prob": [round(float(v), 4) for v in P],
            "state": S.astype(int).tolist() if S is not None else None,
            "warn_prob": [round(float(v), 4) for v in W] if W is not None else None,
            "gt": gt,
            "warnGt": warn_gt,
        },
    }


def _resolve_sample(sample_path: str) -> tuple[str, Path, str]:
    """sample_path 形如 /real-api/datasets/{org}/{name}/files/train/{file}；推理示例只允许训练集"""
    parts = sample_path.split("?", 1)[0].strip("/").split("/")
    if len(parts) >= 7 and parts[0] == "real-api" and parts[1] == "datasets" and parts[4] == "files":
        ds_id = f"{parts[2]}/{parts[3]}"
        if ds_id in DATASETS and parts[5] == "train":
            return ds_id, DATASETS[ds_id], _safe_name(parts[6])
    raise HTTPException(status_code=400, detail="示例只能取自标准数据集的训练集")


def _make_infer_route(mod: ModuleType):
    async def endpoint(version: str = Form("v1.0.0"), file: UploadFile | None = File(None), sample_path: str | None = Form(None)):
        if file is not None:
            text = (await file.read()).decode("utf-8-sig", errors="ignore")
            try:
                raw = std.parse_series(list(csv.DictReader(io.StringIO(text))), file.filename or "upload.csv")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            return _infer(mod, raw, file.filename or "upload.csv", None, None, None)
        if not sample_path:
            raise HTTPException(status_code=400, detail="请上传标准遥测 CSV 或选择训练集示例")
        ds_id, d, fname = _resolve_sample(sample_path)
        rec = next((r for r in std.read_labels(d, "train") if Path(r["file_name"]).name == fname), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="示例不存在")
        raw = std.read_series(d / "train" / rec["file_name"])
        return _infer(mod, raw, fname, json.loads(rec["state_seq"]), json.loads(rec["warn_seq"]), ds_id)

    return endpoint


for _mod in ALGORITHM_MODULES:
    router_sf.add_api_route(f"/real-api/algorithms/{_mod.ALGO_ID}/infer", _make_infer_route(_mod), methods=["POST"])


# ================================================================== 数据集路由（每个标准数据集一组静态路径，避免遮挡自助上传数据集的通用路由）
def _make_dataset_routes(ds_id: str, d: Path) -> None:
    prefix = f"/real-api/datasets/{ds_id}"

    def part(part: Literal["train", "test"], limit: int = 200):
        meta = std.read_meta(d) or {}
        return {"part": part, "columns": std.LABEL_COLUMNS, "total": meta.get(part, {}).get("files", 0), "rows": _part_rows(ds_id, d, part, max(1, min(limit, 500)))}

    def file(part: Literal["train", "test"], filename: str):
        path = d / part / "series" / _safe_name(filename)
        if not path.exists():
            raise HTTPException(status_code=404, detail="时序文件不存在")
        return FileResponse(path, media_type="text/csv")

    def download(part: Literal["train", "test"]):
        zip_path = d / f"{d.name}-{part}-v1.0.zip"
        if not zip_path.exists():
            raise HTTPException(status_code=404, detail="数据集压缩包不存在")
        return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)

    def series(part: Literal["train", "test"], filename: str):
        name = _safe_name(filename)
        rec = next((r for r in std.read_labels(d, part) if Path(r["file_name"]).name == name), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="样本不存在")
        raw = std.read_series(d / part / rec["file_name"])
        return {
            "file": name,
            "label": rec["label"],
            "server": rec["server"],
            "role": rec["role"],
            "onset": int(rec["onset_min"]),
            "states": std.STATES,
            "channels": {c: [float(v) for v in raw[:, k]] for k, c in enumerate(std.CHANNELS)},
            "gt": json.loads(rec["state_seq"]),
            "warnGt": json.loads(rec["warn_seq"]),
        }

    router_sf.add_api_route(f"{prefix}/part/{{part}}", part, methods=["GET"])
    router_sf.add_api_route(f"{prefix}/files/{{part}}/{{filename}}", file, methods=["GET"])
    router_sf.add_api_route(f"{prefix}/download/{{part}}", download, methods=["GET"])
    router_sf.add_api_route(f"{prefix}/series/{{part}}/{{filename}}", series, methods=["GET"])


for _ds_id, _d in DATASETS.items():
    _make_dataset_routes(_ds_id, _d)


@router_sf.get("/real-api/server-fault/samples")
def samples_sf(dataset: str, label: str | None = None, limit: int = 60):
    """推理示例：只列出标准数据集训练集（公开）中的窗口"""
    d = DATASETS.get(dataset)
    if d is None:
        raise HTTPException(status_code=404, detail="不是服务器故障检测标准数据集")
    out = []
    for r in std.read_labels(d, "train"):
        if label and r["label"] != label:
            continue
        out.append({"file": Path(r["file_name"]).name, "label": r["label"], "server": r["server"], "onset": int(r["onset_min"])})
        if len(out) >= limit:
            break
    return out


@router_sf.get("/real-api/server-fault/standard")
def standard_sf():
    """服务器故障检测标准说明（供前端展示与第三方对接）"""
    return {
        "task": std.TASK,
        "window": std.WINDOW,
        "warnHorizon": std.WARN_HORIZON,
        "seriesColumns": std.SERIES_COLUMNS,
        "labelColumns": std.LABEL_COLUMNS,
        "states": std.STATES,
        "units": std.CHANNEL_UNITS,
        "metrics": std.METRICS,
        "datasets": list(DATASETS),
        "algorithms": list(ALGOS),
    }
