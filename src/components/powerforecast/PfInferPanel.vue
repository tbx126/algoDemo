<script setup lang="ts">
/** 新能源功率预测标准：在线推理面板（所有标准算法共用；支持跨标准数据集按场站抽样，或拖拽上传 CSV） */
import { computed, onMounted, ref, watch } from 'vue'
import { Download, FileUp, LoaderCircle, Play, RotateCcw, Shuffle, Sun, Wind } from 'lucide-vue-next'
import type { Algorithm, InferenceResult } from '@/types'
import { infer } from '@/api'
import PfCaseView from './PfCaseView.vue'
import type { PfCase } from './types'

const props = defineProps<{ algo: Algorithm; version: string }>()

interface SampleItem {
  dataset: string
  file: string
  url: string
  station: string
  kind: string
  weather: string
  value: number
  peak_mw: number
}

const datasets = ref<string[]>([])
const dataset = ref('')
const samples = ref<SampleItem[]>([])
const stationList = computed(() => {
  const seen = new Map<string, string>()
  for (const s of samples.value) {
    if (!seen.has(s.station)) seen.set(s.station, s.kind)
  }
  return [...seen.entries()].map(([name, kind]) => ({ name, kind }))
})

const input = ref<{ file?: File; dataUrl?: string; fileName: string; size: number; station?: string } | null>(null)
const result = ref<InferenceResult | null>(null)
const running = ref(false)
const dragging = ref(false)
const error = ref('')
const fileEl = ref<HTMLInputElement>()
const cursor = new Map<string, number>()

/** 上传 CSV 时所属场站的类型与装机容量（功率按容量归一化，风电 / 光伏响应不同） */
const kind = ref<'wind' | 'solar'>('wind')
const capacity = ref(100)

onMounted(async () => {
  try {
    const r = await fetch('/real-api/power-forecast/standard')
    if (r.ok) {
      const ids: string[] = (await r.json()).datasets ?? []
      datasets.value = ids
      dataset.value = ids[0] ?? ''
    }
  } catch {
    /* ignore */
  }
})

