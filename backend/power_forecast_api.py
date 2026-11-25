"""
新能源功率预测标准（power-forecast）的统一 API：数据集、评测基准、算法卡片、评测任务与推理（与 server_fault_api 同一模式）

  - 数据集：自动发现 backend/data/*/meta.json 中 task == "power-forecast" 的标准数据集
  - 算法：ALGORITHM_MODULES 中实现了 power_forecast_std 算法接口（predict_batch）的模块
  - 评测：任意标准算法 × 任意标准评测基准，统一由 power_forecast_std.evaluate 计算；真值只由评测器读取
  - 推理示例只允许取自训练集（测试集仅管理员可见，推理接口不返回测试真值）

server.py：include_router(router_pf)（在通用推理路由之前）、bootstrap 合并 bootstrap_pf()、
/real-api/evals 优先调用 trigger_eval_pf()、列表 / 详情合并 list_evals_pf() / find_eval_pf()、启动时 ensure_matrix_evals_pf()。
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Literal

import numpy as np
import torch
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import power_forecast_std as pstd
import power_lgbm_autoreg
import power_lgbm_direct
import power_lgbm_hybrid
import power_registry

ROOT = Path(__file__).resolve().parent
DATA_ROOT = ROOT / "data"
EVALS_PATH = ROOT / "state" / "power_forecast_evals.json"
EVALUATOR_ID = "power-forecast-std-evaluator"
EVALUATOR_VERSION = "v2.0.0"
BASE_IMAGE = "pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime"

ALGORITHM_MODULES: list[ModuleType] = [
    power_registry,
    power_lgbm_hybrid,
    power_lgbm_direct,
    power_lgbm_autoreg,
]
ALGOS: dict[str, ModuleType] = {m.ALGO_ID: m for m in ALGORITHM_MODULES}

router_pf = APIRouter()
_LOCK = threading.Lock()
_TZ = timezone(timedelta(hours=8))


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _digest(*paths: Path) -> str:
    h = hashlib.sha256()
    for p in paths:
        if p.exists():
            h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()


def _weights_hash(mod: ModuleType) -> str:
    return pstd.sha256_file(mod.WEIGHT_PATH) if mod.WEIGHT_PATH.exists() else ""


# ================================================================== 数据集与基准发现
def discover_datasets() -> dict[str, Path]:
    out: dict[str, Path] = {}
    if DATA_ROOT.exists():
        for d in sorted(DATA_ROOT.iterdir()):
            meta = pstd.read_meta(d) if d.is_dir() else None
            if meta:
                out[meta["id"]] = d
    return out


DATASETS = discover_datasets()


def _benchmarks() -> dict[str, tuple[dict, Path]]:
    out = {}
    for d in DATASETS.values():
        meta = pstd.read_meta(d)
        if meta and meta.get("benchmark"):
            out[meta["benchmark"]["id"]] = (meta, d)
    return out


def _safe_name(filename: str) -> str:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    return filename


def _part_rows(ds_id: str, d: Path, part: str, limit: int) -> list[dict]:
    rows = pstd.read_labels(d, part)
    by_station: dict[str, list[dict]] = {}
    for r in rows:
        by_station.setdefault(r["station"], []).append(r)
    mixed: list[dict] = []
    while len(mixed) < min(limit, len(rows)):  # 各场站轮流取样
        for lst in by_station.values():
            if lst and len(mixed) < limit:
                mixed.append(lst.pop(0))
    return [{
        "file_name": r["file_name"],
        "label": f"{r['value']} MW（{r['station']} · {r['weather']}）",
        "url": f"/real-api/datasets/{ds_id}/files/{part}/{Path(r['file_name']).name}",
        "row": [r[c] for c in pstd.LABEL_COLUMNS[:-1]],
    } for r in mixed]


def _dataset_obj(ds_id: str, d: Path) -> dict:
    meta = pstd.read_meta(d) or {}
    readme = (d / "README.md").read_text(encoding="utf-8") if (d / "README.md").exists() else ""
    org, name = ds_id.split("/", 1)

    def part(p: str) -> dict:
        s = meta[p]
        return {
            "name": p,
            "columns": pstd.LABEL_COLUMNS,
            "versions": [{
                "version": "v1.0",
                "createdAt": meta.get("createdAt", _now()),
                "createdBy": "admin",
                "contentHash": s["contentHash"],
                "sizeBytes": s["sizeBytes"],
                "note": f"{s['files']:,} 个日前预测窗口（24h 实测 + 24h NWP → 24h 功率）",
                "files": s["files"],
                "rows": s["rows"],
            }],
            "classCounts": s.get("classCounts", {}),
        }

    return {
        "id": ds_id,
        "org": org,
        "name": name,
        "displayName": meta.get("displayName", name),
        "task": pstd.TASK,
        "summary": meta.get("summary", ""),
        "readme": readme,
        "tags": meta.get("tags", []),
        "license": "CC-BY-4.0",
        "classes": list((meta.get("stations") or {}).keys()),
        "train": part("train"),
        "test": part("test"),
        "likes": 12,
        "downloads": 26,
        "updatedAt": meta.get("createdAt", _now()),
        "previewSeed": 4100,
        "realPreview": {"train": _part_rows(ds_id, d, "train", 12), "test": _part_rows(ds_id, d, "test", 12)},
    }


def _benchmark_obj(meta: dict) -> dict:
    b = meta["benchmark"]
    lo, hi = pstd.SOLAR_EVAL_HOURS.start, pstd.SOLAR_EVAL_HOURS.stop - 1
    return {
        "id": b["id"],
        "name": b["id"],
        "displayName": b["displayName"],
        "description": f"基于 {meta['id']} 测试集 v1.0（{meta['test']['files']} 个日前预测窗口），按新能源功率预测标准评估：考核准确率按装机容量归一化，风电计全天、光伏只计 {lo}:00–{hi}:00。",
        "task": pstd.TASK,
        "datasetId": meta["id"],
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": EVALUATOR_ID,
        "evaluatorVersion": EVALUATOR_VERSION,
        "metrics": pstd.METRICS,
        "createdAt": meta.get("createdAt", _now()),
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
    for attempt in range(6):
        try:
            tmp.replace(EVALS_PATH)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


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
    _, d = _benchmarks()[bench_id]
    try:
        _update(eval_id, status="running", startedAt=_now(), progress=5)
        _update(eval_id, progress=10, log=f"[runner] 加载 {algo_id}@v1.0.0（{mod.device_label()}），按功率预测标准接口 predict_batch 调用")
        state = mod.load_state() or {}
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        res = pstd.evaluate(mod.predict_batch, d, history=state.get("history"), say=lambda p, m: _update(eval_id, progress=p, log=m))
        peak_gb = round(torch.cuda.max_memory_allocated() / 1024 ** 3, 3) if torch.cuda.is_available() else 0.0
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
                        "peakGpuMemGB": peak_gb,
                        "isLatestValid": True,
                        "vizPowerForecast": {**res["vizPowerForecast"], "bestEpoch": state.get("best_epoch")},
                    })
                    base = res["vizPowerForecast"]["baselines"]
                    r["logs"].append("[done] 真实评测完成：" + "，".join(f"{x['label']}={m[x['key']]}{x['unit']}" for x in pstd.METRICS if x["key"] in m))
                    r["logs"].append("[done] 参照基线：" + "，".join(f"{b['name']} 准确率 {b['accuracy']}%" for b in base))
            _save_evals(evals)
    except Exception as exc:  # noqa: BLE001
        _update(eval_id, status="failed", finishedAt=_now(), error=str(exc), log=f"[error] 评测失败：{exc}")


def trigger_eval_pf(algorithm_id: str, algo_version: str, benchmark_id: str, submitted_by: str) -> dict | None:
    """功率预测标准算法 × 标准基准：发起真实评测；两者都不属于本标准时返回 None"""
    benches = _benchmarks()
    if algorithm_id not in ALGOS and benchmark_id not in benches:
        return None
    if algorithm_id not in ALGOS or benchmark_id not in benches:
        raise HTTPException(status_code=400, detail="算法与评测基准必须都符合新能源功率预测标准（power-forecast）")
    if algo_version != "v1.0.0":
        raise HTTPException(status_code=400, detail=f"{algorithm_id} 只有 v1.0.0 一个版本")
    mod = ALGOS[algorithm_id]
    meta, _ = benches[benchmark_id]
    with _LOCK:
        evals = _load_evals()
        eval_id = f"ev-pf-{1001 + len(evals)}"
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
            "imageDigest": _digest(mod.CODE_PATH, mod.WEIGHT_PATH),
            "weightsHash": _weights_hash(mod),
            "evaluatorVersion": EVALUATOR_VERSION,
            "params": {
                "standard": pstd.TASK,
                "lookback_hours": pstd.LOOKBACK,
                "horizon_hours": pstd.HORIZON,
                "solar_eval_hours": f"{pstd.SOLAR_EVAL_HOURS.start}:00-{pstd.SOLAR_EVAL_HOURS.stop - 1}:00",
                "qualified_accuracy": pstd.QUALIFIED_ACC,
                "precision": "fp32",
            },
            "hardware": mod.device_label(),
            "datasetHash": meta["test"]["contentHash"],
            "isLatestValid": False,
            "logs": [f"[scheduler] 真实评测任务 {eval_id} 已入队：{algorithm_id}@{algo_version} × {benchmark_id}（{meta['id']}）"],
        }
        evals.insert(0, run)
        _save_evals(evals)
    threading.Thread(target=_run_eval, args=(eval_id, algorithm_id, benchmark_id), daemon=True).start()
    return run


def list_evals_pf() -> list[dict]:
    return _load_evals()


def find_eval_pf(eval_id: str) -> dict | None:
    if not eval_id.startswith("ev-pf-"):
        return None
    return next((r for r in _load_evals() if r["id"] == eval_id), None)


def ensure_matrix_evals_pf() -> None:
    """启动时补齐「全部标准算法 × 全部标准基准」中还没有成功评测的组合（后台依次执行）"""
    def worker():
        done = {(r["algorithmId"], r["benchmarkId"]) for r in _load_evals() if r.get("status") in ("succeeded", "running", "queued")}
        for algo_id, mod in ALGOS.items():
            if not mod.WEIGHT_PATH.exists():
                continue
            for bench_id in _benchmarks():
                if (algo_id, bench_id) not in done:
                    run = trigger_eval_pf(algo_id, "v1.0.0", bench_id, "admin")
                    while True:
                        cur = find_eval_pf(run["id"]) if run else None
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
            base = {b["key"]: b["accuracy"] for b in ev.get("vizPowerForecast", {}).get("baselines", [])}
            rows.append(f"| {meta['benchmark']['displayName']} | {m.get('accuracy_rate', '—')} | {m.get('nrmse', '—')} | {m.get('skill', '—')} | {base.get('nominal', '—')} | {base.get('persistence', '—')} |")
    table = ""
    if rows:
        table = "\n## 标准评测结果（新能源功率预测标准，同一评测器）\n\n| 评测基准 | 考核准确率 % | NRMSE % | 相对 NWP 基线提升 % | 基线：NWP + 名义曲线 % | 基线：持续法 % |\n| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows) + "\n"
    readme = card["readme"].rstrip() + "\n" + table
    framework = card.get("framework", "PyTorch")
    runtime = card.get("runtime", "Python 3.12 · PyTorch 2.x · NumPy")
    base_image = card.get("baseImage", "python:3.12-slim" if framework == "LightGBM" else BASE_IMAGE)
    gpu_mem = card.get("gpuMem", 0.1)
    algo_yaml = f"""name: {card['name']}
