/** [0x07] 服务器运行故障检测：评测 / 推理 / 数据集预览共用的数据结构 */

export const ALGO_0X07_ID = 'Admin/0x07'
export const DATASET_0X07_ID = 'Admin/0x07-server-telemetry-dataset'
export const BENCH_0X07_ID = '0x07-server-fault-bench'
export const TASK_0X07 = 'server-fault-0x07'

export const STATES_0X07 = ['正常', 'CPU过载', '内存泄漏', 'GPU过热', '磁盘IO饱和', '网络异常'] as const

export type Channel0x07 = 'cpu_pct' | 'cpu_temp_c' | 'mem_pct' | 'gpu_pct' | 'gpu_temp_c' | 'gpu_mem_pct' | 'disk_io_mbps' | 'net_mbps'

/** 一个 60 分钟窗口：遥测曲线 + 真值（可选）+ 预测（可选） */
export interface Case0x07 {
  file: string
  server?: string
  role?: string
  label?: string
  predLabel?: string
  onset?: number
  channels: Record<Channel0x07, number[]>
  gt?: number[] | null
  warnGt?: number[] | null
  pred?: number[]
  anomaly?: number[]
  warn?: number[]
}

export interface Fault0x07Viz {
  states: string[]
  channels: Channel0x07[]
  history: { epoch: number; train_loss: number; val_loss: number; val_f1: number }[]
  thresholdCurve: { threshold: number; precision: number; recall: number; f1: number; fpr: number }[]
  delayCdf: { minute: number; detected: number }[]
  onsetAligned: { offset: number; anomaly: number; warn: number; gtFault: number; n: number }[]
  cases: Case0x07[]
}
