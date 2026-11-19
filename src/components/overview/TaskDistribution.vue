<script setup lang="ts">
import { computed, ref } from 'vue'
import type { TaskType } from '@/types'
import { TASKS } from '@/utils/meta'
import TaskIcon from '@/components/ui/TaskIcon.vue'

/** 各任务类型的算法数 / 数据集数：分组水平条，颜色跟随系列（算法=1，数据集=2） */
const props = defineProps<{ rows: { task: TaskType; algorithms: number; datasets: number }[] }>()
const max = computed(() => Math.max(1, ...props.rows.flatMap((r) => [r.algorithms, r.datasets])))
const hover = ref<string | null>(null)
</script>

<template>
  <div>
    <div class="mb-3 flex gap-4 text-xs text-gray-600 dark:text-gray-400" role="list" aria-label="图例">
      <span role="listitem" class="inline-flex items-center gap-1.5"><span class="size-2.5 rounded-sm" style="background: var(--series-1)" />算法</span>
      <span role="listitem" class="inline-flex items-center gap-1.5"><span class="size-2.5 rounded-sm" style="background: var(--series-2)" />数据集</span>
    </div>
    <div class="space-y-1.5">
      <RouterLink
        v-for="r in rows"
        :key="r.task"
        :to="`/algorithms?task=${r.task}`"
        class="grid grid-cols-[112px_1fr] items-center gap-3 rounded-md px-1 py-0.5 hover:bg-gray-50 dark:hover:bg-gray-800/50"
        :title="`${TASKS[r.task].label}：${r.algorithms} 个算法，${r.datasets} 个数据集`"
        @mouseenter="hover = r.task"
        @mouseleave="hover = null"
      >
        <span class="flex min-w-0 items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300">
          <TaskIcon :task="r.task" class="size-3.5 shrink-0 text-gray-400" /><span class="truncate">{{ TASKS[r.task].label }}</span>
        </span>
        <span class="space-y-[2px]">
          <span class="flex items-center gap-2">
            <span class="h-2 rounded-r-[4px]" :style="{ width: `max(${r.algorithms ? 4 : 0}px, ${(r.algorithms / max) * 85}%)`, background: 'var(--series-1)', opacity: hover && hover !== r.task ? 0.45 : 1 }" />
            <span class="mono text-xs text-gray-600 dark:text-gray-400">{{ r.algorithms }}</span>
          </span>
          <span class="flex items-center gap-2">
            <span class="h-2 rounded-r-[4px]" :style="{ width: `max(${r.datasets ? 4 : 0}px, ${(r.datasets / max) * 85}%)`, background: 'var(--series-2)', opacity: hover && hover !== r.task ? 0.45 : 1 }" />
            <span class="mono text-xs text-gray-600 dark:text-gray-400">{{ r.datasets }}</span>
          </span>
        </span>
      </RouterLink>
    </div>
  </div>
</template>
