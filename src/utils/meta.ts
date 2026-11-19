import type { AlgoVersionStatus, EvalStatus, Role, TaskType } from '@/types'

export const TASKS: Record<TaskType, { label: string; group: 'CV' | '传统算法' | '其他'; color: string }> = {
  'image-classification': { label: '图像分类', group: 'CV', color: 'text-sky-600 dark:text-sky-400' },
  'object-detection': { label: '目标检测', group: 'CV', color: 'text-amber-600 dark:text-amber-400' },
  'semantic-segmentation': { label: '语义分割', group: 'CV', color: 'text-emerald-600 dark:text-emerald-400' },
  'instance-segmentation': { label: '实例分割', group: 'CV', color: 'text-teal-600 dark:text-teal-400' },
  'keypoint-detection': { label: '关键点检测', group: 'CV', color: 'text-rose-600 dark:text-rose-400' },
  ocr: { label: 'OCR 文字识别', group: 'CV', color: 'text-violet-600 dark:text-violet-400' },
  'signal-processing': { label: '信号处理', group: '传统算法', color: 'text-orange-600 dark:text-orange-400' },
  optimization: { label: '优化求解', group: '传统算法', color: 'text-lime-600 dark:text-lime-400' },
  custom: { label: '自定义任务', group: '其他', color: 'text-slate-600 dark:text-slate-400' },
}

/** 内置评测器 & 原生渲染支持的任务 */
export const BUILTIN_TASKS: TaskType[] = ['image-classification', 'object-detection', 'semantic-segmentation']

/** 算法许可证选项；“/”表示不适用或未声明 */
export const LICENSES = ['/', 'Apache-2.0', 'MIT', 'BSD-3-Clause', 'Internal', 'Proprietary']

export const ROLES: Record<Role, { label: string; desc: string; chip: string }> = {
  admin: { label: '管理员', desc: '全部权限：数据集、评测基准、账号与审核，可查看与下载测试集', chip: 'border-indigo-200 bg-brand-50 text-brand-700 dark:border-brand-700 dark:bg-brand-600/20 dark:text-brand-100' },
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
