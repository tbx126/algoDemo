import type { EvalRun } from '@/types'

/** 评测记录默认为空；猫狗算法的真实评测记录由后端 /real-api/bootstrap 实时提供 */
export const evalRuns: EvalRun[] = []
