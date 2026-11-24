<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  CheckCircle2,
  Clock,
  Layers,
  MapPin,
  Maximize2,
  Search,
  Send,
  X,
  ZoomIn,
  ZoomOut,
} from 'lucide-vue-next'
import {
  ApiError,
  getDispatchedRegions,
  listAlgorithms,
  listDispatches,
  listTrialRequests,
  reviewTrialRequest,
  setAlgorithmDispatches,
} from '@/api'
import { CHINA_MAP_HEIGHT, CHINA_MAP_WIDTH, CHINA_REGIONS } from '@/assets/chinaMapData'
import type { Algorithm, AlgorithmDispatch, RegionName, RegionTrialRequest, TaskType } from '@/types'
import { REGIONS, TASKS } from '@/utils/meta'
import { algoName } from '@/utils/display'
import { layoutRegionLabels, type RegionLabelLayout } from '@/utils/regionLabelLayout'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import TaskIcon from '@/components/ui/TaskIcon.vue'

const { state, currentRegion, can } = useSession()

const algorithms = ref<Algorithm[]>([])
const dispatches = ref<AlgorithmDispatch[]>([])
const trialRequests = ref<RegionTrialRequest[]>([])
const loading = ref(true)

async function loadAll() {
  loading.value = true
  try {
    const [aRes, dRes, tRes] = await Promise.all([
      listAlgorithms({ pageSize: 200 }),
      listDispatches(),
      listTrialRequests(),
    ])
    algorithms.value = aRes.items
    dispatches.value = dRes
    trialRequests.value = tRes
  } finally {
    loading.value = false
  }
}

const algoById = computed(() => new Map(algorithms.value.map((a) => [a.id, a])))
const auditedAlgos = computed(() => algorithms.value.filter((a) => a.versions.some((v) => v.status === 'ready' || v.status === 'building')))

interface RegionSummary {
  region: RegionName
  provinces: string[]
  algos: { algo: Algorithm; dispatch: AlgorithmDispatch }[]
  pendingRequests: RegionTrialRequest[]
}

const regionSummaries = computed<Record<RegionName, RegionSummary>>(() => {
  const out = {} as Record<RegionName, RegionSummary>
  for (const rg of REGIONS) {
    const regDispatches = dispatches.value.filter((d) => d.region === rg)
    const algos = regDispatches
      .map((d) => ({ algo: algoById.value.get(d.algorithmId)!, dispatch: d }))
      .filter((x) => !!x.algo)
    const pending = trialRequests.value.filter((r) => r.region === rg && r.status === 'pending')
    out[rg] = {
      region: rg,
      provinces: CHINA_REGIONS[rg]?.provinces ?? [],
      algos,
      pendingRequests: pending,
    }
  }
  return out
})

const sortedRegionList = computed(() =>
  [...REGIONS]
    .map((rg) => regionSummaries.value[rg])
    .sort((a, b) => b.algos.length - a.algos.length || b.pendingRequests.length - a.pendingRequests.length),
)

/** 为 14 区域预计算「贴合地块轮廓 + 匹配算法名长度」的贴地坐标排版 */
const regionLayouts = computed<Record<RegionName, RegionLabelLayout<{ algo: Algorithm; dispatch: AlgorithmDispatch }>>>(() => {
  const out = {} as Record<RegionName, RegionLabelLayout<{ algo: Algorithm; dispatch: AlgorithmDispatch }>>
  for (const rg of REGIONS) {
    out[rg] = layoutRegionLabels(rg, regionSummaries.value[rg].algos, (x) => algoName(x.algo))
  }
  return out
})

const totalCoveredRegions = computed(() => REGIONS.filter((rg) => regionSummaries.value[rg].algos.length > 0).length)
const totalAuthLinks = computed(() => dispatches.value.length)
const totalPending = computed(() => trialRequests.value.filter((r) => r.status === 'pending').length)

// ==================== 14 区域地块柔和色盘（相邻区域高区分度，自适应亮色 / 暗色主题） ====================
const REGION_COLORS_LIGHT: Record<RegionName, { fill: string; active: string }> = {
  华北: { fill: '#dbeafe', active: '#93c5fd' },
  蒙古: { fill: '#fef3c7', active: '#fcd34d' },
  河北: { fill: '#ede9fe', active: '#c4b5fd' },
  山东: { fill: '#cffafe', active: '#67e8f9' },
  东北: { fill: '#e0f2fe', active: '#7dd3fc' },
  华中: { fill: '#d1fae5', active: '#6ee7b7' },
  华东: { fill: '#ddd6fe', active: '#a78bfa' },
  甘肃: { fill: '#fce7f3', active: '#f9a8d4' },
  新疆: { fill: '#e0e7ff', active: '#a5b4fc' },
  宁夏: { fill: '#ccfbf1', active: '#5eead4' },
  西南: { fill: '#dbeafe', active: '#93c5fd' },
  南方: { fill: '#ccfbf1', active: '#5eead4' },
  云南: { fill: '#dcfce7', active: '#86efac' },
  贵州: { fill: '#fef9c3', active: '#fde047' },
}

