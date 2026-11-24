<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Braces, Cpu, Download, ImageUp, LoaderCircle, Lock, Play, RotateCcw, Zap } from 'lucide-vue-next'
import type { Algorithm, InferenceResult, TaskType } from '@/types'
import { infer } from '@/api'
import { useSession } from '@/stores/session'
import { TASKS } from '@/utils/meta'
import { CLASS_COLORS, sampleImageDataUrl } from '@/utils/synth'
import { hashStr } from '@/utils/format'
import Fault0x6ECharts, { type Fault0x6EVisual } from '@/components/eval/Fault0x6ECharts.vue'

const props = defineProps<{ algo: Algorithm; lockedReason?: string; pendingTrial?: boolean }>()
const emit = defineEmits<{ applyTrial: [] }>()
const { can } = useSession()

const readyVersions = computed(() => props.algo.versions.filter((v) => v.status === 'ready'))
const version = ref(readyVersions.value[0]?.version ?? '')
const isRandomAlgo = computed(() => props.algo.id === 'Admin/random')
const randomTask = ref<TaskType>('image-classification')
const activeTask = computed<TaskType>(() => (isRandomAlgo.value ? randomTask.value : props.algo.task))
const isImageTask = computed(() => !['signal-processing', 'power-forecast', 'optimization', 'custom'].includes(activeTask.value))

const samples = ref<string[]>([])
onMounted(() => {
  if (!isImageTask.value && !isRandomAlgo.value) return
  if (props.algo.sampleImages?.length) samples.value = props.algo.sampleImages
  else samples.value = [0, 1, 2].map((i) => sampleImageDataUrl(hashStr(props.algo.id) + i * 97, activeTask.value, props.algo.labels?.length ?? 3))
})

const input = ref<{ dataUrl?: string; file?: File; fileName: string; size: number } | null>(null)
const result = ref<InferenceResult | null>(null)
const running = ref(false)
const phase = ref('')
const showJson = ref(false)
const thresh = ref(0.5)
const dragging = ref(false)
const fileEl = ref<HTMLInputElement>()
const canvas = ref<HTMLCanvasElement>()
const imgEl = new Image()

function pickSample(i: number) {
  const s = samples.value[i]
  const name = s.startsWith('/') ? s.split('/').pop()! : `sample_${i + 1}.jpg`
  input.value = { dataUrl: s, fileName: name, size: s.length }
  result.value = null
}

function onFile(f?: File | null) {
  if (!f) return
  if (isImageTask.value && !f.type.startsWith('image/')) return
  if (f.size > 10 * 1024 * 1024) {
    alert('文件不能超过 10 MB')
    return
  }
  if (isImageTask.value) {
    const r = new FileReader()
    r.onload = () => {
      input.value = { dataUrl: r.result as string, file: f, fileName: f.name, size: f.size }
      result.value = null
    }
    r.readAsDataURL(f)
  } else {
    input.value = { file: f, fileName: f.name, size: f.size }
    result.value = null
  }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  onFile(e.dataTransfer?.files?.[0])
}

async function run() {
  if (!input.value || !version.value) return
  running.value = true
  result.value = null
  const warm = false
  phase.value = warm ? '容器已预热，推理中…' : '冷启动容器（加载权重）…'
  const t = setTimeout(() => (phase.value = '推理中…'), 900)
  try {
    result.value = await infer(props.algo.id, version.value, { ...input.value, task: isRandomAlgo.value ? randomTask.value : undefined })
  } finally {
    clearTimeout(t)
    running.value = false
  }
}

function reset() {
  input.value = null
  result.value = null
}

const visibleDets = computed(() => result.value?.detections?.filter((d) => d.score >= thresh.value) ?? [])
const labelColor = (l: string) => CLASS_COLORS[Math.max(0, props.algo.labels?.indexOf(l) ?? 0) % CLASS_COLORS.length]

