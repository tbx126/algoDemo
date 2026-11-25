/**
 * labels.csv 规范：训练集与测试集结构一致。
 *   <part>/images/...      具体数据
 *   <part>/labels.csv      真值，UTF-8（兼容带 BOM），首行为表头，必有 file_name 列
 * 不同任务的必需列不同；条件列（weather、light 等）可选，填写后评测可按条件拆分结果。
 */
import type { TaskType } from '@/types'
import { rng } from './format'
import { sceneLayout } from './synth'

export interface LabelSpec {
  required: string[]
  optional: string[]
  /** true = 一个目标一行（一张图可有多行，无目标的图写一行且 label 留空） */
  perObject: boolean
  desc: string
  dataExt: string
}

export const CONDITION_COLUMNS = ['weather', 'light', 'occlusion', 'scene']

export function labelSpec(task: TaskType): LabelSpec {
  switch (task) {
    case 'image-classification':
      return { required: ['file_name', 'label'], optional: CONDITION_COLUMNS, perObject: false, desc: '一张图一行，label 为类别名', dataExt: 'jpg' }
    case 'image-dehazing':
      return { required: ['file_name', 'clear_file'], optional: ['beta', 'airlight'], perObject: false, desc: '一张有雾图一行，clear_file 指向对应的清晰真值图', dataExt: 'jpg' }
    case 'object-detection':
    case 'keypoint-detection':
      return { required: ['file_name', 'label', 'x_min', 'y_min', 'x_max', 'y_max'], optional: CONDITION_COLUMNS, perObject: true, desc: '一个框一行，坐标为像素；无目标的图写一行且 label 留空（用于统计误报）', dataExt: 'jpg' }
    case 'ocr':
      return { required: ['file_name', 'text'], optional: ['category', 'source_receipt', ...CONDITION_COLUMNS], perObject: false, desc: '一张裁剪文本行图片一行，text 为精确文字真值（Ground Truth）', dataExt: 'jpg' }
    case 'semantic-segmentation':
    case 'instance-segmentation':
      return { required: ['file_name', 'mask_file'], optional: CONDITION_COLUMNS, perObject: false, desc: '一张图一行，mask_file 指向 masks/ 下的 PNG（像素值为类别序号）', dataExt: 'jpg' }
    case 'power-forecast':
      return { required: ['file_name', 'value', 'station', 'kind', 'weather', 'peak_mw', 't0', 'target_24h'], optional: [], perObject: false, desc: '新能源功率预测标准：一个日前预测窗口 CSV（24 行：前一天实测 + 次日 NWP）一行，target_24h 为次日 24 个逐小时功率真值（JSON 数组，MW）', dataExt: 'csv' }
    case 'server-fault':
      return { required: ['file_name', 'label', 'server', 'role', 'onset_min', 'state_seq', 'warn_seq'], optional: [], perObject: false, desc: '服务器故障检测标准：一个 60 分钟 × 8 通道遥测 CSV 一行，state_seq 为逐分钟标准状态码（JSON 数组）', dataExt: 'csv' }
    case 'signal-processing':
      return { required: ['file_name', 'label'], optional: ['device', 'speed_rpm'], perObject: false, desc: '一个信号文件一行', dataExt: 'csv' }
    case 'optimization':
      return { required: ['file_name', 'best_known'], optional: ['vehicles'], perObject: false, desc: '一个算例一行，best_known 为已知最优目标值', dataExt: 'vrp' }
    default:
      return { required: ['file_name', 'label'], optional: [], perObject: false, desc: '一个样本一行', dataExt: 'bin' }
  }
}

export const fileNameOf = (part: string, idx: number, ext = 'jpg') => `images/${part}_${String(idx).padStart(6, '0')}.${ext}`

const WEATHER = ['晴', '阴', '雨', '雾']
const LIGHT = ['白天', '白天', '傍晚', '夜间']

/** 由场景布局生成某个样本在 labels.csv 中的行（与预览图一致） */
export function rowsFor(seed: number, idx: number, part: string, task: TaskType, classes: string[], columns: string[], W = 1920, H = 1080): string[][] {
  const spec = labelSpec(task)
  const scene = sceneLayout(seed, task, classes.length)
  const file = fileNameOf(part, idx, spec.dataExt)
  const rc = rng(seed * 13 + 5)
  const cond: Record<string, string> = { weather: WEATHER[Math.floor(rc() * 4)], light: LIGHT[Math.floor(rc() * 4)], occlusion: ['无', '轻度', '中度'][Math.floor(rc() * 3)], scene: ['室外', '室内'][Math.floor(rc() * 2)], device: `D${1 + Math.floor(rc() * 6)}`, speed_rpm: String(900 + Math.floor(rc() * 20) * 60), vehicles: String(5 + Math.floor(rc() * 6)) }
  const base = (extra: Record<string, string>) => columns.map((c) => (c === 'file_name' ? file : (extra[c] ?? cond[c] ?? '')))
  if (spec.perObject) {
    // 少量负样本：无目标
    if (rc() < 0.08) return [base({ label: '' })]
    return scene.objects.map((o) =>
      base({ label: classes[o.cls] ?? '', x_min: String(Math.round(o.x * W)), y_min: String(Math.round(o.y * H)), x_max: String(Math.round((o.x + o.w) * W)), y_max: String(Math.round((o.y + o.h) * H)) }),
    )
  }
  if (task === 'semantic-segmentation' || task === 'instance-segmentation') return [base({ mask_file: file.replace('images/', 'masks/').replace(/\.\w+$/, '.png') })]
  if (task === 'optimization') return [base({ best_known: (800 + rc() * 400).toFixed(2) })]
  return [base({ label: classes[scene.label] ?? '' })]
}

