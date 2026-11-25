<script setup lang="ts">
/** 新能源功率预测标准：在线推理面板（对标 SfInferPanel，支持按场站一键挑样本或上传 CSV） */
import { computed, onMounted, ref } from 'vue'
import { Download, FileUp, LoaderCircle, Play, RotateCcw, Shuffle } from 'lucide-vue-next'
import type { Algorithm, InferenceResult } from '@/types'
import { infer } from '@/api'
import PfCaseView from './PfCaseView.vue'
import type { PfCase } from './types'

const props = defineProps<{ algo: Algorithm; version: string }>()

interface SampleItem {
  file: string
  station: string
  kind: string
  weather: string
  value: number
  peak_mw: number
}

const samples = ref<SampleItem[]>([])
const stations = computed(() => [...new Set(samples.value.map((s) => s.station))])
const input = ref<{ file?: File; dataUrl?: string; fileName: string; size: number } | null>(null)
const result = ref<InferenceResult | null>(null)
const running = ref(false)
const error = ref('')
const fileEl = ref<HTMLInputElement>()
const cursor = new Map<string, number>()

onMounted(async () => {
  try {
    const r = await fetch('/real-api/power-forecast/samples?part=train&limit=600')
    if (r.ok) samples.value = await r.json()
  } catch {
    /* ignore */
  }
})

async function pickStation(st: string) {
  const list = samples.value.filter((s) => s.station === st)
  if (!list.length) return
  const i = (cursor.get(st) ?? -1) + 1
  cursor.set(st, i)
  const s = list[i % list.length]
  input.value = { dataUrl: `/real-api/datasets/Admin/wind-solar-power-dataset/files/train/${s.file}`, fileName: s.file, size: 0 }
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

const raw = computed(() => (result.value?.raw as Record<string, unknown> | undefined) ?? null)
const caseData = computed<PfCase | null>(() => (raw.value?.case as PfCase | undefined) ?? null)
</script>

<template>
  <div class="space-y-3">
    <!-- 一键按场站抽样推理 -->
    <div v-if="stations.length" class="space-y-1.5">
      <p class="flex items-center gap-1 text-xs text-gray-500">
        <Shuffle class="size-3.5" />从训练集按场站随机抽取 24h 窗口直接推理：
      </p>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="st in stations"
          :key="st"
          type="button"
          class="cursor-pointer rounded-full border border-gray-200 bg-white px-2.5 py-0.5 text-[11px] text-gray-700 transition hover:border-brand-400 hover:text-brand-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-200 dark:hover:border-brand-500"
          :disabled="running"
          @click="pickStation(st)"
        >
          {{ st }}
        </button>
      </div>
    </div>

    <!-- 上传自定义 CSV -->
    <div v-if="!input" class="flex items-center gap-2">
      <button type="button" class="btn-default flex-1 justify-center text-xs" @click="fileEl?.click()">
        <FileUp class="size-3.5" />上传 24h 气象与功率 CSV
      </button>
      <a
        v-if="samples.length"
        :href="`/real-api/datasets/Admin/wind-solar-power-dataset/files/train/${samples[0].file}`"
        download
        class="btn-ghost text-xs"
        title="下载标准 CSV 示例"
      >
        <Download class="size-3.5" />示例 CSV
      </a>
    </div>
    <input ref="fileEl" type="file" accept=".csv,text/csv" class="hidden" @change="onFile(($event.target as HTMLInputElement).files?.[0])" />

    <!-- 已选文件操作栏 -->
    <div v-if="input" class="flex items-center gap-2">
      <span class="mono min-w-0 flex-1 truncate rounded-lg border border-gray-200 px-2.5 py-1.5 text-xs dark:border-gray-700">{{ input.fileName }}</span>
      <button type="button" class="btn-brand py-1.5 text-xs" :disabled="running" @click="run">
        <LoaderCircle v-if="running" class="size-3.5 animate-spin" />
        <Play v-else class="size-3.5" />
        {{ running ? '预测中…' : '运行预测' }}
      </button>
      <button type="button" class="btn-default p-1.5" :disabled="running" aria-label="重置" @click="reset">
        <RotateCcw class="size-3.5" />
      </button>
    </div>

    <p v-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{{ error }}</p>

    <!-- 实时推理结果：48h 连续功率折线图（历史 + 预测 + 真值对照） -->
    <div v-if="result && caseData" class="space-y-2 rounded-xl border border-gray-200/80 bg-gray-50/50 p-3 dark:border-gray-800 dark:bg-gray-900/50">
      <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-500">
        <span>{{ result.device }} · 推理 {{ result.latencyMs }} ms</span>
        <span class="mono">预测均值 <strong class="text-brand-600 dark:text-brand-400">{{ raw?.mean_mw }} MW</strong> · 峰值 <strong class="text-gray-900 dark:text-white">{{ raw?.peak_mw }} MW</strong></span>
      </div>
      <PfCaseView :c="caseData" compact />
    </div>
  </div>
</template>
