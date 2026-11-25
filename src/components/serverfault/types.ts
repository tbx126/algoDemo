/**
 * 服务器故障检测标准（task = 'server-fault'）的前端数据结构，与 backend/server_fault_std.py 一一对应。
 * 所有标准算法的评测、推理与所有标准数据集的预览共用这些结构与组件。
 */

export const SF_TASK = 'server-fault'

/** 统一状态码表（与后端 STATES 顺序一致，编码即下标） */
export const SF_STATES = ['正常', 'CPU过载', '内存泄漏', 'GPU过热', '磁盘IO饱和', '网络异常', '显存泄漏', '内存IO雪崩', '其他异常'] as const

export type SfChannel = 'cpu_pct' | 'cpu_temp_c' | 'mem_pct' | 'gpu_pct' | 'gpu_temp_c' | 'gpu_mem_pct' | 'disk_io_mbps' | 'net_mbps'

/** 一个 60 分钟窗口：标准遥测 + 真值（可选）+ 算法输出（可选） */
export interface SfCase {
  file: string
  server?: string
  role?: string
  label?: string
  predLabel?: string
  onset?: number
  channels: Record<SfChannel, number[]>
  gt?: number[] | null
  warnGt?: number[] | null
  /** 逐分钟状态码（算法提供 state 时） */
  pred?: number[] | null
  /** 逐分钟故障概率 fault_prob（0~1） */
  anomaly?: number[] | null
  /** 逐分钟 10 分钟预警概率 warn_prob（算法提供时） */
  warn?: number[] | null
}

/** 统一评测器输出的折线图数据 */
export interface ServerFaultViz {
  states: string[]
  channels: SfChannel[]
  capabilities?: { state: boolean; warn: boolean }
  history: { epoch: number; train_loss: number; val_loss: number; val_f1: number }[]
  thresholdCurve: { threshold: number; precision: number; recall: number; f1: number; fpr: number }[]
  delayCdf: { minute: number; detected: number }[]
  onsetAligned: { offset: number; anomaly: number; warn: number | null; gtFault: number; n: number }[]
  cases: SfCase[]
}
