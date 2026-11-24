<script setup lang="ts">
/** [0x07] 在线推理面板：上传 60 分钟遥测 CSV 或按状态挑选数据集示例，结果以折线图展示 */
import { computed, ref } from 'vue'
import { Download, FileUp, LoaderCircle, Play, RotateCcw, Shuffle } from 'lucide-vue-next'
import type { Algorithm, InferenceResult } from '@/types'
import { infer } from '@/api'
import CaseView0x07 from './CaseView0x07.vue'
import { DATASET_0X07_ID, STATES_0X07, type Case0x07, type Channel0x07 } from './types'

const props = defineProps<{ algo: Algorithm; version: string }>()

const FILES = `/real-api/datasets/${DATASET_0X07_ID}/files/train`
const input = ref<{ file?: File; dataUrl?: string; fileName: string; size: number; label?: string } | null>(null)
const result = ref<InferenceResult | null>(null)
const running = ref(false)
const error = ref('')
const fileEl = ref<HTMLInputElement>()
const sampleCache = new Map<string, { file: string; label: string }[]>()
const cursor = new Map<string, number>()

async function pickSample(label: string) {
  error.value = ''
  try {
    if (!sampleCache.has(label)) {
      const r = await fetch(`/real-api/0x07/samples?label=${encodeURIComponent(label)}&limit=40`)
      if (!r.ok) throw new Error('示例列表获取失败（后端未启动？）')
      sampleCache.set(label, await r.json())
    }
    const list = sampleCache.get(label)!
    if (!list.length) throw new Error('没有该状态的示例')
    const i = (cursor.get(label) ?? -1) + 1
    cursor.set(label, i)
    const s = list[i % list.length]
    input.value = { dataUrl: `${FILES}/${s.file}`, fileName: s.file, size: 0, label }
    result.value = null
    await run()
  } catch (e) {
    error.value = (e as Error).message
  }
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

type Raw0x07 = {
  status: string
  risk_next_10min: number
  max_anomaly: number
  first_fault_minute: number | null
  source_file: string
  states: string[]
  channels: Record<Channel0x07, number[]>
  pred: number[]
  anomaly: number[]
  warn: number[]
  gt: number[] | null
  warnGt: number[] | null
}
const raw = computed(() => (result.value?.raw && 'channels' in (result.value.raw as object) ? (result.value.raw as unknown as Raw0x07) : null))
const caseData = computed<Case0x07 | null>(() => {
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
    pred: r.pred,
    anomaly: r.anomaly,
    warn: r.warn,
  }
})
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
        <span class="text-gray-600 dark:text-gray-300">上传 60 分钟遥测 CSV</span>
        <span class="text-[11px] text-gray-400">8 列：cpu_pct、cpu_temp_c、mem_pct、gpu_pct、gpu_temp_c、gpu_mem_pct、disk_io_mbps、net_mbps</span>
      </div>
      <input ref="fileEl" type="file" class="hidden" accept=".csv,text/csv" @change="onFile(($event.target as HTMLInputElement).files?.[0])" />
      <div>
        <p class="mb-1.5 flex items-center gap-1 text-xs text-gray-500"><Shuffle class="size-3.5" />或按状态取一个训练集示例（再次点击换一个）</p>
        <div class="flex flex-wrap gap-1.5">
          <button v-for="s in STATES_0X07" :key="s" type="button" class="btn-default px-2 py-1 text-xs" @click="pickSample(s)">{{ s }}</button>
        </div>
      </div>
      <a :href="`${FILES}/train_0x07_gpu-node-01_0001.csv`" download="0x07_template.csv" class="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline dark:text-brand-400"><Download class="size-3.5" />下载 CSV 格式示例</a>
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
      </div>
      <div class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-lg border px-2 py-2" :class="statusCls">
          <div class="text-[10px] opacity-80">窗口判定</div>
          <div class="text-sm font-semibold">{{ raw.status }}</div>
        </div>
        <div class="rounded-lg border border-gray-200 px-2 py-2 dark:border-gray-700">
          <div class="text-[10px] text-gray-500">未来 10 分钟风险</div>
          <div class="text-sm font-semibold">{{ raw.pred[raw.pred.length - 1] > 0 ? '故障进行中' : `${raw.risk_next_10min}%` }}</div>
        </div>
        <div class="rounded-lg border border-gray-200 px-2 py-2 dark:border-gray-700">
          <div class="text-[10px] text-gray-500">首次判定故障</div>
          <div class="text-sm font-semibold">{{ raw.first_fault_minute === null ? '—' : `第 ${raw.first_fault_minute} 分钟` }}</div>
        </div>
      </div>
      <CaseView0x07 :c="caseData" :states="raw.states" narrow />
    </template>
  </div>
</template>
