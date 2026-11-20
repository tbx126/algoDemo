<script setup lang="ts">
import { computed, ref } from 'vue'
import { Ban, CircleCheck, CircleX, Clock, LoaderCircle } from 'lucide-vue-next'
import type { EvalStatus } from '@/types'

/** 评测状态构成：一条分段条 + 带图标的图例（状态色不单独承载信息） */
const props = defineProps<{ counts: Record<EvalStatus, number> }>()
const META: { k: EvalStatus; label: string; color: string; icon: unknown }[] = [
  { k: 'succeeded', label: '成功', color: 'var(--status-good)', icon: CircleCheck },
  { k: 'running', label: '运行中', color: 'var(--series-1)', icon: LoaderCircle },
  { k: 'queued', label: '排队中', color: 'var(--status-neutral)', icon: Clock },
  { k: 'failed', label: '失败', color: 'var(--status-critical)', icon: CircleX },
  { k: 'canceled', label: '已取消', color: 'var(--status-muted)', icon: Ban },
]
const total = computed(() => Object.values(props.counts).reduce((s, v) => s + v, 0))
const items = computed(() => META.map((m) => ({ ...m, v: props.counts[m.k] ?? 0 })))
const hover = ref<EvalStatus | null>(null)
</script>

<template>
  <div>
    <div class="flex h-3 gap-[2px] overflow-hidden rounded" role="img" :aria-label="items.map((i) => `${i.label} ${i.v}`).join('，')">
      <div
        v-for="i in items.filter((x) => x.v)"
        :key="i.k"
        class="h-full transition-opacity first:rounded-l last:rounded-r"
        :style="{ width: (total ? (i.v / total) * 100 : 0) + '%', background: i.color, opacity: hover && hover !== i.k ? 0.4 : 1 }"
        :title="`${i.label}：${i.v}（${total ? ((i.v / total) * 100).toFixed(0) : 0}%）`"
        @mouseenter="hover = i.k"
        @mouseleave="hover = null"
      />
    </div>
    <ul class="mt-4 space-y-1.5">
      <li v-for="i in items" :key="i.k" class="flex items-center gap-2 rounded-md px-1 py-0.5 text-sm" :class="hover === i.k ? 'bg-gray-50 dark:bg-gray-800' : ''" @mouseenter="hover = i.k" @mouseleave="hover = null">
        <component :is="i.icon" class="size-4" :style="{ color: i.color }" />
        <span class="text-gray-700 dark:text-gray-300">{{ i.label }}</span>
        <span class="mono ml-auto font-medium text-gray-900 dark:text-white">{{ i.v }}</span>
        <span class="mono w-10 text-right text-xs text-gray-500">{{ total ? ((i.v / total) * 100).toFixed(0) : 0 }}%</span>
      </li>
    </ul>
  </div>
</template>
