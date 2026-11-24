import { CHINA_REGIONS } from '@/assets/chinaMapData'
import type { RegionName } from '@/types'

interface Point {
  x: number
  y: number
}

interface Chord {
  y: number
  x1: number
  x2: number
  width: number
  midX: number
}

/** 解析 M/L/Z SVG 路径为多边形环列表 */
function parsePathRings(d: string): Point[][] {
  const rings: Point[][] = []
  const subpaths = d.split('M').filter(Boolean)
  for (const sp of subpaths) {
    const clean = sp.replace(/Z/g, '').trim()
    if (!clean) continue
    const pts: Point[] = []
    for (const seg of clean.split('L')) {
      const [xs, ys] = seg.trim().split(',')
      const x = Number(xs)
      const y = Number(ys)
      if (!Number.isNaN(x) && !Number.isNaN(y)) pts.push({ x, y })
    }
    if (pts.length >= 3) rings.push(pts)
  }
  return rings
}

/** 计算给定 y 高度下，多边形内部最宽的水平弦段 */
function widestChordAtY(rings: Point[][], y: number): Chord | null {
  const xs: number[] = []
  for (const ring of rings) {
    const n = ring.length
    for (let i = 0; i < n; i++) {
      const a = ring[i]
      const b = ring[(i + 1) % n]
      if ((a.y <= y && b.y > y) || (b.y <= y && a.y > y)) {
        const t = (y - a.y) / (b.y - a.y)
        xs.push(a.x + t * (b.x - a.x))
      }
    }
  }
  if (xs.length < 2) return null
  xs.sort((a, b) => a - b)
  let best: Chord | null = null
  for (let i = 0; i + 1 < xs.length; i += 2) {
    const x1 = xs[i]
    const x2 = xs[i + 1]
    const width = x2 - x1
    if (!best || width > best.width) {
      best = { y, x1, x2, width, midX: (x1 + x2) / 2 }
    }
  }
  return best
}

const chordCache = new Map<RegionName, Chord[]>()

/** 为每个区域预计算沿纵向采样的内部有效弦段（按地块真实轮廓） */
function getRegionChords(rg: RegionName): Chord[] {
  const cached = chordCache.get(rg)
  if (cached) return cached

  const shape = CHINA_REGIONS[rg]
  if (!shape) return []
  const rings = parsePathRings(shape.d)
  const h = shape.maxY - shape.minY
  const steps = 28
  const raw: Chord[] = []

  for (let i = 1; i < steps; i++) {
    const y = shape.minY + (h * i) / steps
    const c = widestChordAtY(rings, y)
    if (c && c.width > 18) raw.push(c)
  }

  // 过滤掉过于贴近顶/底尖角的极窄弦，保留主体地块（>= 最大宽度的 28%）
  const maxW = raw.reduce((m, c) => Math.max(m, c.width), 0)
  const filtered = raw.filter((c) => c.width >= Math.max(24, maxW * 0.28))
  const result = filtered.length >= 3 ? filtered : raw
  chordCache.set(rg, result)
  return result
}

/** 估算中英文混排名称的视觉字符权重（中文=1.7，ASCII=1.0） */
export function estimateNameWeight(text: string): number {
  let w = 0
  for (const ch of text) {
    w += ch.charCodeAt(0) > 127 ? 1.7 : 1.0
  }
  return w
}

/** 稳定哈希（用于产生自然但不闪烁的错落微调） */
function stableHash(str: string): number {
  let h = 2166136261
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return (h >>> 0) / 0xffffffff
}

export interface PlacedAlgoLabel<T> {
  item: T
  mx: number
  my: number
  /** 微小错落偏移（像素），让多算法排布更贴合地图气质而非死板对齐 */
  jitterY: number
}

export interface RegionLabelLayout<T> {
  header: { mx: number; my: number }
  placed: PlacedAlgoLabel<T>[]
}

/**
 * 按「算法名称视觉长度 + 区域地块真实轮廓」计算贴地排版坐标：
 * - 算法不多（<= 3）时：全称不省略，沿地块主体中心自然顺排（随地块倾斜/弯曲而非死板垂直对齐）；
 * - 算法较多（>= 4）时：较长的算法名优先落在地块最宽的弦段，较短的名称填入较窄弦段；
 *   宽阔地块（新疆、西南、蒙古、甘肃、南方等）自动双列错落排布，无需强制平齐。
 */
