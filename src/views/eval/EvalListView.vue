<script setup lang="ts">
import { computed, ref } from 'vue'
import { Cpu, FlaskConical, Flame, Plus, Snowflake } from 'lucide-vue-next'
import { getQueueStatus, listEvals } from '@/api'
import { algoFullLabel } from '@/utils/display'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import StateView from '@/components/ui/StateView.vue'
import EvalTable from '@/components/benchmark/EvalTable.vue'

const { can } = useSession()
const filter = ref<'' | 'mine' | 'running' | 'queued' | 'failed' | 'succeeded'>('')
const { data: runs, loading, error } = useAsync(() => listEvals(filter.value === 'mine' ? { mine: true } : filter.value ? { status: filter.value } : {}), [filter])
const { data: q } = useAsync(() => getQueueStatus())
const tabs = [
  { k: '', label: '全部' },
  { k: 'mine', label: '我提交的' },
  { k: 'running', label: '运行中' },
  { k: 'queued', label: '排队中' },
  { k: 'succeeded', label: '成功' },
  { k: 'failed', label: '失败' },
] as const
const memPct = computed(() => (q.value ? (q.value.gpuMemUsed / q.value.gpuMemTotal) * 100 : 0))
</script>

<template>
  <div class="container-page pt-8">
    <div class="mb-6 flex flex-wrap items-end gap-4">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><FlaskConical class="size-6 text-brand-600" />评测任务</h1>
        <p class="mt-1 text-sm text-gray-500">评测任务串行执行，按 algo.yaml 声明的显存做准入；在线推理优先于未开始的评测。</p>
      </div>
      <RouterLink v-if="can.runEval" to="/evals/new" class="btn-primary ml-auto"><Plus class="size-4" />发起评测</RouterLink>
    </div>

    <!-- 调度器状态 -->
    <div v-if="q" class="card mb-6 grid gap-5 p-4 md:grid-cols-[1.4fr_1fr_1.6fr]">
      <div>
        <p class="mb-1.5 flex items-center gap-1.5 text-xs text-gray-500"><Cpu class="size-3.5" />{{ q.gpuName }} · 显存</p>
        <div class="flex items-baseline gap-1">
          <span class="text-2xl font-semibold text-gray-900 dark:text-white">{{ q.gpuMemUsed.toFixed(1) }}</span>
          <span class="text-sm text-gray-500">/ {{ q.gpuMemTotal }} GB</span>
        </div>
        <div class="mt-2 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          <div class="h-full rounded-full bg-brand-500" :style="{ width: memPct + '%' }" />
        </div>
      </div>
      <div class="flex gap-6">
        <div>
          <p class="text-xs text-gray-500">运行中</p>
          <p class="text-2xl font-semibold text-gray-900 dark:text-white">{{ q.running }}</p>
        </div>
        <div>
          <p class="text-xs text-gray-500">排队中</p>
          <p class="text-2xl font-semibold text-gray-900 dark:text-white">{{ q.queued }}</p>
        </div>
      </div>
      <div>
        <p class="mb-1.5 text-xs text-gray-500">推理容器（空闲 5 分钟自动回收）</p>
        <div class="space-y-1">
          <div v-for="w in q.warmContainers" :key="w.algorithmId" class="flex items-center gap-2 text-xs">
            <Flame class="size-3.5 text-orange-500" />
            <RouterLink :to="`/algorithms/${w.algorithmId}`" class="truncate hover:underline">{{ algoFullLabel(w.algorithmId) }}</RouterLink>
            <span class="ml-auto shrink-0 text-gray-500">{{ w.memGB }} GB · 空闲 {{ Math.floor(w.idleSec / 60) }}m{{ w.idleSec % 60 }}s</span>
          </div>
          <p v-if="!q.warmContainers.length" class="flex items-center gap-1 text-xs text-gray-400"><Snowflake class="size-3.5" />无预热容器</p>
        </div>
      </div>
    </div>

    <div class="mb-3 flex gap-1 no-scrollbar overflow-x-auto overflow-y-hidden border-b border-gray-100 dark:border-gray-800">
      <button v-for="t in tabs" :key="t.k" class="tab" :class="{ 'tab-active': filter === t.k }" @click="filter = t.k">{{ t.label }}</button>
    </div>
    <StateView :loading="loading && !runs" :error="error">
      <EvalTable :runs="runs ?? []" />
    </StateView>
  </div>
</template>