const REGION_COLORS_DARK: Record<RegionName, { fill: string; active: string }> = {
  华北: { fill: '#1e3a5f', active: '#2563eb' },
  蒙古: { fill: '#453411', active: '#d97706' },
  河北: { fill: '#312e81', active: '#6366f1' },
  山东: { fill: '#164e63', active: '#0891b2' },
  东北: { fill: '#1e3a5f', active: '#0284c7' },
  华中: { fill: '#064e3b', active: '#059669' },
  华东: { fill: '#3b2667', active: '#7c3aed' },
  甘肃: { fill: '#4a1d3d', active: '#db2777' },
  新疆: { fill: '#273469', active: '#4f46e5' },
  宁夏: { fill: '#134e4a', active: '#0d9488' },
  西南: { fill: '#1e3a5f', active: '#2563eb' },
  南方: { fill: '#134e4a', active: '#0d9488' },
  云南: { fill: '#14532d', active: '#16a34a' },
  贵州: { fill: '#423810', active: '#ca8a04' },
}

function parcelFill(rg: RegionName): string {
  const isDark = state.dark
  const pal = isDark ? REGION_COLORS_DARK[rg] : REGION_COLORS_LIGHT[rg]
  const isHighlighted = selectedRegion.value === rg || hoveredRegion.value === rg
  if (isHighlighted) return pal.active
  if (regionSummaries.value[rg].algos.length > 0) return pal.fill
  return isDark ? '#1e293b' : '#f1f5f9'
}

function parcelStroke(rg: RegionName): string {
  const isDark = state.dark
  if (selectedRegion.value === rg) return isDark ? '#818cf8' : '#4f46e5'
  if (hoveredRegion.value === rg) return isDark ? '#94a3b8' : '#64748b'
  return isDark ? '#475569' : '#ffffff'
}

function mapCountFill(rg: RegionName): string {
  const isDark = state.dark
  const hasAlgos = regionSummaries.value[rg].algos.length > 0
  if (selectedRegion.value === rg) return isDark ? '#ffffff' : '#1e1b4b'
  if (hasAlgos) return isDark ? '#f8fafc' : '#0f172a'
  return isDark ? 'rgba(148, 163, 184, 0.55)' : 'rgba(100, 116, 139, 0.5)'
}

function mapNameFill(rg: RegionName): string {
  const isDark = state.dark
  const hasAlgos = regionSummaries.value[rg].algos.length > 0
  if (selectedRegion.value === rg) return isDark ? '#e0e7ff' : '#312e81'
  if (hasAlgos) return isDark ? 'rgba(226, 232, 240, 0.88)' : 'rgba(30, 41, 59, 0.78)'
  return isDark ? 'rgba(148, 163, 184, 0.6)' : 'rgba(100, 116, 139, 0.65)'
}

const TASK_DOT_CLS: Record<TaskType, string> = {
  'image-classification': 'bg-sky-500/85 dark:bg-sky-400/90',
  'image-dehazing': 'bg-cyan-500/85 dark:bg-cyan-400/90',
  'object-detection': 'bg-amber-500/85 dark:bg-amber-400/90',
  'semantic-segmentation': 'bg-emerald-500/85 dark:bg-emerald-400/90',
  'instance-segmentation': 'bg-teal-500/85 dark:bg-teal-400/90',
  'keypoint-detection': 'bg-rose-500/85 dark:bg-rose-400/90',
  ocr: 'bg-violet-500/85 dark:bg-violet-400/90',
  'power-forecast': 'bg-indigo-500/85 dark:bg-indigo-400/90',
  'signal-processing': 'bg-orange-500/85 dark:bg-orange-400/90',
  optimization: 'bg-lime-500/85 dark:bg-lime-400/90',
  custom: 'bg-slate-400/85 dark:bg-slate-400/90',
}

/** 放大后地块标签的焦点透明度：当前选中/悬停区域清晰突出，周边区域自然退居次层 */
function regionLabelOpacity(rg: RegionName): number {
  if (searchQ.value && !matchedRegions.value.has(rg)) return 0.16
  const focus = hoveredRegion.value ?? selectedRegion.value
  if (!focus) return 0.84
  return focus === rg ? 0.98 : 0.48
}

/** 放大后算法名称字号随缩放倍率平滑舒展（10.5px ~ 13.5px） */
const algoLabelFontSize = computed(() => {
  const px = Math.min(13.5, Math.max(10.5, 9.0 + viewport.zoom * 1.15))
  return `${px.toFixed(1)}px`
})

// ==================== 地图交互：平滑缩放、拖拽平移、语义层级（LOD） ====================
const mapContainerEl = ref<HTMLElement>()
const containerSize = reactive({ w: 1000, h: 720 })
const viewport = reactive({ x: 0, y: 0, zoom: 1 })
const animating = ref(false)
const hoveredRegion = ref<RegionName | null>(null)
const selectedRegion = ref<RegionName | null>(currentRegion.value ?? null)
const searchQ = ref('')

