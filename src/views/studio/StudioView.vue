<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowRight,
  Box,
  Check,
  ChevronDown,
  ChevronUp,
  Code2,
  Database,
  Eraser,
  FlaskConical,
  Link2,
  LoaderCircle,
  Maximize2,
  Play,
  Plus,
  Redo2,
  Rocket,
  Sliders,
  Sparkles,
  Trash2,
  Undo2,
  Wand2,
  Workflow,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'
import { REAL_DS_IDS, listAlgorithms, listDatasets } from '@/api'
import type { Algorithm, Dataset, TaskType } from '@/types'
import { algoFullLabel } from '@/utils/display'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import Modal from '@/components/ui/Modal.vue'

type NodeType = 'dataset' | 'preprocess' | 'algorithm' | 'postprocess' | 'evaluator'

interface StudioNode {
  id: string
  type: NodeType
  label: string
  x: number
  y: number
  config: Record<string, any>
}

interface StudioEdge {
  id: string
  source: string
  target: string
}

interface NodeIOPortData {
  name: string
  kind: 'image' | 'label' | 'text' | 'classification' | 'metrics' | 'dataset'
  value?: string
  shape?: string
  fromNode?: string
  preview?: string | null
  items?: { label: string; score: number }[]
  branches?: { branch: string; metrics: Record<string, any>; latencyMs: number; previewImage?: string | null }[]
}

interface NodeRunResult {
  nodeId: string
  type: NodeType
  status: 'ok' | 'error'
  latencyMs: number
  summary: string
  inputPreview?: string | null
  previewImage?: string | null
  inputShape?: string | null
  outputShape?: string | null
  gtImage?: string | null
  gtLabel?: string | null
  classification?: { label: string; score: number }[]
  branches?: { branch: string; metrics: Record<string, any>; latencyMs: number; previewImage?: string | null }[]
  inputs?: NodeIOPortData[]
  outputs?: NodeIOPortData[]
}

interface HistorySnapshot {
  nodes: StudioNode[]
  edges: StudioEdge[]
  selectedNodeId: string | null
  desc: string
}

const router = useRouter()
const { user, state } = useSession()

const allAlgos = ref<Algorithm[]>([])
const allDatasets = ref<Dataset[]>([])

const realDatasets = computed(() => allDatasets.value.filter((d) => REAL_DS_IDS.has(d.id) && d.test))
const runnableAlgos = computed(() =>
  allAlgos.value.filter((a) => a.versions.some((v) => v.status === 'ready')),
)

// ==================== 节点组件库与输入/输出契约 ====================
const PALETTE: {
  type: NodeType
  label: string
  desc: string
  inSpec: string | null
  outSpec: string | null
  color: string
  icon: any
  defaultConfig: () => Record<string, any>
}[] = [
  {
    type: 'dataset',
    label: '数据集输入',
    desc: '选择真实测试集与样本',
    inSpec: null,
    outSpec: '图像 + 真值 GT',
    color: 'border-sky-300 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/50 dark:text-sky-300',
    icon: Database,
    defaultConfig: () => ({ datasetId: 'Admin/dehaze-dataset', sampleIndex: 0 }),
  },
  {
    type: 'preprocess',
    label: '图像预处理',
    desc: '伽马 / 对比度 / 去噪 / 锐化',
    inSpec: '待测图像',
    outSpec: '增强图像',
    color: 'border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300',
    icon: Sliders,
    defaultConfig: () => ({ gamma: 1.0, contrast: 1.05, sharpen: 0.2, denoise: false, maxSide: 0 }),
  },
  {
    type: 'algorithm',
    label: '已有算法节点',
    desc: '挂载平台任意已就绪算法',
    inSpec: '输入图像',
    outSpec: '图像 / 预测',
    color: 'border-indigo-300 bg-indigo-50 text-indigo-700 dark:border-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-300',
    icon: Box,
    defaultConfig: () => ({ algorithmId: 'Admin/dehaze-deanet', version: 'v1.0.0' }),
  },
  {
    type: 'postprocess',
    label: '后处理 / 融合',
    desc: '残差融合 / 饱和度 / 锐化',
    inSpec: '算法输出图',
    outSpec: '优化图像',
    color: 'border-violet-300 bg-violet-50 text-violet-700 dark:border-violet-800 dark:bg-violet-950/50 dark:text-violet-300',
    icon: Wand2,
    defaultConfig: () => ({ blendOriginal: 0.08, sharpen: 0.3, saturation: 1.05, gamma: 1.0, autoContrast: false }),
  },
  {
    type: 'evaluator',
    label: '评测指标输出',
    desc: 'PSNR / SSIM / 准确率对比',
    inSpec: '多分支 + GT',
    outSpec: '指标报告',
    color: 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
    icon: FlaskConical,
    defaultConfig: () => ({ metricSet: 'auto' }),
  },
]

const NODE_HEADER_CLS: Record<NodeType, string> = {
  dataset: 'bg-sky-500/12 text-sky-700 dark:text-sky-300 border-sky-200/80 dark:border-sky-900',
  preprocess: 'bg-amber-500/12 text-amber-700 dark:text-amber-300 border-amber-200/80 dark:border-amber-900',
  algorithm: 'bg-indigo-500/12 text-indigo-700 dark:text-indigo-300 border-indigo-200/80 dark:border-indigo-900',
  postprocess: 'bg-violet-500/12 text-violet-700 dark:text-violet-300 border-violet-200/80 dark:border-violet-900',
  evaluator: 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300 border-emerald-200/80 dark:border-emerald-900',
}

const NODE_ICON: Record<NodeType, any> = {
  dataset: Database,
  preprocess: Sliders,
  algorithm: Box,
  postprocess: Wand2,
  evaluator: FlaskConical,
}

function portLabelsFor(node: StudioNode): { inLabel: string | null; outLabel: string | null; inDot: string; outDot: string } {
  if (node.type === 'dataset') return { inLabel: null, outLabel: '图像 + GT', inDot: '', outDot: 'bg-sky-500' }
  if (node.type === 'preprocess') return { inLabel: '图像 (RGB)', outLabel: '增强图像', inDot: 'bg-sky-500', outDot: 'bg-amber-500' }
  if (node.type === 'algorithm') {
    const aid = String(node.config.algorithmId || '')
    const isCls = aid.includes('cat-dog') || aid.includes('cls')
    return {
      inLabel: '图像 (RGB)',
      outLabel: isCls ? '分类预测' : '输出图像',
      inDot: 'bg-sky-500',
      outDot: 'bg-indigo-500',
    }
  }
  if (node.type === 'postprocess') return { inLabel: '算法图像', outLabel: '融合图像', inDot: 'bg-indigo-500', outDot: 'bg-violet-500' }
  return { inLabel: '分支输出 + GT', outLabel: null, inDot: 'bg-emerald-500', outDot: '' }
}

// ==================== 画布状态 & 撤销/重做历史栈 (Ctrl+Z / Ctrl+Y) ====================
const nodes = ref<StudioNode[]>([])
const edges = ref<StudioEdge[]>([])
const selectedNodeId = ref<string | null>(null)
const connectingFrom = ref<string | null>(null)
const pointerCanvasPos = reactive({ x: 0, y: 0 })
const nodeResults = ref<Record<string, NodeRunResult>>({})
const batchResult = ref<{ datasetId: string; samplesEvaluated: number; durationSec: number; branches: { branch: string; samples: number; metrics: Record<string, number>; latencyMs: number }[] } | null>(null)
const resultsOpen = ref(true)
const activePreset = ref<'dehaze-opt' | 'dehaze-compare' | 'catdog-opt' | null>('dehaze-opt')

const MAX_HISTORY = 50
const undoStack = ref<HistorySnapshot[]>([])
const redoStack = ref<HistorySnapshot[]>([])

function makeSnapshot(desc: string): HistorySnapshot {
  return {
    nodes: JSON.parse(JSON.stringify(nodes.value)),
    edges: JSON.parse(JSON.stringify(edges.value)),
    selectedNodeId: selectedNodeId.value,
    desc,
  }
}

function snapshotSignature(s: Pick<HistorySnapshot, 'nodes' | 'edges'>): string {
  return JSON.stringify({ n: s.nodes, e: s.edges })
}

function pushUndoSnapshot(snap: HistorySnapshot) {
  const top = undoStack.value[undoStack.value.length - 1]
  if (top && snapshotSignature(top) === snapshotSignature(snap)) return
  undoStack.value.push(snap)
  if (undoStack.value.length > MAX_HISTORY) undoStack.value.shift()
  redoStack.value = []
}

function captureHistory(desc: string) {
  pushUndoSnapshot(makeSnapshot(desc))
}

function applySnapshot(snap: HistorySnapshot) {
  nodes.value = JSON.parse(JSON.stringify(snap.nodes))
  edges.value = JSON.parse(JSON.stringify(snap.edges))
  selectedNodeId.value = snap.selectedNodeId && nodes.value.some((n) => n.id === snap.selectedNodeId) ? snap.selectedNodeId : null
  connectingFrom.value = null
  const validIds = new Set(nodes.value.map((n) => n.id))
  for (const k of Object.keys(nodeResults.value)) {
    if (!validIds.has(k)) delete nodeResults.value[k]
  }
}

function undo() {
  if (!undoStack.value.length) return
  const prev = undoStack.value.pop()!
  redoStack.value.push(makeSnapshot(prev.desc))
  applySnapshot(prev)
  toast(`已撤销：${prev.desc}`, 'info')
}

function redo() {
  if (!redoStack.value.length) return
  const next = redoStack.value.pop()!
  undoStack.value.push(makeSnapshot(next.desc))
  applySnapshot(next)
  toast(`已重做：${next.desc}`, 'info')
}

// 检查器内编辑参数时，聚焦/按下记录编辑前快照，失焦/松开仅当值确实变化时入栈 1 条历史
let pendingEditSnap: HistorySnapshot | null = null
function beginConfigEdit(desc: string) {
  if (!pendingEditSnap) {
    pendingEditSnap = makeSnapshot(desc)
  }
}
function commitConfigEdit() {
  if (!pendingEditSnap) return
  const before = pendingEditSnap
  pendingEditSnap = null
  if (snapshotSignature(before) !== snapshotSignature({ nodes: nodes.value, edges: edges.value })) {
    pushUndoSnapshot(before)
  }
}