export function layoutRegionLabels<T>(
  rg: RegionName,
  items: T[],
  getLabel: (item: T) => string,
): RegionLabelLayout<T> {
  const shape = CHINA_REGIONS[rg]
  if (!shape) {
    return { header: { mx: 500, my: 390 }, placed: [] }
  }

  const chords = getRegionChords(rg)
  if (!chords.length) {
    return {
      header: { mx: shape.cx, my: shape.cy - 14 },
      placed: items.map((item, idx) => ({
        item,
        mx: shape.cx,
        my: shape.cy + idx * 14,
        jitterY: 0,
      })),
    }
  }

  // 无算法时，标题居中显示
  if (items.length === 0) {
    const mid = chords[Math.floor(chords.length / 2)]
    return {
      header: { mx: mid.midX, my: mid.y },
      placed: [],
    }
  }

  // 放大后地块不显示顶部标题，算法名充分利用整个地块内部有效弦段区间
  const mid = chords[Math.floor(chords.length / 2)]
  const header = { mx: mid.midX, my: mid.y }
  const usable = chords

  const n = items.length

  // 少量算法（1~3 个）：围绕地块重心弦段自然分布，完整显示不省略
  if (n <= 3) {
    const centerFrac = 0.5
    const spanFrac = n === 1 ? 0 : n === 2 ? 0.26 : 0.44
    const placed: PlacedAlgoLabel<T>[] = items.map((item, i) => {
      const frac = n === 1 ? centerFrac : centerFrac - spanFrac / 2 + (spanFrac * i) / (n - 1)
      const cIdx = Math.max(0, Math.min(usable.length - 1, Math.round(frac * (usable.length - 1))))
      const chord = usable[cIdx]
      // 顺着地块真实中线排布，并加轻微有机水平错落（不用强行平齐）
      const seed = stableHash(rg + ':' + getLabel(item))
      const maxShift = Math.min(18, chord.width * 0.14)
      const offsetX = n === 1 ? 0 : (i % 2 === 0 ? -1 : 1) * maxShift * (0.35 + seed * 0.5)
      return {
        item,
        mx: chord.midX + offsetX,
        my: chord.y,
        jitterY: 0,
      }
    })
    return { header, placed }
  }

  // 较多算法（>= 4 个）：按名称长度与地块宽窄动态生成槽位（宽弦可双列错落，长名配宽弦）
  interface Slot {
    mx: number
    my: number
    capacity: number
    jitterY: number
  }

  // 判断哪些弦段足够宽可以左右错落放 2 个算法（如新疆、西南、蒙古、甘肃、南方、华东等）
  const avgWeight = items.reduce((s, it) => s + estimateNameWeight(getLabel(it)), 0) / n
  const estLabelMapWidth = Math.max(46, avgWeight * 4.4)

  // 根据算法数量决定需要采样多少行
  const maxChordW = usable.reduce((m, c) => Math.max(m, c.width), 0)
  const canDoubleCol = maxChordW >= estLabelMapWidth * 1.95
  const targetRows = Math.min(
    usable.length,
    canDoubleCol ? Math.max(3, Math.ceil(n / 1.55)) : Math.max(4, n),
  )

  const slots: Slot[] = []
  for (let r = 0; r < targetRows; r++) {
    const frac = targetRows === 1 ? 0.5 : r / (targetRows - 1)
    const cIdx = Math.round(frac * (usable.length - 1))
    const chord = usable[cIdx]

    if (canDoubleCol && chord.width >= estLabelMapWidth * 1.85 && slots.length + (targetRows - r) < n) {
      // 该弦段很宽：左右错落放 2 个槽位，高度微微错开（不平齐）
      const half = chord.width * 0.26
      const tilt = r % 2 === 0 ? -3 : 3
      slots.push({
        mx: chord.midX - half,
        my: chord.y,
        capacity: chord.width * 0.48,
        jitterY: tilt,
      })
      slots.push({
        mx: chord.midX + half,
        my: chord.y,
        capacity: chord.width * 0.48,
        jitterY: -tilt,
      })
    } else {
      // 单槽位：按弦段轮廓自然左右微错落
      const sway = (r % 2 === 0 ? -1 : 1) * Math.min(22, chord.width * 0.14)
      slots.push({
        mx: chord.midX + sway,
        my: chord.y,
        capacity: chord.width * 0.9,
        jitterY: 0,
      })
    }
  }

  // 如果算法数量多于当前槽位数，在可用弦段中补充额外槽位
  let extraIdx = 0
  while (slots.length < n) {
    const chord = usable[extraIdx % usable.length]
    const side = extraIdx % 2 === 0 ? -0.22 : 0.22
    slots.push({
      mx: chord.midX + chord.width * side,
      my: chord.y + (extraIdx % 3 - 1) * 4,
      capacity: chord.width * 0.5,
      jitterY: (extraIdx % 2 === 0 ? -2 : 2),
    })
    extraIdx++
  }

  // 核心排版策略：按算法名称长度降序 vs 槽位可用宽度降序匹配
  // -> 较长的算法名自动分配到地块最宽处，较短的算法名填入较窄处
  const rankedItems = items
    .map((item) => ({ item, weight: estimateNameWeight(getLabel(item)), label: getLabel(item) }))
    .sort((a, b) => b.weight - a.weight)

  const rankedSlots = slots
    .slice(0, n)
    .map((slot, idx) => ({ slot, idx }))
    .sort((a, b) => b.slot.capacity - a.slot.capacity)

  const placed: PlacedAlgoLabel<T>[] = rankedItems.map((entry, i) => {
    const { slot } = rankedSlots[i]
    const seed = stableHash(rg + ':' + entry.label)
    // 轻微水平扰动，避免多行死板居中对齐
    const organicX = (seed - 0.5) * Math.min(16, Math.max(0, slot.capacity - entry.weight * 3.5) * 0.25)
    return {
      item: entry.item,
      mx: slot.mx + organicX,
      my: slot.my,
      jitterY: slot.jitterY,
    }
  })

  return { header, placed }
}
