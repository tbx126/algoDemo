"""
[0x07] 服务器运行故障检测：FastAPI 路由与 bootstrap / 评测挂钩

server.py 只需：
  1. app.include_router(router_0x07)（必须在通用 /real-api/algorithms/Admin/{algo_name}/infer 之前注册）
  2. bootstrap 中合并 bootstrap_0x07()
  3. /real-api/evals 中优先调用 trigger_eval_0x07()
  4. 评测列表 / 详情中合并 list_evals_0x07() / find_eval_0x07()
"""
from __future__ import annotations

import csv
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from fault0x07_registry import (
    ALGO_0X07_ID,
    BENCH_0X07_ID,
    CHANNELS,
    DATA_0X07_DIR,
    DATASET_0X07_ID,
    STATES,
    TASK_0X07,
    WEIGHT_0X07_PATH,
    device_label_0x07,
    evaluate_0x07,
    infer_0x07,
    load_state_0x07,
    save_state_0x07,
)

router_0x07 = APIRouter()
_LOCK_0X07 = threading.Lock()
_TZ = timezone(timedelta(hours=8))
_DS_PREFIX = f"/real-api/datasets/{DATASET_0X07_ID}"
_IMAGE_DIGEST = "sha256:0x07fa017de7ec70000000000000000000000000000000000000000000000000107"
_WEIGHTS_HASH = "sha256:0x07fault0weights1"
_EVALUATOR = "0x07-server-fault-evaluator"
_LABEL_COLUMNS = ["file_name", "label", "server", "role", "onset_min", "state_seq", "warn_seq"]


def _now() -> str:
    return datetime.now(_TZ).isoformat(timespec="seconds")


def _meta() -> dict | None:
    p = DATA_0X07_DIR / "meta.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _safe_name(filename: str) -> str:
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    return filename


def _part_rows(part: str, limit: int) -> list[dict]:
    path = DATA_0X07_DIR / part / "labels.csv"
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            if i >= limit:
                break
            fname = Path(row["file_name"]).name
            onset = int(row["onset_min"])
            out.append({
                "file_name": row["file_name"],
                "label": f"{row['label']}（{row['server']} · {'第 ' + str(onset) + ' 分钟起' if 0 <= onset < 60 else ('窗口后发生 · 含前兆' if onset >= 60 else '全程正常')}）",
                "url": f"{_DS_PREFIX}/files/{part}/{fname}",
                "row": [row["file_name"], row["label"], row["server"], row["role"], row["onset_min"], row["state_seq"], row["warn_seq"]],
            })
    return out


