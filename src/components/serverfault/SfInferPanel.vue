<script setup lang="ts">
/**
 * 服务器故障检测标准：在线推理面板（所有标准算法共用）
 * 上传标准 8 通道 CSV，或从任一标准数据集的训练集按状态挑选示例——任何标准算法都能直接推理任何标准数据集的样本。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { Download, FileUp, LoaderCircle, Play, RotateCcw, Shuffle } from 'lucide-vue-next'
import type { Algorithm, InferenceResult } from '@/types'
import { infer } from '@/api'
import SfCaseView from './SfCaseView.vue'
import { SF_STATES, type SfCase, type SfChannel } from './types'

const props = defineProps<{ algo: Algorithm; version: string }>()

const datasets = ref<string[]>([])
const dataset = ref('')
const samples = ref<{ file: string; label: string; server: string; onset: number }[]>([])
const labels = computed(() => SF_STATES.filter((s) => samples.value.some((x) => x.label === s)))
const filesBase = computed(() => `/real-api/datasets/${dataset.value}/files/train`)

const input = ref<{ file?: File; dataUrl?: string; fileName: string; size: number; label?: string } | null>(null)
const result = ref<InferenceResult | null>(null)
const running = ref(false)
const error = ref('')
const fileEl = ref<HTMLInputElement>()
const cursor = new Map<string, number>()

onMounted(async () => {
  try {
    const r = await fetch('/real-api/server-fault/standard')
    if (!r.ok) throw new Error()
    const ids: string[] = (await r.json()).datasets
    // 算法自己的训练数据集排在最前面
    const key = props.algo.name.toLowerCase()
    datasets.value = [...ids].sort((a, b) => Number(b.toLowerCase().includes(key)) - Number(a.toLowerCase().includes(key)))
    dataset.value = datasets.value[0] ?? ''
  } catch {
    error.value = '无法获取标准数据集列表（后端未启动？），仍可上传 CSV 推理'
  }
})
watch(dataset, async (id) => {
  samples.value = []
  cursor.clear()
  if (!id) return
  const r = await fetch(`/real-api/server-fault/samples?dataset=${encodeURIComponent(id)}&limit=5000`)
  if (r.ok) samples.value = await r.json()
})

async function pickSample(label: string) {
  const list = samples.value.filter((s) => s.label === label)
  if (!list.length) return
  const i = (cursor.get(label) ?? -1) + 1
  cursor.set(label, i)
  const s = list[i % list.length]
  input.value = { dataUrl: `${filesBase.value}/${s.file}`, fileName: s.file, size: 0, label }
  result.value = null
  await run()
}

function onFile(f?: File | null) {
  if (!f) return
  if (f.size > 2 * 1024 * 1024) {
    error.value = 'CSV 不能超过 2 MB'
    return
  }
  error.value = ''
  input.value = { file: f, fileName: f.name, size: f.size }
  result.value = null
}

async function run() {
  if (!input.value) return
  running.value = true
  error.value = ''
  try {
    result.value = await infer(props.algo.id, props.version, { ...input.value })
  } catch (e) {
    error.value = (e as Error).message || '推理失败'
  } finally {
    running.value = false
  }
}

function reset() {
  input.value = null
  result.value = null
  error.value = ''
}

/** 标准推理输出（server_fault_api._infer） */
type SfRaw = {
  status: string
  diagnosis: string | null
  risk_next_10min: number | null
  max_fault_prob: number
  first_fault_minute: number | null
  source_file: string
  dataset: string | null
  states: string[]
  channels: Record<SfChannel, number[]>
  fault_prob: number[]
  state: number[] | null
  warn_prob: number[] | null
  gt: number[] | null
  warnGt: number[] | null
}
const raw = computed(() => (result.value?.raw && 'fault_prob' in (result.value.raw as object) ? (result.value.raw as unknown as SfRaw) : null))
const caseData = computed<SfCase | null>(() => {
  const r = raw.value
  if (!r) return null
  const onset = r.gt ? r.gt.findIndex((v) => v > 0) : -1
  return {
    file: r.source_file,
    label: r.gt ? (onset >= 0 ? r.states[Math.max(...r.gt)] : '正常') : undefined,
    predLabel: r.status,
    onset: r.gt ? onset : undefined,
    channels: r.channels,
    gt: r.gt,
    warnGt: r.warnGt,
    pred: r.state,
    anomaly: r.fault_prob,
    warn: r.warn_prob,
  }
})
const ongoing = computed(() => (raw.value ? raw.value.fault_prob[raw.value.fault_prob.length - 1] >= 0.5 : false))
const statusCls = computed(() =>
  raw.value?.status === '正常'
    ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300'
    : 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300',
)
</script>

