<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, ArrowUp, Cpu, Database, FlaskConical, Lock, Pencil, Save, Scale, Trophy, X, Table2, ChartScatter } from 'lucide-vue-next'
import { ApiError, getBenchmark, getEvaluator, getLeaderboard, listEvals, updateEvaluator } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { fmtDate, fmtMetric, timeAgo } from '@/utils/format'
import { algoFullLabel, algoName, orgLabel } from '@/utils/display'
import type { EvaluatorParamDef } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import EditBenchmarkModal from '@/components/admin/EditBenchmarkModal.vue'
import TaskBadge from '@/components/ui/TaskBadge.vue'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import EvalTable from '@/components/benchmark/EvalTable.vue'
import TradeoffScatter from '@/components/benchmark/TradeoffScatter.vue'
import CompareBars from '@/components/benchmark/CompareBars.vue'
import { toast } from '@/stores/toast'

const route = useRoute()
const { can } = useSession()
const id = computed(() => route.params.id as string)
const { data: b, loading, error } = useAsync(() => getBenchmark(id.value))
const editOpen = ref(false)
const { data: rows } = useAsync(() => getLeaderboard(id.value))
const { data: runs } = useAsync(() => listEvals({ benchmarkId: id.value }))
const { data: ev } = useAsync(async () => (b.value ? getEvaluator(b.value.evaluator).catch(() => null) : null), [b])

const evConfig = ref<EvaluatorParamDef[]>([])
const savingCfg = ref(false)
watch(
  ev,
  (v) => {
    evConfig.value = v ? JSON.parse(JSON.stringify(v.config)) : []
  },
  { immediate: true },
)
async function saveEvConfig() {
  if (!ev.value) return
  savingCfg.value = true
  try {
    ev.value = await updateEvaluator(ev.value.id, { config: JSON.parse(JSON.stringify(evConfig.value)) })
    toast('评测器参数已保存')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'error')
  } finally {
    savingCfg.value = false
  }
}

const tab = ref<'board' | 'chart' | 'runs' | 'rules'>('board')
const sortKey = ref<string>('')
const sortAsc = ref(false)
const selected = ref<string[]>([])

const primary = computed(() => b.value?.metrics.find((m) => m.primary))
const sorted = computed(() => {
  if (!rows.value || !b.value) return []
  const key = sortKey.value || primary.value!.key
  const m = b.value.metrics.find((x) => x.key === key)!
  const dir = sortKey.value ? (sortAsc.value ? 1 : -1) : m.higherIsBetter ? -1 : 1
  return [...rows.value].sort((x, y) => dir * ((x.run.metrics[key] ?? 0) - (y.run.metrics[key] ?? 0)))
})
function sortBy(k: string) {
  if (sortKey.value === k) sortAsc.value = !sortAsc.value
  else {
    sortKey.value = k
    sortAsc.value = !b.value!.metrics.find((m) => m.key === k)!.higherIsBetter
  }
}
const best = (k: string) => {
  const m = b.value!.metrics.find((x) => x.key === k)!
  const vals = (rows.value ?? []).map((r) => r.run.metrics[k]).filter((v) => v != null)
  return m.higherIsBetter ? Math.max(...vals) : Math.min(...vals)
}
const rowKey = (r: { run: { algorithmId: string; algoVersion: string } }) => `${r.run.algorithmId}@${r.run.algoVersion}`
function toggle(k: string) {
  const i = selected.value.indexOf(k)
  if (i >= 0) selected.value.splice(i, 1)
  else if (selected.value.length >= 4) toast('最多同时对比 4 个算法', 'info')
  else selected.value.push(k)
}
const compareItems = computed(() =>
  selected.value
    .map((k) => rows.value?.find((r) => rowKey(r) === k))
    .filter(Boolean)
    .map((r) => ({ id: rowKey(r!), label: `${algoName(r!.algorithm)} ${r!.run.algoVersion}`, values: r!.run.metrics })),
)
const scatterPts = computed(() =>
  (rows.value ?? [])
    .map((r) => ({ r, lat: r.run.metrics.latency_ms ?? r.run.latencyMs }))
    .filter((x) => x.lat != null && primary.value && x.r.run.metrics[primary.value.key] != null)
    .map(({ r, lat }) => ({
      id: rowKey(r),
      label: `${algoName(r.algorithm)} ${r.run.algoVersion}`,
      x: lat!,
      y: r.run.metrics[primary.value!.key],
      selected: selected.value.includes(rowKey(r)),
    })),
)
</script>

