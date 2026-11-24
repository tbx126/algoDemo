<script setup lang="ts">
import { computed, ref } from 'vue'
import { Activity, Cpu, LineChart, SlidersHorizontal, TrendingUp } from 'lucide-vue-next'

export interface Fault0x6ECase {
  id: string
  node?: string
  faultType: string
  accuracy?: number
  f1?: number
  predProb: number[]
  gtFault?: number[] | null
  telemetry: {
    cpu_pct: number[]
    gpu_util_pct: number[]
    gpu_mem_pct: number[]
    mem_pct: number[]
    disk_io_mbps: number[]
    gpu_temp_c: number[]
  }
}

export interface Fault0x6EVisual {
  tag?: string
  windowLen?: number
  cases: Fault0x6ECase[]
  thresholdCurve?: { threshold: number; f1: number; precision: number; recall: number }[]
  trainingCurve?: { epoch: number; loss: number; val_f1: number }[]
}

const props = defineProps<{
  visual: Fault0x6EVisual
  compact?: boolean
}>()

const activeCaseIdx = ref(0)
const hoverStep = ref<number | null>(null)

const currentCase = computed(() => props.visual.cases[activeCaseIdx.value] ?? props.visual.cases[0])

// 折线图通用坐标映射工具
function buildPolyline(vals: number[], w: number, h: number, padL: number, padR: number, padT: number, padB: number, maxY = 100, minY = 0) {
  const n = Math.max(2, vals.length)
  const plotW = w - padL - padR
  const plotH = h - padT - padB
  const xAt = (i: number) => padL + (i / (n - 1)) * plotW
  const yAt = (v: number) => padT + plotH * (1 - Math.max(0, Math.min(1, (v - minY) / Math.max(1e-6, maxY - minY))))
  const path = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')
  const area = vals.length >= 2
    ? `M${xAt(0).toFixed(1)},${(padT + plotH).toFixed(1)} ${vals.map((v, i) => `L${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ')} L${xAt(vals.length - 1).toFixed(1)},${(padT + plotH).toFixed(1)} Z`
    : ''
  return { path, area, xAt, yAt, plotW, plotH }
}

// 计算 Ground Truth 连续故障区间的背景高亮矩形
function gtFaultSpans(gt: number[] | null | undefined, xAt: (i: number) => number, stepW: number) {
  if (!gt?.length) return []
  const spans: { x: number; w: number }[] = []
  let start: number | null = null
  for (let i = 0; i < gt.length; i++) {
    if (gt[i] >= 50 && start === null) start = i
    if ((gt[i] < 50 || i === gt.length - 1) && start !== null) {
      const end = gt[i] >= 50 ? i : i - 1
      const x1 = Math.max(36, xAt(start) - stepW / 2)
      const x2 = xAt(end) + stepW / 2
      spans.push({ x: x1, w: Math.max(4, x2 - x1) })
      start = null
    }
  }
  return spans
}

const W = 640
const H_MAIN = 175
const H_TELE = 185
const PAD_L = 36
const PAD_R = 14
const PAD_T = 14
const PAD_B = 24

const mainChart = computed(() => {
  const c = currentCase.value
  if (!c) return null
  const pred = buildPolyline(c.predProb, W, H_MAIN, PAD_L, PAD_R, PAD_T, PAD_B, 100, 0)
  const gt = c.gtFault?.length ? buildPolyline(c.gtFault, W, H_MAIN, PAD_L, PAD_R, PAD_T, PAD_B, 100, 0) : null
  const stepW = pred.plotW / Math.max(1, c.predProb.length - 1)
  const spans = gtFaultSpans(c.gtFault, pred.xAt, stepW)
  return { pred, gt, spans, len: c.predProb.length }
})

const TELE_CHANNELS = [
  { key: 'cpu_pct', label: 'CPU %', color: '#3b82f6' },
  { key: 'gpu_util_pct', label: 'GPU算力 %', color: '#8b5cf6' },
  { key: 'gpu_mem_pct', label: 'GPU显存 %', color: '#ec4899' },
  { key: 'mem_pct', label: '内存 %', color: '#10b981' },
  { key: 'gpu_temp_c', label: 'GPU温度 ℃', color: '#f59e0b' },
] as const

const enabledChannels = ref<Set<string>>(new Set(TELE_CHANNELS.map((c) => c.key)))
function toggleChannel(k: string) {
  const next = new Set(enabledChannels.value)
  if (next.has(k) && next.size > 1) next.delete(k)
  else next.add(k)
  enabledChannels.value = next
}

const teleChart = computed(() => {
  const c = currentCase.value
  if (!c) return null
  const len = c.telemetry.cpu_pct.length
  const plotW = W - PAD_L - PAD_R
  const stepW = plotW / Math.max(1, len - 1)
  const xAt = (i: number) => PAD_L + (i / Math.max(1, len - 1)) * plotW
  const lines = TELE_CHANNELS.filter((ch) => enabledChannels.value.has(ch.key)).map((ch) => ({
    ...ch,
    poly: buildPolyline(c.telemetry[ch.key], W, H_TELE, PAD_L, PAD_R, PAD_T, PAD_B, 100, 0),
  }))
  const spans = gtFaultSpans(c.gtFault, xAt, stepW)
  return { lines, spans, xAt, len }
})

const W_SUB = 360
const H_SUB = 160

const threshChart = computed(() => {
  const pts = props.visual.thresholdCurve
  if (!pts?.length) return null
  return {
    f1: buildPolyline(pts.map((p) => p.f1), W_SUB, H_SUB, 34, 12, 14, 24, 100, 0),
    prec: buildPolyline(pts.map((p) => p.precision), W_SUB, H_SUB, 34, 12, 14, 24, 100, 0),
    rec: buildPolyline(pts.map((p) => p.recall), W_SUB, H_SUB, 34, 12, 14, 24, 100, 0),
    pts,
  }
})

const trainChart = computed(() => {
  const pts = props.visual.trainingCurve
  if (!pts?.length) return null
  const maxLoss = Math.max(0.5, ...pts.map((p) => p.loss))
  return {
    loss: buildPolyline(pts.map((p) => p.loss), W_SUB, H_SUB, 34, 34, 14, 24, maxLoss, 0),
    f1: buildPolyline(pts.map((p) => p.val_f1), W_SUB, H_SUB, 34, 34, 14, 24, 100, 0),
    maxLoss,
    pts,
  }
})

function onSvgMove(e: MouseEvent, len: number) {
  const svg = e.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  const relX = ((e.clientX - rect.left) / rect.width) * W
  const frac = (relX - PAD_L) / (W - PAD_L - PAD_R)
  if (frac < 0 || frac > 1) {
    hoverStep.value = null
    return
  }
  hoverStep.value = Math.round(frac * (len - 1))
}
</script>

<template>
  <div v-if="currentCase && mainChart && teleChart" class="space-y-4">
    <!-- 顶部样例切换栏（仅在多测试样例评测视图下展示） -->
    <div v-if="visual.cases.length > 1" class="flex flex-wrap items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span class="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] font-bold text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">0x6E</span>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">时序故障检测预测 vs Ground Truth 折线图</h3>
      </div>
      <div class="flex flex-wrap items-center gap-1">
        <button
          v-for="(c, idx) in visual.cases"
          :key="c.id"
          type="button"
          class="cursor-pointer rounded-lg border px-2.5 py-1 text-xs transition"
          :class="
            activeCaseIdx === idx
              ? 'border-brand-600 bg-brand-600 font-medium text-white'
              : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300'
          "
          @click="activeCaseIdx = idx; hoverStep = null"
        >
          {{ c.faultType }}
        </button>
      </div>
    </div>

    <!-- 折线图 1：预测故障概率曲线 vs Ground Truth -->
    <div class="rounded-xl border border-gray-200/80 bg-white p-3.5 dark:border-gray-800 dark:bg-gray-900/70">
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div class="flex items-center gap-2">
          <Activity class="size-3.5 text-rose-500" />
          <span class="font-semibold text-gray-900 dark:text-white">0x6E 故障风险预测曲线 vs Ground Truth</span>
          <span v-if="currentCase.node" class="mono text-[11px] text-gray-400">{{ currentCase.node }} · {{ currentCase.faultType }}</span>
        </div>
        <div class="flex flex-wrap items-center gap-3 text-[11px] text-gray-500">
          <span class="inline-flex items-center gap-1"><span class="h-0.5 w-3 rounded bg-rose-500" />0x6E 预测概率</span>
          <span v-if="mainChart.gt" class="inline-flex items-center gap-1"><span class="h-2.5 w-3 rounded-xs bg-amber-400/35 ring-1 ring-amber-500/60" />GT 故障区间</span>
          <span class="inline-flex items-center gap-1"><span class="h-0.5 w-3 border-t border-dashed border-gray-400" />阈值 50%</span>
        </div>
      </div>

      <!-- 悬浮读数条 -->
      <div v-if="hoverStep !== null" class="mono mb-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded-lg bg-gray-50 px-2.5 py-1 text-[11px] text-gray-600 dark:bg-gray-800/80 dark:text-gray-300">
        <span>时间步 <strong>t={{ hoverStep }}m</strong></span>
        <span>0x6E 风险 <strong class="text-rose-600 dark:text-rose-400">{{ currentCase.predProb[hoverStep] }}%</strong></span>
        <span v-if="currentCase.gtFault">GT 真值 <strong :class="currentCase.gtFault[hoverStep] >= 50 ? 'text-amber-600 dark:text-amber-400' : 'text-emerald-600 dark:text-emerald-400'">{{ currentCase.gtFault[hoverStep] >= 50 ? '故障 (1)' : '正常 (0)' }}</strong></span>
        <span>CPU {{ currentCase.telemetry.cpu_pct[hoverStep] }}%</span>
        <span>GPU {{ currentCase.telemetry.gpu_util_pct[hoverStep] }}%</span>
        <span>显存 {{ currentCase.telemetry.gpu_mem_pct[hoverStep] }}%</span>
        <span>内存 {{ currentCase.telemetry.mem_pct[hoverStep] }}%</span>
      </div>

      <svg
        :viewBox="`0 0 ${W} ${H_MAIN}`"
        class="block h-auto w-full select-none"
        @mousemove="onSvgMove($event, mainChart.len)"
        @mouseleave="hoverStep = null"
      >
        <defs>
          <linearGradient id="fault-0x6e-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#f43f5e" stop-opacity="0.28" />
            <stop offset="100%" stop-color="#f43f5e" stop-opacity="0.02" />
          </linearGradient>
        </defs>

        <!-- GT 真实故障高亮带 -->
        <rect
          v-for="(sp, i) in mainChart.spans"
          :key="'gt-' + i"
          :x="sp.x"
          :y="PAD_T"
          :width="sp.w"
          :height="H_MAIN - PAD_T - PAD_B"
          fill="rgba(245, 158, 11, 0.16)"
        />

        <!-- 水平网格线 -->
        <g v-for="val in [0, 50, 100]" :key="'g-' + val">
          <line
            :x1="PAD_L"
            :x2="W - PAD_R"
            :y1="mainChart.pred.yAt(val)"
            :y2="mainChart.pred.yAt(val)"
            :stroke="val === 50 ? '#94a3b8' : 'currentColor'"
            :class="val === 50 ? '' : 'text-gray-200 dark:text-gray-800'"
            :stroke-dasharray="val === 50 ? '4 3' : undefined"
            stroke-width="1"
          />
          <text :x="PAD_L - 6" :y="mainChart.pred.yAt(val) + 3" text-anchor="end" class="fill-gray-400 text-[9px]">{{ val }}%</text>
        </g>

        <!-- GT 阶跃折线 -->
        <path v-if="mainChart.gt" :d="mainChart.gt.path" fill="none" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4 2" />

        <!-- 0x6E 预测概率面积与主折线 -->
        <path :d="mainChart.pred.area" fill="url(#fault-0x6e-area)" />
        <path :d="mainChart.pred.path" fill="none" stroke="#f43f5e" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />

        <!-- 悬浮竖线与焦点圆点 -->
        <g v-if="hoverStep !== null">
          <line :x1="mainChart.pred.xAt(hoverStep)" :x2="mainChart.pred.xAt(hoverStep)" :y1="PAD_T" :y2="H_MAIN - PAD_B" stroke="#64748b" stroke-dasharray="2 2" stroke-width="1" />
          <circle :cx="mainChart.pred.xAt(hoverStep)" :cy="mainChart.pred.yAt(currentCase.predProb[hoverStep])" r="3.5" fill="#f43f5e" stroke="#fff" stroke-width="1.5" />
        </g>

        <!-- X 轴时间刻度 -->
        <text v-for="t in [0, 15, 30, 45, 59]" :key="'tx-' + t" :x="mainChart.pred.xAt(t)" :y="H_MAIN - 6" text-anchor="middle" class="fill-gray-400 text-[9px]">
          {{ t }}m
        </text>
      </svg>
    </div>

    <!-- 折线图 2：服务器多维硬件遥测同步折线图（CPU / GPU / 显存 / 内存 / 温度） -->
    <div class="rounded-xl border border-gray-200/80 bg-white p-3.5 dark:border-gray-800 dark:bg-gray-900/70">
      <div class="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div class="flex items-center gap-1.5">
          <Cpu class="size-3.5 text-brand-500" />
          <span class="font-semibold text-gray-900 dark:text-white">服务器多维硬件状态时序折线图（0x6E 遥测输入）</span>
        </div>
        <div class="flex flex-wrap items-center gap-1.5">
          <button
            v-for="ch in TELE_CHANNELS"
            :key="ch.key"
            type="button"
            class="inline-flex cursor-pointer items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] transition"
            :class="
              enabledChannels.has(ch.key)
                ? 'border-gray-200 bg-gray-50 font-medium text-gray-800 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100'
                : 'border-transparent text-gray-400 opacity-50'
            "
            @click="toggleChannel(ch.key)"
          >
            <span class="size-2 rounded-full" :style="{ background: ch.color }" />{{ ch.label }}
          </button>
        </div>
      </div>

      <svg
        :viewBox="`0 0 ${W} ${H_TELE}`"
        class="block h-auto w-full select-none"
        @mousemove="onSvgMove($event, teleChart.len)"
        @mouseleave="hoverStep = null"
      >
        <!-- 同步 GT 故障阴影区间 -->
        <rect
          v-for="(sp, i) in teleChart.spans"
          :key="'ts-' + i"
          :x="sp.x"
          :y="PAD_T"
          :width="sp.w"
          :height="H_TELE - PAD_T - PAD_B"
          fill="rgba(245, 158, 11, 0.13)"
        />

        <!-- 水平网格线 -->
        <g v-for="val in [0, 25, 50, 75, 100]" :key="'tg-' + val">
          <line :x1="PAD_L" :x2="W - PAD_R" :y1="PAD_T + (H_TELE - PAD_T - PAD_B) * (1 - val / 100)" :y2="PAD_T + (H_TELE - PAD_T - PAD_B) * (1 - val / 100)" stroke="currentColor" class="text-gray-100 dark:text-gray-800" stroke-width="1" />
          <text :x="PAD_L - 6" :y="PAD_T + (H_TELE - PAD_T - PAD_B) * (1 - val / 100) + 3" text-anchor="end" class="fill-gray-400 text-[9px]">{{ val }}</text>
        </g>

        <!-- 5 通道硬件指标折线 -->
        <path
          v-for="ln in teleChart.lines"
          :key="ln.key"
          :d="ln.poly.path"
          fill="none"
          :stroke="ln.color"
          stroke-width="1.7"
          stroke-linecap="round"
          stroke-linejoin="round"
        />

        <!-- 同步悬浮游标 -->
        <line v-if="hoverStep !== null" :x1="teleChart.xAt(hoverStep)" :x2="teleChart.xAt(hoverStep)" :y1="PAD_T" :y2="H_TELE - PAD_B" stroke="#64748b" stroke-dasharray="2 2" stroke-width="1" />

        <text v-for="t in [0, 15, 30, 45, 59]" :key="'tt-' + t" :x="teleChart.xAt(t)" :y="H_TELE - 6" text-anchor="middle" class="fill-gray-400 text-[9px]">
          {{ t }}m
        </text>
      </svg>
    </div>

    <!-- 折线图 3 & 4：阈值灵敏度曲线 + 训练收敛曲线（评测详情页完整模式展示） -->
    <div v-if="!compact && (threshChart || trainChart)" class="grid gap-4 md:grid-cols-2">
      <!-- 折线图 3：阈值灵敏度（F1 / Precision / Recall） -->
      <div v-if="threshChart" class="rounded-xl border border-gray-200/80 bg-white p-3.5 dark:border-gray-800 dark:bg-gray-900/70">
        <div class="mb-2 flex items-center justify-between gap-2 text-xs">
          <span class="flex items-center gap-1.5 font-semibold text-gray-900 dark:text-white"><SlidersHorizontal class="size-3.5 text-brand-500" />0x6E 判定阈值灵敏度折线图</span>
          <div class="flex items-center gap-2 text-[10px] text-gray-500">
            <span class="inline-flex items-center gap-1"><span class="h-0.5 w-2.5 bg-indigo-500" />F1</span>
            <span class="inline-flex items-center gap-1"><span class="h-0.5 w-2.5 bg-emerald-500" />Prec</span>
            <span class="inline-flex items-center gap-1"><span class="h-0.5 w-2.5 bg-amber-500" />Rec</span>
          </div>
        </div>
        <svg :viewBox="`0 0 ${W_SUB} ${H_SUB}`" class="block h-auto w-full">
          <g v-for="val in [0, 50, 100]" :key="'thg-' + val">
            <line x1="34" :x2="W_SUB - 12" :y1="threshChart.f1.yAt(val)" :y2="threshChart.f1.yAt(val)" stroke="currentColor" class="text-gray-100 dark:text-gray-800" stroke-width="1" />
            <text x="28" :y="threshChart.f1.yAt(val) + 3" text-anchor="end" class="fill-gray-400 text-[9px]">{{ val }}%</text>
          </g>
          <path :d="threshChart.prec.path" fill="none" stroke="#10b981" stroke-width="1.6" />
          <path :d="threshChart.rec.path" fill="none" stroke="#f59e0b" stroke-width="1.6" />
          <path :d="threshChart.f1.path" fill="none" stroke="#6366f1" stroke-width="2.1" />
          <text v-for="(lbl, idx) in ['0.1', '0.3', '0.5', '0.7', '0.9']" :key="lbl" :x="34 + (idx / 4) * (W_SUB - 46)" :y="H_SUB - 6" text-anchor="middle" class="fill-gray-400 text-[9px]">
            {{ lbl }}
          </text>
        </svg>
      </div>

      <!-- 折线图 4：训练收敛曲线（Loss & Val F1） -->
      <div v-if="trainChart" class="rounded-xl border border-gray-200/80 bg-white p-3.5 dark:border-gray-800 dark:bg-gray-900/70">
        <div class="mb-2 flex items-center justify-between gap-2 text-xs">
          <span class="flex items-center gap-1.5 font-semibold text-gray-900 dark:text-white"><TrendingUp class="size-3.5 text-emerald-500" />0x6E 训练收敛折线图（Loss / Val F1）</span>
          <div class="flex items-center gap-2 text-[10px] text-gray-500">
            <span class="inline-flex items-center gap-1"><span class="h-0.5 w-2.5 bg-rose-500" />Loss</span>
            <span class="inline-flex items-center gap-1"><span class="h-0.5 w-2.5 bg-indigo-500" />Val F1</span>
          </div>
        </div>
        <svg :viewBox="`0 0 ${W_SUB} ${H_SUB}`" class="block h-auto w-full">
          <g v-for="val in [0, 50, 100]" :key="'trg-' + val">
            <line x1="34" :x2="W_SUB - 34" :y1="trainChart.f1.yAt(val)" :y2="trainChart.f1.yAt(val)" stroke="currentColor" class="text-gray-100 dark:text-gray-800" stroke-width="1" />
            <text x="28" :y="trainChart.f1.yAt(val) + 3" text-anchor="end" class="fill-indigo-400 text-[9px]">{{ val }}%</text>
            <text :x="W_SUB - 28" :y="trainChart.f1.yAt(val) + 3" text-anchor="start" class="fill-rose-400 text-[9px]">{{ ((val / 100) * trainChart.maxLoss).toFixed(2) }}</text>
          </g>
          <path :d="trainChart.loss.path" fill="none" stroke="#f43f5e" stroke-width="1.8" stroke-dasharray="4 2" />
          <path :d="trainChart.f1.path" fill="none" stroke="#6366f1" stroke-width="2.1" />
          <text x="34" :y="H_SUB - 6" text-anchor="start" class="fill-gray-400 text-[9px]">Ep {{ trainChart.pts[0]?.epoch }}</text>
          <text :x="W_SUB / 2" :y="H_SUB - 6" text-anchor="middle" class="fill-gray-400 text-[9px]">Epoch</text>
          <text :x="W_SUB - 34" :y="H_SUB - 6" text-anchor="end" class="fill-gray-400 text-[9px]">Ep {{ trainChart.pts[trainChart.pts.length - 1]?.epoch }}</text>
        </svg>
      </div>
    </div>

    <p v-if="!compact" class="flex items-center gap-1.5 text-[11px] text-gray-400">
      <LineChart class="size-3.5" />0x6E 可视化：所有折线数据均由测试集真实遥测与 PyTorch 推理实时生成，移动鼠标至折线图可同步查看每分钟预测风险、GT 真值与服务器硬件读数。
    </p>
  </div>
</template>