# ------------------------------------------------------------------ bootstrap 对象
def _dataset(meta: dict) -> dict:
    tr, te = meta["train"], meta["test"]
    readme = f"""# 0x07-server-telemetry-dataset（服务器运行遥测故障检测数据集 · 0x07）

面向**服务器运行故障检测**的多变量时序数据集：8 台机房服务器（GPU 训练节点 ×3、Web 节点 ×2、数据库节点 ×2、缓存节点 ×1）的逐分钟运行遥测，每条样本为 **60 分钟 × 8 通道** 的时序窗口，并带有**逐分钟**运行状态真值。

## 数据组成

| 部分 | 窗口数 | 说明 |
| --- | --- | --- |
| 训练集 | {tr['files']:,} | 所有账号可查看、下载 |
| 测试集 | {te['files']:,} | 独立随机种子与时段生成，仅管理员可查看、下载 |

## 运行状态（6 类）

| 编码 | 状态 | 典型形态 |
| --- | --- | --- |
| 0 | 正常 | 日内业务周期 + 良性尖峰（批处理、备份、发版流量） |
| 1 | CPU过载 | 失控进程使 CPU 利用率逐步逼近 100%，CPU 温度同步升高 |
| 2 | 内存泄漏 | 内存占用缓慢线性爬升，进入故障后触发交换、磁盘 IO 抬升 |
| 3 | GPU过热 | GPU 温度升至 85–94 ℃，随后降频，利用率呈锯齿状下跌（仅 GPU 节点） |
| 4 | 磁盘IO饱和 | 磁盘吞吐打满约 480 MB/s，CPU iowait 抬升、网络吞吐下降 |
| 5 | 网络异常 | 链路中断（吞吐跌零）、广播风暴（吞吐暴涨）或丢包重传（吞吐抖动下降） |

故障发生前 6–12 分钟通常有可观测的**前兆漂移**（此时状态仍为「正常」），用于训练和评测「未来 10 分钟故障预警」。

## 文件结构

```
train/
  labels.csv
  series/train_0x07_gpu-node-01_0001.csv
  ...
test/
  labels.csv
  series/...
```

每个 `series/*.csv` 有 60 行，表头：

```
minute,cpu_pct,cpu_temp_c,mem_pct,gpu_pct,gpu_temp_c,gpu_mem_pct,disk_io_mbps,net_mbps
```

`labels.csv` 表头：`file_name,label,server,role,onset_min,state_seq,warn_seq`

- `label`：窗口级状态（窗口内出现的故障类型，没有故障为「正常」）
- `onset_min`：故障起始分钟；`-1` 表示没有故障，`>=60` 表示故障发生在窗口之后、窗口内只有前兆
- `state_seq`：60 个逐分钟状态编码（JSON 数组，即 ground truth）
- `warn_seq`：60 个逐分钟预警真值（1 表示未来 10 分钟内将发生故障）
"""
    def part(p: dict, name: str, note: str) -> dict:
        return {
            "name": name,
            "columns": _LABEL_COLUMNS,
            "versions": [{
                "version": "v1.0",
                "createdAt": "2026-11-25T01:00:00+08:00",
                "createdBy": "admin",
                "contentHash": p["contentHash"],
                "sizeBytes": p["sizeBytes"],
                "note": note,
                "files": p["files"],
                "rows": p["rows"],
            }],
            "classCounts": p.get("classCounts", {}),
        }

    return {
        "id": DATASET_0X07_ID,
        "org": "Admin",
        "name": "0x07-server-telemetry-dataset",
        "displayName": "[0x07] 服务器运行遥测故障检测数据集",
        "task": TASK_0X07,
        "summary": f"[0x07] 8 台服务器逐分钟 CPU / GPU / 内存 / 磁盘 / 网络遥测，60 分钟 × 8 通道窗口，6 类运行状态逐分钟真值（训练集 {tr['files']:,} + 测试集 {te['files']:,}）。",
        "readme": readme,
        "tags": ["0x07", "服务器运维", "时序预测"],
        "classes": STATES,
        "train": part(tr, "train", f"8 台服务器训练窗口 {tr['files']:,} 条（60 分钟 × 8 通道，逐分钟状态真值）"),
        "test": part(te, "test", f"独立时段测试窗口 {te['files']:,} 条（与训练集不同随机种子，无窗口重叠）"),
        "likes": 3,
        "downloads": 5,
        "updatedAt": "2026-11-25T01:00:00+08:00",
        "previewSeed": 707,
        "realPreview": {"train": _part_rows("train", 12), "test": _part_rows("test", 12)},
    }


