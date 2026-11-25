<script setup lang="ts">
/** 新能源功率预测标准：评测详情页 5 维折线图面板（对标 SfEvalViz） */
import { computed, ref } from 'vue'
import SfLineChart, { type SfSeries } from '@/components/serverfault/SfLineChart.vue'
import PfCaseView from './PfCaseView.vue'
import type { PfEvalVizData } from './types'

const props = withDefaults(defineProps<{ viz: PfEvalVizData; showCases?: boolean }>(), { showCases: true })

const caseIdx = ref(0)

const horizonX = computed(() => props.viz.horizonCurve.map((d) => d.hour))
const horizonSeries = computed<SfSeries[]>(() => [
  { key: 'nrmse', name: '算法', values: props.viz.horizonCurve.map((d) => d.nrmse), color: 'var(--v7-s2)', area: true, width: 2.2 },
  { key: 'nominal', name: '基线：NWP + 名义曲线', values: props.viz.horizonCurve.map((d) => d.nominal), color: 'var(--v7-s7)', dashed: true, width: 1.8 },
  { key: 'persistence', name: '基线：持续法', values: props.viz.horizonCurve.map((d) => d.persistence), color: 'var(--v7-axis)', dashed: true, width: 1.6 },
])
const evalHoursText = computed(() => (props.viz.solarEvalHours ? `风电全天、光伏 ${props.viz.solarEvalHours[0]}:00–${props.viz.solarEvalHours[1]}:00` : '全天'))

const diurnalX = computed(() => props.viz.diurnalCurve.map((d) => d.hour))
const diurnalSeries = computed<SfSeries[]>(() => [
  { key: 'gt', name: '平均实测功率 (GT)', values: props.viz.diurnalCurve.map((d) => d.gt), color: 'var(--v7-s1)', width: 2.4 },
  { key: 'pred', name: '平均预测功率', values: props.viz.diurnalCurve.map((d) => d.pred), color: 'var(--v7-s2)', dashed: true, width: 2.2 },
])

const cdfX = computed(() => props.viz.errorCdf.map((d) => d.mw))
const cdfSeries = computed<SfSeries[]>(() => [
  { key: 'cdf', name: '累计达标占比', values: props.viz.errorCdf.map((d) => d.pct), color: 'var(--v7-s3)', area: true, width: 2.2 },
])

const epochs = computed(() => props.viz.history.map((h) => h.epoch))
const lossSeries = computed<SfSeries[]>(() => [
  { key: 'tr', name: '训练损失', values: props.viz.history.map((h) => h.train_loss), color: 'var(--v7-s1)' },
  { key: 'va', name: '验证损失', values: props.viz.history.map((h) => h.val_loss), color: 'var(--v7-s2)' },
])
const accSeries = computed<SfSeries[]>(() => [
  { key: 'acc', name: '验证集考核准确率', values: props.viz.history.map((h) => h.val_acc), color: 'var(--v7-s1)', area: true },
])
const bestEp = computed(() => {
  const h = props.viz.history
  if (!h.length) return null
  return h.find((x) => x.epoch === props.viz.bestEpoch) ?? h.reduce((b, x) => (x.val_loss < b.val_loss ? x : b), h[0])
})
const epochMarkers = computed(() => (bestEp.value ? [{ x: bestEp.value.epoch, label: '保存的权重' }] : []))
</script>

