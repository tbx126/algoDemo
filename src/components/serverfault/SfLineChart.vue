<script setup lang="ts">
/**
 * 通用折线图（SVG，服务器故障检测标准组件使用）
 * - 多序列折线，可选阶梯线 / 虚线 / 面积
 * - 背景区间（真值故障段、预警段等），竖向标注线
 * - 悬停十字线 + 提示框；>= 2 个序列时显示图例
 * - 颜色取自 .sf-viz 上的 CSS 变量，亮 / 暗两套
 */
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'

export interface SfSeries {
  key: string
  name: string
  values: (number | null)[]
  color: string // 例如 'var(--v7-s1)'
  dashed?: boolean
  step?: boolean
  area?: boolean
  width?: number
}
export interface SfBand {
  from: number
  to: number
  kind: 'fault' | 'warn' | 'pred'
  label?: string
}

const props = withDefaults(
  defineProps<{
    x: number[]
    series: SfSeries[]
    height?: number
    yMin?: number
    yMax?: number
    yTicks?: number[]
    yFormat?: (v: number) => string
    xFormat?: (v: number) => string
    tipFormat?: (v: number, s: SfSeries) => string
    xLabel?: string
    bands?: SfBand[]
    markers?: { x: number; label: string }[]
    legend?: boolean
    padLeft?: number
  }>(),
  { height: 170, legend: true, padLeft: 40 },
)

const hatchId = `sf-hatch-${useId()}`
const root = ref<HTMLElement>()
const width = ref(560)
let ro: ResizeObserver | undefined
onMounted(() => {
  if (!root.value) return
  width.value = root.value.clientWidth || 560
  ro = new ResizeObserver((es) => (width.value = Math.max(240, es[0].contentRect.width)))
  ro.observe(root.value)
})
onBeforeUnmount(() => ro?.disconnect())

const pad = computed(() => ({ l: props.padLeft, r: 10, t: 10, b: props.xLabel ? 32 : 22 }))
const plotW = computed(() => width.value - pad.value.l - pad.value.r)
const plotH = computed(() => props.height - pad.value.t - pad.value.b)

const xMin = computed(() => props.x[0] ?? 0)
const xMax = computed(() => props.x[props.x.length - 1] ?? 1)
/** 1 / 2 / 2.5 / 5 × 10^k 的整齐步长 */
function niceStep(raw: number) {
  if (raw <= 0 || !Number.isFinite(raw)) return 1
  const p = 10 ** Math.floor(Math.log10(raw))
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p
  return 10 * p
}
const range = computed(() => {
  const vals = props.series.flatMap((s) => s.values.filter((v): v is number => v !== null && Number.isFinite(v)))
  const dataLo = vals.length ? Math.min(...vals) : 0
  const dataHi = vals.length ? Math.max(...vals) : 1
  let lo = props.yMin ?? Math.min(0, dataLo)
  let hi = props.yMax ?? dataHi
  if (hi <= lo) hi = lo + 1
  if (props.yMax === undefined || props.yMin === undefined) {
    // 未固定的一端按整齐步长外扩
    const step = niceStep((hi - lo) / 4)
    if (props.yMin === undefined) lo = Math.floor(lo / step) * step
    if (props.yMax === undefined) hi = Math.ceil(hi / step) * step
    if (hi <= lo) hi = lo + step
  }
  return { lo, hi }
})
const ticks = computed(() => {
  if (props.yTicks) return props.yTicks
  const { lo, hi } = range.value
  const step = niceStep((hi - lo) / 4)
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(+v.toFixed(6))
  return out
})
const xTicks = computed(() => {
  const n = Math.min(7, Math.max(3, Math.floor(plotW.value / 80)))
  const span = xMax.value - xMin.value
  const intX = props.x.every((v) => Number.isInteger(v))
  let step = niceStep(span / (n - 1))
  if (intX) step = step === 2.5 * 10 ** Math.floor(Math.log10(step)) ? step * 2 : Math.max(1, Math.round(step))
  const out: number[] = []
  for (let v = Math.ceil(xMin.value / step) * step; v <= xMax.value + step * 1e-6; v += step) out.push(+v.toFixed(6))
  return out
})

const sx = (v: number) => pad.value.l + ((v - xMin.value) / (xMax.value - xMin.value || 1)) * plotW.value
const sy = (v: number) => pad.value.t + (1 - (v - range.value.lo) / (range.value.hi - range.value.lo)) * plotH.value
const fy = (v: number) => (props.yFormat ? props.yFormat(v) : String(+v.toFixed(2)))
const fx = (v: number) => (props.xFormat ? props.xFormat(v) : String(+v.toFixed(2)))

