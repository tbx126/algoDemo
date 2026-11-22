import { orgs } from '@/mock/orgs'
import { algorithms } from '@/mock/algorithms'
import type { Algorithm } from '@/types'

/** 算法英文标识到中文名称的映射（兼容真实后端与历史数据） */
const ALGO_ZH_MAP: Record<string, string> = {
  'cat-dog-classifier': '猫狗图像识别',
  'dehaze-dcp': '暗通道先验去雾（DCP）',
  'dehaze-aodnet': '轻量物理网络去雾（AOD-Net）',
  'dehaze-ffanet': '特征融合注意力去雾（FFA-Net）',
  'dehaze-deanet': '细节增强注意力去雾（DEA-Net）',
  random: '随机基线',
  LEDmeter: '红色LED数显识别',
  lightningmetermechnicalcount: '避雷器电流表与放电计数识别',
  terminalblock: '柱状压板状态识别',
  LEDlight: 'GIS汇控状态灯亮灭识别',
  openandcloseknob: '旋钮档位状态识别',
  outsideliquid: '主变油位识别',
}

/** 组织/厂商展示名：除 Admin 保留原样外，其余统一显示中文名称 */
export function orgLabel(orgId: string): string {
  if (!orgId) return ''
  if (orgId.toLowerCase() === 'admin') return 'Admin'
  return orgs.find((o) => o.id === orgId)?.displayName ?? orgId
}

/** 算法中文名称 */
export function algoName(
  a: string | (Pick<Algorithm, 'name'> & { displayName?: string; declaration?: { management?: { name?: { zh_CN?: string } } } }),
): string {
  if (typeof a === 'string') {
    const found = algorithms.find((x) => x.id === a || x.name === a)
    if (found) return algoName(found)
    const raw = a.includes('/') ? a.split('/').slice(1).join('/') : a
    return ALGO_ZH_MAP[raw] ?? raw
  }
  return a.displayName || a.declaration?.management?.name?.zh_CN || ALGO_ZH_MAP[a.name] || a.name
}

/** 算法完整展示名：厂商中文名/算法中文名（Admin 保持 Admin/算法中文名） */
export function algoFullLabel(
  a: string | (Pick<Algorithm, 'org' | 'name'> & { displayName?: string; declaration?: { management?: { name?: { zh_CN?: string } } } }),
): string {
  if (typeof a === 'string') {
    const [org, ...rest] = a.split('/')
    if (!rest.length) return algoName(a)
    return `${orgLabel(org)}/${algoName(a)}`
  }
  return `${orgLabel(a.org)}/${algoName(a)}`
}
