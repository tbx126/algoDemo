<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

export interface Pt {
  id: string
  label: string
  x: number // 耗时 ms
  y: number // 主指标
  selected?: boolean
}
const props = defineProps<{ points: Pt[]; xLabel: string; yLabel: string; yUnit?: string }>()
const emit = defineEmits<{ toggle: [id: string] }>()

// 按容器实际宽度绘制（1:1 像素），文字与点不会随宽度被放大
const root = ref<HTMLDivElement>()
const W = ref(640)
const H = 340
const M = { l: 48, r: 24, t: 16, b: 40 }
const hover = ref<Pt | null>(null)
let ro: ResizeObserver | undefined
onMounted(() => {
  ro = new ResizeObserver(([e]) => {
    const w = Math.max(320, Math.round(e.contentRect.width))
    requestAnimationFrame(() => (W.value = w)) // 下一帧再更新，避免 ResizeObserver 循环警告
  })
  ro.observe(root.value!)
})
onBeforeUnmount(() => ro?.disconnect())

function nice(min: number, max: number) {
  const span = max - min || 1
  const step = 10 ** Math.floor(Math.log10(span / 4))
  const s = [1, 2, 5, 10].map((k) => k * step).find((k) => span / k <= 5)!
  return { lo: Math.floor(min / s) * s, hi: Math.ceil(max / s) * s, step: s }
}
const xs = computed(() => nice(0, Math.max(...props.points.map((p) => p.x)) * 1.05))
const ys = computed(() => {
  const v = props.points.map((p) => p.y)
  return nice(Math.min(...v) - 1, Math.max(...v) + 1)
})
const sx = (v: number) => M.l + ((v - xs.value.lo) / (xs.value.hi - xs.value.lo)) * (W.value - M.l - M.r)
const sy = (v: number) => H - M.b - ((v - ys.value.lo) / (ys.value.hi - ys.value.lo)) * (H - M.t - M.b)
const ticks = (s: { lo: number; hi: number; step: number }) => {
  const out: number[] = []
  for (let v = s.lo; v <= s.hi + 1e-9; v += s.step) out.push(+v.toFixed(6))
  return out
}
// 帕累托前沿：更快且更准的点
const pareto = computed(() => {
  const sorted = [...props.points].sort((a, b) => a.x - b.x)
  const out: Pt[] = []
  let best = -Infinity
  for (const p of sorted) if (p.y > best) (out.push(p), (best = p.y))
  return out
})
const labelled = computed(() => new Set([...pareto.value.map((p) => p.id), ...props.points.filter((p) => p.selected).map((p) => p.id)]))
</script>

<template>
  <div ref="root" class="relative">
    <svg :viewBox="`0 0 ${W} ${H}`" class="h-auto w-full" role="img" :aria-label="`${yLabel} 与 ${xLabel} 的散点图`" @mouseleave="hover = null">
      <g class="text-[10px]" fill="currentColor">
        <g v-for="t in ticks(ys)" :key="'y' + t">
          <line :x1="M.l" :x2="W - M.r" :y1="sy(t)" :y2="sy(t)" stroke="var(--chart-grid)" />
          <text :x="M.l - 6" :y="sy(t) + 3" text-anchor="end" class="fill-gray-500">{{ t }}</text>
        </g>
        <g v-for="t in ticks(xs)" :key="'x' + t">
          <text :x="sx(t)" :y="H - M.b + 14" text-anchor="middle" class="fill-gray-500">{{ t }}</text>
        </g>
        <line :x1="M.l" :x2="W - M.r" :y1="H - M.b" :y2="H - M.b" stroke="var(--chart-axis)" />
        <text :x="(W + M.l) / 2" :y="H - 6" text-anchor="middle" class="fill-gray-500 text-[11px]">{{ xLabel }} →（越小越快）</text>
        <text :x="12" :y="(H - M.b) / 2" text-anchor="middle" :transform="`rotate(-90 12 ${(H - M.b) / 2})`" class="fill-gray-500 text-[11px]">{{ yLabel }}{{ yUnit ? ` (${yUnit})` : '' }}</text>
      </g>
      <polyline :points="pareto.map((p) => `${sx(p.x)},${sy(p.y)}`).join(' ')" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-dasharray="4 4" opacity="0.5" />
      <g v-for="p in points" :key="p.id" class="cursor-pointer" @mouseenter="hover = p" @click="emit('toggle', p.id)">
        <circle :cx="sx(p.x)" :cy="sy(p.y)" r="14" fill="transparent" />
        <circle :cx="sx(p.x)" :cy="sy(p.y)" :r="p.selected ? 7 : 5" fill="var(--series-1)" stroke="var(--chart-surface)" stroke-width="2" :opacity="hover && hover.id !== p.id ? 0.45 : 1" />
        <circle v-if="p.selected" :cx="sx(p.x)" :cy="sy(p.y)" r="10" fill="none" stroke="var(--series-1)" stroke-width="1.5" />
        <text v-if="labelled.has(p.id)" :x="sx(p.x) + 9" :y="sy(p.y) - 8" class="fill-gray-700 text-[10px] dark:fill-gray-300">{{ p.label }}</text>
      </g>
    </svg>
    <div
      v-if="hover"
      class="card pointer-events-none absolute z-10 px-2.5 py-1.5 text-xs shadow-lg"
      :style="{ left: `${(sx(hover.x) / W) * 100}%`, top: `${(sy(hover.y) / H) * 100}%`, transform: 'translate(-50%, calc(-100% - 12px))' }"
    >
      <p class="mono font-medium">{{ hover.label }}</p>
      <p class="text-gray-500">{{ yLabel }} <span class="text-gray-900 dark:text-white">{{ hover.y.toFixed(2) }}</span> · {{ xLabel }} <span class="text-gray-900 dark:text-white">{{ hover.x < 1 ? hover.x.toFixed(3) : hover.x.toFixed(1) }}</span></p>
    </div>
  </div>
</template>