const paths = computed(() =>
  props.series.map((s) => {
    let d = ''
    let open = false
    let firstX: number | null = null
    s.values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) {
        open = false
        return
      }
      const X = sx(props.x[i])
      const Y = sy(v)
      if (firstX === null) firstX = X
      if (!open) {
        d += `M${X.toFixed(1)},${Y.toFixed(1)}`
        open = true
      } else if (s.step) {
        d += `H${X.toFixed(1)}V${Y.toFixed(1)}`
      } else {
        d += `L${X.toFixed(1)},${Y.toFixed(1)}`
      }
    })
    const base = sy(Math.max(range.value.lo, 0))
    const area = s.area && d && firstX !== null ? `${d}V${base.toFixed(1)}H${(firstX as number).toFixed(1)}Z` : ''
    return { ...s, d, area }
  }),
)

const bandRects = computed(() =>
  (props.bands ?? []).map((b) => {
    const step = props.x.length > 1 ? (props.x[1] - props.x[0]) / 2 : 0
    const x1 = sx(Math.max(xMin.value, b.from - step))
    const x2 = sx(Math.min(xMax.value, b.to + step))
    return { ...b, x: x1, w: Math.max(1, x2 - x1) }
  }),
)

// ---------- 悬停 ----------
const hover = ref<number | null>(null)
function onMove(e: MouseEvent) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const px = ((e.clientX - rect.left) / rect.width) * width.value
  if (px < pad.value.l - 4 || px > width.value - pad.value.r + 4) {
    hover.value = null
    return
  }
  let best = 0
  let bd = Infinity
  props.x.forEach((xv, i) => {
    const d = Math.abs(sx(xv) - px)
    if (d < bd) {
      bd = d
      best = i
    }
  })
  hover.value = best
}
const tip = computed(() => {
  const i = hover.value
  if (i === null) return null
  const X = sx(props.x[i])
  const rows = props.series
    .map((s) => ({ s, v: s.values[i] }))
    .filter((r) => r.v !== null && r.v !== undefined && Number.isFinite(r.v))
    .map((r) => ({ name: r.s.name, color: r.s.color, text: props.tipFormat ? props.tipFormat(r.v as number, r.s) : fy(r.v as number), y: sy(r.v as number) }))
  const left = X > width.value * 0.62
  return { X, rows, left, title: fx(props.x[i]) }
})
</script>

<template>
  <div ref="root" class="sf-viz relative w-full select-none">
    <div v-if="legend && series.length > 1" class="mb-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-gray-600 dark:text-gray-300">
      <span v-for="s in series" :key="s.key" class="inline-flex items-center gap-1.5">
        <svg width="16" height="8" aria-hidden="true">
          <line x1="1" y1="4" x2="15" y2="4" :stroke="s.color" stroke-width="2" stroke-linecap="round" :stroke-dasharray="s.dashed ? '3 2' : undefined" />
        </svg>
        {{ s.name }}
      </span>
      <span v-for="b in [...new Map((bands ?? []).filter((b) => b.label).map((b) => [b.kind, b])).values()]" :key="b.kind" class="inline-flex items-center gap-1.5">
        <span class="inline-block h-2.5 w-3.5 rounded-sm" :class="`band-${b.kind}`" />{{ b.label }}
      </span>
    </div>
    <svg :viewBox="`0 0 ${width} ${height}`" :width="width" :height="height" class="block max-w-full overflow-visible" role="img" @mousemove="onMove" @mouseleave="hover = null">
      <!-- 背景区间 -->
      <defs>
        <pattern :id="hatchId" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" class="sf-hatch" />
        </pattern>
      </defs>
      <rect v-for="(b, i) in bandRects.filter((b) => b.kind !== 'pred')" :key="'b' + i" :x="b.x" :y="pad.t" :width="b.w" :height="plotH" :class="`band-${b.kind}`" />
      <g v-for="(b, i) in bandRects.filter((b) => b.kind === 'pred')" :key="'p' + i">
        <rect :x="b.x" :y="pad.t" :width="b.w" :height="plotH" :fill="`url(#${hatchId})`" />
        <rect :x="b.x" :y="pad.t + plotH - 4" :width="b.w" height="4" class="sf-pred-strip" />
      </g>
      <!-- 网格与 y 轴刻度 -->
      <g v-for="t in ticks" :key="'t' + t">
        <line :x1="pad.l" :x2="width - pad.r" :y1="sy(t)" :y2="sy(t)" class="sf-grid" />
        <text :x="pad.l - 6" :y="sy(t) + 3" text-anchor="end" class="sf-axis">{{ fy(t) }}</text>
      </g>
      <!-- x 轴刻度 -->
      <text v-for="t in xTicks" :key="'x' + t" :x="sx(t)" :y="height - (xLabel ? 18 : 6)" text-anchor="middle" class="sf-axis">{{ fx(t) }}</text>
      <text v-if="xLabel" :x="pad.l + plotW / 2" :y="height - 3" text-anchor="middle" class="sf-axis">{{ xLabel }}</text>
      <!-- 竖向标注 -->
      <g v-for="(m, i) in markers ?? []" :key="'m' + i">
        <line :x1="sx(m.x)" :x2="sx(m.x)" :y1="pad.t" :y2="pad.t + plotH" class="sf-marker" />
        <text :x="sx(m.x) + 4" :y="pad.t + 10" class="sf-axis sf-marker-text">{{ m.label }}</text>
      </g>
      <!-- 序列 -->
      <path v-for="p in paths.filter((p) => p.area)" :key="'a' + p.key" :d="p.area" :fill="p.color" fill-opacity="0.1" />
      <path
        v-for="p in paths"
        :key="p.key"
        :d="p.d"
        fill="none"
        :stroke="p.color"
        :stroke-width="p.width ?? 2"
        stroke-linejoin="round"
        stroke-linecap="round"
        :stroke-dasharray="p.dashed ? '4 3' : undefined"
      />
      <!-- 悬停 -->
      <g v-if="tip">
        <line :x1="tip.X" :x2="tip.X" :y1="pad.t" :y2="pad.t + plotH" class="sf-cross" />
        <circle v-for="r in tip.rows" :key="r.name" :cx="tip.X" :cy="r.y" r="4" :fill="r.color" class="sf-dot" />
      </g>
    </svg>
    <div
      v-if="tip && tip.rows.length"
      class="pointer-events-none absolute top-6 z-20 min-w-32 rounded-md border border-gray-200 bg-white/95 px-2.5 py-1.5 text-[11px] shadow-lg dark:border-gray-700 dark:bg-gray-900/95"
      :style="tip.left ? { right: `${width - tip.X + 10}px` } : { left: `${tip.X + 10}px` }"
    >
      <div class="mb-0.5 font-medium text-gray-900 dark:text-gray-100">{{ tip.title }}</div>
      <div v-for="r in tip.rows" :key="r.name" class="flex items-center gap-1.5 whitespace-nowrap text-gray-600 dark:text-gray-300">
        <span class="inline-block size-2 rounded-full" :style="{ background: r.color }" />
        <span>{{ r.name }}</span>
        <span class="ml-auto pl-3 font-mono text-gray-900 dark:text-gray-100">{{ r.text }}</span>
      </div>
    </div>
  </div>
