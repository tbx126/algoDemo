"""
构建服务器运行故障时序检测数据集（Admin/0x6E-server-telemetry）：
  - 优先尝试拉取公开 SMD (Server Machine Dataset, NetManAIOps/OmniAnomaly) 真实服务器遥测与异常真值作为真实基线序列；
  - 结合 GPU 推理集群典型硬件通道，按平台「服务器故障检测标准」（server_fault_std）输出 8 通道 60 分钟窗口：
      minute, cpu_pct, cpu_temp_c, mem_pct, gpu_pct, gpu_temp_c, gpu_mem_pct, disk_io_mbps, net_mbps
  - labels.csv 为标准表头 file_name,label,server,role,onset_min,state_seq,warn_seq（逐分钟标准状态码）
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

import math
import random
import urllib.request
from pathlib import Path

import server_fault_std as std

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
NODE_ROLE = {"node-gpu-01": "GPU 推理节点", "node-gpu-02": "GPU 推理节点", "node-infer-03": "GPU 推理节点", "node-train-04": "GPU 训练节点"}


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
        cpu_t = min(98.0, max(32.0, 38.0 + 0.42 * cpu + rng.gauss(0, 0.9)))
        net = min(1000.0, max(5.0, v[14] * 700.0 + 120.0 + rng.gauss(0, 12.0)))  # SMD col 14 = Net
        rows.append({
            "cpu_pct": cpu,
            "cpu_temp_c": cpu_t,
            "mem_pct": mem,
            "gpu_pct": gpu_u,
            "gpu_temp_c": gpu_t,
            "gpu_mem_pct": gpu_m,
            "disk_io_mbps": disk,
            "net_mbps": net,
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
    base_net = rng.uniform(150.0, 420.0)

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
        net = base_net * (1 + 0.1 * wave) + rng.gauss(0, 14.0)
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
        cpu_t = min(98.0, max(30.0, 38.0 + 0.42 * cpu + rng.gauss(0, 0.9)))
        net = min(1000.0, max(5.0, net))

        rows.append({
            "cpu_pct": cpu,
            "cpu_temp_c": cpu_t,
            "mem_pct": mem,
            "gpu_pct": gpu_u,
            "gpu_temp_c": gpu_t,
            "gpu_mem_pct": gpu_m,
            "disk_io_mbps": disk,
            "net_mbps": net,
            "gt_fault": gt,
        })

    label_map = dict(FAULT_CLASSES)
    return rows, label_map[fault_code]


README = """# 0x6E-server-telemetry（服务器多维时序故障检测数据集 · 0x6E）

符合平台**服务器故障检测标准**（task = `server-fault`）的多变量时序数据集，面向 GPU 推理 / 训练集群的运行状态监控与故障检测。{smd_note}所有符合该标准的算法都可以直接在本数据集上评测。

## 数据组成

| 部分 | 窗口数 | 总时间步 | 说明 |
| --- | --- | --- | --- |
| 训练集 | {train} | {train_steps} | 60 分钟多维遥测滑窗，所有账号可下载 |
| 测试集 | {test} | {test_steps} | 独立时段验证窗口，仅管理员可查看下载 |

## 本数据集出现的状态（标准状态码）

| 编码 | 状态 |
| --- | --- |
| 0 | 正常 |
| 1 | CPU过载 |
| 6 | 显存泄漏 |
| 7 | 内存IO雪崩 |

## 文件格式（服务器故障检测标准）

`series/*.csv`：60 行，表头固定为

```
minute,cpu_pct,cpu_temp_c,mem_pct,gpu_pct,gpu_temp_c,gpu_mem_pct,disk_io_mbps,net_mbps
```

`labels.csv`：表头固定为 `file_name,label,server,role,onset_min,state_seq,warn_seq`。`state_seq` 为 60 个逐分钟标准状态码；`warn_seq` 为逐分钟 10 分钟预警真值，由 `state_seq` 推出（窗口结束之后的故障未知，按正常处理）。
"""


def build_dataset() -> dict:
    smd = _try_fetch_smd_real_trace()
    smd_used = smd is not None
    print(f"[0x6E] 公开 SMD 真实服务器遥测拉取：{'成功 (' + str(len(smd[0])) + ' 步)' if smd_used else '未连通，使用物理仿真遥测引擎'}")

    split_records: dict[str, list[dict]] = {}
    for split, count, base_seed in (("train", 800, 600001), ("test", 200, 900001)):
        rng = random.Random(base_seed)
        # 均衡分布：40% 正常，其余 60% 均分为 3 类典型服务器故障
        fault_pool = ["normal"] * int(count * 0.40) + ["cpu_overload"] * int(count * 0.20) + ["gpu_oom_leak"] * int(count * 0.20) + ["mem_io_storm"] * (count - int(count * 0.80))
        rng.shuffle(fault_pool)
        records: list[dict] = []
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
            code = std.STATE_CODE[label]
            states = [code if r["gt_fault"] else 0 for r in rows]
            node = NODES[idx % len(NODES)]
            fname = f"{split}_0x6e_{idx + 1:04d}.csv"
            std.write_series_csv(DATA_DIR / split / "series" / fname, rows)
            records.append(std.make_label_record(f"series/{fname}", node, NODE_ROLE[node], states, std.derive_warn(states + [0] * std.WARN_HORIZON)))
        std.write_labels(DATA_DIR / split / "labels.csv", records)
        split_records[split] = records

    meta = std.write_meta(
        DATA_DIR,
        {
            "id": "Admin/0x6E-server-telemetry",
            "name": "0x6E-server-telemetry",
            "displayName": "服务器多维时序故障检测数据集（0x6E）",
            "summary": "融合公开 SMD 服务器遥测与 GPU 集群硬件通道的 60 分钟 × 8 通道故障检测时序数据集（标准 server-fault 格式，含逐分钟 Ground Truth）。",
            "tags": ["0x6E", "时序故障检测", "服务器监控"],
            "smd_backed": smd_used,
            "createdAt": "2026-11-25T00:57:00+08:00",
            "benchmark": {"id": "0x6E-server-fault-bench", "displayName": "服务器运行故障时序检测评测基准（0x6E）"},
        },
        split_records,
    )
    smd_note = "其中约 25% 的窗口取材于公开 **SMD (Server Machine Dataset)** 真实服务器遥测，其余由物理与运维规律仿真生成。" if smd_used else "全部窗口由物理与运维规律仿真生成（构建时未能拉取公开 SMD 数据）。"
    tr, te = meta["train"]["files"], meta["test"]["files"]
    (DATA_DIR / "README.md").write_text(README.format(smd_note=smd_note, train=f"{tr:,}", test=f"{te:,}", train_steps=f"{tr * 60:,}", test_steps=f"{te * 60:,}"), encoding="utf-8")
    print(f"[0x6E] 已生成 Admin/0x6E-server-telemetry：train={tr} 条，test={te} 条 | 类别分布={meta['test']['classCounts']}")
    return meta


if __name__ == "__main__":
    build_dataset()
