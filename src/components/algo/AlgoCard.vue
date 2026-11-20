<script setup lang="ts">
import { computed } from 'vue'
import { FlaskConical, Heart, Clock } from 'lucide-vue-next'
import type { Algorithm } from '@/types'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import TaskIcon from '@/components/ui/TaskIcon.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { BUSINESS_CATEGORIES, TASKS } from '@/utils/meta'
import { fmtNum, timeAgo } from '@/utils/format'
import { algoFullLabel } from '@/utils/display'

const props = defineProps<{ a: Algorithm }>()
const latest = computed(() => props.a.versions[0])
const biz = computed(() => BUSINESS_CATEGORIES[props.a.business])
</script>

<template>
  <RouterLink
    :to="`/algorithms/${a.id}`"
    class="group block rounded-xl border border-gray-100 bg-gradient-to-r from-gray-50 to-white p-3 transition hover:border-gray-200 hover:shadow-sm dark:border-gray-800 dark:from-gray-900 dark:to-gray-950 dark:hover:border-gray-700"
  >
    <div class="flex items-center gap-2">
      <OrgAvatar :org="a.org" :size="18" />
      <h3 class="truncate font-medium text-gray-800 group-hover:text-brand-600 dark:text-gray-100 dark:group-hover:text-brand-500">{{ algoFullLabel(a) }}</h3>
      <StatusBadge v-if="latest.status !== 'ready'" :status="latest.status" class="ml-auto shrink-0" />
    </div>
    <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
      <span class="inline-flex items-center gap-1"><TaskIcon :task="a.task" class="size-3.5" :class="TASKS[a.task].color" />{{ TASKS[a.task].label }}</span>
      <span v-if="biz" class="chip px-1.5 py-0 text-[11px]" :class="biz.chip">{{ biz.label }}</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span>{{ a.framework }}</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1"><Clock class="size-3" />{{ timeAgo(a.updatedAt) }}更新</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1" title="评测次数"><FlaskConical class="size-3" />{{ a.evalCount }}</span>
      <span class="text-gray-300 dark:text-gray-700">·</span>
      <span class="inline-flex items-center gap-1"><Heart class="size-3" />{{ fmtNum(a.likes) }}</span>
    </div>
    <div v-if="a.tags.length" class="mt-2 flex flex-wrap gap-1">
      <span v-for="t in a.tags.slice(0, 4)" :key="t" class="chip px-1.5 py-0 text-[11px]">{{ t }}</span>
      <span v-if="a.tags.length > 4" class="text-[11px] text-gray-400">+{{ a.tags.length - 4 }}</span>
    </div>
  </RouterLink>
</template>
