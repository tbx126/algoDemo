<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, Box, ClipboardCheck, Cpu, Database, Flame, FlaskConical, Trophy } from 'lucide-vue-next'
import { getQueueStatus, listAlgorithms, listBenchmarks, listDatasets, listEvals, overview } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { ROLES, TASKS } from '@/utils/meta'
import { fmtBytes, fmtMetric, fmtNum, timeAgo } from '@/utils/format'
import { benchmarks as allBench } from '@/mock/benchmarks'
import AlgoCard from '@/components/algo/AlgoCard.vue'
import DatasetCard from '@/components/dataset/DatasetCard.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TaskIcon from '@/components/ui/TaskIcon.vue'
import TrendColumns from '@/components/overview/TrendColumns.vue'
import StatusMix from '@/components/overview/StatusMix.vue'
import TaskDistribution from '@/components/overview/TaskDistribution.vue'

const { state, can } = useSession()
const { data: ov } = useAsync(() => overview())
const { data: q } = useAsync(() => getQueueStatus())
const { data: algos } = useAsync(() => listAlgorithms({ pageSize: 6 }))
const { data: dss } = useAsync(() => listDatasets({ pageSize: 4 }))
const { data: benches } = useAsync(() => listBenchmarks())
const { data: runs } = useAsync(() => listEvals())

const successRate = computed(() => {
  const s = ov.value?.evalStatus
  if (!s) return 0
  const done = s.succeeded + s.failed
  return done ? (s.succeeded / done) * 100 : 0
})
const memPct = computed(() => (q.value ? (q.value.gpuMemUsed / q.value.gpuMemTotal) * 100 : 0))
const primaryOf = (bid: string) => allBench.find((b) => b.id === bid)?.metrics.find((m) => m.primary)
</script>