<template>
  <div class="space-y-3 p-4">
    <template v-if="!input">
      <div
        class="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed border-gray-200 px-4 py-6 text-center text-sm hover:border-gray-300 dark:border-gray-700"
        role="button"
        tabindex="0"
        @click="fileEl?.click()"
        @keydown.enter="fileEl?.click()"
        @dragover.prevent
        @drop.prevent="onFile($event.dataTransfer?.files?.[0])"
      >
        <FileUp class="size-6 text-gray-400" />
        <span class="text-gray-600 dark:text-gray-300">上传 60 分钟标准遥测 CSV</span>
        <span class="text-[11px] text-gray-400">8 列：cpu_pct、cpu_temp_c、mem_pct、gpu_pct、gpu_temp_c、gpu_mem_pct、disk_io_mbps、net_mbps</span>
      </div>
      <input ref="fileEl" type="file" class="hidden" accept=".csv,text/csv" @change="onFile(($event.target as HTMLInputElement).files?.[0])" />
      <div v-if="datasets.length">
        <div class="mb-1.5 flex items-center gap-2 text-xs text-gray-500">
          <Shuffle class="size-3.5 shrink-0" />
          <span class="shrink-0">或从标准数据集训练集取示例</span>
          <select v-model="dataset" class="input min-w-0 flex-1 py-0.5 text-xs" aria-label="选择示例数据集">
            <option v-for="d in datasets" :key="d" :value="d">{{ d.split('/')[1] }}</option>
          </select>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <button v-for="s in labels" :key="s" type="button" class="btn-default px-2 py-1 text-xs" @click="pickSample(s)">{{ s }}</button>
        </div>
      </div>
      <a v-if="samples.length" :href="`${filesBase}/${samples[0].file}`" download="server_fault_template.csv" class="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline dark:text-brand-400"><Download class="size-3.5" />下载标准 CSV 示例</a>
    </template>

    <template v-else>
      <div class="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700">
        <span class="mono truncate text-xs">{{ input.fileName }}</span>
        <span v-if="input.label" class="chip shrink-0 text-[10px]">示例 · {{ input.label }}</span>
        <LoaderCircle v-if="running" class="ml-auto size-4 shrink-0 animate-spin text-gray-400" />
      </div>
      <div class="flex gap-2">
        <button class="btn-brand flex-1" :disabled="running" @click="run">
          <LoaderCircle v-if="running" class="size-4 animate-spin" />
          <Play v-else class="size-4" />
          {{ running ? '推理中…' : '运行推理' }}
        </button>
        <button v-if="input.label" class="btn-default" :disabled="running" aria-label="换一个同类示例" @click="pickSample(input.label!)"><Shuffle class="size-4" /></button>
        <button class="btn-default" :disabled="running" aria-label="重新选择输入" @click="reset"><RotateCcw class="size-4" /></button>
      </div>
    </template>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{{ error }}</p>

    <template v-if="result && raw && caseData">
      <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
        <span>{{ result.device }}</span>
        <span>推理 {{ result.latencyMs }} ms</span>
        <span v-if="raw.dataset" class="mono">{{ raw.dataset }}</span>
      </div>
      <div class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-lg border px-2 py-2" :class="statusCls">
          <div class="text-[10px] opacity-80">窗口判定</div>
          <div class="text-sm font-semibold">{{ raw.status }}</div>
        </div>
        <div class="rounded-lg border border-gray-200 px-2 py-2 dark:border-gray-700">
          <div class="text-[10px] text-gray-500">{{ raw.risk_next_10min === null ? '最大故障概率' : '未来 10 分钟风险' }}</div>
          <div class="text-sm font-semibold">{{ raw.risk_next_10min === null ? `${raw.max_fault_prob}%` : ongoing ? '故障进行中' : `${raw.risk_next_10min}%` }}</div>
        </div>
        <div class="rounded-lg border border-gray-200 px-2 py-2 dark:border-gray-700">
          <div class="text-[10px] text-gray-500">首次判定故障</div>
          <div class="text-sm font-semibold">{{ raw.first_fault_minute === null ? '—' : `第 ${raw.first_fault_minute} 分钟` }}</div>
        </div>
      </div>
      <p v-if="raw.diagnosis" class="rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-700 dark:bg-gray-800/60 dark:text-gray-300">{{ raw.diagnosis }}</p>
      <SfCaseView :c="caseData" :states="raw.states" narrow />
    </template>
  </div>
</template>