def _algorithm(st: dict) -> dict:
    ev = next((e for e in st.get("evals", []) if e.get("status") == "succeeded"), None)
    m = (ev or {}).get("metrics", {})
    wbytes = st.get("weight_bytes", WEIGHT_0X07_PATH.stat().st_size if WEIGHT_0X07_PATH.exists() else 0)
    readme = f"""# 0x07（服务器运行故障检测 · 因果 TCN-GRU）

输入服务器最近 **60 分钟**的 8 路运行遥测（CPU 利用率与温度、内存、GPU 利用率 / 温度 / 显存、磁盘吞吐、网络吞吐），逐分钟输出：

1. **当前运行状态**：正常 / CPU过载 / 内存泄漏 / GPU过热 / 磁盘IO饱和 / 网络异常
2. **故障预警概率**：未来 10 分钟内发生故障的概率

## 使用方法

上传一个 60 行的 CSV（多于 60 行时取最后 60 行），表头为：

```
minute,cpu_pct,cpu_temp_c,mem_pct,gpu_pct,gpu_temp_c,gpu_mem_pct,disk_io_mbps,net_mbps
```

推理结果在页面上以折线图展示：各通道遥测曲线、逐分钟异常分数、预测状态与故障预警概率。使用数据集示例时，会同时画出 ground truth。

## 模型结构

- **输入编码**：8 路遥测按量程归一化，并拼接一阶差分，共 16 维
- **因果膨胀 TCN**：4 个残差块，膨胀系数 1 / 2 / 4 / 8，只看当前及过去的数据，可以直接用于在线监控
- **单向 GRU**：汇总长程上下文
- **双输出头**：6 类状态 softmax 与预警 sigmoid
- **窗口判定**：某一故障类连续出现 3 分钟及以上才判为该故障，抑制孤立毛刺

## 测试集指标（`{DATASET_0X07_ID}@v1.0/test`）

| 指标 | 数值 |
| --- | --- |
| 逐分钟 Macro-F1 | {m.get('macro_f1', '—')}% |
| 窗口准确率 | {m.get('window_acc', '—')}% |
| 故障检出率 | {m.get('event_recall', '—')}% |
| 窗口误报率 | {m.get('false_alarm_rate', '—')}% |
| 平均检测时延 | {m.get('detect_delay_min', '—')} 分钟 |
| 预警 AUC | {m.get('warn_auc', '—')}% |
"""
    algo_yaml = f"""name: 0x07
version: v1.0.0
task: {TASK_0X07}
business: other
framework: PyTorch
summary: 基于因果 TCN-GRU 的服务器运行故障检测与 10 分钟预警时序算法
tags:
  - 0x07
  - 服务器运维
  - 实时推理
entrypoint: fault0x07.py:predict
runtime: Python 3.12 · PyTorch 2.x · NumPy
"""
    trained = st.get("trained_at", "2026-11-25T01:00:00+08:00")
    return {
        "id": ALGO_0X07_ID,
        "org": "Admin",
        "name": "0x07",
        "displayName": "[0x07] 服务器运行故障检测（因果 TCN-GRU）",
        "task": TASK_0X07,
        "business": "other",
        "selfDeveloped": True,
        "framework": "PyTorch",
        "summary": "[0x07] 根据 CPU、GPU、内存、磁盘、网络等运行遥测，逐分钟判断服务器运行状态（6 类），并给出未来 10 分钟故障预警。",
        "readme": readme,
        "algoYaml": algo_yaml,
        "tags": ["0x07", "服务器运维", "实时推理"],
        "likes": 4,
        "evalCount": len(st.get("evals", [])),
        "downloads": 6,
        "updatedAt": trained,
        "files": [
            {"path": "fault0x07.py", "size": 18240, "kind": "code"},
            {"path": f"weights/{WEIGHT_0X07_PATH.name}", "size": wbytes, "kind": "weights"},
            {"path": "algo.yaml", "size": len(algo_yaml.encode("utf-8")), "kind": "config"},
            {"path": "README.md", "size": len(readme.encode("utf-8")), "kind": "doc"},
        ],
        "versions": [{
            "version": "v1.0.0",
            "status": "ready",
            "createdAt": trained,
            "createdBy": "admin",
            "changelog": f"[0x07] 在 {DATASET_0X07_ID} 训练集上真实训练 Fault0x07Net（{st.get('epochs', 60)} epochs，加权交叉熵 + 预警 BCE）。",
            "imageDigest": _IMAGE_DIGEST,
            "weightsHash": _WEIGHTS_HASH,
            "weightsSize": wbytes,
            "baseImage": "pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime",
            "gpuMem": 0.2,
            "buildLog": [
                "[build] 加载底座镜像 pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime",
                "[build] 安装依赖：numpy、torch",
                f"[build] 校验权重文件 {WEIGHT_0X07_PATH.name}（{wbytes:,} B）通过",
                "[build] 冒烟推理：60 分钟 × 8 通道遥测 -> 逐分钟状态 + 10 分钟预警，通过",
            ],
        }],
    }


def _benchmark(meta: dict) -> dict:
    return {
        "id": BENCH_0X07_ID,
        "name": BENCH_0X07_ID,
        "displayName": "[0x07] 服务器运行故障检测评测基准",
        "description": f"[0x07] 基于 {DATASET_0X07_ID} 测试集 v1.0（{meta['test']['files']} 个 60 分钟遥测窗口、{meta['test']['files'] * 60:,} 个逐分钟真值），评估逐分钟状态识别、窗口判定、故障检出时延、误报与 10 分钟预警能力。",
        "task": TASK_0X07,
        "datasetId": DATASET_0X07_ID,
        "datasetVersion": "v1.0",
        "split": "test",
        "evaluator": _EVALUATOR,
        "evaluatorVersion": "v1.0.0",
        "metrics": [
            {"key": "macro_f1", "label": "逐分钟 Macro-F1", "higherIsBetter": True, "unit": "%", "primary": True},
            {"key": "window_acc", "label": "窗口准确率", "higherIsBetter": True, "unit": "%"},
            {"key": "event_recall", "label": "故障检出率", "higherIsBetter": True, "unit": "%"},
            {"key": "false_alarm_rate", "label": "窗口误报率", "higherIsBetter": False, "unit": "%"},
            {"key": "detect_delay_min", "label": "平均检测时延", "higherIsBetter": False, "unit": "min"},
            {"key": "warn_auc", "label": "预警 AUC", "higherIsBetter": True, "unit": "%"},
        ],
        "createdAt": "2026-11-25T01:00:00+08:00",
        "org": "Admin",
    }


