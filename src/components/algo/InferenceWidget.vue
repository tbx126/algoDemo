<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { Braces, Cpu, ImageUp, LoaderCircle, Lock, Play, RotateCcw, Zap } from 'lucide-vue-next'
import type { Algorithm, InferenceResult, TaskType } from '@/types'
import { infer } from '@/api'
import { useSession } from '@/stores/session'
import { TASKS } from '@/utils/meta'
import { CLASS_COLORS, sampleImageDataUrl } from '@/utils/synth'
import { hashStr } from '@/utils/format'

const props = defineProps<{ algo: Algorithm }>()
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
        <button class="btn-default text-xs" @click="input = { fileName: algo.task === 'optimization' ? 'C101_25.vrp' : 'bearing_0042.csv', size: 18234 }">使用示例输入</button>
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