/** 0x6E 服务器故障时序检测结果（含逐分钟预测概率、GT 与多维硬件指标折线图） */
const fault0x6EVisual = computed<Fault0x6EVisual | null>(() => {
  const raw = result.value?.raw as Record<string, unknown> | undefined
  if (!raw || raw.tag !== '0x6E' || !Array.isArray(raw.predProb) || !raw.telemetry) return null
  return {
    tag: '0x6E',
    windowLen: Number(raw.window_len ?? 60),
    cases: [
      {
        id: String(raw.source_file ?? '0x6E-sample.csv'),
        faultType: String(raw.status ?? '检测结果'),
        predProb: raw.predProb as number[],
        gtFault: (raw.gtFault as number[] | null | undefined) ?? null,
        telemetry: raw.telemetry as Fault0x6EVisual['cases'][0]['telemetry'],
      },
    ],
  }
})

/** 时序预测结果曲线数据（当 raw.forecast 为数值数组时渲染 SVG 曲线图） */
const forecastChart = computed(() => {
  const raw = result.value?.raw as Record<string, unknown> | undefined
  if (!raw || !Array.isArray(raw.forecast) || !raw.forecast.length) return null
  const forecast = (raw.forecast as number[]).map(Number).filter((v) => !Number.isNaN(v))
  if (!forecast.length) return null
  const history = Array.isArray(raw.history) ? (raw.history as number[]).map(Number).filter((v) => !Number.isNaN(v)) : []
  const unit = String(raw.unit ?? 'MW')
  const cap = Number(raw.capacity_mw ?? Math.max(100, ...forecast, ...history))
  const maxY = Math.max(10, Math.ceil(Math.max(cap, ...forecast, ...history) / 10) * 10)
  const W = 420
  const H = 148
  const padL = 32
  const padR = 10
  const padT = 12
  const padB = 22
  const plotW = W - padL - padR
  const plotH = H - padT - padB
  const totalPts = Math.max(2, history.length + forecast.length)
  const xAt = (idx: number) => padL + (idx / (totalPts - 1)) * plotW
  const yAt = (val: number) => padT + plotH * (1 - Math.max(0, Math.min(1, val / maxY)))

  const histPath = history.length
    ? history.map((v, i) => `${i === 0 ? 'M' : 'L'}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
    : ''
  const fStart = history.length
  const fPts = forecast.map((v, i) => ({ x: xAt(fStart + i), y: yAt(v) }))
  const bridge = history.length ? `M${xAt(history.length - 1).toFixed(1)},${yAt(history[history.length - 1]).toFixed(1)} ` : ''
  const predPath = bridge + fPts.map((p, i) => `${!bridge && i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const areaPath =
    fPts.length >= 2
      ? `M${fPts[0].x.toFixed(1)},${(padT + plotH).toFixed(1)} ` +
        fPts.map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') +
        ` L${fPts[fPts.length - 1].x.toFixed(1)},${(padT + plotH).toFixed(1)} Z`
      : ''
  const splitX = history.length ? xAt(history.length - 0.5) : null
  const meanVal = raw.mean_mw !== undefined ? Number(raw.mean_mw) : +(forecast.reduce((s, v) => s + v, 0) / forecast.length).toFixed(2)
  const peakVal = raw.peak_mw !== undefined ? Number(raw.peak_mw) : +Math.max(...forecast).toFixed(2)

  return { W, H, padL, padT, plotW, plotH, maxY, unit, histPath, predPath, areaPath, splitX, meanVal, peakVal, horizon: forecast.length, hasHistory: history.length > 0 }
})

function draw() {
  const c = canvas.value
  if (!c || !input.value?.dataUrl) return
  imgEl.onload = () => {
    const maxW = 960
    const scale = Math.min(1, maxW / imgEl.naturalWidth)
    const W = (c.width = Math.round(imgEl.naturalWidth * scale))
    const H = (c.height = Math.round(imgEl.naturalHeight * scale))
    const ctx = c.getContext('2d')!
    ctx.drawImage(imgEl, 0, 0, W, H)
    const r = result.value
    if (!r) return
    const fs = Math.max(11, Math.round(W / 40))
    ctx.font = `600 ${fs}px Inter, "Microsoft YaHei", sans-serif`
    for (const d of visibleDets.value) {
      const [x, y, w, h] = [d.box[0] * W, d.box[1] * H, d.box[2] * W, d.box[3] * H]
      const col = labelColor(d.label)
      ctx.lineWidth = Math.max(2, W / 320)
      ctx.strokeStyle = col
      ctx.strokeRect(x, y, w, h)
      const t = `${d.label} ${(d.score * 100).toFixed(0)}%`
      const tw = ctx.measureText(t).width + 8
      const ty = y - fs - 6 < 0 ? y : y - fs - 6
      ctx.fillStyle = col
      ctx.fillRect(x, ty, tw, fs + 6)
      ctx.fillStyle = '#fff'
      ctx.fillText(t, x + 4, ty + fs)
    }
    for (const s of r.segments ?? []) {
      ctx.beginPath()
      s.polygon.forEach(([px, py], i) => (i ? ctx.lineTo(px * W, py * H) : ctx.moveTo(px * W, py * H)))
      ctx.closePath()
      ctx.fillStyle = s.color + '77'
      ctx.fill()
      ctx.strokeStyle = s.color
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
  }
  imgEl.src = input.value.dataUrl
}
watch([input, result, thresh], () => nextTick(draw), { deep: true })

const segLegend = computed(() => {
  const m = new Map<string, string>()
  for (const s of result.value?.segments ?? []) m.set(s.label, s.color)
  return [...m]
})
const accept = computed(() => (isImageTask.value ? 'image/*' : props.algo.task === 'signal-processing' ? '.csv,.npy,.wav' : '.json,.txt,.vrp'))
</script>

<template>
  <div class="card overflow-hidden">
    <div class="flex items-center gap-2 border-b border-gray-100 px-4 py-2.5 dark:border-gray-800">
      <Zap class="size-4 text-amber-500" />
      <h3 class="text-sm font-semibold">在线推理</h3>
      <select v-if="readyVersions.length" v-model="version" class="input ml-auto w-auto py-1 text-xs" aria-label="选择算法版本">
        <option v-for="v in readyVersions" :key="v.version" :value="v.version">{{ v.version }}</option>
      </select>
    </div>

    <div v-if="!can.infer" class="flex flex-col items-center gap-2 px-4 py-10 text-center text-sm text-gray-500">
      <Lock class="size-6 text-gray-400" />
      当前身份不能使用在线推理
      <RouterLink to="/login" class="btn-default mt-1">去登录</RouterLink>
    </div>
    <div v-else-if="lockedReason" class="flex flex-col items-center gap-2.5 px-5 py-9 text-center text-sm text-gray-600 dark:text-gray-400">
      <Lock class="size-6 text-amber-500" />
      <p class="leading-relaxed">{{ lockedReason }}</p>
      <button
        v-if="!pendingTrial"
        type="button"
        class="btn-brand mt-1 text-xs"
        @click="emit('applyTrial')"
      >
        申请试用该算法
      </button>
      <span v-else class="chip border-amber-200 bg-amber-50 text-xs text-amber-700 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
        试用申请已提交，等待总部审批下发
      </span>
    </div>
    <div v-else-if="!readyVersions.length" class="px-4 py-10 text-center text-sm text-gray-500">暂无可用版本（构建或审核未完成），无法推理</div>

    <div v-else class="space-y-3 p-4">
      <div v-if="isRandomAlgo" class="flex items-center gap-2 text-xs">
        <label for="rand-task" class="shrink-0 text-gray-500">输出任务格式</label>
        <select id="rand-task" v-model="randomTask" class="input py-1 text-xs" @change="result = null">
          <option v-for="(v, k) in TASKS" :key="k" :value="k">{{ v.label }}</option>
        </select>
      </div>
      <!-- 输入区 -->
      <div
        v-if="!input"
        class="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center text-sm transition"
        :class="dragging ? 'border-brand-500 bg-brand-50 dark:bg-brand-600/10' : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'"
        role="button"
        tabindex="0"
        @click="fileEl?.click()"
        @keydown.enter="fileEl?.click()"
        @dragover.prevent="dragging = true"
        @dragleave="dragging = false"
        @drop.prevent="onDrop"
      >
        <ImageUp class="size-7 text-gray-400" />
        <span class="text-gray-600 dark:text-gray-300">{{ isImageTask ? '拖拽图片到这里，或点击上传' : '拖拽输入文件到这里，或点击上传' }}</span>
        <span class="text-xs text-gray-400">{{ isImageTask ? 'JPG / PNG，≤ 10 MB' : accept + '，≤ 10 MB' }}</span>
      </div>
      <input ref="fileEl" type="file" class="hidden" :accept="accept" @change="onFile(($event.target as HTMLInputElement).files?.[0])" />

      <div v-if="!input && samples.length">
        <p class="mb-1.5 text-xs text-gray-500">或使用示例</p>
        <div class="grid grid-cols-3 gap-2">
          <button v-for="(s, i) in samples" :key="i" class="cursor-pointer overflow-hidden rounded-md border border-gray-200 transition hover:ring-2 hover:ring-brand-500/40 dark:border-gray-700" :aria-label="`使用示例图片 ${i + 1}`" @click="pickSample(i)">
            <img :src="s" alt="" class="aspect-[4/3] w-full object-cover" />
          </button>
        </div>
      </div>
      <div v-if="!input && !isImageTask" class="flex gap-2">
        <button
          class="btn-default text-xs"
          @click="input = { fileName: algo.id === 'Admin/0x6E' ? 'server_0x6e_sample.csv' : activeTask === 'optimization' ? 'C101_25.vrp' : activeTask === 'power-forecast' ? 'station_huazhong_24h.csv' : 'bearing_0042.csv', size: 18234 }"
        >
          使用示例输入
        </button>
      </div>

      <!-- 预览 / 结果 -->
      <div v-if="input" class="space-y-3">
        <div v-if="input.dataUrl" class="relative overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800">
          <canvas ref="canvas" class="block h-auto w-full" />
          <div v-if="running" class="absolute inset-0 flex items-center justify-center bg-white/60 dark:bg-black/50">
            <span class="flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs shadow dark:bg-gray-900"><LoaderCircle class="size-3.5 animate-spin" />{{ phase }}</span>
          </div>
        </div>
        <div v-else class="flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700">
          <Braces class="size-4 text-gray-400" /><span class="mono truncate">{{ input.fileName }}</span>
          <LoaderCircle v-if="running" class="ml-auto size-4 animate-spin text-gray-400" />
        </div>

        <div class="flex gap-2">
          <button class="btn-brand flex-1" :disabled="running" @click="run">
            <LoaderCircle v-if="running" class="size-4 animate-spin" />
            <Play v-else class="size-4" />
            {{ running ? phase : '运行推理' }}
          </button>
          <button class="btn-default" :disabled="running" aria-label="重新选择输入" @click="reset"><RotateCcw class="size-4" /></button>
        </div>
      </div>

      <template v-if="result">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
          <span class="inline-flex items-center gap-1"><Cpu class="size-3.5" />{{ result.device }}</span>
          <span>推理 {{ result.latencyMs }} ms</span>
          <span v-if="result.queuedMs">冷启动 {{ (result.queuedMs / 1000).toFixed(1) }} s</span>
          <span v-else class="text-emerald-600">容器已预热</span>
        </div>

        <!-- 图像去雾 / 图像增强结果 -->
        <div v-if="result.outputImage" class="space-y-2">
          <div class="flex items-center justify-between text-xs text-gray-500">
            <span class="font-medium text-gray-700 dark:text-gray-200">去雾后效果（{{ version }}）</span>
            <a :href="result.outputImage" :download="`dehazed_${version}_${input?.fileName || 'output.jpg'}`" class="inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-400">
              <Download class="size-3.5" />下载结果图
            </a>
          </div>
          <div class="overflow-hidden rounded-lg border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-800">
            <img :src="result.outputImage" alt="去雾结果" class="block h-auto w-full" />
          </div>
        </div>

        <!-- 0x6E 服务器故障检测诊断与多折线图可视化 -->
        <div v-if="fault0x6EVisual" class="space-y-2.5">
          <div
            class="rounded-lg border px-3 py-2 text-xs"
            :class="
              (result.raw as Record<string, unknown>).status === '正常'
                ? 'border-emerald-200 bg-emerald-50/70 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300'
                : 'border-rose-200 bg-rose-50/70 text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300'
            "
          >
            <div class="flex flex-wrap items-center justify-between gap-2 font-semibold">
              <span>0x6E 诊断状态：{{ (result.raw as Record<string, unknown>).status }}</span>
              <span class="mono text-[11px]">峰值风险 {{ (result.raw as Record<string, unknown>).peak_risk_pct }}% · 告警 {{ (result.raw as Record<string, unknown>).fault_minutes }} 分钟</span>
            </div>
            <p class="mt-0.5 text-[11px] opacity-90">{{ (result.raw as Record<string, unknown>).diagnosis }}</p>
          </div>
          <Fault0x6ECharts :visual="fault0x6EVisual" compact />
        </div>

        <!-- 时序功率预测曲线可视化 -->
        <div v-if="forecastChart" class="space-y-2 rounded-lg border border-gray-200/80 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-900/60">
          <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span class="font-medium text-gray-800 dark:text-gray-200">未来 {{ forecastChart.horizon }}h 功率预测曲线</span>
            <div class="mono flex items-center gap-2.5 text-[11px] text-gray-500">
              <span>均值 <strong class="text-brand-600 dark:text-brand-400">{{ forecastChart.meanVal }} {{ forecastChart.unit }}</strong></span>
              <span>峰值 <strong class="text-gray-900 dark:text-white">{{ forecastChart.peakVal }} {{ forecastChart.unit }}</strong></span>
            </div>
          </div>
          <svg :viewBox="`0 0 ${forecastChart.W} ${forecastChart.H}`" class="block h-auto w-full">
            <defs>
              <linearGradient id="power-pred-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#6366f1" stop-opacity="0.28" />
                <stop offset="100%" stop-color="#6366f1" stop-opacity="0.02" />
              </linearGradient>
            </defs>
            <!-- 水平网格线与纵轴刻度 -->
            <g v-for="frac in [0, 0.5, 1]" :key="frac">
              <line
                :x1="forecastChart.padL"
                :x2="forecastChart.padL + forecastChart.plotW"
                :y1="forecastChart.padT + forecastChart.plotH * (1 - frac)"
                :y2="forecastChart.padT + forecastChart.plotH * (1 - frac)"
                stroke="currentColor"
                class="text-gray-200 dark:text-gray-800"
                stroke-width="1"
              />
              <text
                :x="forecastChart.padL - 5"
                :y="forecastChart.padT + forecastChart.plotH * (1 - frac) + 3"
                text-anchor="end"
                class="fill-gray-400 text-[9px]"
              >
                {{ Math.round(forecastChart.maxY * frac) }}
              </text>
            </g>
            <!-- 历史 / 预测分界线 -->
            <line
              v-if="forecastChart.splitX !== null"
              :x1="forecastChart.splitX"
              :x2="forecastChart.splitX"
              :y1="forecastChart.padT"
              :y2="forecastChart.padT + forecastChart.plotH"
              stroke="#94a3b8"
              stroke-dasharray="3 3"
              stroke-width="1"
            />
            <!-- 预测曲线面积 -->
            <path v-if="forecastChart.areaPath" :d="forecastChart.areaPath" fill="url(#power-pred-area)" />
            <!-- 历史 24h 曲线 -->
            <path v-if="forecastChart.histPath" :d="forecastChart.histPath" fill="none" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3 2" />
            <!-- 预测 24h 曲线 -->
            <path :d="forecastChart.predPath" fill="none" stroke="#6366f1" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
            <!-- 横轴提示 -->
            <text :x="forecastChart.padL" :y="forecastChart.H - 4" class="fill-gray-400 text-[9px]">
              {{ forecastChart.hasHistory ? '-24h 历史实测' : '+1h' }}
            </text>
            <text v-if="forecastChart.splitX !== null" :x="forecastChart.splitX" :y="forecastChart.H - 4" text-anchor="middle" class="fill-gray-500 text-[9px]">当前时刻</text>
            <text :x="forecastChart.padL + forecastChart.plotW" :y="forecastChart.H - 4" text-anchor="end" class="fill-brand-600 text-[9px] dark:fill-brand-400">
              +{{ forecastChart.horizon }}h 预测
            </text>
          </svg>
        </div>

        <!-- 分类结果 -->
        <div v-if="result.classification" class="space-y-1.5">
          <div v-for="c in result.classification" :key="c.label" class="text-sm">
            <div class="mb-0.5 flex justify-between">
              <span>{{ c.label }}</span><span class="mono text-gray-500">{{ (c.score * 100).toFixed(1) }}%</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
              <div class="h-full rounded-full bg-gradient-to-r from-brand-500 to-sky-400" :style="{ width: c.score * 100 + '%' }" />
            </div>
          </div>
        </div>

        <!-- 检测结果 -->
        <div v-if="result.detections">
          <label class="flex items-center gap-2 text-xs text-gray-500">
            置信度阈值
            <input v-model.number="thresh" type="range" min="0" max="1" step="0.05" class="flex-1 accent-brand-600" />
            <span class="mono w-8 text-right">{{ thresh.toFixed(2) }}</span>
          </label>
          <p class="mt-2 text-xs text-gray-500">检出 {{ visibleDets.length }} / {{ result.detections.length }} 个目标</p>
          <div class="mt-1.5 flex flex-wrap gap-1.5">
            <span v-for="(d, i) in visibleDets" :key="i" class="chip"><span class="size-2 rounded-sm" :style="{ background: labelColor(d.label) }" />{{ d.label }} {{ (d.score * 100).toFixed(0) }}%</span>
          </div>
        </div>

        <!-- 分割图例 -->
        <div v-if="segLegend.length" class="flex flex-wrap gap-1.5">
          <span v-for="[l, c] in segLegend" :key="l" class="chip"><span class="size-2.5 rounded-sm" :style="{ background: c }" />{{ l }}</span>
          <span class="text-xs text-gray-500">共 {{ result.segments!.length }} 个区域</span>
        </div>

        <div>
          <button class="inline-flex cursor-pointer items-center gap-1 text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200" @click="showJson = !showJson"><Braces class="size-3.5" />{{ showJson || !isImageTask ? '原始 JSON 输出' : '查看原始 JSON' }}</button>
          <pre v-if="showJson || !isImageTask" class="scroll-thin mt-1.5 max-h-64 overflow-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100">{{ JSON.stringify(result.raw, null, 2) }}</pre>
        </div>
      </template>
      <p class="text-[11px] leading-relaxed text-gray-400">上传的输入与推理结果仅保留 24 小时。推理请求与评测任务共享 GPU，显存不足时会排队。</p>
    </div>
  </div>
</template>