// ==================== 预设模板 ====================
function loadPreset(preset: 'dehaze-opt' | 'dehaze-compare' | 'catdog-opt', recordHistory = true) {
  if (recordHistory && nodes.value.length) {
    captureHistory('切换模板')
  }
  activePreset.value = preset
  nodeResults.value = {}
  batchResult.value = null
  connectingFrom.value = null
  if (preset === 'dehaze-opt') {
    nodes.value = [
      { id: 'n1', type: 'dataset', label: '去雾测试集', x: 20, y: 165, config: { datasetId: 'Admin/dehaze-dataset', sampleIndex: 0 } },
      { id: 'n2', type: 'algorithm', label: 'DEA-Net 基线', x: 320, y: 30, config: { algorithmId: 'Admin/dehaze-deanet', version: 'v1.0.0' } },
      { id: 'n3', type: 'preprocess', label: '轻度对比度预处理', x: 320, y: 275, config: { gamma: 0.98, contrast: 1.04, sharpen: 0.1, denoise: false, maxSide: 0 } },
      { id: 'n4', type: 'algorithm', label: 'DEA-Net（优化支路）', x: 620, y: 275, config: { algorithmId: 'Admin/dehaze-deanet', version: 'v1.0.0' } },
      { id: 'n5', type: 'postprocess', label: '细节锐化 + 残差融合', x: 920, y: 275, config: { blendOriginal: 0.05, sharpen: 0.25, saturation: 1.04, gamma: 1.0, autoContrast: false } },
      { id: 'n6', type: 'evaluator', label: 'PSNR / SSIM 对比评测', x: 1220, y: 155, config: { metricSet: 'auto' } },
    ]
    edges.value = [
      { id: 'e1', source: 'n1', target: 'n2' },
      { id: 'e2', source: 'n2', target: 'n6' },
      { id: 'e3', source: 'n1', target: 'n3' },
      { id: 'e4', source: 'n3', target: 'n4' },
      { id: 'e5', source: 'n4', target: 'n5' },
      { id: 'e6', source: 'n5', target: 'n6' },
    ]
    selectedNodeId.value = 'n5'
  } else if (preset === 'dehaze-compare') {
    nodes.value = [
      { id: 'n1', type: 'dataset', label: '去雾测试集', x: 40, y: 205, config: { datasetId: 'Admin/dehaze-dataset', sampleIndex: 2 } },
      { id: 'n2', type: 'algorithm', label: 'DEA-Net（现代强基线）', x: 380, y: 35, config: { algorithmId: 'Admin/dehaze-deanet', version: 'v1.0.0' } },
      { id: 'n3', type: 'algorithm', label: 'FFA-Net（注意力 CNN）', x: 380, y: 205, config: { algorithmId: 'Admin/dehaze-ffanet', version: 'v1.0.0' } },
      { id: 'n4', type: 'algorithm', label: 'DCP（暗通道先验）', x: 380, y: 375, config: { algorithmId: 'Admin/dehaze-dcp', version: 'v1.0.0' } },
      { id: 'n5', type: 'evaluator', label: '三路线横向评测', x: 740, y: 205, config: { metricSet: 'auto' } },
    ]
    edges.value = [
      { id: 'e1', source: 'n1', target: 'n2' },
      { id: 'e2', source: 'n1', target: 'n3' },
      { id: 'e3', source: 'n1', target: 'n4' },
      { id: 'e4', source: 'n2', target: 'n5' },
      { id: 'e5', source: 'n3', target: 'n5' },
      { id: 'e6', source: 'n4', target: 'n5' },
    ]
    selectedNodeId.value = 'n1'
  } else {
    nodes.value = [
      { id: 'n1', type: 'dataset', label: '猫狗测试集', x: 40, y: 175, config: { datasetId: 'Admin/cat-dog-dataset', sampleIndex: 0 } },
      { id: 'n2', type: 'preprocess', label: '亮度与对比度增强', x: 360, y: 175, config: { gamma: 1.0, contrast: 1.08, sharpen: 0.15, denoise: false, maxSide: 0 } },
      { id: 'n3', type: 'algorithm', label: '猫狗识别 ConvNeXt', x: 680, y: 175, config: { algorithmId: 'Admin/cat-dog-classifier', version: 'v3.0.0' } },
      { id: 'n4', type: 'evaluator', label: '准确率评测', x: 1000, y: 175, config: { metricSet: 'auto' } },
    ]
    edges.value = [
      { id: 'e1', source: 'n1', target: 'n2' },
      { id: 'e2', source: 'n2', target: 'n3' },
      { id: 'e3', source: 'n3', target: 'n4' },
    ]
    selectedNodeId.value = 'n3'
  }
  nextTick(() => fitView())
}

function clearCanvas() {
  if (!nodes.value.length) return
  captureHistory('清空画布')
  nodes.value = []
  edges.value = []
  selectedNodeId.value = null
  connectingFrom.value = null
  nodeResults.value = {}
  batchResult.value = null
  activePreset.value = null
}

loadPreset('dehaze-opt', false)

// ==================== 节点连接关系查询（供卡片与检查器直观展示 I/O） ====================
const nodeMap = computed(() => new Map(nodes.value.map((n) => [n.id, n])))

function incomingNodesOf(nodeId: string): { edgeId: string; node: StudioNode }[] {
  return edges.value
    .filter((e) => e.target === nodeId)
    .map((e) => ({ edgeId: e.id, node: nodeMap.value.get(e.source)! }))
    .filter((x) => !!x.node)
}

function outgoingNodesOf(nodeId: string): { edgeId: string; node: StudioNode }[] {
  return edges.value
    .filter((e) => e.source === nodeId)
    .map((e) => ({ edgeId: e.id, node: nodeMap.value.get(e.target)! }))
    .filter((x) => !!x.node)
}

const selectedNode = computed(() => nodes.value.find((n) => n.id === selectedNodeId.value) ?? null)
const selectedResult = computed(() => (selectedNodeId.value ? nodeResults.value[selectedNodeId.value] ?? null : null))
const selectedIncoming = computed(() => (selectedNodeId.value ? incomingNodesOf(selectedNodeId.value) : []))
const selectedOutgoing = computed(() => (selectedNodeId.value ? outgoingNodesOf(selectedNodeId.value) : []))
const selectedAlgoVersions = computed(() => {
  if (selectedNode.value?.type !== 'algorithm') return []
  const a = allAlgos.value.find((x) => x.id === selectedNode.value!.config.algorithmId)
  return a?.versions.filter((v) => v.status === 'ready') ?? [{ version: 'v1.0.0' }]
})

// 图片大图弹窗
const lightbox = ref<{ title: string; src: string; subtitle?: string } | null>(null)
const lightboxOpen = computed({ get: () => !!lightbox.value, set: (v) => !v && (lightbox.value = null) })
function openLightbox(title: string, src: string, subtitle?: string) {
  lightbox.value = { title, src, subtitle }
}

// ==================== 无限画布平移 / Ctrl+滚轮缩放 / 节点拖拽与连线 ====================
const canvasEl = ref<HTMLElement>()
let nodeSeq = 20

const NODE_W = 264
const PORT_Y = 49
const MIN_ZOOM = 0.3
const MAX_ZOOM = 2.2

const viewport = reactive({ x: 32, y: 32, zoom: 1 })
const spacePressed = ref(false)
const panState = reactive({ active: false, moved: false, startX: 0, startY: 0, origX: 0, origY: 0 })

const canvasBgStyle = computed(() => {
  const gap = Math.max(10, Math.round(20 * viewport.zoom))
  return {
    backgroundImage: 'radial-gradient(rgba(148, 163, 184, 0.32) 1px, transparent 1px)',
    backgroundSize: `${gap}px ${gap}px`,
    backgroundPosition: `${Math.round(viewport.x)}px ${Math.round(viewport.y)}px`,
  }
})

// 使用整数像素 2D translate（避免 will-change / translate3d 导致 Chromium 将节点光栅化为模糊纹理）
const worldStyle = computed(() => {
  const tx = Math.round(viewport.x)
  const ty = Math.round(viewport.y)
  return {
    transform: Math.abs(viewport.zoom - 1) < 1e-3 ? `translate(${tx}px, ${ty}px)` : `translate(${tx}px, ${ty}px) scale(${viewport.zoom})`,
  }
})

function clientToWorld(clientX: number, clientY: number) {
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: (clientX - rect.left - viewport.x) / viewport.zoom,
    y: (clientY - rect.top - viewport.y) / viewport.zoom,
  }
}

function clampZoom(z: number) {
  return Number(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z)).toFixed(3))
}

function zoomAtClientPoint(nextZoom: number, clientX: number, clientY: number) {
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) {
    viewport.zoom = clampZoom(nextZoom)
    return
  }
  const mx = clientX - rect.left
  const my = clientY - rect.top
  const worldX = (mx - viewport.x) / viewport.zoom
  const worldY = (my - viewport.y) / viewport.zoom
  viewport.zoom = clampZoom(nextZoom)
  viewport.x = Math.round(mx - worldX * viewport.zoom)
  viewport.y = Math.round(my - worldY * viewport.zoom)
}

function zoomBy(factor: number) {
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) {
    viewport.zoom = clampZoom(viewport.zoom * factor)
    return
  }
  zoomAtClientPoint(viewport.zoom * factor, rect.left + rect.width / 2, rect.top + rect.height / 2)
}

function resetZoom() {
  const rect = canvasEl.value?.getBoundingClientRect()
  if (!rect) {
    viewport.zoom = 1
    return
  }
  zoomAtClientPoint(1, rect.left + rect.width / 2, rect.top + rect.height / 2)
}

function fitView() {
  const el = canvasEl.value
  if (!el || !nodes.value.length) {
    viewport.x = 32
    viewport.y = 32
    viewport.zoom = 1
    return
  }
  const rect = el.getBoundingClientRect()
  if (rect.width < 40 || rect.height < 40) return
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of nodes.value) {
    const estH = nodeResults.value[n.id] ? 210 : 148
    minX = Math.min(minX, n.x)
    minY = Math.min(minY, n.y)
    maxX = Math.max(maxX, n.x + NODE_W)
    maxY = Math.max(maxY, n.y + estH)
  }
  const contentW = Math.max(240, maxX - minX)
  const contentH = Math.max(160, maxY - minY)
  const pad = 36
  const scaleX = (rect.width - pad * 2) / contentW
  const scaleY = (rect.height - pad * 2) / contentH
  const rawZoom = Math.min(1, scaleX, scaleY)
  const targetZoom = clampZoom(Math.floor(rawZoom * 20) / 20 || rawZoom)
  viewport.zoom = targetZoom
  viewport.x = Math.round((rect.width - contentW * targetZoom) / 2 - minX * targetZoom)
  viewport.y = Math.round((rect.height - contentH * targetZoom) / 2 - minY * targetZoom)
}

function onCanvasWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    // 支持鼠标 Ctrl+滚轮 以及 触控板双指捏合缩放，以光标为中心缩放
    const factor = Math.exp(-e.deltaY * 0.0018)
    zoomAtClientPoint(viewport.zoom * factor, e.clientX, e.clientY)
    return
  }
  // 普通滚轮 / 触控板双指滚动：自由平移画布（按住 Shift 滚轮横向平移）
  const dx = e.shiftKey && e.deltaX === 0 ? e.deltaY : e.deltaX
  const dy = e.shiftKey && e.deltaX === 0 ? 0 : e.deltaY
  viewport.x = Math.round(viewport.x - dx)
  viewport.y = Math.round(viewport.y - dy)
}

function startPan(e: PointerEvent) {
  panState.active = true
  panState.moved = false
  panState.startX = e.clientX
  panState.startY = e.clientY
  panState.origX = viewport.x
  panState.origY = viewport.y
  window.addEventListener('pointermove', onPanMove)
  window.addEventListener('pointerup', onPanEnd)
}

function onPanMove(e: PointerEvent) {
  if (!panState.active) return
  const dx = e.clientX - panState.startX
  const dy = e.clientY - panState.startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) panState.moved = true
  viewport.x = Math.round(panState.origX + dx)
  viewport.y = Math.round(panState.origY + dy)
}

function onPanEnd() {
  const wasClick = !panState.moved
  panState.active = false
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', onPanEnd)
  if (wasClick) {
    selectedNodeId.value = null
    connectingFrom.value = null
  }
}

function onCanvasPointerDown(e: PointerEvent) {
  const target = e.target as HTMLElement
  if (target.closest('[data-studio-hud]')) return
  // 中键拖拽 或 按住空格拖拽：在画布任意位置（含节点上方）均可平移画布
  if (e.button === 1 || (e.button === 0 && spacePressed.value)) {
    e.preventDefault()
    startPan(e)
    return
  }
  // 左键在画布空白处按住：自由拖动画布
  if (e.button === 0 && !target.closest('[data-studio-node], [data-studio-edge]')) {
    e.preventDefault()
    startPan(e)
  }
}

function addNode(type: NodeType, x?: number, y?: number) {
  const item = PALETTE.find((p) => p.type === type)!
  captureHistory(`添加${item.label}`)
  const id = `n${++nodeSeq}`
  let nx = x
  let ny = y
  if (nx === undefined || ny === undefined) {
    const rect = canvasEl.value?.getBoundingClientRect()
    const center = rect
      ? clientToWorld(rect.left + rect.width / 2, rect.top + rect.height / 2)
      : { x: 320, y: 200 }
    const jitterX = ((nodeSeq * 37) % 140) - 70
    const jitterY = ((nodeSeq * 29) % 100) - 50
    nx = Math.round((center.x - NODE_W / 2 + jitterX) / 5) * 5
    ny = Math.round((center.y - 60 + jitterY) / 5) * 5
  }
  nodes.value.push({
    id,
    type,
    label: item.label,
    x: nx,
    y: ny,
    config: item.defaultConfig(),
  })
  selectedNodeId.value = id
  activePreset.value = null
}

function onPaletteDragStart(e: DragEvent, type: NodeType) {
  e.dataTransfer?.setData('text/studio-node-type', type)
}

function onCanvasDrop(e: DragEvent) {
  const type = e.dataTransfer?.getData('text/studio-node-type') as NodeType | undefined
  if (!type || !canvasEl.value) return
  const pt = clientToWorld(e.clientX, e.clientY)
  const x = Math.round((pt.x - NODE_W / 2) / 5) * 5
  const y = Math.round((pt.y - 36) / 5) * 5
  addNode(type, x, y)
}

function onCanvasPointerMove(e: PointerEvent) {
  if (!connectingFrom.value || !canvasEl.value) return
  const pt = clientToWorld(e.clientX, e.clientY)
  pointerCanvasPos.x = pt.x
  pointerCanvasPos.y = pt.y
}

const dragState = reactive({ id: '', startX: 0, startY: 0, origX: 0, origY: 0 })
let beforeDragSnap: HistorySnapshot | null = null

function startDragNode(e: PointerEvent, node: StudioNode) {
  if (e.button === 1 || spacePressed.value) return
  if ((e.target as HTMLElement).closest('button, img[data-zoomable]')) return
  e.stopPropagation()
  selectedNodeId.value = node.id
  dragState.id = node.id
  dragState.startX = e.clientX
  dragState.startY = e.clientY
  dragState.origX = node.x
  dragState.origY = node.y
  beforeDragSnap = makeSnapshot(`移动「${node.label}」`)
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
}

function onDragMove(e: PointerEvent) {
  const n = nodes.value.find((x) => x.id === dragState.id)
  if (!n) return
  const dx = (e.clientX - dragState.startX) / viewport.zoom
  const dy = (e.clientY - dragState.startY) / viewport.zoom
  n.x = Math.round((dragState.origX + dx) / 5) * 5
  n.y = Math.round((dragState.origY + dy) / 5) * 5
}

function onDragEnd() {
  const movedNode = nodes.value.find((x) => x.id === dragState.id)
  if (movedNode && beforeDragSnap && (movedNode.x !== dragState.origX || movedNode.y !== dragState.origY)) {
    pushUndoSnapshot(beforeDragSnap)
  }
  beforeDragSnap = null
  dragState.id = ''
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
}

function removeNode(id: string) {
  const target = nodeMap.value.get(id)
  captureHistory(`删除「${target?.label ?? '节点'}」`)
  nodes.value = nodes.value.filter((n) => n.id !== id)
  edges.value = edges.value.filter((e) => e.source !== id && e.target !== id)
  if (selectedNodeId.value === id) selectedNodeId.value = null
  if (connectingFrom.value === id) connectingFrom.value = null
  delete nodeResults.value[id]
}

function clickOutputPort(nodeId: string, e: MouseEvent) {
  if (connectingFrom.value === nodeId) {
    connectingFrom.value = null
    return
  }
  connectingFrom.value = nodeId
  const pt = clientToWorld(e.clientX, e.clientY)
  pointerCanvasPos.x = pt.x
  pointerCanvasPos.y = pt.y
}

function clickInputPort(targetId: string) {
  if (!connectingFrom.value || connectingFrom.value === targetId) {
    connectingFrom.value = null
    return
  }
  const exists = edges.value.some((e) => e.source === connectingFrom.value && e.target === targetId)
  if (!exists) {
    const srcName = nodeMap.value.get(connectingFrom.value)?.label ?? ''
    const dstName = nodeMap.value.get(targetId)?.label ?? ''
    captureHistory(`连接 ${srcName} → ${dstName}`)
    edges.value.push({ id: `e${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, source: connectingFrom.value, target: targetId })
  }
  connectingFrom.value = null
}

function removeEdge(id: string) {
  const e = edges.value.find((x) => x.id === id)
  const srcName = e ? (nodeMap.value.get(e.source)?.label ?? '') : ''
  const dstName = e ? (nodeMap.value.get(e.target)?.label ?? '') : ''
  captureHistory(`断开 ${srcName} → ${dstName}`)
  edges.value = edges.value.filter((x) => x.id !== id)
}

function edgePath(e: StudioEdge) {
  const s = nodeMap.value.get(e.source)
  const t = nodeMap.value.get(e.target)
  if (!s || !t) return ''
  const x1 = s.x + NODE_W
  const y1 = s.y + PORT_Y
  const x2 = t.x
  const y2 = t.y + PORT_Y
  const dx = Math.max(52, Math.abs(x2 - x1) * 0.45)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
}

const draftEdgePath = computed(() => {
  if (!connectingFrom.value) return ''
  const s = nodeMap.value.get(connectingFrom.value)
  if (!s) return ''
  const x1 = s.x + NODE_W
  const y1 = s.y + PORT_Y
  const x2 = pointerCanvasPos.x
  const y2 = pointerCanvasPos.y
  const dx = Math.max(48, Math.abs(x2 - x1) * 0.45)
  return `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`
})

function isEdgeHighlighted(e: StudioEdge) {
  return !!selectedNodeId.value && (e.source === selectedNodeId.value || e.target === selectedNodeId.value)
}

// ==================== 全局键盘快捷键：Ctrl+Z / Ctrl+Y / Escape / Delete ====================
function isTextEditingElement(el: Element | null): boolean {
  if (!el) return false
  const tag = el.tagName.toLowerCase()
  if (tag === 'textarea') return true
  if (tag === 'input') {
    const type = (el as HTMLInputElement).type.toLowerCase()
    return ['text', 'search', 'url', 'email', 'password', 'number'].includes(type)
  }
  return (el as HTMLElement).isContentEditable
}

function onKeyDown(e: KeyboardEvent) {
  if (publishOpen.value || lightboxOpen.value) return
  const key = e.key.toLowerCase()
  const mod = e.ctrlKey || e.metaKey

  if (mod && key === 'z' && !e.shiftKey) {
    if (isTextEditingElement(document.activeElement)) return
    e.preventDefault()
    undo()
    return
  }
  if ((mod && key === 'y') || (mod && key === 'z' && e.shiftKey)) {
    if (isTextEditingElement(document.activeElement)) return
    e.preventDefault()
    redo()
    return
  }
  if (mod && key === '0') {
    e.preventDefault()
    fitView()
    return
  }
  if (mod && (key === '=' || key === '+')) {
    e.preventDefault()
    zoomBy(1.15)
    return
  }
  if (mod && key === '-') {
    e.preventDefault()
    zoomBy(1 / 1.15)
    return
  }
  if (e.code === 'Space' && !isTextEditingElement(document.activeElement)) {
    const tag = document.activeElement?.tagName.toLowerCase() ?? ''
    if (!['button', 'select', 'input', 'a'].includes(tag)) e.preventDefault()
    spacePressed.value = true
    return
  }
  if (key === 'escape') {
    connectingFrom.value = null
    return
  }
  if ((key === 'delete' || key === 'backspace') && selectedNodeId.value) {
    if (isTextEditingElement(document.activeElement)) return
    e.preventDefault()
    removeNode(selectedNodeId.value)
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (e.code === 'Space') spacePressed.value = false
}

function onWindowBlur() {
  spacePressed.value = false
}

onMounted(async () => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('blur', onWindowBlur)
  nextTick(() => fitView())
  const [aRes, dRes] = await Promise.all([listAlgorithms({ pageSize: 200 }), listDatasets({ pageSize: 200 })])
  allAlgos.value = aRes.items
  allDatasets.value = dRes.items
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('blur', onWindowBlur)
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', onPanEnd)
})

// ==================== 真实执行：单图试跑 / 批量评测 / 发布为新算法 ====================
const runningSample = ref(false)
const runningBatch = ref(false)
const batchCount = ref(12)

async function runSample() {
  if (!nodes.value.length) return toast('请先添加节点', 'error')
  runningSample.value = true
  try {
    const resp = await fetch('/real-api/studio/run-sample', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes: nodes.value, edges: edges.value }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '试跑失败' }))
      throw new Error(err.detail || '试跑失败')
    }
    const data = await resp.json()
    nodeResults.value = data.nodes || {}
    resultsOpen.value = true
    toast('单图试跑完成，已刷新各节点的输入与输出实况')
  } catch (e: any) {
    toast(e?.message || '试跑失败', 'error')
  } finally {
    runningSample.value = false
  }
}

async function runBatchEval() {
  if (!nodes.value.length) return toast('请先添加节点', 'error')
  runningBatch.value = true
  try {
    const resp = await fetch('/real-api/studio/run-eval', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes: nodes.value, edges: edges.value, sampleCount: batchCount.value }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '批量评测失败' }))
      throw new Error(err.detail || '批量评测失败')
    }
    batchResult.value = await resp.json()
    resultsOpen.value = true
    toast(`已完成 ${batchResult.value!.samplesEvaluated} 张真实测试图评测`)
  } catch (e: any) {
    toast(e?.message || '批量评测失败', 'error')
  } finally {
    runningBatch.value = false
  }
}

// 一键发布优化流水线为新算法
const publishOpen = ref(false)
const publishing = ref(false)
const previewCode = ref('')
const pubForm = reactive({
  name: '',
  displayName: '',
  task: 'image-dehazing' as TaskType,
  summary: '',
})

async function openPublishModal() {
  const dsNode = nodes.value.find((n) => n.type === 'dataset')
  const isCls = (dsNode?.config?.datasetId ?? '').includes('cat-dog')
  const suffix = String(Date.now()).slice(-4)
  pubForm.task = isCls ? 'image-classification' : 'image-dehazing'
  pubForm.name = isCls ? `studio-cls-opt-${suffix}` : `studio-dehaze-opt-${suffix}`
  pubForm.displayName = isCls ? `编排优化分类算法 (${suffix})` : `编排优化去雾算法 (${suffix})`
  pubForm.summary = '通过低代码编排实验室拖拽优化参数并一键发布的可执行算法，可直接在线推理与参与正式基准评测。'
  publishOpen.value = true
  previewCode.value = '# 正在生成标准 predictor.py ...'
  try {
    const resp = await fetch('/real-api/studio/preview-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodes: nodes.value, edges: edges.value, meta: { task: pubForm.task } }),
    })
    if (resp.ok) {
      const d = await resp.json()
      previewCode.value = d.code
    } else {
      const err = await resp.json().catch(() => ({ detail: '生成失败' }))
      previewCode.value = `# 生成失败：${err.detail}`
    }
  } catch {
    previewCode.value = '# 无法连接后端预览代码'
  }
}

async function doPublish() {
  if (!/^[a-z0-9][a-z0-9-]{1,48}$/.test(pubForm.name) || !pubForm.displayName.trim()) {
    return toast('请填写合法的英文标识（小写字母/数字/连字符）与中文名称', 'error')
  }
  publishing.value = true
  try {
    const resp = await fetch('/real-api/studio/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        nodes: nodes.value,
        edges: edges.value,
        createdBy: user.value.username,
        role: state.role,
        meta: {
          org: state.role === 'admin' ? 'Admin' : (user.value.orgId ?? 'Admin'),
          name: pubForm.name,
          displayName: pubForm.displayName.trim(),
          task: pubForm.task,
          business: 'other',
          framework: 'PyTorch',
          version: 'v1.0.0',
          summary: pubForm.summary.trim(),
          changelog: '由低代码编排实验室一键编译发布',
          gpuMem: 1.5,
        },
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '发布失败' }))
      throw new Error(err.detail || '发布失败')
    }
    const algo = await resp.json()
    publishOpen.value = false
    toast(`已成功发布算法「${algo.displayName}」，正在跳转至详情页…`)
    router.push(`/algorithms/${algo.id}`)
  } catch (e: any) {
    toast(e?.message || '发布失败', 'error')
  } finally {
    publishing.value = false
  }
}