// ---------- CSV ----------
function esc(v: string) {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v
}
export const toCsv = (header: string[], rows: string[][]) => [header, ...rows].map((r) => r.map(esc).join(',')).join('\n')

/** 简单 CSV 解析：支持引号、转义引号、BOM、CRLF */
export function parseCsv(text: string): { header: string[]; rows: string[][]; hadBom: boolean } {
  const hadBom = text.charCodeAt(0) === 0xfeff
  if (hadBom) text = text.slice(1)
  const out: string[][] = []
  let row: string[] = []
  let cur = ''
  let q = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (q) {
      if (c === '"' && text[i + 1] === '"') (cur += '"'), i++
      else if (c === '"') q = false
      else cur += c
    } else if (c === '"') q = true
    else if (c === ',') row.push(cur), (cur = '')
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(cur)
      out.push(row)
      row = []
      cur = ''
    } else cur += c
  }
  if (cur || row.length) row.push(cur), out.push(row)
  const rows = out.filter((r) => r.some((x) => x.trim() !== ''))
  return { header: (rows.shift() ?? []).map((h) => h.trim()), rows, hadBom }
}

export interface CheckItem {
  level: 'ok' | 'warn' | 'error'
  text: string
}

/** 对 labels.csv 内容做规范校验（真实执行，用于用户选择的本地 CSV） */
export function checkLabels(header: string[], rows: string[][], task: TaskType, classes: string[] | null): CheckItem[] {
  const spec = labelSpec(task)
  const out: CheckItem[] = []
  const missing = spec.required.filter((c) => !header.includes(c))
  out.push(missing.length ? { level: 'error', text: `缺少必需列：${missing.join(', ')}（需要 ${spec.required.join(', ')}）` } : { level: 'ok', text: `必需列齐全：${spec.required.join(', ')}` })
  const unknown = header.filter((h) => !spec.required.includes(h) && !spec.optional.includes(h))
  if (unknown.length) out.push({ level: 'warn', text: `未识别的列将作为附加信息保留：${unknown.join(', ')}` })
  const condCols = header.filter((h) => spec.optional.includes(h))
  if (condCols.length) out.push({ level: 'ok', text: `包含条件列 ${condCols.join(', ')}，评测可按条件拆分结果` })
  if (!rows.length) {
    out.push({ level: 'error', text: '没有数据行' })
    return out
  }
  const fi = header.indexOf('file_name')
  if (fi >= 0) {
    const empty = rows.filter((r) => !r[fi]?.trim()).length
    if (empty) out.push({ level: 'error', text: `${empty} 行 file_name 为空` })
    const files = new Set(rows.map((r) => r[fi]))
    out.push({ level: 'ok', text: `${rows.length} 行，涉及 ${files.size} 个文件` })
    if (!spec.perObject && files.size < rows.length) out.push({ level: 'error', text: `存在重复的 file_name（该任务要求一个文件一行）` })
  }
  const li = header.indexOf('label')
  if (li >= 0 && classes?.length) {
    const bad = [...new Set(rows.map((r) => r[li]).filter((v) => v && !classes.includes(v)))]
    out.push(bad.length ? { level: 'error', text: `label 不在类别表中：${bad.slice(0, 5).join('、')}${bad.length > 5 ? ' …' : ''}` } : { level: 'ok', text: 'label 均在类别表内' })
  }
  if (spec.perObject && ['x_min', 'y_min', 'x_max', 'y_max'].every((c) => header.includes(c))) {
    const [a, b, c, d] = ['x_min', 'y_min', 'x_max', 'y_max'].map((k) => header.indexOf(k))
    const bad = rows.filter((r) => r[li] && !(+r[a] < +r[c] && +r[b] < +r[d] && +r[a] >= 0 && +r[b] >= 0)).length
    out.push(bad ? { level: 'error', text: `${bad} 个框坐标无效（需 x_min < x_max、y_min < y_max 且非负）` } : { level: 'ok', text: '框坐标有效' })
    if (li >= 0) {
      const neg = rows.filter((r) => !r[li]).length
      if (neg) out.push({ level: 'ok', text: `${neg} 行为无目标样本（label 为空），可用于统计误报` })
    }
  }
  return out
}
