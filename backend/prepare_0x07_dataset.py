"""
[0x07] 构建服务器运行故障检测时序数据集（Admin/0x07-server-telemetry-dataset）

  - 模拟 8 台机房服务器（GPU 训练节点 ×3、Web 节点 ×2、数据库节点 ×2、缓存节点 ×1）的逐分钟运行遥测
  - 每条样本为 60 分钟、8 通道的多变量时序窗口（series/*.csv，60 行）：
      minute, cpu_pct, cpu_temp_c, mem_pct, gpu_pct, gpu_temp_c, gpu_mem_pct, disk_io_mbps, net_mbps
  - 6 类运行状态（逐分钟真值）：
      0 正常 / 1 CPU 过载 / 2 内存泄漏 / 3 GPU 过热 / 4 磁盘 IO 饱和 / 5 网络异常
  - 故障发生前约 6~12 分钟带有可观测的前兆漂移（状态仍为「正常」），用于训练「未来 10 分钟故障预警」
  - labels.csv 表头：file_name,label,server,role,onset_min,state_seq,warn_seq
      label      窗口级状态（窗口内出现的故障类型，无故障为「正常」）
      onset_min  故障起始分钟（窗口内无故障为 -1；可能 >=60 表示故障发生在窗口之后、仅有前兆）
      state_seq  60 个逐分钟状态编码（JSON）
      warn_seq   60 个逐分钟预警真值（JSON，1 = 未来 10 分钟内将发生故障）
  - 训练集 1,200 条 / 测试集 300 条，按不同随机种子与时段独立生成（无窗口重叠泄露）
  - 输出目录：backend/data/0x07-server-telemetry-dataset/{train,test}/{series/*.csv,labels.csv}、zip 包与 meta.json
"""
from __future__ import annotations

import math
import random
from pathlib import Path

import server_fault_std as std

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "0x07-server-telemetry-dataset"

WINDOW = 60
WARN_HORIZON = 10
COLUMNS = std.SERIES_COLUMNS  # 服务器故障检测标准