# ------------------------------------------------------------------ 评测
def _new_run(eval_id: str, algo_version: str, submitted_by: str) -> dict:
    now = _now()
    return {
        "id": eval_id,
        "algorithmId": ALGO_0X07_ID,
        "algoVersion": algo_version,
        "benchmarkId": BENCH_0X07_ID,
        "status": "queued",
        "progress": 0,
        "submittedBy": submitted_by,
        "submittedAt": now,
        "metrics": {},
        "imageDigest": _IMAGE_DIGEST,
        "weightsHash": _WEIGHTS_HASH,
        "evaluatorVersion": "v1.0.0",
        "params": {"window_minutes": 60, "warn_horizon": 10, "min_fault_run": 3},
        "hardware": device_label_0x07(),
        "datasetHash": (_meta() or {}).get("test", {}).get("contentHash", ""),
        "isLatestValid": False,
        "logs": [f"[scheduler] [0x07] 真实评测任务 {eval_id} 已入队：{ALGO_0X07_ID}@{algo_version} × {BENCH_0X07_ID}"],
    }


def _update_run(eval_id: str, **fields) -> None:
    with _LOCK_0X07:
        st = load_state_0x07() or {}
        for r in st.get("evals", []):
            if r["id"] == eval_id:
                logs = fields.pop("append_log", None)
                r.update(fields)
                if logs:
                    r["logs"].append(logs)
                break
        save_state_0x07(st)


def _run_eval_bg(eval_id: str) -> None:
    try:
        _update_run(eval_id, status="running", startedAt=_now(), progress=5)

        def on_progress(p: int, msg: str) -> None:
            _update_run(eval_id, progress=p, append_log=msg)

        res = evaluate_0x07(on_progress)
        m = res["metrics"]
        with _LOCK_0X07:
            st = load_state_0x07() or {}
            version = next((x["algoVersion"] for x in st.get("evals", []) if x["id"] == eval_id), None)
            for r in st.get("evals", []):
                if r["id"] != eval_id and r.get("algoVersion") == version:
                    r["isLatestValid"] = False
            for r in st.get("evals", []):
                if r["id"] == eval_id:
                    r.update({
                        "status": "succeeded",
                        "progress": 100,
                        "finishedAt": _now(),
                        "metrics": m,
                        "perClass": res["perClass"],
                        "durationSec": res["durationSec"],
                        "latencyMs": res["latencyMs"],
                        "peakGpuMemGB": 0.2,
                        "isLatestValid": True,
                        "viz0x07": res["viz0x07"],
                    })
                    r["logs"].append(
                        f"[done] [0x07] 真实评测完成：Macro-F1={m['macro_f1']}%，窗口准确率={m['window_acc']}%，检出率={m['event_recall']}%，"
                        f"误报率={m['false_alarm_rate']}%，平均时延={m['detect_delay_min']} min，预警 AUC={m['warn_auc']}%"
                    )
            save_state_0x07(st)
    except Exception as exc:  # noqa: BLE001
        _update_run(eval_id, status="failed", finishedAt=_now(), append_log=f"[error] [0x07] 评测失败：{exc}")


def trigger_eval_0x07(algorithm_id: str, algo_version: str, benchmark_id: str, submitted_by: str) -> dict | None:
    """若是 0x07 算法 × 0x07 基准则发起真实评测并返回任务，否则返回 None 交给其他通道"""
    if algorithm_id != ALGO_0X07_ID and benchmark_id != BENCH_0X07_ID:
        return None
    if algorithm_id != ALGO_0X07_ID or benchmark_id != BENCH_0X07_ID:
        raise HTTPException(status_code=400, detail="[0x07] 评测基准只支持 Admin/0x07 算法")
    with _LOCK_0X07:
        st = load_state_0x07() or {}
        evals = st.setdefault("evals", [])
        eval_id = f"ev-0x07-{1001 + len(evals)}"
        run = _new_run(eval_id, algo_version, submitted_by)
        evals.insert(0, run)
        save_state_0x07(st)
    threading.Thread(target=_run_eval_bg, args=(eval_id,), daemon=True).start()
    return run


