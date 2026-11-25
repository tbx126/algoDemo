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
  { key: 'nrmse', name: '归一化 RMSE (%)', values: props.viz.horizonCurve.map((d) => d.nrmse), color: 'var(--v7-s2)', area: true, width: 2.2 },
  { key: 'nmae', name: '归一化 MAE (%)', values: props.viz.horizonCurve.map((d) => d.nmae), color: 'var(--v7-s1)', width: 1.9 },
])

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
const bestEp = computed(() => (props.viz.history.length ? props.viz.history.reduce((b, h) => (h.val_loss < b.val_loss ? h : b), props.viz.history[0]) : null))
</script>

<template>
  <div class="space-y-5">
    <!-- 1. 典型场站测试窗口：48h 历史 + 未来 24h GT vs 算法预测 -->
    <section v-if="showCases && viz.cases.length" class="card p-5">
      <h3 class="mb-1 text-sm font-semibold">典型场站样本：Ground Truth vs 算法预测</h3>
      <p class="mb-3 text-xs text-gray-500">6 座风电/光伏场站各取一条典型测试窗口，前 24h 为历史实测，后 24h 对比真实功率与算法预测曲线及 NWP 气象输入。</p>
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
        <h3 class="mb-1 text-sm font-semibold">预测提前期误差曲线（+1h → +24h）</h3>
        <p class="mb-3 text-xs text-gray-500">随预报提前期拉长，NWP 气象不确定性增大，展示各小时步长的归一化 RMSE 与 MAE 变化趋势。</p>
        <SfLineChart
          :x="horizonX"
          :series="horizonSeries"
          :y-min="0"
          :y-format="(v) => `${v.toFixed(0)}%`"
          :tip-format="(v) => `${v.toFixed(2)}%`"
          :x-format="(v) => `+${Math.round(v)}h`"
          x-label="预测提前期（小时）"
          :height="190"
        />
      </section>

      <!-- 24h 日内时刻对齐均值曲线 -->
      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">24 小时日内平均出力对齐曲线</h3>
        <p class="mb-3 text-xs text-gray-500">将测试集 300 条窗口按 0:00–23:00 时刻对齐求均值，检验模型对光伏午峰与风电昼夜规律的拟合度。</p>
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
        <p class="mb-3 text-xs text-gray-500">测试集全部 7,200 个预测小时中，绝对误差不超过 X MW 的样本占比。</p>
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
          训练集 90% 训练、10% 独立验证（测试集零参与）。验证损失最低在第 <strong class="text-gray-800 dark:text-gray-200">{{ bestEp?.epoch }}</strong> 轮（验证准确率 {{ bestEp?.val_acc }}%）。
        </p>
        <SfLineChart
          :x="epochs"
          :series="lossSeries"
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
            :y-min="50"
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