SERVERS = [
    {"id": "gpu-node-01", "role": "GPU 训练节点", "gpu": True, "cpu": 55, "mem": 62, "disk": 120, "net": 380},
    {"id": "gpu-node-02", "role": "GPU 训练节点", "gpu": True, "cpu": 50, "mem": 58, "disk": 110, "net": 340},
    {"id": "gpu-node-03", "role": "GPU 训练节点", "gpu": True, "cpu": 60, "mem": 66, "disk": 140, "net": 420},
    {"id": "web-node-01", "role": "Web 节点", "gpu": False, "cpu": 35, "mem": 45, "disk": 40, "net": 260},
    {"id": "web-node-02", "role": "Web 节点", "gpu": False, "cpu": 32, "mem": 42, "disk": 35, "net": 240},
    {"id": "db-node-01", "role": "数据库节点", "gpu": False, "cpu": 40, "mem": 70, "disk": 210, "net": 150},
    {"id": "db-node-02", "role": "数据库节点", "gpu": False, "cpu": 38, "mem": 68, "disk": 190, "net": 140},
    {"id": "cache-node-01", "role": "缓存节点", "gpu": False, "cpu": 25, "mem": 76, "disk": 20, "net": 300},
]


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _simulate_window(rng: random.Random, srv: dict, fault: int, onset: int, duration: int, precursor: int) -> tuple[list[dict], list[int], list[int]]:
    """生成 60 分钟窗口（额外向后模拟 WARN_HORIZON 分钟以得到预警真值）

    真实感设计：
      - 正常窗口里也会出现良性业务尖峰（批处理任务、夜间备份、发版流量），与故障形态相似但持续短、幅度低
      - 故障按严重程度随机，从起始分钟开始用 2~6 分钟渐进爬升，而非瞬间跳变
      - 传感器噪声与偶发采集掉点（读数瞬间归零）
    """
    total = WINDOW + WARN_HORIZON
    day_phase = rng.uniform(0, 2 * math.pi)
    cpu_b, mem_b, disk_b, net_b = srv["cpu"] + rng.uniform(-8, 8), srv["mem"] + rng.uniform(-8, 6), srv["disk"], srv["net"]
    gpu_b = rng.uniform(62, 92) if srv["gpu"] else 0.0
    gpu_mem_b = rng.uniform(50, 82) if srv["gpu"] else 0.0
    ar = {"cpu": 0.0, "mem": 0.0, "disk": 0.0, "net": 0.0, "gpu": 0.0}
    net_mode = rng.choice(["drop", "storm", "degrade"])
    severity = rng.uniform(0.55, 1.0)
    ramp = rng.randint(2, 6)
    leak_rate = rng.uniform(0.45, 1.3)

    # 良性业务尖峰：(起始, 持续, 类型)
    bursts = []
    for _ in range(rng.choice([0, 0, 1, 1, 2])):
        bursts.append((rng.randint(0, total - 4), rng.randint(2, 7), rng.choice(["cpu", "disk", "net", "gpu", "mem"]), rng.uniform(0.35, 0.8)))

    rows: list[dict] = []
    states: list[int] = []
    for t in range(total):
        cyc = math.sin(day_phase + 2 * math.pi * t / 240.0)
        for k, s in (("cpu", 3.0), ("mem", 0.6), ("disk", 14.0), ("net", 28.0), ("gpu", 3.0)):
            ar[k] = 0.85 * ar[k] + rng.gauss(0, s)
        cpu = cpu_b + 6 * cyc + ar["cpu"]
        mem = mem_b + 1.5 * cyc + ar["mem"]
        disk = disk_b * (1 + 0.15 * cyc) + ar["disk"]
        net = net_b * (1 + 0.12 * cyc) + ar["net"]
        gpu = gpu_b + ar["gpu"] if srv["gpu"] else 0.0
        gpu_mem = gpu_mem_b + 0.3 * ar["gpu"] if srv["gpu"] else 0.0
        gpu_heat = 0.0

        for (bs, bd, kind, amp) in bursts:
            if bs <= t < bs + bd:
                if kind == "cpu":
                    cpu += amp * (100 - cpu) * 0.9
                elif kind == "disk":
                    disk += amp * 330
                elif kind == "net":
                    net *= 1 + amp * 1.1
                elif kind == "gpu" and srv["gpu"]:
                    gpu_heat += amp * 9
                elif kind == "mem":
                    mem += amp * 10

        in_fault = fault > 0 and onset <= t < onset + duration
        pre = (t - (onset - precursor) + 1) / precursor if fault > 0 and onset - precursor <= t < onset else 0.0
        k = severity * min(1.0, (t - onset + 1) / ramp) if in_fault else 0.0  # 渐进爬升强度 0 -> severity

        if fault == 1:  # CPU 过载
            cpu += pre * 12 * severity
            if in_fault:
                cpu = cpu + k * (99 - cpu) + rng.gauss(0, 2.0)
        elif fault == 2:  # 内存泄漏：缓慢线性爬升，进入故障后开始触发交换
            if t >= onset - precursor:
                mem += (t - (onset - precursor)) * leak_rate
            if in_fault:
                disk += k * 90 + rng.gauss(0, 10)
        elif fault == 3 and srv["gpu"]:  # GPU 过热 -> 降频
            gpu_heat += pre * 7 * severity
        elif fault == 4:  # 磁盘 IO 饱和
            disk += pre * 70 * severity
            if in_fault:
                disk = disk + k * (480 - disk) + rng.gauss(0, 15)
                cpu += k * 10
                net *= 1 - 0.2 * k
        elif fault == 5:  # 网络异常
            if net_mode == "drop":
                net *= 1 - 0.35 * pre
                if in_fault:
                    net *= 1 - 0.97 * k
            elif net_mode == "storm":
                net *= 1 + 0.4 * pre
                if in_fault:
                    net = net + k * (960 - net) + rng.gauss(0, 30)
                    cpu += 14 * k
            else:  # degrade：丢包重传导致吞吐抖动下降
                net *= 1 - 0.2 * pre
                if in_fault:
                    net *= 1 - k * (0.45 + 0.35 * abs(math.sin(t * 1.7)))

        cpu_temp = 40 + 0.4 * cpu + rng.gauss(0, 1.1)
        if srv["gpu"]:
            gpu_temp = 50 + 0.3 * gpu + gpu_heat + rng.gauss(0, 1.0)
            if fault == 3 and in_fault:
                target = 84 + 10 * severity
                gpu_temp = gpu_temp + k / severity * (target - gpu_temp) + rng.gauss(0, 1.2)
                gpu = gpu * (1 - 0.45 * k * abs(math.sin(t / 2.3))) + rng.gauss(0, 3)
        else:
            gpu_temp = 0.0

        row = {
            "minute": t,
            "cpu_pct": round(_clip(cpu, 1, 100), 1),
            "cpu_temp_c": round(_clip(cpu_temp, 30, 99), 1),
            "mem_pct": round(_clip(mem, 5, 99.5), 1),
            "gpu_pct": round(_clip(gpu, 0, 100), 1),
            "gpu_temp_c": round(_clip(gpu_temp, 0, 99), 1),
            "gpu_mem_pct": round(_clip(gpu_mem, 0, 100), 1),
            "disk_io_mbps": round(_clip(disk, 0, 500), 1),
            "net_mbps": round(_clip(net, 0, 1000), 1),
        }
        if rng.random() < 0.012:  # 采集掉点：某通道读数瞬间归零
            row[rng.choice(COLUMNS[1:])] = 0.0
        rows.append(row)
        states.append(fault if in_fault else 0)

    warn = [1 if (states[t] == 0 and any(s > 0 for s in states[t + 1 : t + 1 + WARN_HORIZON])) else 0 for t in range(WINDOW)]
    return rows[:WINDOW], states[:WINDOW], warn


