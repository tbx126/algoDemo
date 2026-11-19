<script setup lang="ts">
import { ref } from 'vue'
import { Database, Plus, Trophy, Medal } from 'lucide-vue-next'
import { getLeaderboard, listBenchmarks, type LeaderboardRow } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { TASKS } from '@/utils/meta'
import { fmtMetric, timeAgo } from '@/utils/format'
import type { TaskType } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import TaskBadge from '@/components/ui/TaskBadge.vue'

const { can } = useSession()
const task = ref<TaskType | ''>('')
const { data, loading, error } = useAsync(async () => {
  const bs = await listBenchmarks({ task: task.value })
  const tops = await Promise.all(bs.map((b) => getLeaderboard(b.id)))
  return bs.map((b, i) => ({ b, top: tops[i].slice(0, 3) as LeaderboardRow[], n: tops[i].length }))
}, [task])
</script>

<template>
  <div class="container-page pt-8">
    <div class="mb-6 flex flex-wrap items-end gap-4">
      <div>
        <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><Trophy class="size-6 text-amber-500" />评测基准</h1>
        <p class="mt-1 text-sm text-gray-500">评测基准 = 数据集版本的测试集 + 评测器版本 + 指标配置。排行榜挂在评测基准上，规则变化即新建基准，旧榜单不受影响。</p>
      </div>
      <div class="ml-auto flex items-center gap-2">
        <select v-model="task" class="input w-auto" aria-label="按任务类型筛选">
          <option value="">全部任务</option>
          <option v-for="(v, k) in TASKS" :key="k" :value="k">{{ v.label }}</option>
        </select>
        <RouterLink v-if="can.createBenchmark" to="/benchmarks/new" class="btn-primary"><Plus class="size-4" />新建评测基准</RouterLink>
      </div>
    </div>

    <StateView :loading="loading && !data" :error="error" :empty="data && !data.length" empty-text="暂无可见的评测基准">
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <RouterLink v-for="{ b, top, n } in data" :key="b.id" :to="`/benchmarks/${b.id}`" class="card group flex flex-col p-4 transition hover:border-gray-300 hover:shadow-sm dark:hover:border-gray-700">
          <div class="flex items-start justify-between gap-2">
            <h2 class="font-semibold text-gray-900 group-hover:text-brand-600 dark:text-white">{{ b.displayName }}</h2>
            <TaskBadge :task="b.task" class="shrink-0" />
          </div>
          <p class="mt-1 line-clamp-2 text-sm text-gray-500">{{ b.description }}</p>
          <div class="mt-3 flex flex-wrap gap-1.5 text-xs">
            <span class="chip"><Database class="size-3" />{{ b.datasetId.split('/')[1] }} · 测试集 {{ b.datasetVersion }}</span>
            <span class="chip mono">{{ b.evaluator }}@{{ b.evaluatorVersion }}</span>
          </div>
          <div class="mt-4 flex-1 space-y-1.5 border-t border-gray-100 pt-3 dark:border-gray-800">
            <p v-if="!top.length" class="text-sm text-gray-400">{{ can.seeOthersOnBoard ? '暂无上榜结果' : '你的算法暂未上榜' }}</p>
            <div v-for="r in top" :key="r.run.id" class="flex items-center gap-2 text-sm">
              <Medal class="size-4 shrink-0" :class="['text-amber-500', 'text-gray-400', 'text-orange-700'][r.rank - 1]" />
              <span class="mono min-w-0 flex-1 truncate">{{ r.algorithm.name }}<span class="text-gray-400"> {{ r.run.algoVersion }}</span></span>
              <span v-if="!can.seeOthersOnBoard" class="mono text-xs text-gray-500">第 {{ r.rank }} 名</span>
              <span class="mono font-medium">{{ fmtMetric(r.run.metrics[b.metrics.find((m) => m.primary)!.key], b.metrics.find((m) => m.primary)!.unit) }}</span>
            </div>
          </div>
          <div class="mt-3 flex justify-between text-xs text-gray-500">
            <span>主指标：{{ b.metrics.find((m) => m.primary)!.label }} · {{ can.seeOthersOnBoard ? n + ' 个上榜' : '你有 ' + n + ' 个上榜' }}</span>
            <span>{{ timeAgo(b.createdAt) }}创建</span>
          </div>
        </RouterLink>
      </div>
    </StateView>
  </div>
</template>