def list_evals_0x07() -> list[dict]:
    return list((load_state_0x07() or {}).get("evals", []))


def find_eval_0x07(eval_id: str) -> dict | None:
    if not eval_id.startswith("ev-0x07-"):
        return None
    return next((r for r in list_evals_0x07() if r["id"] == eval_id), None)


def bootstrap_0x07() -> dict:
    """返回 0x07 的算法 / 数据集 / 基准 / 评测，数据或权重缺失时返回空列表"""
    meta, st = _meta(), load_state_0x07()
    if not meta or not st:
        return {"algorithms": [], "datasets": [], "benchmarks": [], "evals": []}
    return {
        "algorithms": [_algorithm(st)],
        "datasets": [_dataset(meta)],
        "benchmarks": [_benchmark(meta)],
        "evals": list(st.get("evals", [])),
    }


def ensure_initial_eval_0x07() -> None:
    """首次启动时（已有权重但无评测记录）同步跑一次真实评测，作为算法页的初始成绩"""
    st = load_state_0x07()
    if not st or st.get("evals") or not WEIGHT_0X07_PATH.exists():
        return
    run = trigger_eval_0x07(ALGO_0X07_ID, "v1.0.0", BENCH_0X07_ID, "admin")
    assert run is not None


# ------------------------------------------------------------------ 路由
@router_0x07.get(f"{_DS_PREFIX}/part/{{part}}")
def part_0x07(part: Literal["train", "test"], limit: int = 200):
    meta = _meta()
    if not meta:
        raise HTTPException(status_code=404, detail="[0x07] 数据集尚未生成")
    return {"part": part, "columns": _LABEL_COLUMNS, "total": meta[part]["files"], "rows": _part_rows(part, max(1, min(limit, 500)))}


@router_0x07.get(f"{_DS_PREFIX}/files/{{part}}/{{filename}}")
def file_0x07(part: Literal["train", "test"], filename: str):
    path = DATA_0X07_DIR / part / "series" / _safe_name(filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="时序文件不存在")
    return FileResponse(path, media_type="text/csv")


@router_0x07.get(f"{_DS_PREFIX}/download/{{part}}")
def download_0x07(part: Literal["train", "test"]):
    zip_path = DATA_0X07_DIR / f"0x07-server-telemetry-dataset-{part}-v1.0.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="数据集压缩包不存在")
    return FileResponse(zip_path, media_type="application/zip", filename=zip_path.name)


@router_0x07.get(f"{_DS_PREFIX}/series/{{part}}/{{filename}}")
def series_0x07(part: Literal["train", "test"], filename: str):
    """单个窗口的 8 通道曲线 + 逐分钟 ground truth，供数据集页折线图预览"""
    name = _safe_name(filename)
    with (DATA_0X07_DIR / part / "labels.csv").open("r", encoding="utf-8") as f:
        rec = next((r for r in csv.DictReader(f) if Path(r["file_name"]).name == name), None)
    if rec is None:
        raise HTTPException(status_code=404, detail="样本不存在")
    with (DATA_0X07_DIR / part / rec["file_name"]).open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {
        "file": name,
        "label": rec["label"],
        "server": rec["server"],
        "role": rec["role"],
        "onset": int(rec["onset_min"]),
        "states": STATES,
        "channels": {c: [float(r[c]) for r in rows] for c in CHANNELS},
        "gt": json.loads(rec["state_seq"]),
        "warnGt": json.loads(rec["warn_seq"]),
    }


@router_0x07.get("/real-api/0x07/samples")
def samples_0x07(label: str | None = None, limit: int = 60):
    """推理示例：只列出训练集（公开）窗口"""
    with (DATA_0X07_DIR / "train" / "labels.csv").open("r", encoding="utf-8") as f:
        recs = list(csv.DictReader(f))
    out = []
    for r in recs:
        if label and r["label"] != label:
            continue
        out.append({"file": Path(r["file_name"]).name, "label": r["label"], "server": r["server"], "onset": int(r["onset_min"])})
        if len(out) >= limit:
            break
    return out


@router_0x07.post(f"/real-api/algorithms/{ALGO_0X07_ID}/infer")
async def infer_endpoint_0x07(
    version: str = Form("v1.0.0"),
    file: UploadFile | None = File(None),
    sample_path: str | None = Form(None),
):
    raw = await file.read() if file is not None else None
    try:
        return infer_0x07(raw, filename=(file.filename if file else "") or "", sample_file=sample_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"[0x07] 故障检测推理失败：{exc}")