const evalResults = computed(() => Object.values(nodeResults.value).filter((r) => r.type === 'evaluator' && r.branches?.length))
const datasetResult = computed(() => Object.values(nodeResults.value).find((r) => r.type === 'dataset') ?? null)
</script>

<template>
  <div class="flex h-full w-full flex-col overflow-hidden bg-gray-50 dark:bg-gray-950">
    <!-- 顶部紧凑工具栏（占满全宽，零留白） -->
    <div class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-white px-3 py-2 dark:border-gray-800 dark:bg-gray-900">
      <div class="flex items-center gap-2">
        <div class="flex size-7 items-center justify-center rounded-lg bg-brand-600/10 text-brand-600 dark:text-brand-400">
          <Workflow class="size-4" />
        </div>
        <h1 class="text-sm font-semibold text-gray-900 dark:text-white">低代码编排实验室</h1>
        <span class="rounded-full border border-amber-300 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-800 dark:bg-amber-950/60 dark:text-amber-300">Beta</span>

        <span class="mx-1 hidden h-4 w-px bg-gray-200 sm:inline-block dark:bg-gray-700" />

        <div class="flex items-center rounded-lg border border-gray-200 bg-gray-50 p-0.5 text-xs dark:border-gray-700 dark:bg-gray-950">
          <button
            type="button"
            class="rounded-md px-2 py-1 transition"
            :class="activePreset === 'dehaze-opt' ? 'bg-white font-medium text-gray-900 shadow-2xs dark:bg-gray-800 dark:text-white' : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'"
            @click="loadPreset('dehaze-opt')"
          >去雾调优</button>
          <button
            type="button"
            class="rounded-md px-2 py-1 transition"
            :class="activePreset === 'dehaze-compare' ? 'bg-white font-medium text-gray-900 shadow-2xs dark:bg-gray-800 dark:text-white' : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'"
            @click="loadPreset('dehaze-compare')"
          >三算法对比</button>
          <button
            type="button"
            class="rounded-md px-2 py-1 transition"
            :class="activePreset === 'catdog-opt' ? 'bg-white font-medium text-gray-900 shadow-2xs dark:bg-gray-800 dark:text-white' : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'"
            @click="loadPreset('catdog-opt')"
          >猫狗增强</button>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-1.5">
        <!-- 撤销 / 重做 / 清空 -->
        <div class="flex items-center rounded-lg border border-gray-200 bg-white p-0.5 dark:border-gray-700 dark:bg-gray-950">
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-700 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-200 dark:hover:bg-gray-800"
            :disabled="!undoStack.length"
            :title="undoStack.length ? `撤销：${undoStack[undoStack.length - 1].desc} (Ctrl+Z)` : '无可撤销操作 (Ctrl+Z)'"
            @click="undo"
          >
            <Undo2 class="size-3.5" />
            <span class="hidden sm:inline">撤销</span>
            <span v-if="undoStack.length" class="mono rounded bg-gray-100 px-1 text-[10px] text-gray-500 dark:bg-gray-800 dark:text-gray-400">{{ undoStack.length }}</span>
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-gray-700 transition hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-40 dark:text-gray-200 dark:hover:bg-gray-800"
            :disabled="!redoStack.length"
            :title="redoStack.length ? `重做：${redoStack[redoStack.length - 1].desc} (Ctrl+Y)` : '无可重做操作 (Ctrl+Y)'"
            @click="redo"
          >
            <Redo2 class="size-3.5" />
          </button>
          <span class="mx-0.5 h-3.5 w-px bg-gray-200 dark:bg-gray-700" />
          <button
            type="button"
            class="inline-flex items-center rounded-md px-2 py-1 text-xs text-gray-500 transition hover:bg-rose-50 hover:text-rose-600 disabled:opacity-40 dark:text-gray-400 dark:hover:bg-rose-950/50 dark:hover:text-rose-400"
            :disabled="!nodes.length"
            title="清空画布（可 Ctrl+Z 撤销）"
            @click="clearCanvas"
          >
            <Eraser class="size-3.5" />
          </button>
        </div>

        <button type="button" class="btn-primary py-1 text-xs" :disabled="runningSample || runningBatch" @click="runSample">
          <LoaderCircle v-if="runningSample" class="size-3.5 animate-spin" />
          <Play v-else class="size-3.5" />
          {{ runningSample ? '试跑中…' : '单图试跑' }}
        </button>

        <div class="flex items-center gap-1">
          <select v-model.number="batchCount" class="input w-[70px] py-1 text-xs" aria-label="批量评测样本数">
            <option :value="6">6 张</option>
            <option :value="12">12 张</option>
            <option :value="25">25 张</option>
            <option :value="50">50 张</option>
          </select>
          <button type="button" class="btn-default py-1 text-xs" :disabled="runningBatch || runningSample" @click="runBatchEval">
            <LoaderCircle v-if="runningBatch" class="size-3.5 animate-spin" />
            <FlaskConical v-else class="size-3.5 text-emerald-600" />
            {{ runningBatch ? '评测中…' : '批量评测' }}
          </button>
        </div>

        <button type="button" class="btn-brand py-1 text-xs" @click="openPublishModal">
          <Rocket class="size-3.5" />发布新算法
        </button>
      </div>
    </div>

    <!-- 主工作区：左组件库 + 中全屏画布(&可折叠结果抽屉) + 右输入输出/属性检查器 -->
    <div class="flex min-h-0 flex-1 overflow-hidden">
      <!-- 左侧组件库 -->
      <aside class="flex w-[196px] shrink-0 flex-col gap-2 overflow-y-auto border-r border-gray-200 bg-white p-2.5 dark:border-gray-800 dark:bg-gray-900">
        <p class="px-0.5 text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">组件库 · 拖拽或点击</p>
        <div
          v-for="item in PALETTE"
          :key="item.type"
          draggable="true"
          class="cursor-grab rounded-lg border p-2 transition hover:shadow-xs active:cursor-grabbing"
          :class="item.color"
          @dragstart="onPaletteDragStart($event, item.type)"
          @click="addNode(item.type)"
        >
          <div class="flex items-center gap-1.5 text-xs font-semibold">
            <component :is="item.icon" class="size-3.5 shrink-0" />
            <span class="truncate">{{ item.label }}</span>
            <Plus class="ml-auto size-3.5 shrink-0 opacity-60" />
          </div>
          <p class="mt-0.5 text-[11px] opacity-80">{{ item.desc }}</p>
          <div class="mt-1.5 flex items-center gap-1 border-t border-current/10 pt-1 text-[10px] opacity-85">
            <span class="truncate">{{ item.inSpec ? `入: ${item.inSpec}` : '数据源' }}</span>
            <ArrowRight class="size-2.5 shrink-0 opacity-60" />
            <span class="truncate font-medium">{{ item.outSpec ? `出: ${item.outSpec}` : '终点' }}</span>
          </div>
        </div>

        <div class="mt-auto space-y-1 rounded-lg border border-gray-100 bg-gray-50 p-2 text-[11px] leading-relaxed text-gray-500 dark:border-gray-800 dark:bg-gray-950/70 dark:text-gray-400">
          <p class="font-semibold text-gray-700 dark:text-gray-300">快捷键与画布操作</p>
          <p><kbd class="mono rounded border border-gray-200 bg-white px-1 py-0.2 text-[10px] dark:border-gray-700 dark:bg-gray-900">Ctrl+滚轮</kbd> 缩放画布</p>
          <p>· 按住空白处或<kbd class="mono rounded border border-gray-200 bg-white px-1 py-0.2 text-[10px] dark:border-gray-700 dark:bg-gray-900">Space</kbd>拖动画布</p>
          <p><kbd class="mono rounded border border-gray-200 bg-white px-1 py-0.2 text-[10px] dark:border-gray-700 dark:bg-gray-900">Ctrl+Z</kbd> 撤销 · <kbd class="mono rounded border border-gray-200 bg-white px-1 py-0.2 text-[10px] dark:border-gray-700 dark:bg-gray-900">Ctrl+Y</kbd> 重做</p>
          <p><kbd class="mono rounded border border-gray-200 bg-white px-1 py-0.2 text-[10px] dark:border-gray-700 dark:bg-gray-900">Del</kbd> 删除 · <kbd class="mono rounded border border-gray-200 bg-white px-1 py-0.2 text-[10px] dark:border-gray-700 dark:bg-gray-900">Ctrl+0</kbd> 适应画布</p>
          <p>· 点击<span class="font-medium text-brand-600">输出点</span>→<span class="font-medium text-emerald-600">输入点</span>连线，点连线断开</p>
        </div>
      </aside>

      <!-- 中间无限平移缩放画布 + 底部可折叠结果抽屉 -->
      <div class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <section
          ref="canvasEl"
          class="relative min-h-0 flex-1 select-none overflow-hidden bg-gray-50/70 dark:bg-gray-950"
          :class="panState.active ? 'cursor-grabbing' : spacePressed ? 'cursor-grab' : 'cursor-grab'"
          :style="canvasBgStyle"
          @dragover.prevent
          @drop.prevent="onCanvasDrop"
          @wheel.prevent="onCanvasWheel"
          @mousedown.middle.prevent
          @pointerdown="onCanvasPointerDown"
          @pointermove="onCanvasPointerMove"
        >
          <!-- 正在连线提示悬浮条（固定在视口顶部，不随画布缩放） -->
          <div
            v-if="connectingFrom"
            data-studio-hud="1"
            class="absolute top-3 left-3 z-30 inline-flex items-center gap-1.5 rounded-full bg-brand-600 px-3 py-1 text-xs text-white shadow-md"
          >
            <Link2 class="size-3.5" />正在连线：点击目标节点的左侧输入圆点完成连接（Esc 或点击空白处取消）
          </div>

          <!-- 世界坐标系变换层（支持无限平移与任意比例缩放，禁用 will-change 避免字体糊化） -->
          <div class="absolute top-0 left-0 origin-top-left" :style="worldStyle">
            <!-- SVG 贝塞尔连线层（overflow-visible 支持任意坐标） -->
            <svg width="1" height="1" class="pointer-events-none absolute top-0 left-0 overflow-visible">
              <defs>
                <marker id="arrow-muted" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#94a3b8" />
                </marker>
                <marker id="arrow-active" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#6366f1" />
                </marker>
              </defs>
              <g v-for="e in edges" :key="e.id" data-studio-edge="1" class="group pointer-events-auto cursor-pointer" @click.stop="removeEdge(e.id)">
                <title>点击断开连线</title>
                <path :d="edgePath(e)" fill="none" stroke="transparent" stroke-width="16" />
                <path
                  :d="edgePath(e)"
                  fill="none"
                  stroke="currentColor"
                  :stroke-width="isEdgeHighlighted(e) ? 2.6 : 2"
                  :marker-end="isEdgeHighlighted(e) ? 'url(#arrow-active)' : 'url(#arrow-muted)'"
                  class="transition-colors"
                  :class="
                    isEdgeHighlighted(e)
                      ? 'text-brand-500 group-hover:text-rose-500'
                      : 'text-gray-400 group-hover:text-rose-500 dark:text-gray-600 dark:group-hover:text-rose-400'
                  "
                />
              </g>
              <!-- 正在连线时的动态虚线 -->
              <path
                v-if="connectingFrom && draftEdgePath"
                :d="draftEdgePath"
                fill="none"
                stroke="#6366f1"
                stroke-width="2"
                stroke-dasharray="6 4"
              />
            </svg>

            <!-- 节点卡片（带直观 I/O 端口条 + 实时 输入→输出 并排预览） -->
            <div
              v-for="node in nodes"
              :key="node.id"
              data-studio-node="1"
              class="absolute z-10 w-[264px] cursor-default select-none rounded-xl border bg-white shadow-sm transition-shadow dark:bg-gray-900"
              :class="selectedNodeId === node.id ? 'border-brand-500 ring-2 ring-brand-500/25 shadow-md' : 'border-gray-200 hover:border-gray-300 hover:shadow dark:border-gray-700 dark:hover:border-gray-600'"
              :style="{ left: node.x + 'px', top: node.y + 'px' }"
              @pointerdown="startDragNode($event, node)"
            >
              <!-- 节点头部 -->
              <div class="flex h-[34px] cursor-move items-center justify-between gap-1.5 rounded-t-[11px] border-b px-2.5 text-xs font-semibold" :class="NODE_HEADER_CLS[node.type]">
                <component :is="NODE_ICON[node.type]" class="size-3.5 shrink-0" />
                <span class="truncate">{{ node.label }}</span>
                <span v-if="nodeResults[node.id]" class="mono ml-auto shrink-0 rounded bg-white/70 px-1 py-0.2 text-[10px] font-medium text-emerald-700 dark:bg-black/30 dark:text-emerald-300">
                  {{ nodeResults[node.id].latencyMs }}ms
                </span>
                <button
                  type="button"
                  class="rounded p-0.5 opacity-60 hover:bg-black/10 hover:opacity-100"
                  :class="{ 'ml-auto': !nodeResults[node.id] }"
                  aria-label="删除节点"
                  @click.stop="removeNode(node.id)"
                >
                  <Trash2 class="size-3" />
                </button>
              </div>

              <!-- 专用输入 / 输出端口条（居中对齐 PORT_Y = 49） -->
              <div class="relative flex h-[30px] items-center justify-between border-b border-gray-100 bg-gray-50/70 px-3 text-[10px] dark:border-gray-800 dark:bg-gray-950/60">
                <!-- 左侧输入端口圆点 + 类型标签 -->
                <div class="flex min-w-0 items-center gap-1">
                  <button
                    v-if="node.type !== 'dataset'"
                    type="button"
                    title="输入端口：点击完成连线"
                    class="absolute top-1/2 -left-[9px] flex size-[18px] -translate-y-1/2 items-center justify-center rounded-full border-2 border-white shadow transition dark:border-gray-900"
                    :class="
                      connectingFrom && connectingFrom !== node.id
                        ? 'scale-125 bg-emerald-500 ring-2 ring-emerald-400/50'
                        : incomingNodesOf(node.id).length
                          ? portLabelsFor(node).inDot
                          : 'bg-gray-300 hover:bg-emerald-500 dark:bg-gray-600'
                    "
                    @click.stop="clickInputPort(node.id)"
                  />
                  <template v-if="portLabelsFor(node).inLabel">
                    <span class="mono rounded bg-sky-100/90 px-1 font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-300">IN</span>
                    <span class="truncate text-gray-600 dark:text-gray-300">{{ portLabelsFor(node).inLabel }}</span>
                    <span v-if="!incomingNodesOf(node.id).length" class="shrink-0 text-[9px] font-medium text-amber-600 dark:text-amber-400">· 未连</span>
                  </template>
                  <span v-else class="text-gray-400">数据源起点</span>
                </div>

                <!-- 右侧输出端口标签 + 圆点 -->
                <div class="flex min-w-0 items-center gap-1">
                  <template v-if="portLabelsFor(node).outLabel">
                    <span class="truncate text-gray-600 dark:text-gray-300">{{ portLabelsFor(node).outLabel }}</span>
                    <span class="mono rounded bg-indigo-100/90 px-1 font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">OUT</span>
                  </template>
                  <span v-else class="font-medium text-emerald-600 dark:text-emerald-400">评测终点</span>
                  <button
                    v-if="node.type !== 'evaluator'"
                    type="button"
                    title="输出端口：点击发起连线"
                    class="absolute top-1/2 -right-[9px] flex size-[18px] -translate-y-1/2 items-center justify-center rounded-full border-2 border-white shadow transition dark:border-gray-900"
                    :class="
                      connectingFrom === node.id
                        ? 'scale-125 bg-brand-600 ring-2 ring-brand-400/50'
                        : `${portLabelsFor(node).outDot} hover:scale-110`
                    "
                    @click.stop="clickOutputPort(node.id, $event)"
                  />
                </div>
              </div>

              <!-- 节点参数摘要 + 直观的 输入 → 输出 视觉展示区 -->
              <div class="space-y-2 p-2.5 text-[11px] text-gray-600 dark:text-gray-300">
                <p v-if="node.type === 'dataset'" class="mono truncate text-gray-500">{{ node.config.datasetId }} #{{ node.config.sampleIndex + 1 }}</p>
                <p v-else-if="node.type === 'algorithm'" class="mono truncate text-gray-500">{{ node.config.algorithmId }}@{{ node.config.version }}</p>
                <p v-else-if="node.type === 'preprocess'" class="truncate text-gray-500">γ={{ node.config.gamma }} · 对比={{ node.config.contrast }} · 锐化={{ node.config.sharpen }}</p>
                <p v-else-if="node.type === 'postprocess'" class="truncate text-gray-500">融合={{ node.config.blendOriginal }} · 锐化={{ node.config.sharpen }} · 饱和={{ node.config.saturation }}</p>
                <p v-else class="truncate text-gray-500">接入 {{ incomingNodesOf(node.id).length }} 条分支 · 自动匹配真值</p>

                <!-- 运行前：显示上下游数据流向摘要 -->
                <div v-if="!nodeResults[node.id]" class="flex items-center justify-between gap-1 rounded-md bg-gray-50 px-2 py-1 text-[10px] text-gray-500 dark:bg-gray-950/70 dark:text-gray-400">
                  <span class="truncate">
                    <template v-if="node.type === 'dataset'">输出 → {{ outgoingNodesOf(node.id).length }} 个下游</template>
                    <template v-else-if="incomingNodesOf(node.id).length">
                      来自：{{ incomingNodesOf(node.id).map((x) => x.node.label).join('、') }}
                    </template>
                    <template v-else>等待接入上游输出</template>
                  </span>
                  <span v-if="node.type !== 'dataset' && node.type !== 'evaluator'" class="shrink-0 text-gray-400">→ {{ outgoingNodesOf(node.id).length }}</span>
                </div>

                <!-- 运行后：直接在卡片上直观展示 输入 → 输出 -->
                <template v-else>
                  <!-- 1) 数据集节点：待测输出图 + 真值 GT -->
                  <div v-if="node.type === 'dataset'" class="grid grid-cols-2 gap-1.5">
                    <div v-if="nodeResults[node.id].previewImage" class="relative overflow-hidden rounded-md border border-sky-200/80 dark:border-sky-900">
                      <img
                        data-zoomable="1"
                        :src="nodeResults[node.id].previewImage!"
                        alt="待测图像"
                        class="h-[68px] w-full cursor-zoom-in object-cover"
                        @click.stop="openLightbox(`${node.label} · 输出待测图像`, nodeResults[node.id].previewImage!, nodeResults[node.id].outputShape ?? '')"
                      />
                      <span class="pointer-events-none absolute bottom-0.5 left-0.5 rounded bg-sky-900/80 px-1 text-[9px] text-white">输出图</span>
                    </div>
                    <div v-if="nodeResults[node.id].gtImage" class="relative overflow-hidden rounded-md border border-emerald-200/80 dark:border-emerald-900">
                      <img
                        data-zoomable="1"
                        :src="nodeResults[node.id].gtImage!"
                        alt="清晰真值"
                        class="h-[68px] w-full cursor-zoom-in object-cover"
                        @click.stop="openLightbox(`${node.label} · 清晰真值 GT`, nodeResults[node.id].gtImage!)"
                      />
                      <span class="pointer-events-none absolute bottom-0.5 left-0.5 rounded bg-emerald-900/80 px-1 text-[9px] text-white">真值 GT</span>
                    </div>
                    <div v-else-if="nodeResults[node.id].gtLabel" class="flex flex-col justify-center rounded-md border border-emerald-200 bg-emerald-50/70 px-2 py-1 dark:border-emerald-900 dark:bg-emerald-950/40">
                      <span class="text-[9px] font-medium text-emerald-700 dark:text-emerald-300">真值 GT</span>
                      <span class="mono truncate text-xs font-semibold text-gray-900 dark:text-white">{{ nodeResults[node.id].gtLabel }}</span>
                    </div>
                  </div>

                  <!-- 2) 图像到图像节点（预处理 / 图像算法 / 后处理）：输入 → 输出 并排对比 -->
                  <div v-else-if="nodeResults[node.id].inputPreview && nodeResults[node.id].previewImage" class="relative grid grid-cols-2 gap-1.5">
                    <div class="relative overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
                      <img
                        data-zoomable="1"
                        :src="nodeResults[node.id].inputPreview!"
                        alt="节点输入"
                        class="h-[68px] w-full cursor-zoom-in object-cover"
                        @click.stop="openLightbox(`${node.label} · 输入图像`, nodeResults[node.id].inputPreview!, nodeResults[node.id].inputShape ?? '')"
                      />
                      <span class="pointer-events-none absolute bottom-0.5 left-0.5 rounded bg-gray-900/80 px-1 text-[9px] text-white">输入</span>
                    </div>
                    <span class="pointer-events-none absolute top-1/2 left-1/2 z-10 flex size-5 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-white bg-brand-600 text-white shadow">
                      <ArrowRight class="size-3" />
                    </span>
                    <div class="relative overflow-hidden rounded-md border border-brand-200 dark:border-brand-800">
                      <img
                        data-zoomable="1"
                        :src="nodeResults[node.id].previewImage!"
                        alt="节点输出"
                        class="h-[68px] w-full cursor-zoom-in object-cover"
                        @click.stop="openLightbox(`${node.label} · 输出图像`, nodeResults[node.id].previewImage!, nodeResults[node.id].outputShape ?? '')"
                      />
                      <span class="pointer-events-none absolute bottom-0.5 right-0.5 rounded bg-brand-700/90 px-1 text-[9px] text-white">输出</span>
                    </div>
                  </div>

                  <!-- 3) 分类算法节点：输入图 → 分类概率输出 -->
                  <div v-else-if="nodeResults[node.id].classification?.length" class="relative grid grid-cols-[84px_1fr] items-center gap-1.5">
                    <div v-if="nodeResults[node.id].inputPreview" class="relative overflow-hidden rounded-md border border-gray-200 dark:border-gray-700">
                      <img
                        data-zoomable="1"
                        :src="nodeResults[node.id].inputPreview!"
                        alt="输入图像"
                        class="h-[58px] w-full cursor-zoom-in object-cover"
                        @click.stop="openLightbox(`${node.label} · 输入图像`, nodeResults[node.id].inputPreview!)"
                      />
                      <span class="pointer-events-none absolute bottom-0.5 left-0.5 rounded bg-gray-900/80 px-1 text-[9px] text-white">输入</span>
                    </div>
                    <div class="space-y-1 rounded-md border border-indigo-100 bg-indigo-50/50 p-1.5 dark:border-indigo-900/60 dark:bg-indigo-950/30">
                      <div v-for="c in nodeResults[node.id].classification!.slice(0, 2)" :key="c.label" class="space-y-0.5">
                        <div class="flex justify-between text-[10px]">
                          <span class="font-medium text-gray-800 dark:text-gray-200">{{ c.label }}</span>
                          <span class="mono text-indigo-600 dark:text-indigo-300">{{ (c.score * 100).toFixed(1) }}%</span>
                        </div>
                        <div class="h-1 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-900/60">
                          <div class="h-full rounded-full bg-indigo-500" :style="{ width: Math.round(c.score * 100) + '%' }" />
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 4) 评测节点：各分支输入 → 输出指标 -->
                  <div v-else-if="nodeResults[node.id].branches?.length" class="space-y-1">
                    <div
                      v-for="(br, bi) in nodeResults[node.id].branches"
                      :key="bi"
                      class="rounded-md border border-emerald-100 bg-emerald-50/50 px-2 py-1 dark:border-emerald-900/50 dark:bg-emerald-950/30"
                    >
                      <div class="truncate text-[10px] font-medium text-gray-800 dark:text-gray-200">{{ br.branch }}</div>
                      <div class="mono mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-emerald-700 dark:text-emerald-300">
                        <span v-for="(val, mk) in br.metrics" :key="mk">{{ mk }}={{ val }}</span>
                      </div>
                    </div>
                  </div>

                  <div class="flex items-center justify-between gap-1 text-[10px] text-gray-400">
                    <span class="inline-flex items-center gap-0.5 truncate text-emerald-600 dark:text-emerald-400">
                      <Check class="size-3 shrink-0" />
                      <span class="truncate">{{ nodeResults[node.id].outputShape || nodeResults[node.id].summary }}</span>
                    </span>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- 左下角画布状态浮标 -->
          <div
            data-studio-hud="1"
            class="pointer-events-none absolute bottom-3 left-3 z-20 inline-flex items-center gap-2 rounded-lg border border-gray-200/90 bg-white/90 px-2.5 py-1 text-[11px] text-gray-500 shadow-xs backdrop-blur dark:border-gray-800 dark:bg-gray-900/90 dark:text-gray-400"
          >
            <span class="mono">{{ nodes.length }} 节点 · {{ edges.length }} 连线</span>
            <span class="text-gray-300 dark:text-gray-700">|</span>
            <span>拖动画布平移 · Ctrl+滚轮缩放</span>
          </div>

          <!-- 右下角画布缩放与适应控件 -->
          <div
            data-studio-hud="1"
            class="absolute right-3 bottom-3 z-20 flex items-center gap-0.5 rounded-lg border border-gray-200/90 bg-white/95 p-1 text-xs text-gray-600 shadow-sm backdrop-blur dark:border-gray-800 dark:bg-gray-900/95 dark:text-gray-300"
          >
            <button
              type="button"
              class="rounded-md p-1 transition hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800"
              :disabled="viewport.zoom <= MIN_ZOOM"
              title="缩小 (Ctrl + -)"
              @click="zoomBy(1 / 1.15)"
            >
              <ZoomOut class="size-3.5" />
            </button>
            <button
              type="button"
              class="mono min-w-[46px] rounded-md px-1.5 py-0.5 text-center text-[11px] font-medium transition hover:bg-gray-100 dark:hover:bg-gray-800"
              title="点击重置为 100%"
              @click="resetZoom"
            >
              {{ Math.round(viewport.zoom * 100) }}%
            </button>
            <button
              type="button"
              class="rounded-md p-1 transition hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800"
              :disabled="viewport.zoom >= MAX_ZOOM"
              title="放大 (Ctrl + +)"
              @click="zoomBy(1.15)"
            >
              <ZoomIn class="size-3.5" />
            </button>
            <span class="mx-0.5 h-3.5 w-px bg-gray-200 dark:bg-gray-700" />
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] transition hover:bg-gray-100 dark:hover:bg-gray-800"
              title="自适应居中全部节点 (Ctrl + 0)"
              @click="fitView"
            >
              <Maximize2 class="size-3.5" />
              <span class="hidden sm:inline">适应</span>
            </button>
          </div>
        </section>

        <!-- 底部可折叠评测结果抽屉（不占额外页面留白） -->
        <div
          v-if="evalResults.length || batchResult"
          class="shrink-0 border-t border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
        >
          <div
            class="flex cursor-pointer items-center justify-between px-3 py-1.5 text-xs hover:bg-gray-50 dark:hover:bg-gray-800/50"
            @click="resultsOpen = !resultsOpen"
          >
            <div class="flex items-center gap-2 font-semibold text-gray-900 dark:text-white">
              <Sparkles class="size-3.5 text-amber-500" />
              <span>运行对比结果</span>
              <span v-if="evalResults.length" class="chip text-[10px]">单图 {{ evalResults[0].branches?.length ?? 0 }} 分支</span>
              <span v-if="batchResult" class="chip border-emerald-200 bg-emerald-50 text-[10px] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300">
                批量 {{ batchResult.samplesEvaluated }} 张 · {{ batchResult.durationSec }}s
              </span>
            </div>
            <div class="flex items-center gap-1 text-gray-400">
              <button type="button" class="rounded p-0.5 hover:bg-gray-200/70 dark:hover:bg-gray-700" :aria-label="resultsOpen ? '折叠' : '展开'">
                <ChevronDown v-if="resultsOpen" class="size-4" />
                <ChevronUp v-else class="size-4" />
              </button>
            </div>
          </div>

          <div v-if="resultsOpen" class="grid max-h-[230px] gap-3 overflow-y-auto border-t border-gray-100 p-3 lg:grid-cols-2 dark:border-gray-800">
            <!-- 单图视觉与指标对比 -->
            <div v-if="evalResults.length">
              <p class="mb-2 text-[11px] font-semibold text-gray-500">单图试跑视觉与指标对比</p>
              <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <div v-if="datasetResult?.previewImage" class="space-y-1">
                  <img
                    :src="datasetResult.previewImage"
                    alt="原始输入"
                    class="aspect-[4/3] w-full cursor-zoom-in rounded-md border border-gray-200 object-cover dark:border-gray-700"
                    @click="openLightbox('原始输入图像', datasetResult.previewImage!)"
                  />
                  <p class="text-[11px] font-medium">原始输入</p>
                </div>
                <div v-if="datasetResult?.gtImage" class="space-y-1">
                  <img
                    :src="datasetResult.gtImage"
                    alt="清晰真值"
                    class="aspect-[4/3] w-full cursor-zoom-in rounded-md border border-emerald-200 object-cover dark:border-emerald-800"
                    @click="openLightbox('清晰真值 (GT)', datasetResult.gtImage!)"
                  />
                  <p class="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">清晰真值 (GT)</p>
                </div>
                <div v-for="(br, i) in evalResults[0].branches" :key="i" class="space-y-1">
                  <img
                    v-if="br.previewImage"
                    :src="br.previewImage"
                    :alt="br.branch"
                    class="aspect-[4/3] w-full cursor-zoom-in rounded-md border border-brand-200 object-cover dark:border-brand-800"
                    @click="openLightbox(br.branch, br.previewImage!)"
                  />
                  <p class="truncate text-[11px] font-medium text-gray-900 dark:text-white">{{ br.branch }}</p>
                  <p class="mono text-[10px] text-brand-600 dark:text-brand-400">
                    <span v-for="(val, k) in br.metrics" :key="k" class="mr-1.5">{{ k }}={{ val }}</span>
                    <span class="text-gray-400">{{ br.latencyMs }}ms</span>
                  </p>
                </div>
              </div>
            </div>

            <!-- 批量测试集对比表 -->
            <div v-if="batchResult" :class="{ 'lg:col-span-2': !evalResults.length }">
              <p class="mb-2 text-[11px] font-semibold text-gray-500">批量测试集评测对比（{{ batchResult.datasetId }} · {{ batchResult.samplesEvaluated }} 张）</p>
              <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table class="table-base text-xs">
                  <thead>
                    <tr>
                      <th>编排分支</th>
                      <th>评测指标</th>
                      <th>单图均耗</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(b, idx) in batchResult.branches" :key="idx">
                      <td class="font-medium text-gray-900 dark:text-white">{{ b.branch }}</td>
                      <td class="mono">
                        <span v-for="(v, k) in b.metrics" :key="k" class="mr-2 inline-block rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                          {{ k }}: {{ v }}
                        </span>
                      </td>
                      <td class="mono text-gray-500">{{ b.latencyMs }} ms</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧节点输入输出 & 属性检查器 -->
      <aside class="flex w-[340px] shrink-0 flex-col overflow-hidden border-l border-gray-200 bg-white xl:w-[376px] dark:border-gray-800 dark:bg-gray-900">
        <div class="flex shrink-0 items-center justify-between border-b border-gray-100 px-3.5 py-2.5 dark:border-gray-800">
          <div class="flex min-w-0 items-center gap-1.5">
            <h2 class="truncate text-xs font-semibold text-gray-900 dark:text-white">
              {{ selectedNode ? selectedNode.label : '节点检查器' }}
            </h2>
            <span v-if="selectedNode" class="chip mono text-[10px]">{{ selectedNode.type }}</span>
          </div>
          <button
            v-if="selectedNode"
            type="button"
            class="rounded p-1 text-gray-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/50"
            title="删除当前节点 (Del)"
            @click="removeNode(selectedNode.id)"
          >
            <Trash2 class="size-3.5" />
          </button>
        </div>

        <div v-if="!selectedNode" class="flex flex-1 flex-col items-center justify-center p-6 text-center text-xs text-gray-400">
          <Workflow class="mb-2 size-8 opacity-30" />
          <p class="font-medium text-gray-500 dark:text-gray-400">点击画布中的任意节点</p>
          <p class="mt-1 leading-relaxed">查看该节点的<strong>输入 / 输出数据与图像对比</strong>，并实时调节参数。</p>
        </div>

        <div v-else class="flex-1 space-y-4 overflow-y-auto p-3.5 text-xs">
          <!-- ===== 区块 1：节点输入 / 输出总览（静态拓扑 + 实时数据） ===== -->
          <div class="space-y-2.5 rounded-xl border border-gray-200/90 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-950/50">
            <div class="flex items-center justify-between">
              <span class="text-[11px] font-semibold text-gray-800 dark:text-gray-200">节点输入 / 输出</span>
              <span v-if="selectedResult" class="mono text-[10px] text-emerald-600 dark:text-emerald-400">已运行 · {{ selectedResult.latencyMs }} ms</span>
              <span v-else class="text-[10px] text-gray-400">点击「单图试跑」查看实况</span>
            </div>

            <!-- 输入区 -->
            <div class="rounded-lg border border-sky-200/70 bg-white p-2 dark:border-sky-900/60 dark:bg-gray-900">
              <div class="mb-1.5 flex items-center justify-between">
                <span class="inline-flex items-center gap-1 text-[10px] font-semibold text-sky-700 dark:text-sky-300">
                  <span class="mono rounded bg-sky-100 px-1 dark:bg-sky-950">IN</span>输入
                  <span v-if="portLabelsFor(selectedNode).inLabel" class="font-normal text-gray-400">({{ portLabelsFor(selectedNode).inLabel }})</span>
                </span>
                <span v-if="selectedResult?.inputShape" class="mono text-[10px] text-gray-400">{{ selectedResult.inputShape }}</span>
              </div>

              <!-- 上游连接来源标签 -->
              <div v-if="selectedNode.type !== 'dataset'" class="mb-1.5 flex flex-wrap gap-1">
                <span
                  v-for="up in selectedIncoming"
                  :key="up.edgeId"
                  class="inline-flex items-center gap-1 rounded-md border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-300"
                >
                  <button type="button" class="hover:underline" @click="selectedNodeId = up.node.id">← {{ up.node.label }}</button>
                  <button type="button" class="opacity-60 hover:text-rose-600 hover:opacity-100" title="断开此输入" @click="removeEdge(up.edgeId)">
                    <X class="size-2.5" />
                  </button>
                </span>
                <span v-if="!selectedIncoming.length" class="text-[10px] text-amber-600 dark:text-amber-400">尚未连接上游节点</span>
              </div>

              <!-- 实时输入数据卡片 -->
              <div v-if="selectedResult?.inputs?.length" class="space-y-1.5">
                <div v-for="(inp, idx) in selectedResult.inputs" :key="idx" class="rounded-md bg-gray-50 p-1.5 dark:bg-gray-950/70">
                  <div class="flex items-center justify-between gap-1 text-[10px]">
                    <span class="font-medium text-gray-700 dark:text-gray-200">{{ inp.name }}</span>
                    <span v-if="inp.shape" class="mono text-gray-400">{{ inp.shape }}</span>
                  </div>
                  <p v-if="inp.value" class="mono mt-0.5 truncate text-[10px] text-gray-500" :title="inp.value">{{ inp.value }}</p>
                  <img
                    v-if="inp.preview"
                    :src="inp.preview"
                    :alt="inp.name"
                    class="mt-1 h-24 w-full cursor-zoom-in rounded border border-gray-200 object-cover dark:border-gray-800"
                    @click="openLightbox(`${selectedNode.label} · 输入 (${inp.name})`, inp.preview!, inp.shape)"
                  />
                </div>
              </div>
              <p v-else-if="selectedNode.type === 'dataset'" class="mono text-[10px] text-gray-500">
                {{ selectedNode.config.datasetId }} · 样本 #{{ selectedNode.config.sampleIndex + 1 }}
              </p>
            </div>

            <!-- 输出区 -->
            <div class="rounded-lg border border-indigo-200/70 bg-white p-2 dark:border-indigo-900/60 dark:bg-gray-900">
              <div class="mb-1.5 flex items-center justify-between">
                <span class="inline-flex items-center gap-1 text-[10px] font-semibold text-indigo-700 dark:text-indigo-300">
                  <span class="mono rounded bg-indigo-100 px-1 dark:bg-indigo-950">OUT</span>输出
                  <span v-if="portLabelsFor(selectedNode).outLabel" class="font-normal text-gray-400">({{ portLabelsFor(selectedNode).outLabel }})</span>
                </span>
                <span v-if="selectedResult?.outputShape" class="mono text-[10px] text-gray-400">{{ selectedResult.outputShape }}</span>
              </div>

              <!-- 下游去向标签 -->
              <div v-if="selectedNode.type !== 'evaluator'" class="mb-1.5 flex flex-wrap gap-1">
                <span
                  v-for="dn in selectedOutgoing"
                  :key="dn.edgeId"
                  class="inline-flex items-center gap-1 rounded-md border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-300"
                >
                  <button type="button" class="hover:underline" @click="selectedNodeId = dn.node.id">→ {{ dn.node.label }}</button>
                  <button type="button" class="opacity-60 hover:text-rose-600 hover:opacity-100" title="断开此输出" @click="removeEdge(dn.edgeId)">
                    <X class="size-2.5" />
                  </button>
                </span>
                <span v-if="!selectedOutgoing.length" class="text-[10px] text-gray-400">未连接下游节点</span>
              </div>

              <!-- 实时输出数据卡片 -->
              <div v-if="selectedResult?.outputs?.length" class="space-y-1.5">
                <div v-for="(outp, idx) in selectedResult.outputs" :key="idx" class="rounded-md bg-gray-50 p-1.5 dark:bg-gray-950/70">
                  <div class="flex items-center justify-between gap-1 text-[10px]">
                    <span class="font-medium text-gray-700 dark:text-gray-200">{{ outp.name }}</span>
                    <span v-if="outp.shape" class="mono text-gray-400">{{ outp.shape }}</span>
                  </div>
                  <p v-if="outp.value && !outp.items?.length && !outp.branches?.length" class="mono mt-0.5 break-all text-[10px] text-gray-600 dark:text-gray-300">{{ outp.value }}</p>
                  <img
                    v-if="outp.preview"
                    :src="outp.preview"
                    :alt="outp.name"
                    class="mt-1 h-24 w-full cursor-zoom-in rounded border border-indigo-200/80 object-cover dark:border-indigo-900"
                    @click="openLightbox(`${selectedNode.label} · 输出 (${outp.name})`, outp.preview!, outp.shape)"
                  />
                  <div v-if="outp.items?.length" class="mt-1 space-y-1">
                    <div v-for="c in outp.items" :key="c.label" class="space-y-0.5">
                      <div class="flex justify-between text-[10px]">
                        <span class="font-medium">{{ c.label }}</span>
                        <span class="mono text-indigo-600 dark:text-indigo-300">{{ (c.score * 100).toFixed(2) }}%</span>
                      </div>
                      <div class="h-1.5 overflow-hidden rounded-full bg-indigo-100 dark:bg-indigo-950">
                        <div class="h-full rounded-full bg-indigo-500" :style="{ width: Math.round(c.score * 100) + '%' }" />
                      </div>
                    </div>
                  </div>
                  <div v-if="outp.branches?.length" class="mt-1 space-y-1">
                    <div v-for="(br, bi) in outp.branches" :key="bi" class="rounded border border-emerald-200/70 bg-white px-2 py-1 dark:border-emerald-900/60 dark:bg-gray-900">
                      <div class="font-medium text-gray-800 dark:text-gray-100">{{ br.branch }}</div>
                      <div class="mono mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-emerald-700 dark:text-emerald-300">
                        <span v-for="(val, k) in br.metrics" :key="k">{{ k }}={{ val }}</span>
                        <span class="text-gray-400">{{ br.latencyMs }}ms</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ===== 区块 2：节点参数配置（每次变更自动支持 Ctrl+Z 撤销） ===== -->
          <div class="space-y-3">
            <h3 class="text-[11px] font-semibold tracking-wide text-gray-500 uppercase dark:text-gray-400">参数配置</h3>

            <div>
              <label class="label text-xs">节点名称</label>
              <input
                v-model="selectedNode.label"
                class="input py-1.5 text-xs"
                @focus="beginConfigEdit('重命名节点')"
                @blur="commitConfigEdit"
              />
            </div>

            <!-- 数据集节点配置 -->
            <template v-if="selectedNode.type === 'dataset'">
              <div>
                <label class="label text-xs">真实数据集</label>
                <select
                  v-model="selectedNode.config.datasetId"
                  class="input py-1.5 text-xs"
                  @focus="beginConfigEdit('切换数据集')"
                  @change="commitConfigEdit"
                >
                  <option v-for="d in realDatasets" :key="d.id" :value="d.id">{{ d.id }}</option>
                </select>
              </div>
              <div>
                <label class="label text-xs">测试样本序号 (#{{ selectedNode.config.sampleIndex + 1 }})</label>
                <input
                  v-model.number="selectedNode.config.sampleIndex"
                  type="range"
                  min="0"
                  max="49"
                  class="w-full accent-brand-600"
                  @pointerdown="beginConfigEdit('调整样本序号')"
                  @change="commitConfigEdit"
                />
              </div>
            </template>

            <!-- 算法节点配置 -->
            <template v-else-if="selectedNode.type === 'algorithm'">
              <div>
                <label class="label text-xs">选择平台已有算法</label>
                <select
                  v-model="selectedNode.config.algorithmId"
                  class="input py-1.5 text-xs"
                  @focus="beginConfigEdit('切换算法')"
                  @change="selectedNode.config.version = 'v1.0.0'; commitConfigEdit()"
                >
                  <option v-for="a in runnableAlgos" :key="a.id" :value="a.id">{{ algoFullLabel(a) }}</option>
                </select>
              </div>
              <div>
                <label class="label text-xs">算法版本</label>
                <select
                  v-model="selectedNode.config.version"
                  class="input py-1.5 text-xs"
                  @focus="beginConfigEdit('切换算法版本')"
                  @change="commitConfigEdit"
                >
                  <option v-for="v in selectedAlgoVersions" :key="v.version" :value="v.version">{{ v.version }}</option>
                </select>
              </div>
            </template>

            <!-- 预处理节点配置 -->
            <template v-else-if="selectedNode.type === 'preprocess'">
              <div>
                <label class="label text-xs">伽马校正 γ ({{ selectedNode.config.gamma }})</label>
                <input
                  v-model.number="selectedNode.config.gamma"
                  type="range"
                  min="0.7"
                  max="1.4"
                  step="0.02"
                  class="w-full accent-amber-500"
                  @pointerdown="beginConfigEdit('调整预处理伽马')"
                  @change="commitConfigEdit"
                />
              </div>
              <div>
                <label class="label text-xs">对比度增强 ({{ selectedNode.config.contrast }})</label>
                <input
                  v-model.number="selectedNode.config.contrast"
                  type="range"
                  min="0.8"
                  max="1.4"
                  step="0.02"
                  class="w-full accent-amber-500"
                  @pointerdown="beginConfigEdit('调整预处理对比度')"
                  @change="commitConfigEdit"
                />
              </div>
              <div>
                <label class="label text-xs">边缘锐化 ({{ selectedNode.config.sharpen }})</label>
                <input
                  v-model.number="selectedNode.config.sharpen"
                  type="range"
                  min="0"
                  max="1.5"
                  step="0.05"
                  class="w-full accent-amber-500"
                  @pointerdown="beginConfigEdit('调整预处理锐化')"
                  @change="commitConfigEdit"
                />
              </div>
              <label class="flex items-center gap-2">
                <input
                  v-model="selectedNode.config.denoise"
                  type="checkbox"
                  class="size-3.5 accent-amber-500"
                  @pointerdown="beginConfigEdit('切换去噪开关')"
                  @change="commitConfigEdit"
                />开启 3×3 中值轻度去噪
              </label>
            </template>

            <!-- 后处理/融合优化节点配置 -->
            <template v-else-if="selectedNode.type === 'postprocess'">
              <div>
                <label class="label text-xs">原图残差融合权重 ({{ selectedNode.config.blendOriginal }})</label>
                <input
                  v-model.number="selectedNode.config.blendOriginal"
                  type="range"
                  min="0"
                  max="0.4"
                  step="0.01"
                  class="w-full accent-violet-500"
                  @pointerdown="beginConfigEdit('调整残差融合权重')"
                  @change="commitConfigEdit"
                />
                <p class="hint">轻度融回原图可缓解过度去雾导致的色彩失真</p>
              </div>
              <div>
                <label class="label text-xs">高频细节锐化 ({{ selectedNode.config.sharpen }})</label>
                <input
                  v-model.number="selectedNode.config.sharpen"
                  type="range"
                  min="0"
                  max="1.5"
                  step="0.05"
                  class="w-full accent-violet-500"
                  @pointerdown="beginConfigEdit('调整后处理锐化')"
                  @change="commitConfigEdit"
                />
              </div>
              <div>
                <label class="label text-xs">色彩饱和度 ({{ selectedNode.config.saturation }})</label>
                <input
                  v-model.number="selectedNode.config.saturation"
                  type="range"
                  min="0.8"
                  max="1.4"
                  step="0.02"
                  class="w-full accent-violet-500"
                  @pointerdown="beginConfigEdit('调整饱和度')"
                  @change="commitConfigEdit"
                />
              </div>
              <div>
                <label class="label text-xs">输出伽马 γ ({{ selectedNode.config.gamma }})</label>
                <input
                  v-model.number="selectedNode.config.gamma"
                  type="range"
                  min="0.8"
                  max="1.3"
                  step="0.02"
                  class="w-full accent-violet-500"
                  @pointerdown="beginConfigEdit('调整输出伽马')"
                  @change="commitConfigEdit"
                />
              </div>
              <label class="flex items-center gap-2">
                <input
                  v-model="selectedNode.config.autoContrast"
                  type="checkbox"
                  class="size-3.5 accent-violet-500"
                  @pointerdown="beginConfigEdit('切换自动对比度')"
                  @change="commitConfigEdit"
                />自动百分位对比度拉伸
              </label>
            </template>

            <!-- 评测节点配置 -->
            <template v-else>
              <p class="rounded-lg bg-emerald-50 p-2.5 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300">
                支持连接多条上游算法/优化分支，自动按数据集真值计算 PSNR / SSIM 或准确率并横向对比。
              </p>
            </template>
          </div>
        </div>
      </aside>
    </div>

    <!-- 节点图像放大查看弹窗 -->
    <Modal v-model:open="lightboxOpen" :title="lightbox?.title ?? ''" width="max-w-3xl">
      <div v-if="lightbox" class="space-y-2">
        <div class="overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-950">
          <img :src="lightbox.src" :alt="lightbox.title" class="mx-auto max-h-[70vh] w-auto object-contain" />
        </div>
        <p v-if="lightbox.subtitle" class="mono text-center text-xs text-gray-500">{{ lightbox.subtitle }}</p>
      </div>
    </Modal>

    <!-- 一键发布为新算法弹窗 -->
    <Modal v-model:open="publishOpen" title="将编排优化链路发布为平台新算法" width="max-w-2xl">
      <div class="space-y-4">
        <div class="grid gap-3 sm:grid-cols-2">
          <div>
            <label class="label">算法英文标识</label>
            <input v-model.trim="pubForm.name" class="input mono" placeholder="studio-dehaze-opt" />
          </div>
          <div>
            <label class="label">算法中文名称</label>
            <input v-model="pubForm.displayName" class="input" placeholder="编排优化去雾算法" />
          </div>
        </div>
        <div>
          <label class="label">简介</label>
          <textarea v-model="pubForm.summary" rows="2" class="input" />
        </div>
        <div>
          <p class="label flex items-center gap-1.5"><Code2 class="size-4 text-brand-600" />自动编译生成的标准 <code class="mono">predictor.py</code></p>
          <pre class="mono max-h-56 overflow-auto rounded-lg bg-gray-900 p-3 text-[11px] leading-relaxed text-gray-100">{{ previewCode }}</pre>
        </div>
        <div class="flex justify-end gap-2 border-t border-gray-100 pt-3 dark:border-gray-800">
          <button type="button" class="btn-default" @click="publishOpen = false">取消</button>
          <button type="button" class="btn-brand" :disabled="publishing" @click="doPublish">
            <LoaderCircle v-if="publishing" class="size-4 animate-spin" />
            <Rocket v-else class="size-4" />
            {{ publishing ? '编译并冒烟测试中…' : '确认发布至算法库' }}
          </button>
        </div>
      </div>
    </Modal>
  </div>
</template>
