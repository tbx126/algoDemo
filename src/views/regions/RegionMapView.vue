<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Maximize2, X, ZoomIn, ZoomOut } from 'lucide-vue-next'
import { listAlgorithms, listDispatches, listTrialRequests } from '@/api'
import { CHINA_MAP_HEIGHT, CHINA_MAP_WIDTH, CHINA_REGIONS } from '@/assets/chinaMapData'
import type { Algorithm, AlgorithmDispatch, RegionName, RegionTrialRequest, TaskType } from '@/types'
import { REGIONS, TASKS } from '@/utils/meta'
import { algoName } from '@/utils/display'
import { useSession } from '@/stores/session'

const { state, currentRegion } = useSession()

const algorithms = ref<Algorithm[]>([])
const dispatches = ref<AlgorithmDispatch[]>([])
const trialRequests = ref<RegionTrialRequest[]>([])

async function loadAll() {
  const [aRes, dRes, tRes] = await Promise.all([
    listAlgorithms({ pageSize: 200 }),
    listDispatches(),
    listTrialRequests(),
  ])
  algorithms.value = aRes.items
  dispatches.value = dRes
  trialRequests.value = tRes
}

const algoById = computed(() => new Map(algorithms.value.map((a) => [a.id, a])))

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

const totalAuthLinks = computed(() => dispatches.value.length)

// ==================== 14 区域地块柔和色盘 ====================
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

const TASK_DOT_CLS: Record<TaskType, string> = {
  'image-classification': 'bg-sky-500',
  'image-dehazing': 'bg-cyan-500',
  'object-detection': 'bg-amber-500',
  'semantic-segmentation': 'bg-emerald-500',
  'instance-segmentation': 'bg-teal-500',
  'keypoint-detection': 'bg-rose-500',
  ocr: 'bg-violet-500',
  'power-forecast': 'bg-indigo-500',
  'server-fault-0x07': 'bg-red-500',
  'signal-processing': 'bg-orange-500',
  optimization: 'bg-lime-500',
  custom: 'bg-slate-400',
}

const hoveredRegion = ref<RegionName | null>(null)
const pinnedRegion = ref<RegionName | null>(null)
const activeRegion = computed<RegionName | null>(() => pinnedRegion.value ?? hoveredRegion.value)

function parcelFill(rg: RegionName): string {
  const isDark = state.dark
  const pal = isDark ? REGION_COLORS_DARK[rg] : REGION_COLORS_LIGHT[rg]
  if (activeRegion.value === rg) return pal.active
  if (regionSummaries.value[rg].algos.length > 0) return pal.fill
  return isDark ? '#1e293b' : '#f1f5f9'
}

function parcelStroke(rg: RegionName): string {
  const isDark = state.dark
  if (pinnedRegion.value === rg) return isDark ? '#818cf8' : '#4f46e5'
  if (hoveredRegion.value === rg) return isDark ? '#94a3b8' : '#64748b'
  return isDark ? '#475569' : '#ffffff'
}

function mapCountFill(rg: RegionName): string {
  const isDark = state.dark
  const hasAlgos = regionSummaries.value[rg].algos.length > 0
  if (activeRegion.value === rg) return isDark ? '#ffffff' : '#1e1b4b'
  if (hasAlgos) return isDark ? '#f8fafc' : '#0f172a'
  return isDark ? 'rgba(148, 163, 184, 0.55)' : 'rgba(100, 116, 139, 0.5)'
}

function mapNameFill(rg: RegionName): string {
  const isDark = state.dark
  const hasAlgos = regionSummaries.value[rg].algos.length > 0
  if (activeRegion.value === rg) return isDark ? '#e0e7ff' : '#312e81'
  if (hasAlgos) return isDark ? 'rgba(226, 232, 240, 0.88)' : 'rgba(30, 41, 59, 0.78)'
  return isDark ? 'rgba(148, 163, 184, 0.6)' : 'rgba(100, 116, 139, 0.65)'
}