const MIN_ZOOM = 0.85
const MAX_ZOOM = 4.6
/** 语义缩放阈值：zoom >= 1.55 时地块由「授权数量」切换为「具体授权算法列表」 */
const DETAIL_ZOOM_THRESHOLD = 1.55
const isDetailMode = computed(() => viewport.zoom >= DETAIL_ZOOM_THRESHOLD)

const baseScale = computed(() => {
  const pad = 40
  return Math.min((containerSize.w - pad * 2) / CHINA_MAP_WIDTH, (containerSize.h - pad * 2) / CHINA_MAP_HEIGHT)
})

function mapToScreen(mx: number, my: number) {
  const s = baseScale.value * viewport.zoom
  return {
    x: viewport.x + mx * s,
    y: viewport.y + my * s,
  }
}

function clampZoom(z: number) {
  return Number(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z)).toFixed(3))
}

function fitChina(smooth = false) {
  animating.value = smooth
  const s = baseScale.value
  viewport.zoom = 1
  viewport.x = Math.round((containerSize.w - CHINA_MAP_WIDTH * s) / 2)
  viewport.y = Math.round((containerSize.h - CHINA_MAP_HEIGHT * s) / 2)
  if (smooth) setTimeout(() => (animating.value = false), 360)
}

function focusRegion(rg: RegionName, targetMinZoom = 2.15) {
  selectedRegion.value = rg
  const meta = CHINA_REGIONS[rg]
  if (!meta) return
  animating.value = true
  const bw = Math.max(95, meta.maxX - meta.minX)
  const bh = Math.max(85, meta.maxY - meta.minY)
  const fitZ = Math.min((containerSize.w * 0.56) / (bw * baseScale.value), (containerSize.h * 0.58) / (bh * baseScale.value))
  const z = clampZoom(Math.max(targetMinZoom, Math.min(3.4, fitZ)))
  const s = baseScale.value * z
  const centerX = (meta.minX + meta.maxX) / 2
  const centerY = (meta.minY + meta.maxY) / 2
  viewport.zoom = z
  viewport.x = Math.round(containerSize.w / 2 - centerX * s)
  viewport.y = Math.round(containerSize.h / 2 - centerY * s)
  setTimeout(() => (animating.value = false), 360)
}

function zoomAt(nextZoom: number, clientX: number, clientY: number) {
  const el = mapContainerEl.value
  if (!el) return
  animating.value = false
  const rect = el.getBoundingClientRect()
  const mx = clientX - rect.left
  const my = clientY - rect.top
  const oldS = baseScale.value * viewport.zoom
  const mapX = (mx - viewport.x) / oldS
  const mapY = (my - viewport.y) / oldS
  viewport.zoom = clampZoom(nextZoom)
  const newS = baseScale.value * viewport.zoom
  viewport.x = Math.round(mx - mapX * newS)
  viewport.y = Math.round(my - mapY * newS)
}

function zoomBy(factor: number) {
  const el = mapContainerEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  zoomAt(viewport.zoom * factor, rect.left + rect.width / 2, rect.top + rect.height / 2)
}

function onWheel(e: WheelEvent) {
  const factor = Math.exp(-e.deltaY * 0.0018)
  zoomAt(viewport.zoom * factor, e.clientX, e.clientY)
}

const pan = reactive({ active: false, moved: false, startX: 0, startY: 0, origX: 0, origY: 0 })
function onPointerDown(e: PointerEvent) {
  const target = e.target as HTMLElement
  if (target.closest('[data-map-hud], a, button')) return
  if (e.button !== 0 && e.button !== 1) return
  animating.value = false
  pan.active = true
  pan.moved = false
  pan.startX = e.clientX
  pan.startY = e.clientY
  pan.origX = viewport.x
  pan.origY = viewport.y
  window.addEventListener('pointermove', onPanMove)
  window.addEventListener('pointerup', onPanEnd)
}

function onPanMove(e: PointerEvent) {
  if (!pan.active) return
  const dx = e.clientX - pan.startX
  const dy = e.clientY - pan.startY
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) pan.moved = true
  viewport.x = Math.round(pan.origX + dx)
  viewport.y = Math.round(pan.origY + dy)
}

function onPanEnd() {
  pan.active = false
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', onPanEnd)
}

function onClickProvince(rg: RegionName) {
  if (pan.moved) return
  focusRegion(rg)
}

const matchedRegions = computed<Set<RegionName>>(() => {
  const kw = searchQ.value.trim().toLowerCase()
  if (!kw) return new Set(REGIONS)
  const hit = new Set<RegionName>()
  for (const rg of REGIONS) {
    const sum = regionSummaries.value[rg]
    if (
      rg.toLowerCase().includes(kw) ||
      sum.provinces.some((p) => p.toLowerCase().includes(kw)) ||
      sum.algos.some(({ algo }) => algo.id.toLowerCase().includes(kw) || algoName(algo).toLowerCase().includes(kw))
    ) {
      hit.add(rg)
    }
  }
  return hit
})