<template>
  <StateView :loading="loading" :error="error">
    <template v-if="b">
      <div class="border-b border-gray-100 bg-gradient-to-t from-amber-50/50 to-white pt-8 dark:border-gray-800 dark:from-amber-900/10 dark:to-gray-950">
        <div class="container-page">
          <div class="flex flex-wrap items-start gap-4">
            <div class="min-w-0 flex-1">
              <p class="flex items-center gap-1.5 text-sm text-gray-500"><Trophy class="size-4 text-amber-500" />评测基准 · <span class="mono">{{ b.name }}</span></p>
              <h1 class="mt-1 text-2xl font-semibold text-gray-900 dark:text-white">{{ b.displayName }}</h1>
              <p class="mt-1 max-w-3xl text-sm text-gray-600 dark:text-gray-400">{{ b.description }}</p>
              <div class="mt-3 flex flex-wrap gap-1.5">
                <TaskBadge :task="b.task" />
                <RouterLink :to="`/datasets/${b.datasetId}`" class="chip hover:border-gray-400"><Database class="size-3" />{{ b.datasetId }} · 测试集 {{ b.datasetVersion }}</RouterLink>
                <button type="button" class="chip mono cursor-pointer hover:border-gray-400" @click="tab = 'rules'">{{ b.evaluator }}@{{ b.evaluatorVersion }}</button>
                <span class="chip"><Lock class="size-3" />GT 仅平台可见</span>
              </div>
            </div>
            <div class="flex gap-2">
              <button v-if="can.admin" class="btn-default" @click="editOpen = true"><Pencil class="size-4" />编辑</button>
              <RouterLink v-if="can.runEval" :to="`/evals/new?bench=${b.id}`" class="btn-primary"><FlaskConical class="size-4" />提交评测</RouterLink>
            </div>
          </div>
          <div class="mt-5 flex gap-1 no-scrollbar overflow-x-auto overflow-y-hidden">
            <button class="tab" :class="{ 'tab-active': tab === 'board' }" @click="tab = 'board'"><Table2 class="size-4" />排行榜</button>
            <button class="tab" :class="{ 'tab-active': tab === 'chart' }" @click="tab = 'chart'"><ChartScatter class="size-4" />精度 / 速度</button>
            <button class="tab" :class="{ 'tab-active': tab === 'runs' }" @click="tab = 'runs'"><FlaskConical class="size-4" />全部评测<span class="chip px-1 py-0 text-[10px]">{{ runs?.length ?? 0 }}</span></button>
            <button class="tab" :class="{ 'tab-active': tab === 'rules' }" @click="tab = 'rules'">评测规则</button>
          </div>
        </div>
      </div>

      <div class="container-page pt-6">
        <!-- 排行榜 -->
        <div v-if="tab === 'board'">
          <p class="mb-3 text-sm text-gray-500">每个“算法版本”仅取最新一次有效结果上榜。<template v-if="can.seeOthersOnBoard">勾选最多 4 个进行对比；点击列头排序。</template><template v-else>厂商账号仅显示你的算法的成绩与名次，其他厂商的结果不可见。</template></p>
          <StateView :loading="!rows" :empty="rows && !rows.length" empty-text="暂无上榜结果">
            <div class="card overflow-x-auto">
              <table class="table-base">
                <thead>
                  <tr>
                    <th class="w-8"><span class="sr-only">对比</span></th>
                    <th class="w-12">排名</th>
                    <th>算法</th>
                    <th>版本</th>
                    <th v-for="m in b.metrics" :key="m.key" class="cursor-pointer text-right select-none hover:text-gray-900 dark:hover:text-white" @click="sortBy(m.key)">
                      <span class="inline-flex items-center gap-0.5" :class="m.primary ? 'text-gray-900 dark:text-white' : ''">
                        {{ m.label }}<span v-if="m.unit" class="font-normal text-gray-400">({{ m.unit }})</span>
                        <ArrowUp v-if="sortKey === m.key && sortAsc" class="size-3" />
                        <ArrowDown v-else-if="sortKey === m.key" class="size-3" />
                      </span>
                    </th>
                    <th>评测时间</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in sorted" :key="r.run.id" class="hover:bg-gray-50 dark:hover:bg-gray-900" :class="selected.includes(rowKey(r)) ? 'bg-brand-50/60 dark:bg-brand-600/10' : ''">
                    <td><input type="checkbox" class="size-4 accent-brand-600" :checked="selected.includes(rowKey(r))" :aria-label="`对比 ${r.algorithm.name}`" @change="toggle(rowKey(r))" /></td>
                    <td class="mono font-semibold" :class="r.rank <= 3 ? ['text-amber-500', 'text-gray-400', 'text-orange-700'][r.rank - 1] : 'text-gray-500'">{{ r.rank }}</td>
                    <td>
                      <RouterLink :to="`/algorithms/${r.algorithm.id}`" class="flex items-center gap-1.5 hover:text-brand-600">
                        <OrgAvatar :org="r.algorithm.org" :size="16" />{{ algoFullLabel(r.algorithm) }}
                      </RouterLink>
                    </td>
                    <td><RouterLink :to="`/evals/${r.run.id}`" class="mono text-gray-600 hover:underline dark:text-gray-400">{{ r.run.algoVersion }}</RouterLink></td>
                    <td v-for="m in b.metrics" :key="m.key" class="mono text-right" :class="[can.seeOthersOnBoard && r.run.metrics[m.key] === best(m.key) ? 'font-semibold text-emerald-600 dark:text-emerald-400' : '', m.primary ? 'bg-gray-50/70 dark:bg-gray-900' : '']">
                      {{ fmtMetric(r.run.metrics[m.key], m.unit) }}
                    </td>
                    <td class="whitespace-nowrap text-gray-500">{{ timeAgo(r.run.finishedAt ?? r.run.submittedAt) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </StateView>

          <div v-if="compareItems.length" class="card mt-6 p-5">
            <div class="mb-4 flex items-center gap-2">
              <h2 class="section-title">算法对比</h2>
              <span class="text-sm text-gray-500">{{ compareItems.length }} / 4</span>
              <button class="btn-ghost ml-auto text-xs" @click="selected = []"><X class="size-3.5" />清除</button>
            </div>
            <CompareBars :metrics="b.metrics" :items="compareItems" />
          </div>
        </div>

        <!-- 精度/速度 -->
        <div v-else-if="tab === 'chart'" class="card p-5">
          <h2 class="section-title">{{ primary!.label }} 与单图耗时</h2>
          <p class="mt-1 mb-4 text-sm text-gray-500">虚线为帕累托前沿（同等耗时下精度最高）。点击点可加入/移出对比。硬件：RTX 4060 Laptop。</p>
          <TradeoffScatter v-if="scatterPts.length" :points="scatterPts" x-label="单图耗时 ms" :y-label="primary!.label" :y-unit="primary!.unit" @toggle="toggle" />
          <p v-else class="text-sm text-gray-500">暂无数据</p>
        </div>

        <!-- 全部评测 -->
        <div v-else-if="tab === 'runs'">
          <EvalTable :runs="runs ?? []" hide-bench />
        </div>

        <!-- 规则 -->
        <div v-else class="space-y-6">
          <div class="grid gap-6 lg:grid-cols-2">
            <div class="card p-5">
              <h2 class="section-title mb-3">指标配置</h2>
              <table class="table-base">
                <thead><tr><th>指标</th><th>键</th><th>方向</th><th>角色</th></tr></thead>
                <tbody>
                  <tr v-for="m in b.metrics" :key="m.key">
                    <td>{{ m.label }} <span v-if="m.unit" class="text-gray-400">({{ m.unit }})</span></td>
                    <td class="mono">{{ m.key }}</td>
                    <td>{{ m.higherIsBetter ? '越高越好' : '越低越好' }}</td>
                    <td><span v-if="m.primary" class="chip border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300">主指标</span><span v-else class="text-gray-400">辅助</span></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div class="card space-y-3 p-5 text-sm">
              <h2 class="section-title">评测流程</h2>
              <ol class="list-inside list-decimal space-y-1.5 text-gray-600 dark:text-gray-400">
                <li>算法容器以 <code class="mono">batch</code> 模式启动，<b>断网</b>，按声明限制 CPU / 内存 / 显存。</li>
                <li>只读挂载 <code class="mono">{{ b.datasetId }}@{{ b.datasetVersion }}</code> 测试集的 <code class="mono">images/</code>（不挂载 labels.csv）。</li>
                <li>容器输出 <code class="mono">predictions.json</code> 后退出。</li>
                <li>平台侧评测器 <code class="mono">{{ b.evaluator }}@{{ b.evaluatorVersion }}</code> 读取 GT 计算指标。</li>
                <li>记录镜像 digest、权重哈希、参数与硬件信息，保证可复现。</li>
              </ol>
              <p class="text-xs text-gray-500">创建于 {{ fmtDate(b.createdAt) }} · 组织 {{ orgLabel(b.org) }}</p>
            </div>
          </div>

          <!-- 评测器说明与可调参数 -->
          <div class="card overflow-hidden">
            <div class="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-5 py-4 dark:border-gray-800">
              <div class="min-w-0 flex-1">
                <h2 class="section-title flex items-center gap-2">
                  <Scale class="size-4 text-brand-600" />
                  评测器：{{ ev?.name ?? b.evaluator }}
                  <span class="chip mono text-xs font-normal">{{ b.evaluator }}@{{ b.evaluatorVersion }}</span>
                </h2>
                <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
                  {{ ev?.description ?? '平台侧评测器负责读取隐藏测试集真值（labels.csv），并与算法预测结果比对计算各项指标。' }}
                </p>
                <div v-if="ev" class="mt-2 flex flex-wrap gap-1.5">
                  <span class="chip"><Cpu class="size-3 text-gray-400" />{{ ev.runtime }}</span>
                  <span class="chip mono">入口：{{ ev.entrypoint }}</span>
                </div>
              </div>
              <button v-if="can.admin && ev && evConfig.length" class="btn-primary text-xs" :disabled="savingCfg" @click="saveEvConfig">
                <Save class="size-3.5" />{{ savingCfg ? '保存中…' : '保存参数' }}
              </button>
            </div>

            <div v-if="evConfig.length" class="divide-y divide-gray-100 dark:divide-gray-800">
              <div v-for="p in evConfig" :key="p.key" class="grid items-center gap-3 px-5 py-3 sm:grid-cols-[1fr_220px]">
                <div class="min-w-0">
                  <p class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ p.label }} <code class="mono ml-1 text-xs font-normal text-gray-400">{{ p.key }}</code>
                  </p>
                  <p v-if="p.desc" class="text-xs text-gray-500">{{ p.desc }}</p>
                </div>
                <div>
                  <input v-if="p.type === 'number'" v-model.number="p.value" type="number" step="any" class="input mono" :disabled="!can.admin" />
                  <select v-else-if="p.type === 'select'" v-model="p.value" class="input" :disabled="!can.admin">
                    <option v-for="opt in p.options" :key="opt" :value="opt">{{ opt }}</option>
                  </select>
                  <label v-else-if="p.type === 'boolean'" class="inline-flex cursor-pointer items-center gap-2 text-sm">
                    <input v-model="p.value" type="checkbox" class="size-4 accent-brand-600" :disabled="!can.admin" />
                    <span>{{ p.value ? '开启' : '关闭' }}</span>
                  </label>
                  <input v-else v-model="p.value" class="input mono" :disabled="!can.admin" />
                </div>
              </div>
            </div>
            <p v-else class="px-5 py-4 text-sm text-gray-500">该评测器使用默认算分规则，无需额外调整参数。</p>
          </div>
        </div>
      </div>
      <EditBenchmarkModal v-model:open="editOpen" :b="b" @saved="b = $event" />
    </template>
  </StateView>
</template>