def _make_split(split: str, count: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    records: list[dict] = []
    for i in range(count):
        srv = SERVERS[i % len(SERVERS)]
        # 35% 正常窗口；其余注入一种故障（GPU 过热仅在 GPU 节点上发生）
        if rng.random() < 0.35:
            fault = 0
        else:
            choices = [1, 2, 4, 5] + ([3, 3] if srv["gpu"] else [])
            fault = rng.choice(choices)
        if fault:
            # 10% 故障发生在窗口之后（窗口内只有前兆），其余故障在窗口内 15~52 分钟发生
            onset = rng.randint(61, 66) if rng.random() < 0.1 else rng.randint(15, 52)
            duration = rng.randint(12, 40)
            precursor = rng.randint(6, 12)
        else:
            onset, duration, precursor = -1, 0, 1
        rows, states, warn = _simulate_window(rng, srv, fault, onset, duration, precursor)
        fname = f"{split}_0x07_{srv['id']}_{i + 1:04d}.csv"
        std.write_series_csv(DATA_DIR / split / "series" / fname, rows)
        records.append(std.make_label_record(f"series/{fname}", srv["id"], srv["role"], states, warn, onset=onset if fault else None))
    std.write_labels(DATA_DIR / split / "labels.csv", records)
    return records


README = """# 0x07-server-telemetry-dataset（服务器运行遥测故障检测数据集 · 0x07）

符合平台**服务器故障检测标准**（task = `server-fault`）的多变量时序数据集：8 台机房服务器（GPU 训练节点 ×3、Web 节点 ×2、数据库节点 ×2、缓存节点 ×1）的逐分钟运行遥测，每条样本为 **60 分钟 × 8 通道** 窗口，并带有**逐分钟**运行状态真值。所有符合该标准的算法都可以直接在本数据集上评测。

## 数据组成

| 部分 | 窗口数 | 说明 |
| --- | --- | --- |
| 训练集 | {train} | 所有账号可查看、下载 |
| 测试集 | {test} | 独立随机种子与时段生成，仅管理员可查看、下载 |

## 本数据集出现的状态（标准状态码）

| 编码 | 状态 | 典型形态 |
| --- | --- | --- |
| 0 | 正常 | 日内业务周期 + 良性尖峰（批处理、备份、发版流量） |
| 1 | CPU过载 | 失控进程使 CPU 利用率逐步逼近 100%，CPU 温度同步升高 |
| 2 | 内存泄漏 | 内存占用缓慢线性爬升，进入故障后触发交换、磁盘 IO 抬升 |
| 3 | GPU过热 | GPU 温度升至 85–94 ℃，随后降频，利用率呈锯齿状下跌（仅 GPU 节点） |
| 4 | 磁盘IO饱和 | 磁盘吞吐打满约 480 MB/s，CPU iowait 抬升、网络吞吐下降 |
| 5 | 网络异常 | 链路中断、广播风暴或丢包重传 |

故障发生前 6–12 分钟通常有可观测的**前兆漂移**（此时状态仍为「正常」），用于「未来 10 分钟故障预警」。

## 文件格式（服务器故障检测标准）

`series/*.csv`：60 行，表头固定为

```
minute,cpu_pct,cpu_temp_c,mem_pct,gpu_pct,gpu_temp_c,gpu_mem_pct,disk_io_mbps,net_mbps
```

非 GPU 节点的 GPU 三列为 0。

`labels.csv`：表头固定为 `file_name,label,server,role,onset_min,state_seq,warn_seq`

- `state_seq`：60 个逐分钟标准状态码（JSON 数组，即 ground truth）
- `warn_seq`：60 个逐分钟预警真值（1 表示当前正常且未来 10 分钟内将发生故障）
- `onset_min`：故障起始分钟；`-1` 表示没有故障，`>=60` 表示故障发生在窗口之后、窗口内只有前兆
"""


def build_dataset() -> dict:
    split_records = {split: _make_split(split, count, seed) for split, count, seed in (("train", 1200, 20261125), ("test", 300, 20261199))}
    meta = std.write_meta(
        DATA_DIR,
        {
            "id": "Admin/0x07-server-telemetry-dataset",
            "name": "0x07-server-telemetry-dataset",
            "displayName": "[0x07] 服务器运行遥测故障检测数据集",
            "summary": "[0x07] 8 台服务器逐分钟 CPU / GPU / 内存 / 磁盘 / 网络遥测，60 分钟 × 8 通道窗口，6 类运行状态逐分钟真值与 10 分钟预警真值。",
            "tags": ["0x07", "服务器运维", "时序预测"],
            "servers": [s["id"] for s in SERVERS],
            "createdAt": "2026-11-25T01:00:00+08:00",
            "benchmark": {"id": "0x07-server-fault-bench", "displayName": "[0x07] 服务器运行故障检测评测基准"},
        },
        split_records,
    )
    (DATA_DIR / "README.md").write_text(README.format(train=f"{meta['train']['files']:,}", test=f"{meta['test']['files']:,}"), encoding="utf-8")
    print(f"[0x07] 已生成 Admin/0x07-server-telemetry-dataset：train={meta['train']['files']} 条，test={meta['test']['files']} 条")
    print(f"[0x07] test 类别分布 {meta['test']['classCounts']}")
    return meta


if __name__ == "__main__":
    build_dataset()