watch(dataset, async (id) => {
  samples.value = []
  cursor.clear()
  if (!id) return
  try {
    const r = await fetch(`/real-api/power-forecast/samples?dataset=${encodeURIComponent(id)}&limit=5000`)
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
  input.value = { dataUrl: s.url, fileName: s.file, size: 0, station: st }
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

function onDrop(e: DragEvent) {
  dragging.value = false
  onFile(e.dataTransfer?.files?.[0])
}

async function run() {
  if (!input.value) return
  running.value = true
  error.value = ''
  try {
    const fields = input.value.file ? { kind: kind.value, capacity_mw: String(capacity.value) } : undefined
    result.value = await infer(props.algo.id, props.version, { ...input.value, fields })
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
  <div class="space-y-3.5 p-4">
    <template v-if="!input">
      <!-- 拖拽 / 点击上传标准 CSV -->
      <div
        class="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-5 text-center transition"
        :class="
          dragging
            ? 'border-brand-500 bg-brand-50/70 dark:bg-brand-950/30'
            : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50/60 dark:border-gray-700 dark:hover:border-gray-600 dark:hover:bg-gray-800/40'
        "
        role="button"
        tabindex="0"
        @click="fileEl?.click()"
        @keydown.enter="fileEl?.click()"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="onDrop"
      >
        <FileUp class="size-5 text-gray-400" />
        <span class="text-xs font-medium text-gray-700 dark:text-gray-200">上传 24 小时标准气象与功率 CSV</span>
        <span class="text-[11px] leading-relaxed text-gray-400">支持拖拽，含前一天实测 + 次日 NWP（9 列标准格式）</span>
      </div>
      <input ref="fileEl" type="file" accept=".csv,text/csv" class="hidden" @change="onFile(($event.target as HTMLInputElement).files?.[0])" />

      <!-- 上传 CSV 对应的场站参数 -->
      <div class="grid grid-cols-2 gap-2.5 text-xs">
        <label class="flex flex-col gap-1 text-gray-500">
          <span class="text-[11px]">场站类型</span>
          <select v-model="kind" class="input py-1.5 text-xs">
            <option value="wind">风电</option>
            <option value="solar">光伏</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-gray-500">
          <span class="text-[11px]">装机容量（MW）</span>
          <input v-model.number="capacity" type="number" min="1" class="input py-1.5 text-xs tabular-nums" />
        </label>
      </div>

      <!-- 一键按场站抽样推理 -->
      <div v-if="datasets.length" class="space-y-2 border-t border-gray-100 pt-3 dark:border-gray-800">
        <div class="flex items-center justify-between gap-2">
          <span class="flex items-center gap-1 text-xs text-gray-500">
            <Shuffle class="size-3.5 shrink-0" />按场站快速体验
          </span>
          <a
            v-if="samples.length"
            :href="samples[0].url"
            download="power_forecast_sample.csv"
            class="inline-flex shrink-0 items-center gap-1 text-[11px] font-medium text-brand-600 hover:underline dark:text-brand-400"
          >
            <Download class="size-3" />下载示例 CSV
          </a>
        </div>
        <select v-if="datasets.length > 1" v-model="dataset" class="input py-1 text-xs" aria-label="选择示例数据集">
          <option v-for="d in datasets" :key="d" :value="d">{{ d.split('/')[1] }}</option>
        </select>
        <div v-if="stationList.length" class="grid grid-cols-2 gap-1.5">
          <button
            v-for="st in stationList"
            :key="st.name"
            type="button"
            class="flex cursor-pointer items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-left text-xs text-gray-700 transition hover:border-brand-300 hover:bg-brand-50/40 hover:text-brand-700 disabled:opacity-50 dark:border-gray-700/80 dark:bg-gray-900 dark:text-gray-200 dark:hover:border-brand-600 dark:hover:bg-brand-950/30"
            :disabled="running"
            @click="pickStation(st.name)"
          >
            <Sun v-if="st.kind === 'solar'" class="size-3.5 shrink-0 text-amber-500" />
            <Wind v-else class="size-3.5 shrink-0 text-sky-500" />
            <span class="truncate">{{ st.name }}</span>
          </button>
        </div>
      </div>
    </template>

    <!-- 已选文件操作栏 -->
    <template v-else>
      <div class="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50/70 px-3 py-2 text-xs dark:border-gray-700 dark:bg-gray-800/40">
        <span class="mono min-w-0 flex-1 truncate text-gray-700 dark:text-gray-200" :title="input.fileName">{{ input.fileName }}</span>
        <span v-if="input.station" class="chip shrink-0 text-[10px]">{{ input.station }}</span>
        <LoaderCircle v-if="running" class="size-3.5 shrink-0 animate-spin text-brand-500" />
      </div>

      <div v-if="input.file" class="grid grid-cols-2 gap-2.5 text-xs">
        <label class="flex flex-col gap-1 text-gray-500">
          <span class="text-[11px]">场站类型</span>
          <select v-model="kind" class="input py-1.5 text-xs">
            <option value="wind">风电</option>
            <option value="solar">光伏</option>
          </select>
        </label>
        <label class="flex flex-col gap-1 text-gray-500">
          <span class="text-[11px]">装机容量（MW）</span>
          <input v-model.number="capacity" type="number" min="1" class="input py-1.5 text-xs tabular-nums" />
        </label>
      </div>

      <div class="flex gap-2">
        <button type="button" class="btn-brand flex-1 py-1.5 text-xs" :disabled="running" @click="run">
          <LoaderCircle v-if="running" class="size-3.5 animate-spin" />
          <Play v-else class="size-3.5" />
          {{ running ? '预测中…' : '运行预测' }}
        </button>
        <button
          v-if="input.station"
          type="button"
          class="btn-default px-2.5 py-1.5 text-xs"
          :disabled="running"
          title="换一个同场站窗口"
          aria-label="换一个同场站窗口"
          @click="pickStation(input.station!)"
        >
          <Shuffle class="size-3.5" />
        </button>
        <button
          type="button"
          class="btn-default px-2.5 py-1.5 text-xs"
          :disabled="running"
          title="重新选择输入"
          aria-label="重新选择输入"
          @click="reset"
        >
          <RotateCcw class="size-3.5" />
        </button>
      </div>
    </template>

    <p v-if="error" class="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{{ error }}</p>

    <!-- 实时推理结果：核心指标 + 48h 连续功率折线图 -->
    <template v-if="result && caseData">
      <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-gray-500">
        <span>{{ result.device }} · 推理 {{ result.latencyMs }} ms</span>
        <span v-if="caseData.weather" class="chip text-[10px]">{{ caseData.weather }}</span>
      </div>

      <div class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-lg border border-brand-200 bg-brand-50/50 px-2 py-2 dark:border-brand-900 dark:bg-brand-950/30">
          <div class="text-[10px] text-brand-700/80 dark:text-brand-300/80">次日均值</div>
          <div class="mt-0.5 text-sm font-semibold tabular-nums text-brand-700 dark:text-brand-300">{{ raw?.mean_mw }} <span class="text-[10px] font-normal">MW</span></div>
        </div>
        <div class="rounded-lg border border-gray-200 px-2 py-2 dark:border-gray-700">
          <div class="text-[10px] text-gray-500">次日峰值</div>
          <div class="mt-0.5 text-sm font-semibold tabular-nums text-gray-900 dark:text-white">{{ raw?.peak_mw }} <span class="text-[10px] font-normal text-gray-400">MW</span></div>
        </div>
        <div class="rounded-lg border border-gray-200 px-2 py-2 dark:border-gray-700">
          <div class="text-[10px] text-gray-500">{{ caseData.accuracy != null ? '样本准确度' : '预测步长' }}</div>
          <div class="mt-0.5 text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
            {{ caseData.accuracy != null ? `${caseData.accuracy.toFixed(1)}%` : '24 h' }}
          </div>
        </div>
      </div>

      <div class="rounded-xl border border-gray-200/80 bg-gray-50/50 p-2.5 dark:border-gray-800 dark:bg-gray-900/50">
        <PfCaseView :c="caseData" compact />
      </div>
    </template>
  </div>
</template>