</template>

<style>
.sf-viz,
.sf-viz-scope {
  --v7-s1: #2a78d6;
  --v7-s2: #eb6834;
  --v7-s3: #1baf7a;
  --v7-s4: #eda100;
  --v7-s5: #e87ba4;
  --v7-s6: #008300;
  --v7-s7: #6250d6;
  --v7-s8: #e34948;
  --v7-ink: #52514e;
  --v7-grid: #ececea;
  --v7-axis: #8a8985;
  --v7-band-fault: rgba(227, 73, 72, 0.12);
  --v7-band-warn: rgba(237, 161, 0, 0.14);
  --v7-pred: #eb6834;
}
.dark .sf-viz,
.dark .sf-viz-scope {
  --v7-s1: #3987e5;
  --v7-s2: #d95926;
  --v7-s3: #199e70;
  --v7-s4: #c98500;
  --v7-s5: #d55181;
  --v7-s6: #0ca30c;
  --v7-s7: #9085e9;
  --v7-s8: #e66767;
  --v7-ink: #c3c2b7;
  --v7-grid: #262624;
  --v7-axis: #8f8e88;
  --v7-band-fault: rgba(230, 103, 103, 0.18);
  --v7-band-warn: rgba(201, 133, 0, 0.2);
  --v7-pred: #d95926;
}
.sf-viz .sf-grid {
  stroke: var(--v7-grid);
  stroke-width: 1;
}
.sf-viz .sf-axis {
  fill: var(--v7-axis);
  font-size: 10px;
}
.sf-viz .sf-marker {
  stroke: var(--v7-ink);
  stroke-width: 1;
  stroke-dasharray: 3 3;
  opacity: 0.6;
}
.sf-viz .sf-marker-text {
  fill: var(--v7-ink);
}
.sf-viz .sf-cross {
  stroke: var(--v7-axis);
  stroke-width: 1;
}
.sf-viz .sf-dot {
  stroke: white;
  stroke-width: 2;
}
.dark .sf-viz .sf-dot {
  stroke: #111827;
}
.sf-viz .band-fault {
  fill: var(--v7-band-fault);
  background: var(--v7-band-fault);
}
.sf-viz .band-warn {
  fill: var(--v7-band-warn);
  background: var(--v7-band-warn);
}
.sf-viz .band-pred {
  background: repeating-linear-gradient(-45deg, var(--v7-pred) 0 1.5px, transparent 1.5px 4px);
  box-shadow: inset 0 -3px 0 var(--v7-pred);
}
.sf-viz .sf-hatch {
  stroke: var(--v7-pred);
  stroke-width: 1.5;
  opacity: 0.45;
}
.sf-viz .sf-pred-strip {
  fill: var(--v7-pred);
}
</style>
