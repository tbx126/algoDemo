<script setup lang="ts">
import { ref } from 'vue'
import type { MetricDef } from '@/types'
import { fmtMetric } from '@/utils/format'

/** 多算法对比：每个指标一组水平条，颜色跟随算法（固定顺序，最多 4 个） */
const props = defineProps<{ metrics: MetricDef[]; items: { id: string; label: string; values: Record<string, number> }[] }>()
const COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']
const hover = ref<string | null>(null)

function width(m: MetricDef, v: number) {
  const vals = props.items.map((i) => i.values[m.key] ?? 0)
  const max = Math.max(...vals)
  return max ? (v / max) * 100 : 0
}
function best(m: MetricDef) {
  const vals = props.items.map((i) => i.values[m.key] ?? NaN)
  return m.higherIsBetter ? Math.max(...vals) : Math.min(...vals)
}
</script>

<template>
  <div>
    <div class="mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs" role="list" aria-label="图例">
      <span v-for="(it, i) in items" :key="it.id" role="listitem" class="inline-flex items-center gap-1.5">
        <span class="size-2.5 rounded-sm" :style="{ background: COLORS[i] }" /><span class="mono">{{ it.label }}</span>
      </span>
    </div>
    <div class="grid gap-5 sm:grid-cols-2">
      <div v-for="m in metrics" :key="m.key">
        <p class="mb-1.5 text-xs font-medium text-gray-500">
          {{ m.label }}<span v-if="m.unit"> ({{ m.unit }})</span> · {{ m.higherIsBetter ? '越高越好' : '越低越好' }}
        </p>
        <div class="space-y-[2px]">
          <div v-for="(it, i) in items" :key="it.id" class="flex items-center gap-2" @mouseenter="hover = it.id + m.key" @mouseleave="hover = null">
            <div class="h-4 flex-1">
              <div
                class="h-full rounded-r-[4px] transition-opacity"
                :style="{ width: Math.max(1, width(m, it.values[m.key] ?? 0)) + '%', background: COLORS[i], opacity: hover && hover !== it.id + m.key ? 0.55 : 1 }"
                :title="`${it.label} · ${m.label}: ${fmtMetric(it.values[m.key], m.unit)}`"
              />
            </div>
            <span class="mono w-14 text-right text-xs" :class="it.values[m.key] === best(m) ? 'font-semibold text-gray-900 dark:text-white' : 'text-gray-500'">{{ fmtMetric(it.values[m.key], m.unit) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
