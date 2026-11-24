<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, Box, ClipboardCheck, Cpu, Database, FlaskConical, MapPin, Send, Sparkles, Trophy } from 'lucide-vue-next'
import { getQueueStatus, listAlgorithms, listBenchmarks, listDatasets, listEvals, overview } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { BUSINESS_CATEGORIES, ROLES, TASKS } from '@/utils/meta'
import { fmtBytes, fmtDate, fmtMetric, fmtNum, timeAgo } from '@/utils/format'
import { algoName } from '@/utils/display'
import { benchmarks as allBench } from '@/mock/benchmarks'
import AlgoCard from '@/components/algo/AlgoCard.vue'
import DatasetCard from '@/components/dataset/DatasetCard.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TaskIcon from '@/components/ui/TaskIcon.vue'
import DonutChart, { type DonutSlice } from '@/components/overview/DonutChart.vue'

const { state, can } = useSession()
const { data: ov } = useAsync(() => overview())
const { data: q } = useAsync(() => getQueueStatus())
const { data: allAlgos } = useAsync(() => listAlgorithms({ pageSize: 200 }))
const algos = computed(() => (allAlgos.value ? { ...allAlgos.value, items: allAlgos.value.items.slice(0, 6) } : null))
const { data: allDss } = useAsync(() => listDatasets({ pageSize: 50 }))
const dss = computed(() => (allDss.value ? { ...allDss.value, items: allDss.value.items.slice(0, 4) } : null))
const { data: benches } = useAsync(() => listBenchmarks())
const { data: runs } = useAsync(() => listEvals())

const successRate = computed(() => {
  const s = ov.value?.evalStatus
  if (!s) return 0
  const done = s.succeeded + s.failed
  return done ? (s.succeeded / done) * 100 : 0
})
const primaryOf = (bid: string) => (benches.value ?? allBench).find((b) => b.id === bid)?.metrics.find((m) => m.primary)

function fmtValWithUnit(v: number | undefined, unit?: string) {
  const s = fmtMetric(v, unit)
  if (s === '—' || !unit) return s
  return unit === '%' ? `${s}%` : `${s} ${unit}`
}

const TASK_COLORS: Record<string, [string, string]> = {
  'image-classification': ['#3b82f6', '#6366f1'],
  'image-dehazing': ['#06b6d4', '#0ea5e9'],
  ocr: ['#8b5cf6', '#a855f7'],
  'object-detection': ['#f59e0b', '#f97316'],
  'semantic-segmentation': ['#10b981', '#14b8a6'],
  'instance-segmentation': ['#14b8a6', '#06b6d4'],
  'keypoint-detection': ['#f43f5e', '#ec4899'],
  'power-forecast': ['#6366f1', '#8b5cf6'],
  'server-fault-0x07': ['#ef4444', '#f97316'],
  'signal-processing': ['#f97316', '#f59e0b'],
  optimization: ['#84cc16', '#22c55e'],
  custom: ['#64748b', '#94a3b8'],
}

const taskDonutSlices = computed<DonutSlice[]>(() =>
  (ov.value?.byTask ?? []).map((r) => {
    const [c1, c2] = TASK_COLORS[r.task] ?? ['#64748b', '#94a3b8']
    return {
      key: r.task,
      label: TASKS[r.task].label,
      value: r.algorithms,
      color: c1,
      colorEnd: c2,
      to: `/algorithms?task=${r.task}`,
    }
  }),
)