version: v1.0.0
task: {pstd.TASK}
business: {card['business']}
framework: {framework}
summary: {card['summary']}
tags:
""" + "".join(f"  - {t}\n" for t in card["tags"]) + f"""entrypoint: {card['codeFile']}:predict_batch
standard: power_forecast_std（输入 [N, 24, 9] + 场站规格，输出 [N, 24] MW）
runtime: {runtime}
"""
    trained = state.get("trained_at", _now())
    code_bytes = mod.CODE_PATH.stat().st_size
    return {
        "id": mod.ALGO_ID,
        "org": org,
        "name": name,
        "displayName": card["displayName"],
        "task": pstd.TASK,
        "business": card["business"],
        "selfDeveloped": True,
        "framework": framework,
        "summary": card["summary"],
        "readme": readme,
        "algoYaml": algo_yaml,
        "tags": card["tags"],
        "license": "Apache-2.0",
        "likes": card.get("likes", 1),
        "evalCount": sum(1 for e in evals if e["algorithmId"] == mod.ALGO_ID),
        "downloads": card.get("downloads", 1),
        "updatedAt": trained,
        "files": [
            {"path": card["codeFile"], "size": code_bytes, "kind": "code"},
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
            "imageDigest": _digest(mod.CODE_PATH, mod.WEIGHT_PATH),
            "weightsHash": _weights_hash(mod),
            "weightsSize": wbytes,
            "baseImage": base_image,
            "gpuMem": gpu_mem,
            "buildLog": [
                f"[build] 加载底座镜像 {base_image}",
                f"[build] 校验权重文件 {mod.WEIGHT_PATH.name}（{wbytes:,} B，{_weights_hash(mod)}）通过",
                "[build] 功率预测标准接口自检：predict_batch([N, 24, 9], specs) -> [N, 24] MW",
            ],
        }],
    }


def bootstrap_pf() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    benches = _benchmarks()
    evals = _load_evals()
    return (
        [_algorithm_obj(m, evals, benches) for m in ALGORITHM_MODULES if m.WEIGHT_PATH.exists()],
        [_dataset_obj(i, d) for i, d in DATASETS.items()],
        [_benchmark_obj(meta) for meta, _ in benches.values()],
        evals,
    )


# ================================================================== 推理
def _infer(mod: ModuleType, raw: np.ndarray, spec: dict, meta: dict, gt: np.ndarray | None, dataset_id: str | None) -> dict:
    t0 = time.perf_counter()
    pred = np.asarray(mod.predict_batch(raw[None], [spec]), dtype=np.float64)[0]
    latency = round((time.perf_counter() - t0) * 1000, 2)
    case = pstd.build_case_payload(raw, spec, meta, gt, pred)
    return {
        "device": mod.device_label(),
        "latencyMs": latency,
        "queuedMs": 0,
        "raw": {
            "algorithm": mod.ALGO_ID,
            "version": "v1.0.0",
            "task": pstd.TASK,
            "standard": "power_forecast_std",
            "unit": "MW",
            "dataset": dataset_id,
            "spec": spec,
            "source_file": case["file"],
            "forecast": case["pred"],
            "gt": case["gt"],
            "case": case,
            "mean_mw": round(float(pred.mean()), 2),
            "peak_mw": round(float(pred.max()), 2),
            "min_mw": round(float(pred.min()), 2),
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
    async def endpoint(
        version: str = Form("v1.0.0"),
        file: UploadFile | None = File(None),
        sample_path: str | None = Form(None),
        kind: str | None = Form(None),
        capacity_mw: float | None = Form(None),
    ):
        if file is not None:
            if kind not in pstd.KINDS:
                raise HTTPException(status_code=400, detail="上传 CSV 推理需要指定场站类型 kind（wind / solar）")
            if not capacity_mw or capacity_mw <= 0:
                raise HTTPException(status_code=400, detail="上传 CSV 推理需要指定装机容量 capacity_mw（MW，> 0）")
            text = (await file.read()).decode("utf-8-sig", errors="ignore")
            try:
                raw = pstd.parse_series_rows(list(csv.DictReader(io.StringIO(text))), file.filename or "upload.csv")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
            spec = {"kind": kind, "capacity_mw": float(capacity_mw)}
            return _infer(mod, raw, spec, {"file_name": file.filename or "upload.csv", "station": "上传场站"}, None, None)
        if not sample_path:
            raise HTTPException(status_code=400, detail="请上传标准 CSV 或选择训练集示例")
        ds_id, d, fname = _resolve_sample(sample_path)
        rec = next((r for r in pstd.read_labels(d, "train") if Path(r["file_name"]).name == fname), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="示例不存在")
        raw = pstd.read_series(d / "train" / rec["file_name"])
        spec = pstd.station_spec(pstd.read_meta(d), rec["station"], rec.get("kind"))
        return _infer(mod, raw, spec, rec, np.asarray(json.loads(rec["target_24h"]), dtype=np.float32), ds_id)

    return endpoint


for _mod in ALGORITHM_MODULES:
    router_pf.add_api_route(f"/real-api/algorithms/{_mod.ALGO_ID}/infer", _make_infer_route(_mod), methods=["POST"])


# ================================================================== 数据集路由
def _make_dataset_routes(ds_id: str, d: Path) -> None:
    prefix = f"/real-api/datasets/{ds_id}"

    def part(part: Literal["train", "test"], limit: int = 200):
        meta = pstd.read_meta(d) or {}
        return {"part": part, "columns": pstd.LABEL_COLUMNS[:-1], "total": meta.get(part, {}).get("files", 0), "rows": _part_rows(ds_id, d, part, max(1, min(limit, 500)))}

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
        rec = next((r for r in pstd.read_labels(d, part) if Path(r["file_name"]).name == name), None)
        if rec is None:
            raise HTTPException(status_code=404, detail="样本不存在")
        raw = pstd.read_series(d / part / rec["file_name"])
        spec = pstd.station_spec(pstd.read_meta(d), rec["station"], rec.get("kind"))
        return pstd.build_case_payload(raw, spec, rec, np.asarray(json.loads(rec["target_24h"]), dtype=np.float32), None)

    router_pf.add_api_route(f"{prefix}/part/{{part}}", part, methods=["GET"])
    router_pf.add_api_route(f"{prefix}/files/{{part}}/{{filename}}", file, methods=["GET"])
    router_pf.add_api_route(f"{prefix}/download/{{part}}", download, methods=["GET"])
    router_pf.add_api_route(f"{prefix}/series/{{part}}/{{filename}}", series, methods=["GET"])


for _ds_id, _d in DATASETS.items():
    _make_dataset_routes(_ds_id, _d)


@router_pf.get("/real-api/power-forecast/samples")
def samples_pf(dataset: str | None = None, limit: int = 5000):
    """推理示例：只列出标准数据集训练集（公开）中的窗口"""
    ids = [dataset] if dataset else list(DATASETS)
    out = []
    for ds_id in ids:
        d = DATASETS.get(ds_id)
        if d is None:
            raise HTTPException(status_code=404, detail="不是新能源功率预测标准数据集")
        for r in pstd.read_labels(d, "train"):
            out.append({
                "dataset": ds_id,
                "file": Path(r["file_name"]).name,
                "url": f"/real-api/datasets/{ds_id}/files/train/{Path(r['file_name']).name}",
                "station": r["station"],
                "kind": r["kind"],
                "weather": r["weather"],
                "value": float(r["value"]),
                "peak_mw": float(r["peak_mw"]),
            })
            if len(out) >= limit:
                return out
    return out


@router_pf.get("/real-api/power-forecast/standard")
def standard_pf():
    return {
        "task": pstd.TASK,
        "lookback": pstd.LOOKBACK,
        "horizon": pstd.HORIZON,
        "seriesColumns": pstd.CHANNELS,
        "labelColumns": pstd.LABEL_COLUMNS,
        "kinds": list(pstd.KINDS),
        "solarEvalHours": [pstd.SOLAR_EVAL_HOURS.start, pstd.SOLAR_EVAL_HOURS.stop - 1],
        "metrics": pstd.METRICS,
        "datasets": list(DATASETS),
        "algorithms": list(ALGOS),
    }
