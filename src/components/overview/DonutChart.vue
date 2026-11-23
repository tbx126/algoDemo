<script setup lang="ts">
import { computed, ref } from 'vue'

export interface DonutSlice {
  key: string
  label: string
  value: number
  color: string
  colorEnd?: string
  badge?: string
  to?: string
}

const props = withDefaults(
  defineProps<{
    slices: DonutSlice[]
    size?: number
    thickness?: number
    centerLabel?: string
  }>(),
  { size: 128, thickness: 18, centerLabel: '总计' },
)

const uid = Math.random().toString(36).slice(2, 8)
const hovered = ref<string | null>(null)
const total = computed(() => props.slices.reduce((s, x) => s + x.value, 0))
const r = computed(() => (props.size - props.thickness) / 2 - 4)
const circum = computed(() => 2 * Math.PI * r.value)

const arcs = computed(() => {
  const sum = Math.max(1, total.value)
  const nonZero = props.slices.filter((s) => s.value > 0)
  const gap = nonZero.length > 1 ? 3 : 0
  let offset = 0
  return nonZero.map((s) => {
    const pct = (s.value / sum) * 100
    const rawLen = (s.value / sum) * circum.value
    const len = Math.max(2, rawLen - gap)
    const dashOffset = -offset
    offset += rawLen
    return { ...s, pct, len, dashOffset, gradId: `dg-${uid}-${s.key}` }
  })
})

const activeSlice = computed(() => arcs.value.find((a) => a.key === hovered.value) ?? null)
const isCompact = computed(() => props.size <= 104)
</script>

<template>
  <div class="flex w-full items-center gap-4">
    <!-- 立体感交互式 SVG 环形饼图 -->
    <div class="relative shrink-0" :style="{ width: size + 'px', height: size + 'px' }">
      <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="-rotate-90 overflow-visible">
        <defs>
          <linearGradient v-for="a in arcs" :id="a.gradId" :key="a.gradId" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" :stop-color="a.color" />
            <stop offset="100%" :stop-color="a.colorEnd ?? a.color" />
          </linearGradient>
          <filter :id="`glow-${uid}`" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="1.5" stdDeviation="2.5" flood-opacity="0.16" />
          </filter>
        </defs>

        <!-- 底层轨道环 + 内圈柔光描边 -->
        <circle
          :cx="size / 2"
          :cy="size / 2"
          :r="r"
          fill="none"
          :stroke-width="thickness"
          class="stroke-gray-100 dark:stroke-gray-800/80"
        />
        <circle
          :cx="size / 2"
          :cy="size / 2"
          :r="Math.max(4, r - thickness / 2 - 4)"
          fill="none"
          stroke-width="1"
          class="stroke-gray-100/80 dark:stroke-gray-800/70"
        />

        <!-- 各数据扇区 -->
        <circle
          v-for="a in arcs"
          :key="a.key"
          :cx="size / 2"
          :cy="size / 2"
          :r="r"
          fill="none"
          :stroke="`url(#${a.gradId})`"
          :stroke-width="hovered === a.key ? thickness + 4 : thickness"
          :stroke-dasharray="`${a.len} ${circum}`"
          :stroke-dashoffset="a.dashOffset"
          stroke-linecap="butt"
          :filter="hovered === a.key ? `url(#glow-${uid})` : undefined"
          class="cursor-pointer transition-all duration-200"
          :style="{ opacity: hovered && hovered !== a.key ? 0.32 : 1 }"
          @mouseenter="hovered = a.key"
          @mouseleave="hovered = null"
        />
      </svg>

      <!-- 环心动态读数 -->
      <div class="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-2 text-center">
        <span
          class="mono leading-none font-bold tracking-tight text-gray-900 transition-colors dark:text-white"
          :class="isCompact ? 'text-base' : 'text-xl'"
          :style="activeSlice ? { color: activeSlice.color } : undefined"
        >
          {{ activeSlice ? `${activeSlice.pct.toFixed(0)}%` : total }}
        </span>
        <span class="mt-1 truncate text-[10px] font-medium text-gray-500" :class="isCompact ? 'max-w-[54px]' : 'max-w-[74px]'">
          {{ activeSlice ? activeSlice.label : centerLabel }}
        </span>
      </div>
    </div>

    <!-- 统一列对齐的可点击图例 -->
    <div class="min-w-0 flex-1 space-y-1">
      <component
        :is="a.to ? 'RouterLink' : 'div'"
        v-for="a in arcs"
        :key="a.key"
        :to="a.to"
        class="group flex items-center justify-between gap-2 rounded-lg px-2 py-1 text-xs transition"
        :class="[
          a.to ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/60' : '',
          hovered === a.key ? 'bg-gray-50 dark:bg-gray-800/60' : '',
        ]"
        @mouseenter="hovered = a.key"
        @mouseleave="hovered = null"
      >
        <span class="flex min-w-0 items-center gap-2">
          <span
            class="size-2.5 shrink-0 rounded-full ring-2 ring-white transition-transform dark:ring-gray-900"
            :class="hovered === a.key ? 'scale-125' : ''"
            :style="{ background: `linear-gradient(135deg, ${a.color}, ${a.colorEnd ?? a.color})` }"
          />
          <span class="truncate text-gray-700 group-hover:text-gray-900 dark:text-gray-300 dark:group-hover:text-white">{{ a.label }}</span>
          <span
            v-if="a.badge"
            class="shrink-0 rounded bg-sky-50 px-1 py-0.2 text-[10px] font-medium text-sky-600 dark:bg-sky-950/60 dark:text-sky-400"
          >{{ a.badge }}</span>
        </span>
        <span class="mono flex shrink-0 items-baseline gap-1.5 text-[11px] tabular-nums">
          <strong class="w-4 text-right font-semibold text-gray-900 dark:text-gray-100">{{ a.value }}</strong>
          <span class="w-8 text-right text-[10px] text-gray-400">{{ a.pct.toFixed(0) }}%</span>
        </span>
      </component>
    </div>
  </div>
</template>