function jumpToSearchMatch() {
  const first = [...matchedRegions.value][0]
  if (first && searchQ.value.trim()) {
    focusRegion(first)
  }
}

const quickAlgoId = ref('')
const quickDispatching = ref(false)
const availableToDispatch = computed(() => {
  if (!selectedRegion.value) return []
  const already = new Set(regionSummaries.value[selectedRegion.value].algos.map((x) => x.algo.id))
  return auditedAlgos.value.filter((a) => !already.has(a.id))
})

async function quickDispatchToSelected() {
  if (!selectedRegion.value || !quickAlgoId.value || quickDispatching.value) return
  quickDispatching.value = true
  try {
    const cur = getDispatchedRegions(quickAlgoId.value)
    await setAlgorithmDispatches(quickAlgoId.value, [...new Set([...cur, selectedRegion.value])])
    toast(`已下发至「${selectedRegion.value}」区域`)
    quickAlgoId.value = ''
    await loadAll()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '下发失败', 'error')
  } finally {
    quickDispatching.value = false
  }
}

async function quickRevokeFromSelected(algoId: string) {
  if (!selectedRegion.value) return
  try {
    const cur = getDispatchedRegions(algoId).filter((r) => r !== selectedRegion.value)
    await setAlgorithmDispatches(algoId, cur)
    toast(`已取消「${selectedRegion.value}」区域的该算法授权`, 'info')
    await loadAll()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '操作失败', 'error')
  }
}

async function quickApproveTrial(reqId: string) {
  try {
    await reviewTrialRequest(reqId, true, '区域地图页快捷审批通过并下发')
    toast('审批已通过并下发至该区域')
    await loadAll()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '审批失败', 'error')
  }
}

let ro: ResizeObserver | null = null
onMounted(async () => {
  await loadAll()
  await nextTick()
  const el = mapContainerEl.value
  if (el) {
    const updateSize = () => {
      const r = el.getBoundingClientRect()
      if (r.width > 20 && r.height > 20) {
        const first = containerSize.w === 1000 && viewport.x === 0
        containerSize.w = r.width
        containerSize.h = r.height
        if (first) fitChina(false)
      }
    }
    updateSize()
    ro = new ResizeObserver(updateSize)
    ro.observe(el)
    fitChina(false)
  }
})

onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('pointermove', onPanMove)
  window.removeEventListener('pointerup', onPanEnd)
})

const svgTransformStyle = computed(() => {
  const s = baseScale.value * viewport.zoom
  return {
    transform: `translate(${Math.round(viewport.x)}px, ${Math.round(viewport.y)}px) scale(${s})`,
  }
})
</script>

