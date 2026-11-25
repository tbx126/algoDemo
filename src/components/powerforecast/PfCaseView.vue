<script setup lang="ts">
/**
 * 新能源功率预测标准：单个日前预测窗口的 48h 折线图
 *   功率：前一天 24h 实测 → 次日 24h 真值 / 算法预测 / 基线（NWP + 名义功率曲线）
 *   气象：前一天 24h 实测 → 次日 24h NWP 预报（同一条时间轴，NWP 画在预测时段）
 */
import { computed } from 'vue'
import SfLineChart, { type SfSeries } from '@/components/serverfault/SfLineChart.vue'
import type { PfCase } from './types'

const props = defineProps<{ c: PfCase; compact?: boolean }>()

/** x = 相对预测起点的小时：前一天 h 时在 h − 23，次日 h 时在 h + 1 */
const x48 = Array.from({ length: 48 }, (_, i) => i - 23)
const past = (v: number[]) => [...v, ...Array<null>(24).fill(null)]
/** 次日曲线，并与前一天最后一点相连 */
const future = (v: number[], joinWith?: number) => [...Array<null>(23).fill(null), joinWith ?? null, ...v]

const powerSeries = computed<SfSeries[]>(() => {
  const last = props.c.history[23]
  const list: SfSeries[] = [{ key: 'hist', name: '前一天实测', values: past(props.c.history), color: 'var(--v7-axis)', width: 1.8 }]
  if (props.c.gt) list.push({ key: 'gt', name: '次日真值 (GT)', values: future(props.c.gt, last), color: 'var(--v7-s1)', width: 2.3 })
  if (props.c.pred) list.push({ key: 'pred', name: '算法预测', values: future(props.c.pred, last), color: 'var(--v7-s2)', area: true, width: 2.3 })
  if (props.c.nominal) list.push({ key: 'nom', name: '基线：NWP + 名义曲线', values: future(props.c.nominal), color: 'var(--v7-s7)', dashed: true, width: 1.6 })
  return list
})

const isSolar = computed(() => props.c.kind === 'solar')
const meteoSeries = computed<SfSeries[]>(() =>
  isSolar.value
    ? [
        { key: 'irr', name: '前一天实测辐照度', values: past(props.c.channels.irradiance_wm2), color: 'var(--v7-axis)', width: 1.8 },
        { key: 'nwp_irr', name: '次日 NWP 预报辐照度', values: future(props.c.channels.nwp_irr_wm2), color: 'var(--v7-s3)', dashed: true, width: 2 },
      ]
    : [
        { key: 'w', name: '前一天实测风速', values: past(props.c.channels.wind_speed_ms), color: 'var(--v7-axis)', width: 1.8 },
        { key: 'nwp_w', name: '次日 NWP 预报风速', values: future(props.c.channels.nwp_wind_ms), color: 'var(--v7-s3)', dashed: true, width: 2 },
      ],
)
const cap = computed(() => props.c.capacityMw || 100)
const fmtMw = (v: number) => `${Math.round(v)} MW`
const fmtTipMw = (v: number) => `${v.toFixed(2)} MW`
const fmtClock = (v: number) => {
  const h = (props.c.startHour + ((Math.round(v) + 23) % 24) + 24) % 24
  return `${v <= 0 ? '前一天' : '次日'} ${String(h).padStart(2, '0')}:00`
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap items-center justify-between gap-2 text-xs">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="rounded bg-brand-50 px-1.5 py-0.5 font-semibold text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">{{ c.station }}</span>
        <span class="chip py-0 text-[11px]">{{ isSolar ? '光伏' : '风电' }} · {{ cap }} MW</span>
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
      <p class="mb-1 text-[11px] font-medium text-gray-500">功率（MW，纵轴上限 = 装机容量）<template v-if="isSolar">：光伏只考核 6:00–19:00</template></p>
      <SfLineChart
        :x="x48"
        :series="powerSeries"
        :y-min="0"
        :y-max="cap"
        :y-format="fmtMw"
        :tip-format="fmtTipMw"
        :x-format="fmtClock"
        :markers="[{ x: 0.5, label: '00:00 发布预测' }]"
        x-label="前一天 24h 实测 → 次日 24h 预测"
        :height="compact ? 170 : 210"
        :pad-left="46"
      />
    </div>

    <!-- 副折线图：主导气象与 NWP 预报曲线 -->
    <div>
      <p class="mb-1 text-[11px] font-medium text-gray-500">
        {{ isSolar ? '辐照度（W/m²）：前一天实测 → 次日 NWP 预报' : '风速（m/s）：前一天实测 → 次日 NWP 预报' }}
      </p>
      <SfLineChart
        :x="x48"
        :series="meteoSeries"
        :markers="[{ x: 0.5, label: '' }]"
        :y-min="0"
        :y-format="(v) => (isSolar ? `${Math.round(v)}` : `${v.toFixed(0)} m/s`)"
        :tip-format="(v) => (isSolar ? `${v.toFixed(1)} W/m²` : `${v.toFixed(2)} m/s`)"
        :x-format="fmtClock"
        :height="compact ? 125 : 145"
        :pad-left="46"
      />
    </div>
  </div>
</template>
