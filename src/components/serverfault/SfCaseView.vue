<script setup lang="ts">
/**
 * 服务器故障检测标准：单个 60 分钟窗口的折线图视图（所有标准算法 / 数据集共用）：
 *   1. 遥测曲线（利用率 / 温度 / 磁盘吞吐 / 网络吞吐），背景标出预警真值段（浅黄）、真值故障段（浅红）与算法预测故障段（橙色斜线 + 底部色条）
 *   2. 运行状态：ground truth vs 算法预测（阶梯线）
 *   3. 故障概率与未来 10 分钟预警概率，背景标出真值故障段与预警真值段
 */
import { computed } from 'vue'
import SfLineChart, { type SfBand, type SfSeries } from './SfLineChart.vue'
import { SF_STATES, type SfCase } from './types'

const props = withDefaults(defineProps<{ c: SfCase; states?: readonly string[]; narrow?: boolean }>(), { states: () => SF_STATES })

const x = computed(() => props.c.channels.cpu_pct.map((_, i) => i))
const hasGpu = computed(() => props.c.channels.gpu_pct.some((v) => v > 0) || props.c.channels.gpu_temp_c.some((v) => v > 0))
const hasGt = computed(() => Array.isArray(props.c.gt) && props.c.gt.length > 0)
const hasPred = computed(() => Array.isArray(props.c.pred) && props.c.pred.length > 0)

function runs(seq: number[] | null | undefined, kind: SfBand['kind'], label: string): SfBand[] {
  const out: SfBand[] = []
  if (!seq) return out
  let start = -1
  seq.forEach((v, i) => {
    if (v > 0 && start < 0) start = i
    if ((v <= 0 || i === seq.length - 1) && start >= 0) {
      out.push({ from: start, to: v > 0 ? i : i - 1, kind, label })
      start = -1
    }
  })
  return out
}
const gtBands = computed(() => runs(props.c.gt, 'fault', '真值故障段'))
// 预测故障段用橙色斜线 + 底部色条绘制，与真值的浅红背景可叠加区分（重叠 = 命中，只有斜线 = 误报，只有浅红 = 漏报）
const predBands = computed(() => runs(props.c.pred, 'pred', '预测故障段'))
const warnBands = computed(() => runs(props.c.warnGt, 'warn', '预警真值段'))
const bgBands = computed(() => [...warnBands.value, ...gtBands.value, ...predBands.value])

const minute = (v: number) => `第 ${Math.round(v)} 分钟`
const pct = (v: number) => `${Math.round(v)}%`

const util = computed<SfSeries[]>(() => {
  const ch = props.c.channels
  const s: SfSeries[] = [
    { key: 'cpu', name: 'CPU 利用率', values: ch.cpu_pct, color: 'var(--v7-s1)' },
    { key: 'mem', name: '内存占用', values: ch.mem_pct, color: 'var(--v7-s2)' },
  ]
  if (hasGpu.value) {
    s.push({ key: 'gpu', name: 'GPU 利用率', values: ch.gpu_pct, color: 'var(--v7-s3)' })
    s.push({ key: 'gmem', name: 'GPU 显存', values: ch.gpu_mem_pct, color: 'var(--v7-s7)', dashed: true })
  }
  return s
})
const temps = computed<SfSeries[]>(() => {
  const s: SfSeries[] = [{ key: 'ct', name: 'CPU 温度', values: props.c.channels.cpu_temp_c, color: 'var(--v7-s1)' }]
  if (hasGpu.value) s.push({ key: 'gt', name: 'GPU 温度', values: props.c.channels.gpu_temp_c, color: 'var(--v7-s3)' })
  return s
})
/** 磁盘 / 网络坐标上限：有机器规格时用该机器的容量，否则取数据最大值 */
const niceMax = (vals: number[]) => Math.max(10, Math.ceil(Math.max(...vals) / 10) * 10)
const diskMax = computed(() => props.c.spec?.disk_max_mbps ?? niceMax(props.c.channels.disk_io_mbps))
const netMax = computed(() => props.c.spec?.net_max_mbps ?? niceMax(props.c.channels.net_mbps))
const fmtCap = (v: number, unit: string) => (v >= 1000 && unit === 'Mbps' ? `${+(v / 1000).toFixed(1)} Gbps` : `${v.toLocaleString()} ${unit}`)
const disk = computed<SfSeries[]>(() => [{ key: 'disk', name: '磁盘吞吐', values: props.c.channels.disk_io_mbps, color: 'var(--v7-s1)', area: true }])
const net = computed<SfSeries[]>(() => [{ key: 'net', name: '网络吞吐', values: props.c.channels.net_mbps, color: 'var(--v7-s1)', area: true }])

const stateSeries = computed<SfSeries[]>(() => {
  const s: SfSeries[] = []
  if (hasGt.value) s.push({ key: 'gt', name: 'Ground Truth', values: props.c.gt!, color: 'var(--v7-s1)', step: true, width: 4 })
  if (hasPred.value) s.push({ key: 'pred', name: '算法预测', values: props.c.pred!, color: 'var(--v7-s2)', step: true, width: 2 })
  return s
})
const stateTicks = computed(() => props.states.map((_, i) => i))
const stateName = (v: number) => props.states[Math.round(v)] ?? String(v)

const scoreSeries = computed<SfSeries[]>(() => {
  const s: SfSeries[] = []
  if (props.c.anomaly) s.push({ key: 'an', name: '故障概率', values: props.c.anomaly.map((v) => v * 100), color: 'var(--v7-s2)', area: true })
  if (props.c.warn) s.push({ key: 'wn', name: '10 分钟预警概率', values: props.c.warn.map((v) => v * 100), color: 'var(--v7-s7)' })
  return s
})
const scoreBands = bgBands