<template>
  <div class="container-page pt-6">
    <!-- 标题行 -->
    <div class="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <h1 class="text-xl font-semibold text-gray-900 dark:text-white">平台总览</h1>
      <p class="text-xs text-gray-500">按「{{ ROLES[state.role].label }}」可见范围统计 · 数据截至 2026-11-19 12:00</p>
    </div>

    <!-- KPI -->
    <section class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5" aria-label="核心指标">
      <RouterLink to="/algorithms" class="card group p-4 hover:border-gray-300 dark:hover:border-gray-700">
        <p class="flex items-center gap-1.5 text-xs text-gray-500"><Box class="size-3.5" />算法</p>
        <p class="mt-1 text-3xl font-semibold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.algorithms.total ?? '–' }}</p>
        <p class="mt-1 text-xs text-gray-500">{{ ov?.algorithms.versions ?? 0 }} 个版本 · {{ ov?.algorithms.readyVersions ?? 0 }} 个可用</p>
      </RouterLink>
      <RouterLink to="/datasets" class="card group p-4 hover:border-gray-300 dark:hover:border-gray-700">
        <p class="flex items-center gap-1.5 text-xs text-gray-500"><Database class="size-3.5" />数据集</p>
        <p class="mt-1 text-3xl font-semibold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.datasets.total ?? '–' }}</p>
        <p class="mt-1 text-xs text-gray-500">{{ fmtNum(ov?.datasets.samples ?? 0) }} 样本 · {{ fmtBytes(ov?.datasets.bytes ?? 0) }}</p>
      </RouterLink>
      <RouterLink to="/benchmarks" class="card group p-4 hover:border-gray-300 dark:hover:border-gray-700">
        <p class="flex items-center gap-1.5 text-xs text-gray-500"><Trophy class="size-3.5" />评测基准</p>
        <p class="mt-1 text-3xl font-semibold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.benchmarks.total ?? '–' }}</p>
        <p class="mt-1 text-xs text-gray-500">{{ ov?.benchmarks.leaderboardEntries ?? 0 }} 条上榜结果</p>
      </RouterLink>
      <RouterLink to="/evals" class="card group p-4 hover:border-gray-300 dark:hover:border-gray-700">
        <p class="flex items-center gap-1.5 text-xs text-gray-500"><FlaskConical class="size-3.5" />评测次数</p>
        <p class="mt-1 text-3xl font-semibold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.evals.total ?? '–' }}</p>
        <p class="mt-1 text-xs text-gray-500">近 7 天 {{ ov?.evals.last7d ?? 0 }} 次 · 成功率 {{ successRate.toFixed(0) }}%</p>
      </RouterLink>
      <RouterLink :to="can.review ? '/admin/reviews' : '/evals'" class="card group col-span-2 p-4 hover:border-gray-300 md:col-span-1 dark:hover:border-gray-700">
        <p class="flex items-center gap-1.5 text-xs text-gray-500"><Cpu class="size-3.5" />进行中</p>
        <p class="mt-1 text-3xl font-semibold tracking-tight text-gray-900 tabular-nums dark:text-white">
          {{ ov?.evals.running ?? '–' }}<span class="ml-1 text-base font-normal text-gray-400">运行</span>
          <span class="ml-2">{{ ov?.evals.queued ?? '–' }}</span><span class="ml-1 text-base font-normal text-gray-400">排队</span>
        </p>
        <p v-if="can.review" class="mt-1 flex items-center gap-1 text-xs text-amber-700 dark:text-amber-400"><ClipboardCheck class="size-3.5" />{{ ov?.pendingReview ?? 0 }} 个厂商提交待审核</p>
        <p v-else class="mt-1 text-xs text-gray-500">GPU 显存占用 {{ memPct.toFixed(0) }}%</p>
      </RouterLink>
    </section>

    <!-- 图表 -->
    <section class="mt-4 grid gap-4 lg:grid-cols-3">
      <div class="card p-5 lg:col-span-2">
        <div class="mb-1 flex items-baseline justify-between">
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">近 30 天评测完成数</h2>
          <RouterLink to="/evals" class="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-white">全部任务 →</RouterLink>
        </div>
        <p class="mb-3 text-xs text-gray-500">按完成日期统计，悬停查看当日明细</p>
        <TrendColumns v-if="ov" :data="ov.trend" />
      </div>
      <div class="card p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white">评测任务状态</h2>
        <p class="mb-4 text-xs text-gray-500">共 {{ ov?.evals.total ?? 0 }} 个任务</p>
        <StatusMix v-if="ov" :counts="ov.evalStatus" />
      </div>
      <div class="card p-5 lg:col-span-2">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white">任务类型分布</h2>
        <p class="mb-3 text-xs text-gray-500">各任务类型下的算法与数据集数量，点击查看对应算法</p>
        <TaskDistribution v-if="ov" :rows="ov.byTask" />
      </div>
      <div class="card p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white">GPU 资源</h2>
        <p class="mb-4 text-xs text-gray-500">{{ q?.gpuName ?? '—' }} · 评测与在线推理共享</p>
        <template v-if="q">
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-semibold text-gray-900 tabular-nums dark:text-white">{{ q.gpuMemUsed.toFixed(1) }}</span>
            <span class="text-sm text-gray-500">/ {{ q.gpuMemTotal }} GB</span>
          </div>
          <div class="mt-2 h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800" role="img" :aria-label="`显存占用 ${memPct.toFixed(0)}%`">
            <div class="h-full rounded-full" style="background: var(--series-1)" :style="{ width: memPct + '%' }" />
          </div>
          <p class="mt-5 mb-2 text-xs text-gray-500">预热中的推理容器</p>
          <div v-for="w in q.warmContainers" :key="w.algorithmId" class="flex items-center gap-2 py-1 text-xs">
            <Flame class="size-3.5 shrink-0 text-orange-500" />
            <RouterLink :to="`/algorithms/${w.algorithmId}`" class="mono truncate hover:underline">{{ w.algorithmId.split('/')[1] }}</RouterLink>
            <span class="ml-auto shrink-0 text-gray-500">{{ w.memGB }} GB</span>
          </div>
        </template>
      </div>
    </section>

    <!-- 资源列表 -->
    <section class="mt-10 grid gap-10 lg:grid-cols-[1fr_380px]">
      <div class="min-w-0 space-y-10">
        <div>
          <div class="mb-3 flex items-center justify-between">
            <h2 class="section-title flex items-center gap-2"><Box class="size-5 text-gray-400" />{{ state.role === 'vendor' ? '我的算法' : '热门算法' }}</h2>
            <RouterLink to="/algorithms" class="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">全部<ArrowRight class="size-3.5" /></RouterLink>
          </div>
          <div class="grid gap-3 xl:grid-cols-2"><AlgoCard v-for="a in algos?.items" :key="a.id" :a="a" /></div>
        </div>
        <div>
          <div class="mb-3 flex items-center justify-between">
            <h2 class="section-title flex items-center gap-2"><Database class="size-5 text-gray-400" />热门数据集</h2>
            <RouterLink to="/datasets" class="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">全部<ArrowRight class="size-3.5" /></RouterLink>
          </div>
          <div class="grid gap-3 xl:grid-cols-2"><DatasetCard v-for="d in dss?.items" :key="d.id" :d="d" /></div>
        </div>
      </div>

      <aside class="space-y-8">
        <div>
          <h2 class="section-title mb-3 flex items-center gap-2"><Trophy class="size-5 text-amber-500" />评测基准</h2>
          <div class="card divide-y divide-gray-100 dark:divide-gray-800">
            <RouterLink v-for="b in benches" :key="b.id" :to="`/benchmarks/${b.id}`" class="flex items-center gap-2 px-3 py-2.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50">
              <TaskIcon :task="b.task" class="size-4 shrink-0" :class="TASKS[b.task].color" />
              <span class="truncate">{{ b.displayName }}</span>
              <ArrowRight class="ml-auto size-3.5 shrink-0 text-gray-300" />
            </RouterLink>
          </div>
        </div>
        <div>
          <h2 class="section-title mb-3 flex items-center gap-2"><FlaskConical class="size-5 text-gray-400" />最近评测</h2>
          <div class="space-y-1">
            <RouterLink v-for="r in runs?.slice(0, 7)" :key="r.id" :to="`/evals/${r.id}`" class="block rounded-lg px-2 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-900">
              <div class="flex items-center gap-2">
                <span class="mono truncate">{{ r.algorithmId.split('/')[1] }}</span>
                <span class="mono text-xs text-gray-400">{{ r.algoVersion }}</span>
                <StatusBadge :status="r.status" kind="eval" class="ml-auto" />
              </div>
              <div class="mt-0.5 flex justify-between text-xs text-gray-500">
                <span class="truncate">{{ allBench.find((b) => b.id === r.benchmarkId)?.displayName }}</span>
                <span v-if="r.status === 'succeeded' && primaryOf(r.benchmarkId)" class="mono shrink-0">{{ primaryOf(r.benchmarkId)!.label }} {{ fmtMetric(r.metrics[primaryOf(r.benchmarkId)!.key], primaryOf(r.benchmarkId)!.unit) }}</span>
                <span v-else class="shrink-0">{{ timeAgo(r.submittedAt) }}</span>
              </div>
            </RouterLink>
          </div>
        </div>
      </aside>
    </section>
  </div>
</template>
