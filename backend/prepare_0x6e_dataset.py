"""
构建服务器运行故障时序检测数据集（Admin/0x6E-server-telemetry）：
  - 优先尝试拉取公开 SMD (Server Machine Dataset, NetManAIOps/OmniAnomaly) 真实服务器遥测与异常真值作为真实基线序列；
  - 结合 GPU 推理集群典型硬件通道，构建 6 维核心服务器状态时序（每条样本为 60 分钟步长窗口）：
      step, cpu_pct, gpu_util_pct, gpu_mem_pct, mem_pct, disk_io_mbps, gpu_temp_c, gt_fault
  - 覆盖 4 类真实运行状态标签：
      正常 (normal)、CPU过载 (cpu_overload)、显存泄漏 (gpu_oom_leak)、内存IO雪崩 (mem_io_storm)
  - 训练集（800 条 60-step 窗口 = 48,000 步）与测试集（200 条独立时间段窗口 = 12,000 步）严格隔离无泄露
  - 输出目录：
      backend/data/0x6e-server-telemetry/{train,test}/series/*.csv
      backend/data/0x6e-server-telemetry/{train,test}/labels.csv
      backend/data/0x6e-server-telemetry/0x6e-server-telemetry-{train,test}-v1.0.zip
      backend/data/0x6e-server-telemetry/meta.json
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "0x6e-server-telemetry"

SMD_TEST_URL = "https://raw.githubusercontent.com/NetManAIOps/OmniAnomaly/master/ServerMachineDataset/test/machine-1-1.txt"
SMD_LABEL_URL = "https://raw.githubusercontent.com/NetManAIOps/OmniAnomaly/master/ServerMachineDataset/test_label/machine-1-1.txt"

WINDOW_LEN = 60  # 60 分钟滑窗

FAULT_CLASSES = [
    ("normal", "正常"),
    ("cpu_overload", "CPU过载"),
    ("gpu_oom_leak", "显存泄漏"),
    ("mem_io_storm", "内存IO雪崩"),
]

NODES = ["node-gpu-01", "node-gpu-02", "node-infer-03", "node-train-04"]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()[:16]


def _try_fetch_smd_real_trace(max_rows: int = 8000) -> tuple[list[list[float]], list[int]] | None:
    """尝试拉取真实公开 SMD 服务器机台遥测数据（超时 6 秒，失败自动降级）"""
    try:
        req1 = urllib.request.Request(SMD_TEST_URL, headers={"User-Agent": "AlgoHub-0x6E/1.0"})
        req2 = urllib.request.Request(SMD_LABEL_URL, headers={"User-Agent": "AlgoHub-0x6E/1.0"})
        with urllib.request.urlopen(req1, timeout=6) as r1, urllib.request.urlopen(req2, timeout=6) as r2:
            raw_x = r1.read().decode("utf-8", errors="ignore").splitlines()[:max_rows]
            raw_y = r2.read().decode("utf-8", errors="ignore").splitlines()[:max_rows]
        n = min(len(raw_x), len(raw_y))
        if n < 600:
            return None
        xs: list[list[float]] = []
        ys: list[int] = []
        for i in range(n):
            vals = [float(v) for v in raw_x[i].split(",") if v.strip()]
            if len(vals) < 12:
                continue
            xs.append(vals)
            ys.append(1 if int(float(raw_y[i].strip())) > 0 else 0)
        return (xs, ys) if len(xs) >= 600 else None
    except Exception:
        return None


def _build_window_from_smd(smd_x: list[list[float]], smd_y: list[int], start: int, rng: random.Random) -> tuple[list[dict], str]:
    """将真实 SMD 38 维遥测切片映射为 6 维服务器硬件指标，并保留真实异常 Ground Truth"""
    rows: list[dict] = []
    fault_steps = 0
    for t in range(WINDOW_LEN):
        v = smd_x[start + t]
        gt = smd_y[start + t]
        fault_steps += gt
        # SMD col 0=CPU load, 1=CPU user, 9=Mem usage, 11=Disk IO, 14=Net/PCIe
        cpu = min(99.5, max(4.0, v[0] * 100.0 * 0.85 + 14.0 + (22.0 if gt else 0.0) + rng.gauss(0, 1.2)))
        mem = min(99.0, max(18.0, v[9] * 100.0 * 0.82 + 24.0 + (14.0 if gt else 0.0) + rng.gauss(0, 0.9)))
        disk = min(950.0, max(12.0, v[11] * 480.0 + 35.0 + (180.0 if gt else 0.0) + rng.gauss(0, 6.0)))
        gpu_u = min(99.5, max(5.0, (v[1] * 65.0 + v[14] * 35.0) + 18.0 + (24.0 if gt else 0.0) + rng.gauss(0, 1.8)))
        gpu_m = min(99.0, max(12.0, (v[9] * 55.0 + 28.0) + (20.0 if gt else 0.0) + rng.gauss(0, 1.1)))
        gpu_t = min(96.0, max(34.0, 38.0 + 0.36 * gpu_u + 0.14 * gpu_m + (9.0 if gt else 0.0) + rng.gauss(0, 0.7)))
        rows.append({
            "step": t,
            "cpu_pct": round(cpu, 2),
            "gpu_util_pct": round(gpu_u, 2),
            "gpu_mem_pct": round(gpu_m, 2),
            "mem_pct": round(mem, 2),
            "disk_io_mbps": round(disk, 2),
            "gpu_temp_c": round(gpu_t, 2),
            "gt_fault": gt,
        })
    if fault_steps == 0:
        label = "正常"
    else:
        max_cpu = max(r["cpu_pct"] for r in rows)
        max_gm = max(r["gpu_mem_pct"] for r in rows)
        if max_gm >= 82.0:
            label = "显存泄漏"
        elif max_cpu >= 80.0:
            label = "CPU过载"
        else:
            label = "内存IO雪崩"
    return rows, label


def _simulate_server_window(fault_code: str, seed: int) -> tuple[list[dict], str]:
    """物理与运维规律驱动的 60 分钟服务器多维遥测窗口生成器"""
    rng = random.Random(seed)
    phase = rng.uniform(0, 2 * math.pi)
    base_cpu = rng.uniform(22.0, 44.0)
    base_gpu = rng.uniform(26.0, 52.0)
    base_gmem = rng.uniform(30.0, 54.0)
    base_mem = rng.uniform(36.0, 58.0)
    base_disk = rng.uniform(35.0, 110.0)

    # 故障起止步长（每条故障样本在窗口中段或后段出现清晰故障区间）
    f_start = rng.randint(14, 34)
    f_len = rng.randint(12, 24)
    f_end = min(WINDOW_LEN - 2, f_start + f_len)

    rows: list[dict] = []
    cpu_drift = 0.0
    gmem_leak = 0.0
    mem_surge = 0.0

    for t in range(WINDOW_LEN):
        wave = math.sin(2 * math.pi * t / 30.0 + phase)
        cpu = base_cpu + 6.5 * wave + rng.gauss(0, 2.2)
        gpu_u = base_gpu + 8.0 * math.cos(2 * math.pi * t / 24.0 + phase) + rng.gauss(0, 2.8)
        gpu_m = base_gmem + 3.0 * wave + rng.gauss(0, 1.4)
        mem = base_mem + 2.5 * wave + rng.gauss(0, 1.2)
        disk = base_disk + 18.0 * abs(wave) + rng.gauss(0, 8.5)
        gt = 0

        if fault_code == "cpu_overload":
            if f_start - 3 <= t < f_start:
                # 故障前兆爬坡
                ramp = (t - (f_start - 3)) / 3.0
                cpu += 22.0 * ramp
                disk += 60.0 * ramp
            elif f_start <= t <= f_end:
                gt = 1
                cpu_drift = min(56.0, cpu_drift + rng.uniform(8.0, 16.0))
                cpu = max(82.0, cpu + cpu_drift)
                mem += 14.0 + rng.gauss(0, 2.0)
                disk += 150.0 + rng.gauss(0, 22.0)
            elif t > f_end:
                cpu_drift *= 0.62
                cpu += cpu_drift

        elif fault_code == "gpu_oom_leak":
            if f_start - 6 <= t < f_start:
                # 显存缓慢泄漏爬升
                ramp = (t - (f_start - 6)) / 6.0
                gmem_leak = 26.0 * ramp
                gpu_m += gmem_leak
                gpu_u += 14.0 * ramp
            elif f_start <= t <= f_end:
                gt = 1
                gmem_leak = min(58.0, gmem_leak + rng.uniform(3.5, 7.5))
                gpu_m = max(85.0, gpu_m + gmem_leak)
                gpu_u = max(84.0, gpu_u + 34.0 + rng.gauss(0, 3.0))
            elif t > f_end:
                # 触发 OOM 重启后显存骤降恢复
                gmem_leak *= 0.35
                gpu_m += gmem_leak

        elif fault_code == "mem_io_storm":
            if f_start - 4 <= t < f_start:
                ramp = (t - (f_start - 4)) / 4.0
                mem_surge = 20.0 * ramp
                mem += mem_surge
                disk += 120.0 * ramp
            elif f_start <= t <= f_end:
                gt = 1
                mem_surge = min(52.0, mem_surge + rng.uniform(5.0, 11.0))
                mem = max(84.0, mem + mem_surge)
                disk = max(460.0, disk + 420.0 + rng.gauss(0, 45.0))
                cpu += 22.0 + rng.gauss(0, 3.0)
            elif t > f_end:
                mem_surge *= 0.55
                mem += mem_surge

        cpu = min(99.8, max(3.0, cpu))
        gpu_u = min(99.8, max(2.0, gpu_u))
        gpu_m = min(99.5, max(8.0, gpu_m))
        mem = min(99.5, max(12.0, mem))
        disk = min(980.0, max(8.0, disk))
        gpu_t = min(97.0, max(32.0, 36.0 + 0.38 * gpu_u + 0.16 * gpu_m + (7.5 if (gt and fault_code == "gpu_oom_leak") else 0.0) + rng.gauss(0, 0.8)))

        rows.append({
            "step": t,
            "cpu_pct": round(cpu, 2),
            "gpu_util_pct": round(gpu_u, 2),
            "gpu_mem_pct": round(gpu_m, 2),
            "mem_pct": round(mem, 2),
            "disk_io_mbps": round(disk, 2),
            "gpu_temp_c": round(gpu_t, 2),
            "gt_fault": gt,
        })

    label_map = dict(FAULT_CLASSES)
    return rows, label_map[fault_code]


def _pack_split_zip(split: str) -> tuple[Path, int, str]:
    split_dir = DATA_DIR / split
    zip_path = DATA_DIR / f"0x6e-server-telemetry-{split}-v1.0.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(split_dir / "labels.csv", arcname=f"{split}/labels.csv")
        for f in sorted((split_dir / "series").glob("*.csv")):
            zf.write(f, arcname=f"{split}/series/{f.name}")
    return zip_path, zip_path.stat().st_size, _sha256_file(zip_path)


def build_dataset() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for split in ("train", "test"):
        (DATA_DIR / split / "series").mkdir(parents=True, exist_ok=True)

    smd = _try_fetch_smd_real_trace()
    smd_used = smd is not None
    print(f"[0x6E] 公开 SMD 真实服务器遥测拉取：{'成功 (' + str(len(smd[0])) + ' 步)' if smd_used else '未连通，使用物理仿真遥测引擎'}")

    split_specs = [("train", 800, 600001), ("test", 200, 900001)]
    meta: dict = {
        "id": "Admin/0x6E-server-telemetry",
        "name": "0x6E-server-telemetry",
        "task": "power-forecast",
        "window_len": WINDOW_LEN,
        "smd_backed": smd_used,
        "classes": [zh for _, zh in FAULT_CLASSES],
        "columns": ["file_name", "value", "fault_type", "node"],
    }

    for split, count, base_seed in split_specs:
        rng = random.Random(base_seed)
        records: list[dict] = []
        class_counts: dict[str, int] = {}

        # 均衡分布：40% 正常，其余 60% 均分为 3 类典型服务器故障
        fault_pool = ["normal"] * int(count * 0.40) + ["cpu_overload"] * int(count * 0.20) + ["gpu_oom_leak"] * int(count * 0.20) + ["mem_io_storm"] * (count - int(count * 0.80))
        rng.shuffle(fault_pool)

        for idx in range(count):
            # 若成功拉取 SMD，前 25% 窗口直接取材真实 SMD 遥测切片，其余覆盖全量 GPU/CPU 故障类型
            if smd_used and smd is not None and idx < count // 4:
                smd_x, smd_y = smd
                half = len(smd_x) // 2
                lo = 0 if split == "train" else half
                hi = (half - WINDOW_LEN - 1) if split == "train" else (len(smd_x) - WINDOW_LEN - 1)
                start = rng.randint(lo, max(lo, hi))
                rows, label = _build_window_from_smd(smd_x, smd_y, start, rng)
            else:
                rows, label = _simulate_server_window(fault_pool[idx], base_seed + idx * 37)

            node = NODES[idx % len(NODES)]
            fname = f"{split}_0x6e_{idx + 1:04d}.csv"
            rel = f"series/{fname}"
            csv_path = DATA_DIR / split / rel
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["step", "cpu_pct", "gpu_util_pct", "gpu_mem_pct", "mem_pct", "disk_io_mbps", "gpu_temp_c", "gt_fault"])
                for r in rows:
                    w.writerow([r["step"], r["cpu_pct"], r["gpu_util_pct"], r["gpu_mem_pct"], r["mem_pct"], r["disk_io_mbps"], r["gpu_temp_c"], r["gt_fault"]])

            gt_seq = [r["gt_fault"] for r in rows]
            fault_ratio = round(sum(gt_seq) / len(gt_seq) * 100.0, 2)
            records.append({
                "file_name": rel,
                "value": f"{fault_ratio:.2f}",
                "fault_type": label,
                "node": node,
                "gt_seq": json.dumps(gt_seq),
            })
            class_counts[label] = class_counts.get(label, 0) + 1

        lbl_path = DATA_DIR / split / "labels.csv"
        with lbl_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["file_name", "value", "fault_type", "node", "gt_seq"])
            for rec in records:
                w.writerow([rec["file_name"], rec["value"], rec["fault_type"], rec["node"], rec["gt_seq"]])

        _, zsize, sha = _pack_split_zip(split)
        meta[split] = {
            "files": len(records),
            "rows": len(records),
            "sizeBytes": zsize,
            "contentHash": sha,
            "classCounts": class_counts,
        }

    (DATA_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[0x6E] 已生成 Admin/0x6E-server-telemetry：train={meta['train']['files']} 条，test={meta['test']['files']} 条 | 类别分布={meta['test']['classCounts']}")
    return meta


if __name__ == "__main__":
    build_dataset()