<template>
  <div class="flex h-full w-full overflow-hidden bg-gray-50 dark:bg-gray-950">
    <!-- 主交互式中国 14 区域地图区（仅保留区域边界，与平台亮/暗主题完全统一） -->
    <div
      ref="mapContainerEl"
      class="relative min-w-0 flex-1 select-none overflow-hidden bg-gray-50/80 dark:bg-gray-950"
      :class="pan.active ? 'cursor-grabbing' : 'cursor-grab'"
      style="background-image: radial-gradient(rgba(148, 163, 184, 0.28) 1px, transparent 1px); background-size: 20px 20px"
      @wheel.prevent="onWheel"
      @pointerdown="onPointerDown"
      @mousedown.middle.prevent
    >
      <!-- 顶部 HUD：标题统计卡片 + 搜索框 -->
      <div
        data-map-hud="1"
        class="pointer-events-none absolute top-3 right-3 left-3 z-20 flex flex-wrap items-start justify-between gap-2.5"
      >
        <div class="pointer-events-auto rounded-xl border border-gray-200/90 bg-white/95 px-3.5 py-2 shadow-xs backdrop-blur dark:border-gray-800 dark:bg-gray-900/95">
          <div class="flex items-center gap-2">
            <span class="flex size-6 items-center justify-center rounded-lg bg-brand-50 text-brand-600 ring-1 ring-brand-100 dark:bg-brand-950/60 dark:text-brand-400 dark:ring-brand-900">
              <MapPin class="size-3.5" />
            </span>
            <h1 class="text-sm font-semibold text-gray-900 dark:text-white">全国 {{ REGIONS.length }} 区域算法授权地图</h1>
            <span
              class="rounded-full border px-2 py-0.2 text-[10px] font-medium"
              :class="
                isDetailMode
                  ? 'border-brand-200 bg-brand-50 text-brand-700 dark:border-brand-800 dark:bg-brand-950/60 dark:text-brand-300'
                  : 'border-gray-200 bg-gray-100 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300'
              "
            >
              {{ isDetailMode ? '明细视图 · 地块算法名' : '总览视图 · 授权数量' }}
            </span>
          </div>
          <div class="mono mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
            <span>覆盖区域 <strong class="text-gray-900 dark:text-white">{{ totalCoveredRegions }}</strong>/{{ REGIONS.length }}</span>
            <span class="text-gray-300 dark:text-gray-700">·</span>
            <span>累计授权 <strong class="text-emerald-600 dark:text-emerald-400">{{ totalAuthLinks }}</strong> 项次</span>
            <span class="text-gray-300 dark:text-gray-700">·</span>
            <span>待审批 <strong class="text-amber-600 dark:text-amber-400">{{ totalPending }}</strong></span>
          </div>
        </div>

        <form
          class="pointer-events-auto flex items-center gap-1.5 rounded-xl border border-gray-200/90 bg-white/95 px-2.5 py-1.5 shadow-xs backdrop-blur dark:border-gray-800 dark:bg-gray-900/95"
          @submit.prevent="jumpToSearchMatch"
        >
          <Search class="size-3.5 text-gray-400" />
          <input
            v-model="searchQ"
            class="w-44 bg-transparent text-xs text-gray-800 placeholder:text-gray-400 focus:outline-none sm:w-52 dark:text-gray-100"
            placeholder="搜索区域、省份或算法名…"
            aria-label="搜索区域或算法"
          />
          <button v-if="searchQ" type="button" class="text-gray-400 hover:text-gray-700 dark:hover:text-gray-200" @click="searchQ = ''">
            <X class="size-3.5" />
          </button>
        </form>
      </div>

      <!-- 矢量中国 14 区域融合地图层（无内部省界，仅显示区域外边界） -->
      <div
        class="pointer-events-none absolute top-0 left-0 origin-top-left"
        :class="{ 'transition-transform duration-300 ease-out': animating }"
        :style="svgTransformStyle"
      >
        <svg :width="CHINA_MAP_WIDTH" :height="CHINA_MAP_HEIGHT" :viewBox="`0 0 ${CHINA_MAP_WIDTH} ${CHINA_MAP_HEIGHT}`" class="overflow-visible">
          <defs>
            <filter id="china-soft-shadow" x="-6%" y="-6%" width="112%" height="116%">
              <feDropShadow dx="0" dy="6" stdDeviation="6" :flood-color="state.dark ? '#000000' : '#0f172a'" :flood-opacity="state.dark ? 0.5 : 0.1" />
            </filter>
            <!-- 各区域自然地形主轴曲线（用于维多利亚 3 / P社风格贴合地块走势的文字排版） -->
            <path
              v-for="rg in REGIONS"
              :id="'spine-' + rg"
              :key="'spine-' + rg"
              :d="CHINA_REGIONS[rg].labelPath"
            />
          </defs>

          <!-- 14 区域融合地块（仅区域边界，无省界） -->
          <g filter="url(#china-soft-shadow)">
            <path
              v-for="rg in REGIONS"
              :key="rg"
              :d="CHINA_REGIONS[rg].d"
              class="pointer-events-auto cursor-pointer transition-colors duration-150"
              :fill="parcelFill(rg)"
              :fill-opacity="searchQ && !matchedRegions.has(rg) ? 0.28 : 1"
              :stroke="state.dark ? '#475569' : '#ffffff'"
              :stroke-width="1.6 / viewport.zoom"
              stroke-linejoin="round"
              stroke-linecap="round"
              @mouseenter="hoveredRegion = rg"
              @mouseleave="hoveredRegion = null"
              @click.stop="onClickProvince(rg)"
            />
          </g>

          <!-- 悬停 / 选中区域顶层高亮外边框 -->
          <path
            v-if="hoveredRegion && hoveredRegion !== selectedRegion"
            :d="CHINA_REGIONS[hoveredRegion].d"
            fill="none"
            class="pointer-events-none"
            :stroke="parcelStroke(hoveredRegion)"
            :stroke-width="1.8 / viewport.zoom"
            stroke-linejoin="round"
          />
          <path
            v-if="selectedRegion"
            :d="CHINA_REGIONS[selectedRegion].d"
            fill="none"
            class="pointer-events-none"
            :stroke="parcelStroke(selectedRegion)"
            :stroke-width="2.4 / viewport.zoom"
            stroke-linejoin="round"
          />

          <!-- 模式 A：缩小时（zoom < 1.55）维多利亚 3 / P社风格地块贴合排版（区域名 + 大号算法数量） -->
          <g v-if="!isDetailMode" class="pointer-events-none select-none">
            <g
              v-for="rg in REGIONS"
              :key="'p社-' + rg"
              :opacity="searchQ && !matchedRegions.has(rg) ? 0.25 : 1"
            >
              <!-- 沿地块走势弯曲的区域名 -->
              <text
                class="carto-region-name"
                :font-size="CHINA_REGIONS[rg].nameSize"
                :dy="-(CHINA_REGIONS[rg].nameSize * 0.72 + 4)"
                dominant-baseline="central"
                :letter-spacing="CHINA_REGIONS[rg].nameSize >= 18 ? '0.28em' : '0.14em'"
                :fill="mapNameFill(rg)"
                :stroke="state.dark ? 'rgba(15, 23, 42, 0.75)' : 'rgba(255, 255, 255, 0.88)'"
                stroke-width="3"
                stroke-linejoin="round"
                paint-order="stroke"
              >
                <textPath :href="'#spine-' + rg" startOffset="50%" text-anchor="middle">
                  {{ currentRegion === rg ? `● ${rg}` : rg }}
                </textPath>
              </text>

              <!-- 沿地块走势排版的大号算法授权数量 -->
              <text
                class="carto-region-count"
                :font-size="CHINA_REGIONS[rg].countSize"
                :dy="CHINA_REGIONS[rg].countSize * 0.3"
                dominant-baseline="central"
                :fill="mapCountFill(rg)"
                :stroke="state.dark ? 'rgba(15, 23, 42, 0.85)' : 'rgba(255, 255, 255, 0.92)'"
                stroke-width="4.5"
                stroke-linejoin="round"
                paint-order="stroke"
              >
                <textPath :href="'#spine-' + rg" startOffset="50%" text-anchor="middle">
                  {{ regionSummaries[rg].algos.length }}
                </textPath>
              </text>

              <!-- 若存在待审批试用，在地块数字旁标示琥珀色圆点 -->
              <circle
                v-if="regionSummaries[rg].pendingRequests.length"
                :cx="CHINA_REGIONS[rg].cx + CHINA_REGIONS[rg].countSize * 0.62"
                :cy="CHINA_REGIONS[rg].cy - CHINA_REGIONS[rg].nameSize * 0.65"
                :r="Math.max(4, CHINA_REGIONS[rg].nameSize * 0.24)"
                fill="#f59e0b"
                :stroke="state.dark ? '#0f172a' : '#ffffff'"
                stroke-width="1.5"
              />
            </g>
          </g>
        </svg>
      </div>

      <!-- 模式 B：放大后（zoom >= 1.55）仅直接在地块上按轮廓分布算法完整名称（不显示区域名/数量，不标注自研） -->
      <div v-if="isDetailMode" class="pointer-events-none absolute inset-0 z-10 overflow-hidden">
        <template v-for="rg in REGIONS" :key="'ov-' + rg">
          <template v-if="CHINA_REGIONS[rg] && regionLayouts[rg]">
            <!-- 逐项贴合地块轮廓自然分布的算法完整名称 -->
            <RouterLink
              v-for="p in regionLayouts[rg].placed"
              :key="rg + '-' + p.item.algo.id"
              data-map-hud="1"
              :to="`/algorithms/${p.item.algo.id}`"
              class="carto-algo-label carto-text-halo pointer-events-auto absolute inline-flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 rounded-full px-1.5 py-0.5 font-medium whitespace-nowrap text-slate-700/90 transition-[color,opacity,background-color] duration-150 hover:z-30 hover:bg-white/80 hover:font-semibold hover:text-brand-700 hover:opacity-100 hover:shadow-2xs dark:text-slate-200/85 dark:hover:bg-slate-900/80 dark:hover:text-brand-300"
              :class="[
                { 'transition-all duration-300 ease-out': animating },
                selectedRegion === rg || hoveredRegion === rg ? 'z-20' : 'z-10',
              ]"
              :style="{
                left: Math.round(mapToScreen(p.mx, p.my).x) + 'px',
                top: Math.round(mapToScreen(p.mx, p.my).y + p.jitterY) + 'px',
                fontSize: algoLabelFontSize,
                opacity: regionLabelOpacity(rg),
              }"
              @mouseenter="hoveredRegion = rg"
              @mouseleave="hoveredRegion = null"
            >
              <span class="size-1.5 shrink-0 rounded-full" :class="TASK_DOT_CLS[p.item.algo.task]" />
              <span>{{ algoName(p.item.algo) }}</span>
            </RouterLink>
          </template>
        </template>
      </div>

      <!-- 底部左侧图例栏 -->
      <div
        data-map-hud="1"
        class="absolute bottom-3 left-3 z-20 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-gray-200/90 bg-white/95 px-3 py-1.5 text-[11px] text-gray-600 shadow-xs backdrop-blur dark:border-gray-800 dark:bg-gray-900/95 dark:text-gray-300"
      >
        <span class="inline-flex items-center gap-1.5"><span class="size-2.5 rounded-sm bg-emerald-200 ring-1 ring-emerald-400/60 dark:bg-emerald-900" />已授权区域</span>
        <span class="inline-flex items-center gap-1.5"><span class="size-2.5 rounded-sm bg-slate-100 ring-1 ring-slate-300 dark:bg-slate-800 dark:ring-slate-700" />暂未授权</span>
        <span class="inline-flex items-center gap-1.5"><span class="size-2 rounded-full bg-amber-500" />含待审批试用</span>
        <span class="hidden text-gray-300 sm:inline dark:text-gray-700">|</span>
        <span class="hidden text-gray-400 sm:inline">滚轮放大 ≥155% 或点击地块自动展开授权算法</span>
      </div>

      <!-- 底部右侧缩放控件（与编排实验页保持一致） -->
      <div
        data-map-hud="1"
        class="absolute right-3 bottom-3 z-20 flex items-center gap-0.5 rounded-lg border border-gray-200/90 bg-white/95 p-1 text-xs text-gray-600 shadow-sm backdrop-blur dark:border-gray-800 dark:bg-gray-900/95 dark:text-gray-300"
      >
        <button
          type="button"
          class="cursor-pointer rounded-md p-1 transition hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800"
          :disabled="viewport.zoom <= MIN_ZOOM"
          title="缩小"
          @click="zoomBy(1 / 1.25)"
        >
          <ZoomOut class="size-3.5" />
        </button>
        <span class="mono min-w-[46px] text-center text-[11px] font-medium">{{ Math.round(viewport.zoom * 100) }}%</span>
        <button
          type="button"
          class="cursor-pointer rounded-md p-1 transition hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800"
          :disabled="viewport.zoom >= MAX_ZOOM"
          title="放大（≥155% 展开算法详情）"
          @click="zoomBy(1.25)"
        >
          <ZoomIn class="size-3.5" />
        </button>
        <span class="mx-0.5 h-3.5 w-px bg-gray-200 dark:bg-gray-700" />
        <button
          type="button"
          class="inline-flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-1 text-[11px] transition hover:bg-gray-100 dark:hover:bg-gray-800"
          title="重置为全国总览视图"
          @click="selectedRegion = null; fitChina(true)"
        >
          <Maximize2 class="size-3.5" />全国
        </button>
      </div>
    </div>

    <!-- 右侧区域授权明细面板（与 StudioView 检查器同款结构与质感） -->
    <aside class="flex w-[340px] shrink-0 flex-col overflow-hidden border-l border-gray-200 bg-white xl:w-[376px] dark:border-gray-800 dark:bg-gray-900">
      <div class="flex shrink-0 items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-800">
        <div class="flex items-center gap-2">
          <Layers class="size-4 text-brand-600 dark:text-brand-400" />
          <h2 class="text-sm font-semibold text-gray-900 dark:text-white">
            {{ selectedRegion ? `${selectedRegion}区域授权详情` : `${REGIONS.length} 区域授权总览` }}
          </h2>
        </div>
        <button
          v-if="selectedRegion"
          type="button"
          class="btn-ghost px-2 py-0.5 text-xs"
          @click="selectedRegion = null; fitChina(true)"
        >
          返回全国
        </button>
      </div>

      <!-- 模式 1：全国 14 区域总览列表 -->
      <div v-if="!selectedRegion" class="flex-1 space-y-1.5 overflow-y-auto p-3">
        <p class="mb-2 text-xs text-gray-500">点击任意区域卡片或地图地块，自动缩放定位并查看授权算法明细。</p>
        <button
          v-for="item in sortedRegionList"
          :key="item.region"
          type="button"
          class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-xl border border-gray-100 bg-gray-50/50 px-3 py-2.5 text-left transition hover:border-brand-200 hover:bg-white hover:shadow-2xs dark:border-gray-800 dark:bg-gray-800/30 dark:hover:border-brand-800 dark:hover:bg-gray-800/70"
          @mouseenter="hoveredRegion = item.region"
          @mouseleave="hoveredRegion = null"
          @click="focusRegion(item.region)"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <span class="text-xs font-semibold text-gray-900 dark:text-white">{{ item.region }}区域</span>
              <span
                v-if="currentRegion === item.region"
                class="chip border-emerald-200 bg-emerald-50 py-0 text-[10px] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300"
              >当前</span>
              <span
                v-if="item.pendingRequests.length"
                class="chip border-amber-200 bg-amber-50 py-0 text-[10px] text-amber-700 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300"
              >{{ item.pendingRequests.length }} 待审</span>
            </div>
            <p class="mt-0.5 truncate text-[11px] text-gray-500">{{ item.provinces.join(' · ') }}</p>
          </div>
          <span
            class="mono shrink-0 rounded-md px-2 py-0.5 text-xs font-semibold"
            :class="item.algos.length ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-300' : 'bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-500'"
          >
            {{ item.algos.length }} 项
          </span>
        </button>
      </div>

      <!-- 模式 2：单个区域授权算法明细 + 快捷下发/审批 -->
      <div v-else class="flex-1 space-y-4 overflow-y-auto p-4 text-xs">
        <div class="rounded-xl border border-gray-200/80 bg-gray-50/70 p-3 dark:border-gray-800 dark:bg-gray-950/60">
          <div class="flex items-center justify-between">
            <span class="text-sm font-semibold text-gray-900 dark:text-white">{{ selectedRegion }}区域</span>
            <span class="mono rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">
              已授权 {{ regionSummaries[selectedRegion].algos.length }} 项
            </span>
          </div>
          <p class="mt-1 text-[11px] text-gray-500">
            覆盖片区：{{ regionSummaries[selectedRegion].provinces.join('、') }}
          </p>
        </div>

        <!-- 已授权算法列表 -->
        <div>
          <h3 class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-gray-900 dark:text-white">
            <CheckCircle2 class="size-3.5 text-emerald-600 dark:text-emerald-400" />已授权算法（{{ regionSummaries[selectedRegion].algos.length }}）
          </h3>
          <div v-if="regionSummaries[selectedRegion].algos.length" class="space-y-2">
            <div
              v-for="{ algo, dispatch } in regionSummaries[selectedRegion].algos"
              :key="algo.id"
              class="rounded-xl border border-gray-200/90 bg-white p-2.5 transition hover:border-gray-300 dark:border-gray-800 dark:bg-gray-900/80 dark:hover:border-gray-700"
            >
              <div class="flex items-center gap-1.5">
                <TaskIcon :task="algo.task" class="size-3.5 shrink-0" :class="TASKS[algo.task].color" />
                <RouterLink :to="`/algorithms/${algo.id}`" class="truncate font-medium text-gray-900 hover:text-brand-600 dark:text-white dark:hover:text-brand-400">
                  {{ algoName(algo) }}
                </RouterLink>
                <button
                  v-if="can.dispatch"
                  type="button"
                  class="ml-auto cursor-pointer rounded p-0.5 text-gray-400 hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/50 dark:hover:text-rose-400"
                  title="取消该区域授权"
                  @click="quickRevokeFromSelected(algo.id)"
                >
                  <X class="size-3.5" />
                </button>
              </div>
              <div class="mt-1 flex items-center justify-between text-[11px] text-gray-500">
                <span>{{ TASKS[algo.task].label }} · {{ algo.framework }}</span>
                <span class="chip py-0 text-[10px]">{{ dispatch.source === 'approved_request' ? '审批下发' : '总部直发' }}</span>
              </div>
            </div>
          </div>
          <p v-else class="rounded-lg border border-dashed border-gray-200 py-5 text-center text-gray-400 dark:border-gray-800">
            该区域暂未授权算法
          </p>
        </div>

        <!-- 待审批试用申请 -->
        <div v-if="regionSummaries[selectedRegion].pendingRequests.length">
          <h3 class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-300">
            <Clock class="size-3.5" />待审批试用申请（{{ regionSummaries[selectedRegion].pendingRequests.length }}）
          </h3>
          <div class="space-y-2">
            <div
              v-for="req in regionSummaries[selectedRegion].pendingRequests"
              :key="req.id"
              class="rounded-xl border border-amber-200 bg-amber-50/70 p-2.5 dark:border-amber-900 dark:bg-amber-950/30"
            >
              <RouterLink :to="`/algorithms/${req.algorithmId}`" class="font-medium text-gray-900 hover:text-brand-600 dark:text-white">
                {{ algoById.get(req.algorithmId) ? algoName(algoById.get(req.algorithmId)!) : req.algorithmId }}
              </RouterLink>
              <p class="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{{ req.reason }}</p>
              <button
                v-if="can.dispatch"
                type="button"
                class="btn-brand mt-2 py-1 text-[11px]"
                @click="quickApproveTrial(req.id)"
              >
                <Send class="size-3" />审批通过并下发
              </button>
            </div>
          </div>
        </div>

        <!-- 管理员快捷下发 -->
        <div v-if="can.dispatch && availableToDispatch.length" class="border-t border-gray-100 pt-3 dark:border-gray-800">
          <h3 class="mb-2 flex items-center gap-1.5 text-xs font-semibold text-gray-900 dark:text-white">
            <Send class="size-3.5 text-brand-600 dark:text-brand-400" />快捷下发算法至{{ selectedRegion }}区域
          </h3>
          <div class="flex gap-1.5">
            <select
              v-model="quickAlgoId"
              class="input min-w-0 flex-1 py-1.5 text-xs"
              aria-label="选择要下发的算法"
            >
              <option value="" disabled>选择已审核算法…</option>
              <option v-for="a in availableToDispatch" :key="a.id" :value="a.id">{{ algoName(a) }}</option>
            </select>
            <button
              type="button"
              class="btn-brand shrink-0 py-1.5 text-xs"
              :disabled="!quickAlgoId || quickDispatching"
              @click="quickDispatchToSelected"
            >
              下发
            </button>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
/* 维多利亚 3 / P社风格地图领土排版 */
.carto-region-name {
  font-family: 'Songti SC', 'Noto Serif SC', 'STSong', 'SimSun', Georgia, serif;
  font-weight: 700;
}

.carto-region-count {
  font-family: Georgia, 'Times New Roman', 'Noto Serif SC', serif;
  font-weight: 800;
  font-variant-numeric: lining-nums tabular-nums;
}

.carto-algo-label {
  font-family: 'Inter', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', system-ui, sans-serif;
  letter-spacing: 0.02em;
  line-height: 1.25;
}

/* 放大后直接贴地显示的柔和地图文字光晕，自然融入地块底色 */
.carto-text-halo {
  text-shadow:
    0 0 2.5px rgba(255, 255, 255, 0.88),
    0 0 6px rgba(255, 255, 255, 0.65),
    0 1px 1.5px rgba(255, 255, 255, 0.78);
}

:global(.dark) .carto-text-halo {
  text-shadow:
    0 0 3px rgba(15, 23, 42, 0.92),
    0 0 7px rgba(15, 23, 42, 0.72),
    0 1px 1.5px rgba(15, 23, 42, 0.85);
}
</style>
