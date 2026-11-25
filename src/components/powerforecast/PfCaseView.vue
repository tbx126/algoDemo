<script setup lang="ts">
/** 新能源功率预测标准：单窗口 48h 连续折线图（前 24h 历史实测 + 后 24h GT vs 预测 + 气象/NWP 通道） */
import { computed } from 'vue'
import SfLineChart, { type SfSeries } from '@/components/serverfault/SfLineChart.vue'
import type { PfCase } from './types'

const props = defineProps<{ c: PfCase; compact?: boolean }>()

const x48 = computed(() => Array.from({ length: 48 }, (_, i) => i - 23))
const x24 = computed(() => Array.from({ length: 24 }, (_, i) => i + 1))

const powerSeries = computed<SfSeries[]>(() => {
  const hist: (number | null)[] = [...props.c.history, ...Array(24).fill(null)]
  const list: SfSeries[] = [
    { key: 'hist', name: '过去 24h 实测', values: hist, color: '#94a3b8', dashed: true, width: 1.8 },
  ]
  if (props.c.gt) {
    const gt: (number | null)[] = [...Array(23).fill(null), props.c.history[23], ...props.c.gt]
    list.push({ key: 'gt', name: '未来 24h 真值 (GT)', values: gt, color: 'var(--v7-s1)', width: 2.3 })
  }
  if (props.c.pred) {
    const pred: (number | null)[] = [...Array(23).fill(null), props.c.history[23], ...props.c.pred]
    list.push({ key: 'pred', name: '算法预测功率', values: pred, color: 'var(--v7-s2)', area: true, width: 2.3 })
  }
  return list
})

const meteoSeries = computed<SfSeries[]>(() => {
  if (props.c.kind === 'solar') {
    return [
      { key: 'irr', name: '历史辐照度 (W/m²)', values: props.c.channels.irradiance_wm2, color: 'var(--v7-s7)', width: 1.8 },
      { key: 'nwp_irr', name: '未来 24h NWP 预报辐照', values: props.c.channels.nwp_irr_wm2, color: 'var(--v7-s3)', dashed: true, width: 2 },
    ]
  }
  return [
    { key: 'w', name: '历史风速 (m/s)', values: props.c.channels.wind_speed_ms, color: 'var(--v7-s1)', width: 1.8 },
    { key: 'nwp_w', name: '未来 24h NWP 预报风速', values: props.c.channels.nwp_wind_ms, color: 'var(--v7-s2)', dashed: true, width: 2 },
  ]
})

const fmtMw = (v: number) => `${Math.round(v)} MW`
const fmtTipMw = (v: number) => `${v.toFixed(2)} MW`
const fmtH48 = (v: number) => (v <= 0 ? `${v}h` : `+${v}h`)
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="rounded bg-brand-50 px-1.5 py-0.5 font-semibold text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">{{ c.station }}</span>
        <span class="chip py-0 text-[11px]">{{ c.kind === 'solar' ? '光伏' : '风电' }}</span>
        <span class="chip py-0 text-[11px]">{{ c.weather }}</span>
        <span class="mono text-[11px] text-gray-400">{{ c.file }}</span>
      </div>
      <div v-if="c.accuracy !== undefined" class="mono flex flex-wrap items-center gap-2.5 text-[11px] text-gray-500">
        <span>准确率 <strong class="text-emerald-600 dark:text-emerald-400">{{ c.accuracy }}%</strong></span>
        <span>NRMSE <strong class="text-gray-800 dark:text-gray-200">{{ c.nrmse }}%</strong></span>
        <span>峰值误差 <strong class="text-gray-800 dark:text-gray-200">{{ c.peakErrMw }} MW</strong></span>
      </div>
    </div>

    <!-- 主折线图：48h 功率曲线（前 24h 历史 + 后 24h GT vs 预测） -->
    <div>
      <p class="mb-1 text-[11px] font-medium text-gray-500">48 小时连续功率曲线（MW）</p>
      <SfLineChart
        :x="x48"
        :series="powerSeries"
        :y-min="0"
        :y-max="100"
        :y-format="fmtMw"
        :tip-format="fmtTipMw"
        :x-format="fmtH48"
        :markers="[{ x: 0, label: '预测起点' }]"
        x-label="相对预测起点（小时）"
        :height="compact ? 170 : 210"
        :pad-left="46"
      />
    </div>

    <!-- 副折线图：主导气象与 NWP 预报曲线 -->
    <div>
      <p class="mb-1 text-[11px] font-medium text-gray-500">
        {{ c.kind === 'solar' ? '太阳辐照度（历史实测 vs 未来 24h NWP 预报）' : '场站风速（历史实测 vs 未来 24h NWP 预报）' }}
      </p>
      <SfLineChart
        :x="x24"
        :series="meteoSeries"
        :y-min="0"
        :y-format="(v) => (c.kind === 'solar' ? `${Math.round(v)}` : `${v.toFixed(0)} m/s`)"
        :tip-format="(v) => (c.kind === 'solar' ? `${v.toFixed(1)} W/m²` : `${v.toFixed(2)} m/s`)"
        :x-format="(v) => `第 ${Math.round(v)}h`"
        :height="compact ? 125 : 145"
        :pad-left="46"
      />
    </div>
  </div>
</template>