const datasetSummaryRows = computed(() =>
  (allDss.value?.items ?? []).slice(0, 5).map((d) => {
    const tr = d.train.versions[0]
    const te = d.test?.versions[0]
    const brief = d.summary.split(/[（(，,。]/)[0].trim() || d.summary
    return {
      ds: d,
      brief,
      trainFiles: tr?.files ?? 0,
      testFiles: te?.files ?? 0,
      hasTest: !!te,
      totalBytes: (tr?.sizeBytes ?? 0) + (te?.sizeBytes ?? 0),
    }
  }),
)

/** 每个评测基准的当前 SOTA 冠亚军 + 主/副指标（直接构建双行迷你榜单） */
const benchLeaders = computed(() => {
  const blist = benches.value ?? []
  const rlist = runs.value ?? []
  return blist
    .map((b) => {
      const primary = b.metrics.find((m) => m.primary)
      if (!primary) return null
      const secondary = b.metrics.find((m) => !m.primary)
      const valid = rlist.filter((r) => r.benchmarkId === b.id && r.status === 'succeeded' && r.isLatestValid && r.metrics[primary.key] !== undefined)
      if (!valid.length) return null
      valid.sort((x, y) => (primary.higherIsBetter ? 1 : -1) * ((y.metrics[primary.key] ?? 0) - (x.metrics[primary.key] ?? 0)))
      const top2 = valid.slice(0, 2)
      const secShortLabel = secondary ? secondary.label.replace(/^Macro\s+/i, '') : ''
      return { bench: b, primary, secondary, secShortLabel, top2, entries: valid.length }
    })
    .filter((x): x is NonNullable<typeof x> => !!x)
    .slice(0, 3)
})

const BIZ_BAR_COLORS: [string, string][] = [
  ['#10b981', '#14b8a6'],
  ['#3b82f6', '#6366f1'],
  ['#f59e0b', '#f97316'],
  ['#8b5cf6', '#a855f7'],
  ['#06b6d4', '#0ea5e9'],
  ['#64748b', '#94a3b8'],
]
const businessDonutSlices = computed<DonutSlice[]>(() => {
  const items = allAlgos.value?.items ?? []
  const counts = new Map<string, number>()
  for (const a of items) counts.set(a.business, (counts.get(a.business) ?? 0) + 1)
  return [...counts.entries()]
    .sort((a, b) => {
      if (b[1] !== a[1]) return b[1] - a[1]
      if (a[0] === 'other') return 1
      if (b[0] === 'other') return -1
      return a[0].localeCompare(b[0])
    })
    .map(([k, count], i) => {
      const [c1, c2] = BIZ_BAR_COLORS[i % BIZ_BAR_COLORS.length]
      return {
        key: k,
        label: BUSINESS_CATEGORIES[k as keyof typeof BUSINESS_CATEGORIES]?.label ?? k,
        value: count,
        color: c1,
        colorEnd: c2,
        to: `/algorithms?business=${k}`,
      }
    })
})
</script>

<template>
  <div class="container-page pt-5">
    <!-- 标题行 + 硬件与待审状态 -->
    <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
      <div class="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
        <h1 class="text-lg font-semibold text-gray-900 dark:text-white">平台总览</h1>
        <p class="text-xs text-gray-500">「{{ ROLES[state.role].label }}」可见范围 · 截至 {{ fmtDate(new Date().toISOString()) }}</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500">
        <span v-if="q" class="inline-flex items-center gap-1.5 rounded-full border border-gray-200/80 bg-white px-2.5 py-0.5 shadow-2xs dark:border-gray-800 dark:bg-gray-900">
          <Cpu class="size-3.5 text-brand-600 dark:text-brand-400" />
          <span>{{ q.gpuName }}</span>
          <span class="mono text-gray-700 dark:text-gray-300">{{ q.gpuMemUsed.toFixed(1) }}/{{ q.gpuMemTotal }}GB</span>
          <span class="text-gray-300 dark:text-gray-700">|</span>
          <span>{{ ov?.evals.running ?? 0 }} 运行 · {{ ov?.evals.queued ?? 0 }} 排队</span>
        </span>
        <span
          v-if="state.role === 'regional'"
          class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 font-medium text-emerald-700 shadow-2xs dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300"
        >
          <MapPin class="size-3.5" />{{ state.region }}区域
        </span>
        <RouterLink
          v-if="can.review && (ov?.pendingTrialRequests ?? 0) > 0"
          to="/admin/dispatches"
          class="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2.5 py-0.5 font-medium text-sky-700 shadow-2xs hover:bg-sky-100 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300"
        >
          <Send class="size-3.5" />{{ ov?.pendingTrialRequests }} 待下发审批
        </RouterLink>
        <RouterLink
          v-if="can.review && (ov?.pendingReview ?? 0) > 0"
          to="/admin/reviews"
          class="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 font-medium text-amber-700 shadow-2xs hover:bg-amber-100 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300"
        >
          <ClipboardCheck class="size-3.5" />{{ ov?.pendingReview }} 待审核
        </RouterLink>
      </div>
    </div>

    <!-- 带柔光图标徽章的紧凑 KPI 卡片条 -->
    <section class="grid grid-cols-2 gap-2.5 lg:grid-cols-4" aria-label="核心指标">
      <RouterLink to="/algorithms" class="card group flex items-center gap-3 px-3.5 py-2.5 shadow-xs transition hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-sm dark:hover:border-brand-800">
        <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600 ring-1 ring-brand-100 dark:bg-brand-950/60 dark:text-brand-400 dark:ring-brand-900">
          <Box class="size-4" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs text-gray-500">算法</span>
            <span class="mono text-[11px] text-gray-400">
              <span class="font-medium text-brand-600 dark:text-brand-400">自研 {{ ov?.algorithms.selfDeveloped ?? 0 }}</span> · {{ ov?.algorithms.readyVersions ?? 0 }}/{{ ov?.algorithms.versions ?? 0 }} 可用
            </span>
          </div>
          <p class="text-xl leading-tight font-bold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.algorithms.total ?? '–' }}</p>
        </div>
      </RouterLink>

      <RouterLink to="/datasets" class="card group flex items-center gap-3 px-3.5 py-2.5 shadow-xs transition hover:-translate-y-0.5 hover:border-sky-200 hover:shadow-sm dark:hover:border-sky-800">
        <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-sky-50 text-sky-600 ring-1 ring-sky-100 dark:bg-sky-950/60 dark:text-sky-400 dark:ring-sky-900">
          <Database class="size-4" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs text-gray-500">数据集</span>
            <span class="mono text-[11px] text-gray-400">{{ fmtNum(ov?.datasets.samples ?? 0) }} · {{ fmtBytes(ov?.datasets.bytes ?? 0) }}</span>
          </div>
          <p class="text-xl leading-tight font-bold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.datasets.total ?? '–' }}</p>
        </div>
      </RouterLink>

      <RouterLink to="/benchmarks" class="card group flex items-center gap-3 px-3.5 py-2.5 shadow-xs transition hover:-translate-y-0.5 hover:border-amber-200 hover:shadow-sm dark:hover:border-amber-800">
        <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-amber-50 text-amber-600 ring-1 ring-amber-100 dark:bg-amber-950/60 dark:text-amber-400 dark:ring-amber-900">
          <Trophy class="size-4" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs text-gray-500">评测基准</span>
            <span class="mono text-[11px] text-gray-400">{{ ov?.benchmarks.leaderboardEntries ?? 0 }} 条上榜</span>
          </div>
          <p class="text-xl leading-tight font-bold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.benchmarks.total ?? '–' }}</p>
        </div>
      </RouterLink>

      <RouterLink to="/evals" class="card group flex items-center gap-3 px-3.5 py-2.5 shadow-xs transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-sm dark:hover:border-emerald-800">
        <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100 dark:bg-emerald-950/60 dark:text-emerald-400 dark:ring-emerald-900">
          <FlaskConical class="size-4" />
        </span>
        <div class="min-w-0 flex-1">
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs text-gray-500">评测次数</span>
            <span class="mono text-[11px] font-medium text-emerald-600 dark:text-emerald-400">{{ successRate.toFixed(0) }}% 成功 · 7d {{ ov?.evals.last7d ?? 0 }}</span>
          </div>
          <p class="text-xl leading-tight font-bold tracking-tight text-gray-900 tabular-nums dark:text-white">{{ ov?.evals.total ?? '–' }}</p>
        </div>
      </RouterLink>
    </section>

    <!-- 2×2 对称高密度核心看板：左列双环图（算法总览 + 业务场景） | 右列双榜单（SOTA 榜首 + 数据集一览） -->
    <section class="mt-3 grid gap-3 lg:grid-cols-12">
      <!-- 左上：算法总览（按任务类型分布） -->
      <div class="card flex flex-col p-4 shadow-xs lg:col-span-5">
        <div class="mb-2 flex items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <h2 class="text-xs font-semibold text-gray-900 dark:text-white">算法总览</h2>
            <RouterLink
              to="/algorithms?selfDeveloped=only"
              class="inline-flex items-center gap-0.5 rounded-full border border-brand-200 bg-brand-50 px-2 py-0.2 text-[10px] font-semibold text-brand-700 transition hover:bg-brand-100 dark:border-brand-800 dark:bg-brand-950/60 dark:text-brand-300 dark:hover:bg-brand-900/60"
            >
              <Sparkles class="size-2.5" />自研 {{ ov?.algorithms.selfDeveloped ?? 0 }}
            </RouterLink>
          </div>
          <span class="mono text-[11px] text-gray-400">{{ ov?.algorithms.readyVersions ?? 0 }}/{{ ov?.algorithms.versions ?? 0 }} 可用 · 点击筛选</span>
        </div>
        <div class="flex flex-1 items-center py-1">
          <DonutChart v-if="taskDonutSlices.length" :slices="taskDonutSlices" :size="124" :thickness="17" center-label="算法总数" />
        </div>
      </div>

      <!-- 右上：各基准 SOTA 榜首速览（双行迷你榜单：清晰对比 Top 1 / Top 2） -->
      <div class="card flex flex-col justify-between p-4 shadow-xs lg:col-span-7">
        <div class="mb-2 flex items-baseline justify-between">
          <h2 class="text-xs font-semibold text-gray-900 dark:text-white">各基准 SOTA 榜首速览</h2>
          <RouterLink to="/benchmarks" class="text-[11px] text-gray-500 hover:text-gray-900 dark:hover:text-white">全部榜单 →</RouterLink>
        </div>
        <div v-if="benchLeaders.length" class="space-y-2">
          <div
            v-for="item in benchLeaders"
            :key="item.bench.id"
            class="overflow-hidden rounded-lg border border-gray-100 bg-gray-50/50 transition hover:border-gray-200 dark:border-gray-800 dark:bg-gray-800/30 dark:hover:border-gray-700"
          >
            <!-- 基准标题条 -->
            <RouterLink
              :to="`/benchmarks/${item.bench.id}`"
              class="flex items-center justify-between gap-2 border-b border-gray-100/90 bg-white/80 px-2.5 py-1.5 text-xs hover:text-brand-600 dark:border-gray-800 dark:bg-gray-900/60 dark:hover:text-brand-400"
            >
              <span class="flex min-w-0 items-center gap-1.5 font-semibold text-gray-900 dark:text-white">
                <TaskIcon :task="item.bench.task" class="size-3.5 shrink-0" :class="TASKS[item.bench.task].color" />
                <span class="truncate">{{ item.bench.displayName }}</span>
              </span>
              <span class="shrink-0 text-[10px] text-gray-400">{{ item.entries }} 项上榜 · 主指标 {{ item.primary.label }}</span>
            </RouterLink>

            <!-- Top 1 / Top 2 紧凑表行 -->
            <div class="divide-y divide-gray-100/80 dark:divide-gray-800/70">
              <RouterLink
                v-for="(run, idx) in item.top2"
                :key="run.id"
                :to="`/evals/${run.id}`"
                class="flex items-center justify-between gap-2 px-2.5 py-1.5 text-[11px] transition hover:bg-white dark:hover:bg-gray-800/60"
              >
                <span class="flex min-w-0 items-center gap-1.5">
                  <span
                    class="inline-flex size-4 shrink-0 items-center justify-center rounded text-[10px] font-bold"
                    :class="
                      idx === 0
                        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/60 dark:text-amber-300'
                        : 'bg-gray-200/80 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
                    "
                  >{{ idx + 1 }}</span>
                  <span class="truncate" :class="idx === 0 ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300'">
                    {{ algoName(run.algorithmId) }}
                  </span>
                  <span class="mono shrink-0 text-[10px] text-gray-400">{{ run.algoVersion }}</span>
                </span>
                <span class="flex shrink-0 items-center gap-2">
                  <span class="mono hidden text-[10px] text-gray-400 sm:inline">
                    <template v-if="item.secondary && run.metrics[item.secondary.key] !== undefined">
                      {{ item.secShortLabel }} {{ fmtValWithUnit(run.metrics[item.secondary.key], item.secondary.unit) }}
                    </template>
                    <template v-if="run.latencyMs !== undefined"> · {{ run.latencyMs }}ms</template>
                  </span>
                  <span
                    class="mono w-[74px] rounded px-1.5 py-0.5 text-right text-[11px] tabular-nums"
                    :class="
                      idx === 0
                        ? 'bg-emerald-50 font-semibold text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300'
                        : 'text-gray-500 dark:text-gray-400'
                    "
                  >
                    {{ fmtValWithUnit(run.metrics[item.primary.key], item.primary.unit) }}
                  </span>
                </span>
              </RouterLink>
            </div>
          </div>
        </div>
        <p v-else class="py-4 text-center text-xs text-gray-400">暂无已完成的基准评测结果</p>
      </div>

      <!-- 左下：业务场景分布 -->
      <div class="card flex flex-col p-4 shadow-xs lg:col-span-5">
        <div class="mb-2 flex items-baseline justify-between">
          <h2 class="text-xs font-semibold text-gray-900 dark:text-white">业务场景分布</h2>
          <span class="mono text-[11px] text-gray-400">{{ allAlgos?.items.length ?? 0 }} 算法 · 点击筛选</span>
        </div>
        <div class="flex flex-1 items-center py-1">
          <DonutChart v-if="businessDonutSlices.length" :slices="businessDonutSlices" :size="124" :thickness="17" center-label="业务" />
        </div>
      </div>

      <!-- 右下：数据集一览（专门展示平台已有数据集清单与规模） -->
      <div class="card flex flex-col justify-between p-4 shadow-xs lg:col-span-7">
        <div class="mb-2 flex items-baseline justify-between">
          <div class="flex items-baseline gap-2">
            <h2 class="text-xs font-semibold text-gray-900 dark:text-white">数据集一览</h2>
            <span class="mono text-[11px] text-gray-400">共 {{ allDss?.items.length ?? 0 }} 个 · {{ fmtNum(ov?.datasets.samples ?? 0) }} 样本 · {{ fmtBytes(ov?.datasets.bytes ?? 0) }}</span>
          </div>
          <RouterLink to="/datasets" class="text-[11px] text-gray-500 hover:text-gray-900 dark:hover:text-white">全部数据集 →</RouterLink>
        </div>

        <div v-if="datasetSummaryRows.length" class="flex-1 divide-y divide-gray-100 overflow-hidden rounded-lg border border-gray-100 dark:divide-gray-800 dark:border-gray-800">
          <RouterLink
            v-for="row in datasetSummaryRows"
            :key="row.ds.id"
            :to="`/datasets/${row.ds.id}`"
            class="flex flex-wrap items-center justify-between gap-2 bg-gray-50/40 px-3 py-2.5 text-xs transition hover:bg-white dark:bg-gray-800/20 dark:hover:bg-gray-800/60"
          >
            <div class="flex min-w-0 flex-1 items-center gap-2.5">
              <span class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-sky-50 text-sky-600 ring-1 ring-sky-100 dark:bg-sky-950/60 dark:text-sky-400 dark:ring-sky-900">
                <TaskIcon :task="row.ds.task" class="size-3.5" />
              </span>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <span class="mono truncate font-semibold text-gray-900 dark:text-white">{{ row.ds.id }}</span>
                  <span class="shrink-0 rounded bg-gray-100 px-1.5 py-0.2 text-[10px] text-gray-600 dark:bg-gray-800 dark:text-gray-300">{{ TASKS[row.ds.task].label }}</span>
                </div>
                <p class="mt-0.5 truncate text-[11px] text-gray-500">
                  {{ row.brief }}<template v-if="row.ds.classes.length"> · {{ row.ds.classes.slice(0, 4).join(' / ') }}</template>
                </p>
              </div>
            </div>
            <div class="mono flex shrink-0 items-center gap-2 text-[11px]">
              <span class="rounded bg-white px-1.5 py-0.5 text-gray-600 ring-1 ring-gray-200/80 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-700">
                train {{ fmtNum(row.trainFiles) }}
              </span>
              <span
                class="rounded px-1.5 py-0.5 ring-1"
                :class="
                  row.hasTest
                    ? 'bg-emerald-50 text-emerald-700 ring-emerald-200/70 dark:bg-emerald-950/50 dark:text-emerald-300 dark:ring-emerald-900'
                    : 'bg-amber-50 text-amber-700 ring-amber-200/70 dark:bg-amber-950/50 dark:text-amber-300 dark:ring-amber-900'
                "
              >
                {{ row.hasTest ? `test ${fmtNum(row.testFiles)}` : '无 test' }}
              </span>
              <span class="w-14 text-right text-[10px] text-gray-400">{{ fmtBytes(row.totalBytes) }}</span>
            </div>
          </RouterLink>
        </div>
        <p v-else class="py-6 text-center text-xs text-gray-400">暂无数据集</p>
      </div>
    </section>

    <!-- 资源列表 -->
    <section class="mt-8 grid gap-10 lg:grid-cols-[1fr_380px]">
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
                <span class="truncate">{{ algoName(r.algorithmId) }}</span>
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
