<script setup lang="ts">
import { computed } from 'vue'
import { Clock, Download, Heart, Images } from 'lucide-vue-next'
import type { Dataset } from '@/types'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import TaskIcon from '@/components/ui/TaskIcon.vue'
import { TASKS } from '@/utils/meta'
import { fmtNum, timeAgo } from '@/utils/format'

const props = defineProps<{ d: Dataset }>()
const total = computed(() => props.d.train.versions[0].files + (props.d.test?.versions[0].files ?? 0))
</script>

<template>
  <RouterLink
    :to="`/datasets/${d.id}`"
    class="group block rounded-xl border border-gray-100 bg-gradient-to-r from-gray-50 to-white p-3 transition hover:border-gray-200 hover:shadow-sm dark:border-gray-800 dark:from-gray-900 dark:to-gray-950 dark:hover:border-gray-700"
  >
    <div class="flex items-center gap-2">
      <OrgAvatar :org="d.org" :size="18" />
      <h3 class="mono truncate font-medium text-gray-800 group-hover:text-brand-600 dark:text-gray-100 dark:group-hover:text-brand-500">{{ d.id }}</h3>
    </div>
    <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
      <span class="inline-flex items-center gap-1"><TaskIcon :task="d.task" class="size-3.5" :class="TASKS[d.task].color" />{{ TASKS[d.task].label }}</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1"><Images class="size-3" />{{ fmtNum(total) }} 样本</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1"><Clock class="size-3" />{{ timeAgo(d.updatedAt) }}更新</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1"><Download class="size-3" />{{ fmtNum(d.downloads) }}</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1"><Heart class="size-3" />{{ fmtNum(d.likes) }}</span>
    </div>
  </RouterLink>
</template>