// ==================== 地图视口、拖拽与悬浮窗定位 ====================
const mapContainerEl = ref<HTMLElement>()
const containerSize = reactive({ w: 800, h: 480 })
const viewport = reactive({ x: 0, y: 0, zoom: 1 })
const animating = ref(false)
const pointerPos = reactive({ x: 0, y: 0 })

const MIN_ZOOM = 0.9
const MAX_ZOOM = 3.2

const baseScale = computed(() => {
  const padX = 28
  const padY = 34
  return Math.min((containerSize.w - padX * 2) / CHINA_MAP_WIDTH, (containerSize.h - padY * 2) / CHINA_MAP_HEIGHT)
})

function clampZoom(z: number) {
  return Number(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z)).toFixed(3))
}

function fitChina(smooth = false) {
  animating.value = smooth
  const s = baseScale.value
  viewport.zoom = 1
  viewport.x = Math.round((containerSize.w - CHINA_MAP_WIDTH * s) / 2)
  viewport.y = Math.round((containerSize.h - CHINA_MAP_HEIGHT * s) / 2 + 8)
  if (smooth) setTimeout(() => (animating.value = false), 320)
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
  // 若鼠标位于已固定的详情浮窗内部，保留浮窗内列表的正常滚动
  if ((e.target as HTMLElement | null)?.closest('[data-map-popover]')) return
  e.preventDefault()
  const factor = Math.exp(-e.deltaY * 0.002)
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

function updatePointer(e: MouseEvent) {
  const el = mapContainerEl.value
  if (!el || pinnedRegion.value) return
  const rect = el.getBoundingClientRect()
  pointerPos.x = e.clientX - rect.left
  pointerPos.y = e.clientY - rect.top
}

function onEnterParcel(rg: RegionName, e: MouseEvent) {
  hoveredRegion.value = rg
  updatePointer(e)
}

function onClickParcel(rg: RegionName, e: MouseEvent) {
  if (pan.moved) return
  if (pinnedRegion.value === rg) {
    pinnedRegion.value = null
    return
  }
  const el = mapContainerEl.value
  if (el) {
    const rect = el.getBoundingClientRect()
    pointerPos.x = e.clientX - rect.left
    pointerPos.y = e.clientY - rect.top
  }
  pinnedRegion.value = rg
}

function onBgClick() {
  if (!pan.moved && pinnedRegion.value) pinnedRegion.value = null
}

/** 悬浮/固定详情窗坐标（自动防溢出容器边缘） */
const popoverStyle = computed(() => {
  const popW = 248
  const popH = 260
  const pad = 12
  let left = pointerPos.x + 16
  let top = pointerPos.y - 24
  if (left + popW + pad > containerSize.w) left = Math.max(pad, pointerPos.x - popW - 16)
  if (top + popH + pad > containerSize.h) top = Math.max(pad, containerSize.h - popH - pad)
  if (top < 54) top = 54
  return { left: `${Math.round(left)}px`, top: `${Math.round(top)}px` }
})

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') pinnedRegion.value = null
}

let ro: ResizeObserver | null = null
onMounted(async () => {
  window.addEventListener('keydown', onKeydown)
  await loadAll()
  await nextTick()
  const el = mapContainerEl.value
  if (el) {
    const updateSize = () => {
      const r = el.getBoundingClientRect()
      if (r.width > 20 && r.height > 20) {
        containerSize.w = r.width
        containerSize.h = r.height
        fitChina(false)
      }
    }
    updateSize()
    ro = new ResizeObserver(updateSize)
    ro.observe(el)
  }
})

onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('keydown', onKeydown)
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
  <div
    ref="mapContainerEl"
    class="relative h-full w-full select-none overflow-hidden bg-gray-50/70 dark:bg-gray-950/70"
    :class="pan.active ? 'cursor-grabbing' : 'cursor-grab'"
    style="background-image: radial-gradient(rgba(148, 163, 184, 0.25) 1px, transparent 1px); background-size: 18px 18px"
    @wheel="onWheel"
    @pointerdown="onPointerDown"
    @mousemove="updatePointer"
    @click="onBgClick"
    @mousedown.middle.prevent
  >
    <!-- 左上角精简总授权次数统计徽章 -->
    <div
      data-map-hud="1"
      class="pointer-events-none absolute top-3 left-3 z-20"
    >
      <div class="pointer-events-auto rounded-xl border border-gray-200/80 bg-white/90 px-3.5 py-2 shadow-xs backdrop-blur-md dark:border-gray-800/90 dark:bg-gray-900/90">
        <div class="flex items-center gap-1.5 text-[11px] font-medium text-gray-500 dark:text-gray-400">
          <span class="size-1.5 rounded-full bg-emerald-500 ring-2 ring-emerald-500/25" />
          <span>总授权次数</span>
        </div>
        <div class="mt-0.5 flex items-baseline gap-1">
          <span class="mono text-2xl leading-none font-bold tracking-tight text-gray-900 tabular-nums dark:text-white">
            {{ totalAuthLinks }}
          </span>
          <span class="text-[11px] text-gray-400">项次</span>
        </div>
      </div>
    </div>

    <!-- 矢量中国 14 区域融合地图层（仅区域边界 + 维多利亚 3 / P社风格地块排版） -->
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
          <path
            v-for="rg in REGIONS"
            :id="'spine-' + rg"
            :key="'spine-' + rg"
            :d="CHINA_REGIONS[rg].labelPath"
          />
        </defs>

        <!-- 14 区域融合地块 -->
        <g filter="url(#china-soft-shadow)">
          <path
            v-for="rg in REGIONS"
            :key="rg"
            :d="CHINA_REGIONS[rg].d"
            class="pointer-events-auto cursor-pointer transition-colors duration-150"
            :fill="parcelFill(rg)"
            :stroke="state.dark ? '#475569' : '#ffffff'"
            :stroke-width="1.6 / viewport.zoom"
            stroke-linejoin="round"
            stroke-linecap="round"
            @mouseenter="onEnterParcel(rg, $event)"
            @mouseleave="hoveredRegion = null"
            @click.stop="onClickParcel(rg, $event)"
          />
        </g>

        <!-- 悬停 / 固定区域顶层高亮外边框 -->
        <path
          v-if="activeRegion"
          :d="CHINA_REGIONS[activeRegion].d"
          fill="none"
          class="pointer-events-none"
          :stroke="parcelStroke(activeRegion)"
          :stroke-width="2.2 / viewport.zoom"
          stroke-linejoin="round"
        />

        <!-- 维多利亚 3 / P社风格地块贴合排版（区域名 + 大号算法授权数量） -->
        <g class="pointer-events-none select-none">
          <g
            v-for="rg in REGIONS"
            :key="'carto-' + rg"
          >
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
          </g>
        </g>
      </svg>
    </div>

    <!-- 悬浮 / 点击固定时的额外算法详情浮窗 -->
    <div
      v-if="activeRegion && regionSummaries[activeRegion]"
      data-map-hud="1"
      data-map-popover="1"
      class="absolute z-30 w-[248px] rounded-xl border border-gray-200/90 bg-white/95 p-3 shadow-lg backdrop-blur-md dark:border-gray-700/90 dark:bg-gray-900/95"
      :class="pinnedRegion ? 'pointer-events-auto ring-2 ring-brand-500/20' : 'pointer-events-none'"
      :style="popoverStyle"
      @click.stop
    >
      <div class="mb-2 flex items-start justify-between gap-2 border-b border-gray-100 pb-2 dark:border-gray-800">
        <div class="min-w-0">
          <div class="flex items-center gap-1.5">
            <span class="text-xs font-semibold text-gray-900 dark:text-white">{{ activeRegion }}区域</span>
            <span class="mono rounded-full bg-brand-50 px-1.5 py-0.2 text-[10px] font-semibold text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">
              {{ regionSummaries[activeRegion].algos.length }} 项
            </span>
          </div>
          <p class="mt-0.5 truncate text-[10px] text-gray-400">
            {{ regionSummaries[activeRegion].provinces.join(' · ') }}
          </p>
        </div>
        <button
          v-if="pinnedRegion"
          type="button"
          class="cursor-pointer rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200"
          aria-label="关闭浮窗"
          @click="pinnedRegion = null"
        >
          <X class="size-3.5" />
        </button>
      </div>

      <div v-if="regionSummaries[activeRegion].algos.length" class="scroll-thin max-h-44 space-y-1 overflow-y-auto pr-0.5">
        <RouterLink
          v-for="{ algo } in regionSummaries[activeRegion].algos"
          :key="algo.id"
          :to="`/algorithms/${algo.id}`"
          class="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[11px] text-gray-700 transition hover:bg-brand-50 hover:text-brand-700 dark:text-gray-200 dark:hover:bg-brand-950/50 dark:hover:text-brand-300"
        >
          <span class="size-1.5 shrink-0 rounded-full" :class="TASK_DOT_CLS[algo.task]" />
          <span class="min-w-0 flex-1 truncate font-medium">{{ algoName(algo) }}</span>
          <span class="shrink-0 text-[10px] text-gray-400">{{ TASKS[algo.task].label }}</span>
        </RouterLink>
      </div>
      <p v-else class="py-2 text-center text-[11px] text-gray-400">该区域暂未授权算法</p>

      <p v-if="!pinnedRegion" class="mt-2 border-t border-gray-100 pt-1.5 text-[10px] text-gray-400 dark:border-gray-800">
        点击地块可固定浮窗并跳转算法详情
      </p>
    </div>

    <!-- 底部提示与缩放控件 -->
    <div
      data-map-hud="1"
      class="pointer-events-none absolute right-3 bottom-3 left-3 z-20 flex items-center justify-between gap-2"
    >
      <span class="hidden rounded-lg border border-gray-200/80 bg-white/90 px-2.5 py-1 text-[11px] text-gray-500 backdrop-blur sm:inline-flex dark:border-gray-800 dark:bg-gray-900/90 dark:text-gray-400">
        悬浮查看授权算法 · 点击固定浮窗 · 滚轮缩放
      </span>

      <div class="pointer-events-auto ml-auto flex items-center gap-0.5 rounded-lg border border-gray-200/80 bg-white/90 p-0.5 text-xs text-gray-600 shadow-2xs backdrop-blur dark:border-gray-800 dark:bg-gray-900/90 dark:text-gray-300">
        <button
          type="button"
          class="cursor-pointer rounded p-1 transition hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800"
          :disabled="viewport.zoom <= MIN_ZOOM"
          title="缩小"
          @click="zoomBy(1 / 1.25)"
        >
          <ZoomOut class="size-3.5" />
        </button>
        <span class="mono min-w-[40px] text-center text-[10px] font-medium">{{ Math.round(viewport.zoom * 100) }}%</span>
        <button
          type="button"
          class="cursor-pointer rounded p-1 transition hover:bg-gray-100 disabled:opacity-40 dark:hover:bg-gray-800"
          :disabled="viewport.zoom >= MAX_ZOOM"
          title="放大"
          @click="zoomBy(1.25)"
        >
          <ZoomIn class="size-3.5" />
        </button>
        <span class="mx-0.5 h-3 w-px bg-gray-200 dark:bg-gray-700" />
        <button
          type="button"
          class="inline-flex cursor-pointer items-center gap-1 rounded px-1.5 py-1 text-[10px] transition hover:bg-gray-100 dark:hover:bg-gray-800"
          title="重置视图"
          @click="pinnedRegion = null; fitChina(true)"
        >
          <Maximize2 class="size-3" />重置
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.carto-region-name {
  font-family: 'Songti SC', 'Noto Serif SC', 'STSong', 'SimSun', Georgia, serif;
  font-weight: 700;
}

.carto-region-count {
  font-family: Georgia, 'Times New Roman', 'Noto Serif SC', serif;
  font-weight: 800;
  font-variant-numeric: lining-nums tabular-nums;
}
</style>