<template>
  <div class="space-y-5">
    <!-- 0. 参照基线：算法应明显优于不训练的基线 -->
    <section v-if="viz.baselines?.length" class="card p-5">
      <h3 class="mb-1 text-sm font-semibold">参照基线（同一测试集、同一考核口径）</h3>
      <p class="mb-3 text-xs text-gray-500">考核时段：{{ evalHoursText }}，共 {{ (viz.evalHours ?? 0).toLocaleString() }} 个预测小时。基线不训练：持续法直接用前一天曲线，「NWP + 名义曲线」把 NWP 预报代入通用风机功率曲线 / 光伏标准条件效率。</p>
      <div class="grid gap-2 sm:grid-cols-2">
        <div v-for="b in viz.baselines" :key="b.key" class="flex items-center justify-between rounded-lg border border-gray-200 px-3 py-2 text-xs dark:border-gray-700">
          <span class="text-gray-600 dark:text-gray-300">{{ b.name }}</span>
          <span class="mono">准确率 <strong class="text-gray-900 dark:text-white">{{ b.accuracy }}%</strong> · NRMSE {{ b.nrmse }}%</span>
        </div>
      </div>
    </section>

    <!-- 1. 典型场站测试窗口：48h 历史 + 未来 24h GT vs 算法预测 -->
    <section v-if="showCases && viz.cases.length" class="card p-5">
      <h3 class="mb-1 text-sm font-semibold">典型场站样本：Ground Truth vs 算法预测</h3>
      <p class="mb-3 text-xs text-gray-500">每座场站取一个出力起伏较大的测试窗口：前一天 24h 实测，次日 24h 对比真值、算法预测与 NWP 名义曲线基线；下方为同一时间轴上的实测气象与次日 NWP 预报。</p>
      <div class="mb-4 flex flex-wrap gap-1.5" role="tablist" aria-label="选择场站样本">
        <button
          v-for="(c, i) in viz.cases"
          :key="c.file"
          type="button"
          role="tab"
          :aria-selected="caseIdx === i"
          class="cursor-pointer rounded-full border px-2.5 py-1 text-xs transition"
          :class="
            caseIdx === i
              ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900'
              : 'border-gray-200 text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:text-gray-300'
          "
          @click="caseIdx = i"
        >
          {{ c.station }} <span class="opacity-65">· {{ c.accuracy }}%</span>
        </button>
      </div>
      <PfCaseView v-if="viz.cases[caseIdx]" :key="viz.cases[caseIdx].file" :c="viz.cases[caseIdx]" />
    </section>
    <p v-else-if="!showCases" class="rounded-lg border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-500 dark:border-gray-700">
      测试集单样本逐小时曲线（Ground Truth vs 预测）仅管理员可见，以下为汇总统计折线图。
    </p>

    <!-- 2–5. 四象限汇总统计折线图 -->
    <div class="grid gap-5 lg:grid-cols-2">
      <!-- 提前期误差增长曲线 -->
      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">各预测时刻的归一化 RMSE（算法 vs 基线）</h3>
        <p class="mb-3 text-xs text-gray-500">次日 00:00–23:00 每个时刻的误差（只计考核时段）；NWP 误差随提前期增大，越靠后越难。</p>
        <SfLineChart
          :x="horizonX"
          :series="horizonSeries"
          :y-min="0"
          :y-format="(v) => `${v.toFixed(0)}%`"
          :tip-format="(v) => `${v.toFixed(2)}%`"
          :x-format="(v) => `次日 ${String(Math.round(v) - 1).padStart(2, '0')}:00`"
          x-label="次日时刻"
          :height="190"
        />
      </section>

      <!-- 24h 日内时刻对齐均值曲线 -->
      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">24 小时日内平均出力对齐曲线</h3>
        <p class="mb-3 text-xs text-gray-500">全部测试窗口按次日时刻对齐求平均（各场站合计），检验对光伏午峰与风电昼夜规律的拟合。</p>
        <SfLineChart
          :x="diurnalX"
          :series="diurnalSeries"
          :y-min="0"
          :y-format="(v) => `${Math.round(v)} MW`"
          :tip-format="(v) => `${v.toFixed(2)} MW`"
          :x-format="(v) => `${String(Math.round(v)).padStart(2, '0')}:00`"
          x-label="一天时刻"
          :height="190"
          :pad-left="46"
        />
      </section>

      <!-- 绝对误差累计分布 CDF -->
      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">逐小时绝对误差累计分布（CDF）</h3>
        <p class="mb-3 text-xs text-gray-500">考核时段内全部 {{ (viz.evalHours ?? 0).toLocaleString() }} 个预测小时中，绝对误差不超过 X MW 的占比。</p>
        <SfLineChart
          :x="cdfX"
          :series="cdfSeries"
          :y-min="0"
          :y-max="100"
          :y-format="(v) => `${Math.round(v)}%`"
          :tip-format="(v) => `${v.toFixed(1)}%`"
          :x-format="(v) => `≤ ${Math.round(v)} MW`"
          x-label="绝对误差上限（MW）"
          :height="190"
        />
      </section>

      <!-- 训练/验证收敛曲线 -->
      <section v-if="viz.history.length" class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">训练与验证收敛曲线</h3>
        <p class="mb-3 text-xs text-gray-500">
          只用训练集：训练时段最后 20 天作验证集（剔除与其时间重叠的窗口），保存验证损失最低的第 <strong class="text-gray-800 dark:text-gray-200">{{ bestEp?.epoch }}</strong> 轮（验证准确率 {{ bestEp?.val_acc }}%）。
        </p>
        <SfLineChart
          :x="epochs"
          :series="lossSeries"
          :markers="epochMarkers"
          :y-min="0"
          :y-format="(v) => v.toFixed(3)"
          :tip-format="(v) => v.toFixed(5)"
          :x-format="(v) => `第 ${Math.round(v)} 轮`"
          :height="110"
          :pad-left="44"
        />
        <div class="mt-3">
          <SfLineChart
            :x="epochs"
            :series="accSeries"
            :markers="epochMarkers"
            :y-min="0"
            :y-max="100"
            :y-format="(v) => `${Math.round(v)}%`"
            :tip-format="(v) => `${v.toFixed(2)}%`"
            :x-format="(v) => `第 ${Math.round(v)} 轮`"
            x-label="训练轮次（epoch）"
            :height="110"
            :pad-left="44"
          />
        </div>
      </section>
    </div>
  </div>
</template>