const onsetMarker = computed(() => (props.c.onset !== undefined && props.c.onset >= 0 && props.c.onset < 60 ? [{ x: props.c.onset, label: '故障起点' }] : []))
const firstPred = computed(() => (props.c.pred ? props.c.pred.findIndex((v) => v > 0) : -1))
const delay = computed(() => {
  if (!props.c.gt || !props.c.pred || props.c.onset === undefined || props.c.onset < 0 || props.c.onset >= 60) return null
  const gtCls = Math.max(...props.c.gt)
  const hit = props.c.pred.findIndex((v, i) => i >= props.c.onset! && v === gtCls)
  return hit < 0 ? null : hit - props.c.onset!
})
const agree = computed(() => {
  if (!props.c.gt || !props.c.pred) return null
  const n = props.c.gt.filter((v, i) => v === props.c.pred![i]).length
  return Math.round((n / props.c.gt.length) * 1000) / 10
})
</script>

<template>
  <div class="sf-viz-scope space-y-4">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-600 dark:text-gray-300">
      <span v-if="c.server" class="mono">{{ c.server }}<span v-if="c.role" class="text-gray-400"> · {{ c.role }}</span></span>
      <span v-if="c.spec" class="text-gray-500">规格：<template v-if="c.spec.cpu_cores">{{ c.spec.cpu_cores }} 核 · </template><template v-if="c.spec.mem_gb">{{ c.spec.mem_gb }} GB · </template>磁盘 {{ fmtCap(c.spec.disk_max_mbps, 'MB/s') }} · 网络 {{ fmtCap(c.spec.net_max_mbps, 'Mbps') }}</span>
      <span v-if="c.label">真值：<strong class="text-gray-900 dark:text-white">{{ c.label }}</strong></span>
      <span v-if="c.predLabel">预测：<strong class="text-gray-900 dark:text-white">{{ c.predLabel }}</strong></span>
      <span v-if="c.onset !== undefined && c.onset >= 60" class="text-gray-500">故障发生在窗口之后（第 {{ c.onset }} 分钟），窗口内只有前兆</span>
      <span v-else-if="firstPred >= 0 && !hasGt">首次判定故障：第 {{ firstPred }} 分钟</span>
      <span v-if="delay !== null">检测时延：<strong class="text-gray-900 dark:text-white">{{ delay }} 分钟</strong></span>
      <span v-if="agree !== null">逐分钟一致率：<strong class="text-gray-900 dark:text-white">{{ agree }}%</strong></span>
    </div>

    <div class="grid gap-x-6 gap-y-4" :class="narrow ? 'grid-cols-1' : 'md:grid-cols-2'">
      <div>
        <p class="mb-1 text-xs font-medium text-gray-700 dark:text-gray-200">利用率（%）</p>
        <SfLineChart :x="x" :series="util" :bands="bgBands" :markers="onsetMarker" :y-min="0" :y-max="100" :y-format="pct" :x-format="minute" :height="narrow ? 150 : 170" />
      </div>
      <div>
        <p class="mb-1 text-xs font-medium text-gray-700 dark:text-gray-200">温度（℃）</p>
        <SfLineChart :x="x" :series="temps" :bands="bgBands" :markers="onsetMarker" :y-min="30" :y-max="100" :y-format="(v) => `${Math.round(v)}℃`" :x-format="minute" :height="narrow ? 150 : 170" />
      </div>
      <div>
        <p class="mb-1 text-xs font-medium text-gray-700 dark:text-gray-200">磁盘吞吐（MB/s<template v-if="c.spec">，纵轴上限 = 该机器磁盘上限</template>）</p>
        <SfLineChart :x="x" :series="disk" :bands="bgBands" :markers="onsetMarker" :y-min="0" :y-max="diskMax" :y-format="(v) => String(Math.round(v))" :x-format="minute" :height="narrow ? 130 : 150" />
      </div>
      <div>
        <p class="mb-1 text-xs font-medium text-gray-700 dark:text-gray-200">网络吞吐（Mbps<template v-if="c.spec">，纵轴上限 = 该机器带宽</template>）</p>
        <SfLineChart :x="x" :series="net" :bands="bgBands" :markers="onsetMarker" :y-min="0" :y-max="netMax" :y-format="(v) => String(Math.round(v))" :x-format="minute" :height="narrow ? 130 : 150" />
      </div>
    </div>

    <div v-if="stateSeries.length">
      <p class="mb-1 text-xs font-medium text-gray-700 dark:text-gray-200">运行状态：{{ hasGt && hasPred ? 'Ground Truth vs 算法预测' : hasGt ? 'Ground Truth' : '算法预测' }}</p>
      <SfLineChart
        :x="x"
        :series="stateSeries"
        :markers="onsetMarker"
        :y-min="0"
        :y-max="states.length - 1"
        :y-ticks="stateTicks"
        :y-format="stateName"
        :tip-format="(v) => stateName(v)"
        :pad-left="74"
        :x-format="minute"
        :height="narrow ? 170 : 190"
        x-label="窗口内分钟"
      />
    </div>

    <div v-if="scoreSeries.length">
      <p class="mb-1 text-xs font-medium text-gray-700 dark:text-gray-200">{{ c.warn ? '故障概率与未来 10 分钟故障预警（%）' : '故障概率（%）' }}</p>
      <SfLineChart :x="x" :series="scoreSeries" :bands="scoreBands" :markers="onsetMarker" :y-min="0" :y-max="100" :y-format="pct" :tip-format="(v) => `${v.toFixed(1)}%`" :x-format="minute" :height="narrow ? 150 : 170" x-label="窗口内分钟" />
    </div>
  </div>
</template>
