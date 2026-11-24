import type { AlgoVersionStatus, BusinessCategory, EvalStatus, EvaluatorStatus, RegionName, Role, TaskType } from '@/types'

export const REGIONS: readonly RegionName[] = ['华北', '蒙古', '河北', '山东', '东北', '华中', '华东', '甘肃', '新疆', '宁夏', '西南', '南方', '云南', '贵州'] as const

export const TASKS: Record<TaskType, { label: string; group: '视觉与识别' | '预测与优化' | '其他'; color: string }> = {
  'image-classification': { label: '图像识别', group: '视觉与识别', color: 'text-sky-600 dark:text-sky-400' },
  'image-dehazing': { label: '图像去雾', group: '视觉与识别', color: 'text-cyan-600 dark:text-cyan-400' },
  'object-detection': { label: '目标检测', group: '视觉与识别', color: 'text-amber-600 dark:text-amber-400' },
  'semantic-segmentation': { label: '语义分割', group: '视觉与识别', color: 'text-emerald-600 dark:text-emerald-400' },
  'instance-segmentation': { label: '实例分割', group: '视觉与识别', color: 'text-teal-600 dark:text-teal-400' },
  'keypoint-detection': { label: '关键点检测', group: '视觉与识别', color: 'text-rose-600 dark:text-rose-400' },
  ocr: { label: 'OCR 文字识别', group: '视觉与识别', color: 'text-violet-600 dark:text-violet-400' },
  'power-forecast': { label: '功率预测', group: '预测与优化', color: 'text-indigo-600 dark:text-indigo-400' },
  'server-fault-0x07': { label: '服务器故障检测', group: '预测与优化', color: 'text-red-600 dark:text-red-400' },
  'signal-processing': { label: '信号处理', group: '预测与优化', color: 'text-orange-600 dark:text-orange-400' },
  optimization: { label: '优化求解', group: '预测与优化', color: 'text-lime-600 dark:text-lime-400' },
  custom: { label: '自定义任务', group: '其他', color: 'text-slate-600 dark:text-slate-400' },
}

export const BUSINESS_CATEGORIES: Record<BusinessCategory, { label: string; color: string; chip: string }> = {
  security: { label: '安防', color: 'text-blue-600 dark:text-blue-400', chip: 'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950/50 dark:text-blue-300' },
  inspection: { label: '巡检', color: 'text-emerald-600 dark:text-emerald-400', chip: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300' },
  'fire-safety': { label: '消防', color: 'text-rose-600 dark:text-rose-400', chip: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-300' },
  'env-control': { label: '环控', color: 'text-cyan-600 dark:text-cyan-400', chip: 'border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-900 dark:bg-cyan-950/50 dark:text-cyan-300' },
  production: { label: '生产', color: 'text-amber-600 dark:text-amber-400', chip: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300' },
  other: { label: '其他', color: 'text-slate-600 dark:text-slate-400', chip: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300' },
}

/** 内置评测器 & 原生渲染支持的任务 */
export const BUILTIN_TASKS: TaskType[] = ['image-classification', 'image-dehazing', 'object-detection', 'semantic-segmentation', 'ocr']

export const ROLES: Record<Role, { label: string; desc: string; chip: string }> = {
  admin: { label: '管理员', desc: '全部权限：数据集、评测基准、账号与审核，可查看与下载测试集', chip: 'border-indigo-200 bg-brand-50 text-brand-700 dark:border-brand-700 dark:bg-brand-600/20 dark:text-brand-100' },
  regional: { label: '区域侧', desc: '可查看全部已审核算法与代码；已下发至本区域的算法可直接使用，未下发的可申请试用', chip: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-900/30 dark:text-emerald-300' },
  demo: { label: '演示账号', desc: '查看全部算法与排行榜，可在线推理、下载训练集；不能提交或评测', chip: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-900/30 dark:text-sky-300' },
  vendor: { label: '厂商账号', desc: '仅见自己的算法；提交需审核，可在测试集上评测但看不到测试集内容', chip: 'border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-900/30 dark:text-violet-300' },
}

export const VERSION_STATUS: Record<AlgoVersionStatus, { label: string; cls: string }> = {
  submitted: { label: '已提交', cls: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300' },
  pending_review: { label: '待审核', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' },
  rejected: { label: '已驳回', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300' },
  building: { label: '构建中', cls: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' },
  ready: { label: '可用', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' },
  failed: { label: '构建失败', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300' },
}

export const EVAL_STATUS: Record<EvalStatus, { label: string; cls: string }> = {
  queued: { label: '排队中', cls: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300' },
  running: { label: '运行中', cls: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300' },
  succeeded: { label: '成功', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' },
  failed: { label: '失败', cls: 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300' },
  canceled: { label: '已取消', cls: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' },
}

export const EVALUATOR_STATUS: Record<EvaluatorStatus, { label: string; cls: string }> = {
  ready: { label: '已就绪', cls: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300' },
  uninitialized: { label: '待初始化', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' },
  disabled: { label: '已停用', cls: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400' },
}
