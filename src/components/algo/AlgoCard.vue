<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, Clock, FlaskConical, Heart, Lock, MapPin, Sparkles } from 'lucide-vue-next'
import type { Algorithm } from '@/types'
import { getDispatchedRegions, getRegionTrialRequest, isDispatchedToRegion } from '@/api'
import { useSession } from '@/stores/session'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import TaskIcon from '@/components/ui/TaskIcon.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { BUSINESS_CATEGORIES, REGIONS, TASKS } from '@/utils/meta'
import { fmtNum, timeAgo } from '@/utils/format'
import { algoFullLabel } from '@/utils/display'

const props = defineProps<{ a: Algorithm }>()
const { state, currentRegion } = useSession()
const latest = computed(() => props.a.versions[0])
const biz = computed(() => BUSINESS_CATEGORIES[props.a.business])
const dispatchedRegions = computed(() => getDispatchedRegions(props.a.id))
const regionalAuthorized = computed(() => isDispatchedToRegion(props.a.id, currentRegion.value))
const regionalReq = computed(() => getRegionTrialRequest(props.a.id, currentRegion.value))
</script>

<template>
  <RouterLink
    :to="`/algorithms/${a.id}`"
    class="group block rounded-xl border border-gray-100 bg-gradient-to-r from-gray-50 to-white p-3 transition hover:border-gray-200 hover:shadow-sm dark:border-gray-800 dark:from-gray-900 dark:to-gray-950 dark:hover:border-gray-700"
  >
    <div class="flex items-center gap-2">
      <OrgAvatar :org="a.org" :size="18" />
      <h3 class="truncate font-medium text-gray-800 group-hover:text-brand-600 dark:text-gray-100 dark:group-hover:text-brand-500">{{ algoFullLabel(a) }}</h3>
      <span
        v-if="a.selfDeveloped"
        class="inline-flex shrink-0 items-center gap-0.5 rounded-md border border-brand-200 bg-brand-50 px-1.5 py-0.2 text-[10px] font-semibold text-brand-700 dark:border-brand-800 dark:bg-brand-950/60 dark:text-brand-300"
      >
        <Sparkles class="size-2.5" />自研
      </span>
      <StatusBadge v-if="latest.status !== 'ready'" :status="latest.status" class="ml-auto shrink-0" />
      <template v-else-if="state.role === 'regional'">
        <span
          v-if="regionalAuthorized"
          class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300"
        >
          <CheckCircle2 class="size-3" />已下发可用
        </span>
        <span
          v-else-if="regionalReq?.status === 'pending'"
          class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300"
        >
          <Clock class="size-3" />试用审批中
        </span>
        <span
          v-else
          class="ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border border-gray-200 bg-gray-100/80 px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
        >
          <Lock class="size-3" />可申请试用
        </span>
      </template>
      <span
        v-else-if="state.role === 'admin' && dispatchedRegions.length"
        class="mono ml-auto inline-flex shrink-0 items-center gap-1 rounded-full border border-sky-200/80 bg-sky-50/80 px-2 py-0.5 text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-300"
        :title="`已下发区域：${dispatchedRegions.join('、')}`"
      >
        <MapPin class="size-2.5" />{{ dispatchedRegions.length }}/{{ REGIONS.length }} 区域
      </span>
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
