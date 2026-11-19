<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { CircleCheck, CircleX } from 'lucide-vue-next'

/** 近 N 天评测完成数：堆叠柱（成功 / 失败），悬停显示当日明细 */
const props = defineProps<{ data: { date: string; succeeded: number; failed: number }[] }>()

const root = ref<HTMLDivElement>()
const W = ref(600)
const H = 200
const M = { l: 28, r: 8, t: 12, b: 24 }
const hover = ref<number | null>(null)
let ro: ResizeObserver | undefined
onMounted(() => {
  ro = new ResizeObserver(([e]) => {
    const w = Math.max(280, Math.round(e.contentRect.width))
    requestAnimationFrame(() => (W.value = w)) // 下一帧再更新，避免 ResizeObserver 循环警告
  })
  ro.observe(root.value!)
})
onBeforeUnmount(() => ro?.disconnect())

const maxV = computed(() => Math.max(2, ...props.data.map((d) => d.succeeded + d.failed)))
const ticks = computed(() => {
  const step = Math.max(1, Math.ceil(maxV.value / 4))
  const out: number[] = []
  for (let v = 0; v <= maxV.value + step - 1; v += step) out.push(v)
  return out
})
const top = computed(() => ticks.value[ticks.value.length - 1])
const slot = computed(() => (W.value - M.l - M.r) / props.data.length)
const bw = computed(() => Math.max(3, Math.min(18, slot.value * 0.62)))
const y = (v: number) => H - M.b - (v / top.value) * (H - M.t - M.b)
const x = (i: number) => M.l + slot.value * i + (slot.value - bw.value) / 2

/** 顶端 4px 圆角、底部贴基线的柱形路径 */
function bar(x0: number, y0: number, w: number, h: number, round: boolean) {
  if (h <= 0) return ''
  const r = round ? Math.min(4, w / 2, h) : 0
  return `M${x0},${y0 + h}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + w - r}Q${x0 + w},${y0} ${x0 + w},${y0 + r}V${y0 + h}Z`
}
const totals = computed(() => props.data.reduce((s, d) => ({ s: s.s + d.succeeded, f: s.f + d.failed }), { s: 0, f: 0 }))
</script>

<template>
  <div>
    <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-400" role="list" aria-label="图例">
      <span role="listitem" class="inline-flex items-center gap-1.5"><CircleCheck class="size-3.5" style="color: var(--status-good)" />成功 {{ totals.s }}</span>
      <span role="listitem" class="inline-flex items-center gap-1.5"><CircleX class="size-3.5" style="color: var(--status-critical)" />失败 {{ totals.f }}</span>
    </div>
    <div ref="root" class="relative" @mouseleave="hover = null">
      <svg :viewBox="`0 0 ${W} ${H}`" class="h-auto w-full" role="img" :aria-label="`近 ${data.length} 天每日评测完成数，成功 ${totals.s} 次，失败 ${totals.f} 次`">
        <g v-for="t in ticks" :key="t">
          <line :x1="M.l" :x2="W - M.r" :y1="y(t)" :y2="y(t)" :stroke="t === 0 ? 'var(--chart-axis)' : 'var(--chart-grid)'" />
          <text :x="M.l - 6" :y="y(t) + 3" text-anchor="end" class="fill-gray-500 text-[10px]">{{ t }}</text>
        </g>
        <g v-for="(d, i) in data" :key="d.date">
          <rect :x="M.l + slot * i" :y="M.t" :width="slot" :height="H - M.t - M.b" fill="transparent" @mouseenter="hover = i" />
          <rect v-if="hover === i" :x="M.l + slot * i" :y="M.t" :width="slot" :height="H - M.t - M.b" class="fill-gray-100 dark:fill-gray-800" opacity="0.6" pointer-events="none" />
          <!-- 成功在下，失败叠在上方；两段之间留 2px 间隙 -->
          <path :d="bar(x(i), y(d.succeeded), bw, y(0) - y(d.succeeded), !d.failed)" fill="var(--status-good)" pointer-events="none" />
          <path :d="bar(x(i), y(d.succeeded + d.failed), bw, y(d.succeeded) - y(d.succeeded + d.failed) - (d.succeeded ? 2 : 0), true)" fill="var(--status-critical)" pointer-events="none" />
          <text v-if="i % 5 === 4 || i === data.length - 1" :x="x(i) + bw / 2" :y="H - 8" text-anchor="middle" class="fill-gray-500 text-[10px]">{{ d.date }}</text>
        </g>
      </svg>
      <div
        v-if="hover !== null"
        class="card pointer-events-none absolute top-0 z-10 px-2.5 py-1.5 text-xs shadow-lg"
        :style="{ left: `${((x(hover) + bw / 2) / W) * 100}%`, transform: `translateX(${hover > data.length / 2 ? 'calc(-100% - 8px)' : '8px'})` }"
      >
        <p class="font-medium text-gray-900 dark:text-white">{{ data[hover].date }}</p>
        <p class="mt-0.5 flex items-center gap-1.5 text-gray-600 dark:text-gray-400"><span class="size-2 rounded-sm" style="background: var(--status-good)" />成功 <b class="text-gray-900 dark:text-white">{{ data[hover].succeeded }}</b></p>
        <p class="flex items-center gap-1.5 text-gray-600 dark:text-gray-400"><span class="size-2 rounded-sm" style="background: var(--status-critical)" />失败 <b class="text-gray-900 dark:text-white">{{ data[hover].failed }}</b></p>
      </div>
    </div>
  </div>
</template>
