<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Ban, CircleAlert, Clock, Cpu, FileJson, FlaskConical, Gauge, RotateCw, ScrollText } from 'lucide-vue-next'
import { cancelEval, createEval, getBenchmark, getEval, ApiError } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { fmtDate, fmtDuration, fmtMetric, hashStr } from '@/utils/format'
import { algoFullLabel } from '@/utils/display'
import { isImageTask, latencyLabel } from '@/utils/meta'
import { datasets } from '@/mock/datasets'
import StateView from '@/components/ui/StateView.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import HashText from '@/components/ui/HashText.vue'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import SynthImage from '@/components/ui/SynthImage.vue'
import SfEvalViz from '@/components/serverfault/SfEvalViz.vue'
import PfEvalViz from '@/components/powerforecast/PfEvalViz.vue'
import { useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const { can, user } = useSession()
const { data: run, loading, error, reload } = useAsync(() => getEval(route.params.id as string))
// 真实评测任务运行中静默轮询进度与日志（不触发 loading 闪烁）
let pollTimer: ReturnType<typeof setInterval> | undefined
let polling = false
watch(
  () => run.value?.status,
  (st) => {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = undefined
    }
    if (st === 'queued' || st === 'running') {
      pollTimer = setInterval(async () => {
        if (polling) return
        polling = true
        try {
          run.value = await getEval(route.params.id as string)
        } catch {
          /* ignore transient poll error */
        } finally {
          polling = false
        }
      }, 1200)
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => pollTimer && clearInterval(pollTimer))
const benchId = computed(() => run.value?.benchmarkId ?? '')
const { data: bench } = useAsync(async () => (benchId.value ? getBenchmark(benchId.value) : undefined), [benchId])
const ds = computed(() => datasets.find((d) => d.id === bench.value?.datasetId))
const primary = computed(() => bench.value?.metrics.find((m) => m.primary))
const task = computed(() => bench.value?.task ?? ds.value?.task)

/** 下载本次评测结果（指标、分类别结果、参数、日志与可视化数据）为 JSON */
function downloadResult() {
  if (!run.value) return
  const blob = new Blob([JSON.stringify(run.value, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${run.value.id}.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 1000)
}

// 指标卡片自适应列数：1~7 个指标在桌面端单行铺满，8 个指标 4×2 对称排布，避免第二行落单
const metricsGridClass = computed(() => {
  const n = bench.value?.metrics.length ?? 0
  if (n <= 2) return 'grid-cols-2'
  if (n === 3) return 'grid-cols-2 sm:grid-cols-3'
  if (n === 4) return 'grid-cols-2 lg:grid-cols-4'
  if (n === 5) return 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5'
  if (n === 6) return 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6'
  if (n === 7) return 'grid-cols-2 sm:grid-cols-4 lg:grid-cols-7'
  if (n === 8) return 'grid-cols-2 sm:grid-cols-4'
  return 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5'
})

const canCancel = computed(() => run.value && (run.value.status === 'queued' || run.value.status === 'running') && (can.value.admin || run.value.submittedBy === user.value.username))

// 每类指标：优先展示真实评测返回的 perClass，否则按基准降级
const perClass = computed(() => {
  if (!run.value || run.value.status !== 'succeeded') return []
  if (run.value.perClass?.length) {
    return [...run.value.perClass]
      .map((c) => {
        const raw = c as unknown as Record<string, unknown>
        const label = String(raw.label ?? raw.name ?? '类别')
        const v = Number(raw.value ?? raw.accuracy_rate ?? 0)
        return { label, v: Number.isFinite(v) ? v : 0 }
      })
      .sort((a, b) => a.v - b.v)
  }
  if (!ds.value || !primary.value) return []
  const base = run.value.metrics[primary.value.key]
  return ds.value.classes
    .filter((c) => !c.startsWith('……'))
    .slice(0, 10)
    .map((c) => {
      const h = hashStr(c + run.value!.id)
      return { label: c, v: Math.max(0, Math.min(100, base + ((h % 200) - 100) / 8)) }
    })
    .sort((a, b) => a.v - b.v)
})
const errTypes = ['漏检', '误检', '定位偏差', '类别混淆']

async function cancel() {
  await cancelEval(run.value!.id)
  toast('任务已取消', 'info')
  reload()
}
async function rerun() {
  try {
    const r = await createEval({ algorithmId: run.value!.algorithmId, algoVersion: run.value!.algoVersion, benchmarkId: run.value!.benchmarkId, params: run.value!.params })
    toast(`已按相同配置重新提交：${r.id}`)
    router.push(`/evals/${r.id}`)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '提交失败', 'error')
  }
}
</script>

<template>
  <StateView :loading="loading && !run" :error="error">
    <div v-if="run" class="container-page pt-8">
      <div class="flex flex-wrap items-start gap-4">
        <div class="min-w-0 flex-1">
          <p class="flex items-center gap-1.5 text-sm text-gray-500"><FlaskConical class="size-4" />评测任务 <span class="mono">{{ run.id }}</span></p>
          <h1 class="mt-1 flex flex-wrap items-center gap-2 text-xl font-semibold text-gray-900 dark:text-white">
            <OrgAvatar :org="run.algorithmId.split('/')[0]" :size="22" />
            <RouterLink :to="`/algorithms/${run.algorithmId}`" class="hover:text-brand-600">{{ algoFullLabel(run.algorithmId) }}</RouterLink>
            <span class="mono text-gray-400">{{ run.algoVersion }}</span>
            <span class="text-gray-300">×</span>
            <RouterLink :to="`/benchmarks/${run.benchmarkId}`" class="hover:text-brand-600">{{ bench?.displayName ?? run.benchmarkId }}</RouterLink>
          </h1>
          <div class="mt-2 flex flex-wrap items-center gap-3 text-sm text-gray-500">
            <StatusBadge :status="run.status" kind="eval" />
            <span v-if="run.status === 'succeeded'" class="text-xs" :class="run.isLatestValid ? 'text-emerald-600' : 'text-gray-400'">{{ run.isLatestValid ? '✓ 当前上榜结果' : '已被同版本更新的结果覆盖' }}</span>
            <span>由 {{ run.submittedBy }} 提交于 {{ fmtDate(run.submittedAt) }}</span>
          </div>
        </div>
        <div class="flex gap-2">
          <button v-if="canCancel" class="btn-danger" @click="cancel"><Ban class="size-4" />取消任务</button>
          <button v-if="can.runEval && (run.status === 'succeeded' || run.status === 'failed' || run.status === 'canceled')" class="btn-default" @click="rerun"><RotateCw class="size-4" />按相同配置重跑</button>
        </div>
      </div>

      <!-- 进度 -->
      <div v-if="run.status === 'running' || run.status === 'queued'" class="card mt-6 p-4">
        <div class="mb-2 flex justify-between text-sm">
          <span>{{ run.status === 'queued' ? '等待 GPU 资源…' : '推理中' }}</span><span class="mono">{{ run.progress }}%</span>
        </div>
        <div class="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          <div class="h-full rounded-full bg-sky-500 transition-all" :class="{ 'animate-pulse': run.status === 'queued' }" :style="{ width: Math.max(run.progress, 2) + '%' }" />
        </div>
      </div>
      <div v-if="run.error" class="mt-6 flex gap-2 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300">
        <CircleAlert class="size-5 shrink-0" />
        <div><p class="font-medium">任务失败</p><p class="mt-0.5">{{ run.error }}</p></div>
      </div>

      <!-- 指标 -->
      <div v-if="bench && run.status === 'succeeded'" class="mt-6 grid gap-3" :class="metricsGridClass">
        <div
          v-for="m in bench.metrics"
          :key="m.key"
          class="card flex flex-col justify-between p-3.5 sm:p-4"
          :class="m.primary ? 'border-amber-300 bg-amber-50/30 dark:border-amber-800 dark:bg-amber-950/15' : ''"
        >
          <div class="flex items-start justify-between gap-1.5">
            <p class="text-xs leading-snug text-gray-500">{{ m.label }}</p>
            <span
              v-if="m.primary"
              class="shrink-0 rounded bg-amber-100/80 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300"
            >
              主指标
            </span>
          </div>
          <p class="mt-2 text-2xl font-semibold tracking-tight tabular-nums text-gray-900 dark:text-white">
            {{ fmtMetric(run.metrics[m.key], m.unit) }}<span class="ml-0.5 text-sm font-normal text-gray-400">{{ m.unit }}</span>
          </p>
        </div>
      </div>

      <!-- 服务器故障检测标准：统一评测器折线图（测试集样本曲线仅管理员可见） -->
      <SfEvalViz v-if="run.status === 'succeeded' && run.vizServerFault" class="mt-6" :viz="run.vizServerFault" :show-cases="can.testAccess" />
      <!-- 新能源功率预测标准：5 维折线图可视化（测试集单样本曲线仅管理员可见） -->
      <PfEvalViz v-if="run.status === 'succeeded' && run.vizPowerForecast" class="mt-6" :viz="run.vizPowerForecast" :show-cases="can.testAccess" />

      <div class="mt-6 grid gap-6 lg:grid-cols-[1fr_380px]">
        <div class="min-w-0 space-y-6">
          <!-- 每类指标 -->
          <div v-if="perClass.length" class="card p-5">
            <h2 class="section-title mb-1">{{ run.perClassLabel ?? `各类别 ${primary?.label ?? ''}` }}</h2>
            <p class="mb-4 text-xs text-gray-500">按得分升序，便于定位薄弱类别</p>
            <div class="space-y-2">
              <div v-for="c in perClass" :key="c.label" class="flex items-center gap-3 text-sm">
                <span class="w-28 shrink-0 truncate">{{ c.label }}</span>
                <div class="h-3 flex-1 overflow-hidden rounded-r bg-gray-100 dark:bg-gray-800">
                  <div class="h-full rounded-r-[4px]" style="background: var(--series-1)" :style="{ width: c.v + '%' }" />
                </div>
                <span class="mono w-12 text-right text-xs text-gray-600 dark:text-gray-400">{{ c.v.toFixed(1) }}</span>
              </div>
            </div>
          </div>

          <!-- 错误样例 -->
          <div v-if="can.testAccess && ds && run.status === 'succeeded' && isImageTask(task)" class="card p-5">
            <h2 class="section-title mb-1">错误样例</h2>
            <p class="mb-4 text-xs text-gray-500">
              来自测试集，仅管理员可见<template v-if="run.errorSamples">（展示 {{ run.errorSamples.length }} 个真实误判样本）</template>
            </p>
            <template v-if="run.errorSamples">
              <p v-if="!run.errorSamples.length" class="text-sm text-emerald-600">测试集全部预测正确，无错误样例。</p>
              <div v-else class="grid grid-cols-2 gap-2.5 md:grid-cols-4">
                <div v-for="item in run.errorSamples" :key="item.fileName" class="overflow-hidden rounded-lg border border-gray-100 dark:border-gray-800">
                  <div class="relative bg-gray-100 dark:bg-gray-900">
                    <img :src="item.url" :alt="item.fileName" class="block aspect-[4/3] w-full object-cover" loading="lazy" />
                    <span class="pointer-events-none absolute top-1.5 left-1.5 rounded bg-gray-900/75 px-1.5 py-0.5 text-[11px] font-medium text-white">
                      真值：{{ item.groundTruth }}
                    </span>
                  </div>
                  <div class="space-y-0.5 px-2 py-1.5 text-[11px]">
                    <div class="mono truncate text-gray-500" :title="item.fileName">{{ item.fileName.replace('images/', '') }}</div>
                    <div class="flex items-center justify-between gap-1">
                      <span class="rounded bg-rose-100 px-1.5 py-0.5 font-medium text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                        误判为 {{ item.predicted }}
                      </span>
                      <span class="mono text-gray-400">{{ (item.confidence * 100).toFixed(1) }}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <div v-else class="grid grid-cols-2 gap-2 md:grid-cols-4">
              <div v-for="i in 8" :key="i" class="overflow-hidden rounded-lg border border-gray-100 dark:border-gray-800">
                <SynthImage :seed="ds.previewSeed + 90000 + i * 13" :task="ds.task" :classes="ds.classes" annotate :width="240" :height="180" />
                <div class="flex items-center justify-between px-2 py-1 text-[11px]">
                  <span class="mono text-gray-500">test/{{ String(90000 + i * 13).padStart(6, '0') }}</span>
                  <span class="rounded bg-rose-100 px-1 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">{{ errTypes[(i + run.id.length) % 4] }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 日志 -->
          <div class="card p-5">
            <h2 class="section-title mb-3 flex items-center gap-2"><ScrollText class="size-4" />运行日志</h2>
            <pre class="scroll-thin max-h-72 overflow-auto rounded-lg bg-gray-900 p-3 text-xs leading-relaxed text-gray-100"><span v-for="(l, i) in run.logs" :key="i" class="block" :class="/error|失败|out of memory/i.test(l) ? 'text-rose-400' : l.startsWith('[evaluator]') ? 'text-emerald-300' : ''">{{ l }}</span></pre>
          </div>
        </div>

        <!-- 复现信息 -->
        <aside class="space-y-6">
          <div class="card p-5">
            <h2 class="section-title mb-3">复现信息</h2>
            <dl class="space-y-2.5 text-sm">
              <div><dt class="text-xs text-gray-500">镜像 digest</dt><dd><HashText :value="run.imageDigest ?? ''" :short="30" /></dd></div>
              <div><dt class="text-xs text-gray-500">权重哈希</dt><dd><HashText :value="run.weightsHash ?? ''" :short="30" /></dd></div>
              <div><dt class="text-xs text-gray-500">评测基准</dt><dd class="mono">{{ run.benchmarkId }}</dd></div>
              <div v-if="bench"><dt class="text-xs text-gray-500">测试集版本</dt><dd class="mono">{{ bench.datasetId }} · test@{{ bench.datasetVersion }}</dd></div>
              <div><dt class="text-xs text-gray-500">评测器版本</dt><dd class="mono">{{ bench?.evaluator }}@{{ run.evaluatorVersion }}</dd></div>
              <div><dt class="text-xs text-gray-500">硬件</dt><dd class="flex items-start gap-1"><Cpu class="mt-0.5 size-3.5 shrink-0 text-gray-400" />{{ run.hardware }}</dd></div>
            </dl>
          </div>
          <div class="card p-5">
            <h2 class="section-title mb-3 flex items-center gap-2"><FileJson class="size-4" />运行参数</h2>
            <pre class="rounded-lg bg-gray-50 p-3 text-xs dark:bg-gray-800/60">{{ JSON.stringify(run.params, null, 2) }}</pre>
          </div>
          <div class="card space-y-2 p-5 text-sm">
            <div class="flex justify-between"><span class="flex items-center gap-1 text-gray-500"><Clock class="size-3.5" />总耗时</span><span>{{ fmtDuration(run.durationSec) }}</span></div>
            <div class="flex justify-between"><span class="flex items-center gap-1 text-gray-500"><Gauge class="size-3.5" />{{ latencyLabel(task) }}</span><span>{{ run.latencyMs != null ? run.latencyMs + ' ms' : '—' }}</span></div>
            <div class="flex justify-between"><span class="flex items-center gap-1 text-gray-500"><Cpu class="size-3.5" />峰值显存</span><span :title="run.peakGpuMemGB == null ? '纯 CPU 运行或未测量' : undefined">{{ run.peakGpuMemGB != null ? run.peakGpuMemGB + ' GB' : run.hardware?.startsWith('CPU') ? '—（CPU 运行）' : '—' }}</span></div>
            <div class="flex justify-between"><span class="text-gray-500">开始</span><span>{{ run.startedAt ? fmtDate(run.startedAt) : '—' }}</span></div>
            <div class="flex justify-between"><span class="text-gray-500">结束</span><span>{{ run.finishedAt ? fmtDate(run.finishedAt) : '—' }}</span></div>
            <button v-if="run.status === 'succeeded' && can.runEval" class="btn-default mt-2 w-full" @click="downloadResult"><FileJson class="size-4" />下载评测结果 JSON</button>
          </div>
        </aside>
      </div>
    </div>
  </StateView>
</template>
