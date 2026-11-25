<script setup lang="ts">
/** 服务器故障检测标准：统一评测器的折线图面板（所有标准算法 × 所有标准数据集共用）：典型样本、故障起点对齐、阈值扫描、检测时延、训练曲线 */
import { computed, ref } from 'vue'
import SfLineChart, { type SfSeries } from './SfLineChart.vue'
import SfCaseView from './SfCaseView.vue'
import type { ServerFaultViz } from './types'

const props = withDefaults(defineProps<{ viz: ServerFaultViz; showCases?: boolean }>(), { showCases: true })

const epochs = computed(() => props.viz.history.map((h) => h.epoch))
const lossSeries = computed<SfSeries[]>(() => [
  { key: 'tr', name: '训练损失', values: props.viz.history.map((h) => h.train_loss), color: 'var(--v7-s1)' },
  { key: 'va', name: '验证损失', values: props.viz.history.map((h) => h.val_loss), color: 'var(--v7-s2)' },
])
const f1Series = computed<SfSeries[]>(() => [{ key: 'f1', name: '验证集 F1', values: props.viz.history.map((h) => h.val_f1), color: 'var(--v7-s1)', area: true }])
const lowestLoss = computed(() => props.viz.history.reduce((b, h) => (h.val_loss < b.val_loss ? h : b), props.viz.history[0]))
const savedEpoch = computed(() => props.viz.bestEpoch ?? null)
const epochMarkers = computed(() => (savedEpoch.value ? [{ x: savedEpoch.value, label: '保存的权重' }] : []))

const ths = computed(() => props.viz.thresholdCurve.map((t) => t.threshold))
const thSeries = computed<SfSeries[]>(() => [
  { key: 'p', name: '精确率', values: props.viz.thresholdCurve.map((t) => t.precision), color: 'var(--v7-s1)' },
  { key: 'r', name: '召回率', values: props.viz.thresholdCurve.map((t) => t.recall), color: 'var(--v7-s2)' },
  { key: 'f', name: 'F1', values: props.viz.thresholdCurve.map((t) => t.f1), color: 'var(--v7-s3)', width: 2.5 },
])
const thMin = computed(() => Math.max(0, Math.floor((Math.min(...props.viz.thresholdCurve.flatMap((t) => [t.precision, t.recall, t.f1])) - 1) / 5) * 5))
const fprSeries = computed<SfSeries[]>(() => [{ key: 'fpr', name: '误报率', values: props.viz.thresholdCurve.map((t) => t.fpr), color: 'var(--v7-s7)', area: true }])
const bestTh = computed(() => props.viz.thresholdCurve.reduce((b, t) => (t.f1 > b.f1 ? t : b), props.viz.thresholdCurve[0]))

const delayX = computed(() => props.viz.delayCdf.map((d) => d.minute))
const delaySeries = computed<SfSeries[]>(() => [{ key: 'cdf', name: '累计检出率', values: props.viz.delayCdf.map((d) => d.detected), color: 'var(--v7-s1)', step: true, area: true }])

const alignX = computed(() => props.viz.onsetAligned.map((a) => a.offset))
const alignSeries = computed<SfSeries[]>(() => [
  { key: 'gt', name: 'Ground Truth 故障占比', values: props.viz.onsetAligned.map((a) => a.gtFault), color: 'var(--v7-s1)', step: true, width: 3 },
  { key: 'an', name: '平均异常分数', values: props.viz.onsetAligned.map((a) => a.anomaly), color: 'var(--v7-s2)' },
  ...(props.viz.onsetAligned.some((a) => a.warn !== null) ? [{ key: 'wn', name: '平均预警概率', values: props.viz.onsetAligned.map((a) => a.warn), color: 'var(--v7-s7)', dashed: true }] : []),
])

const pct = (v: number) => `${Math.round(v)}%`
const caseIdx = ref(0)
const caseTitle = (c: ServerFaultViz['cases'][number]) => (c.label === '正常' ? (c.warnGt?.some((v) => v > 0) ? '正常（含前兆）' : '正常') : c.label)
</script>

<template>
  <div class="space-y-5">
    <section v-if="showCases" class="card p-5">
      <h3 class="mb-1 text-sm font-semibold">典型样本：Ground Truth vs 算法预测</h3>
      <p class="mb-3 text-xs text-gray-500">测试集中每类故障各取一个窗口，另取一个全程正常的窗口（数据集中有仅含前兆的窗口时也会列出）。浅红色背景为真值故障段，浅黄色背景为预警真值段（故障前 10 分钟）。</p>
      <div class="mb-4 flex flex-wrap gap-1.5" role="tablist" aria-label="选择样本">
        <button
          v-for="(c, i) in viz.cases"
          :key="c.file"
          type="button"
          role="tab"
          :aria-selected="caseIdx === i"
          class="cursor-pointer rounded-full border px-2.5 py-1 text-xs transition"
          :class="caseIdx === i ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900' : 'border-gray-200 text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:text-gray-300'"
          @click="caseIdx = i"
        >
          {{ caseTitle(c) }}
          <span v-if="c.predLabel && c.predLabel !== c.label" class="ml-1 text-rose-500">✕</span>
        </button>
      </div>
      <SfCaseView v-if="viz.cases[caseIdx]" :key="viz.cases[caseIdx].file" :c="viz.cases[caseIdx]" :states="viz.states" />
    </section>
    <p v-else class="rounded-lg border border-dashed border-gray-200 px-4 py-3 text-xs text-gray-500 dark:border-gray-700">测试集样本的逐分钟曲线（Ground Truth vs 预测）仅管理员可见，以下为汇总曲线。</p>

    <div class="grid gap-5 lg:grid-cols-2">
      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">故障起点对齐曲线</h3>
        <p class="mb-3 text-xs text-gray-500">把测试集里所有窗口内故障按起始分钟对齐（0 = 故障起点），对每个相对分钟取平均：故障概率越早、越陡地贴合真值越好；有预警输出的算法，预警概率应在故障前就开始上升。</p>
        <SfLineChart :x="alignX" :series="alignSeries" :y-min="0" :y-max="100" :y-format="pct" :tip-format="(v) => `${v.toFixed(1)}%`" :x-format="(v) => (v > 0 ? `+${v}` : `${v}`) + ' 分钟'" :markers="[{ x: 0, label: '故障起点' }]" x-label="相对故障起点（分钟）" :height="200" />
      </section>

      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">阈值扫描（逐分钟故障概率 fault_prob）</h3>
        <p class="mb-3 text-xs text-gray-500">按逐分钟「故障 / 正常」二分类计算。F1 最高的阈值为 <strong class="text-gray-800 dark:text-gray-200">{{ bestTh.threshold }}</strong>（F1 {{ bestTh.f1 }}%，误报率 {{ bestTh.fpr }}%）。</p>
        <SfLineChart :x="ths" :series="thSeries" :y-min="thMin" :y-max="100" :y-format="pct" :tip-format="(v) => `${v.toFixed(2)}%`" :x-format="(v) => v.toFixed(2)" :markers="[{ x: bestTh.threshold, label: '最佳 F1' }]" :height="170" />
        <p class="mt-3 mb-1 text-[11px] text-gray-500">正常分钟误报率（%）</p>
        <SfLineChart :x="ths" :series="fprSeries" :y-min="0" :y-format="(v) => `${+v.toFixed(1)}%`" :tip-format="(v) => `${v.toFixed(2)}%`" :x-format="(v) => v.toFixed(2)" :markers="[{ x: bestTh.threshold, label: '' }]" x-label="判定阈值" :height="110" />
      </section>

      <section class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">检测时延累计分布</h3>
        <p class="mb-3 text-xs text-gray-500">窗口内发生的故障中，在起点后 N 分钟内被正确类别检出的比例。</p>
        <SfLineChart :x="delayX" :series="delaySeries" :y-min="0" :y-max="100" :y-format="pct" :tip-format="(v) => `${v.toFixed(1)}%`" :x-format="(v) => `≤ ${v} 分钟`" x-label="故障起点后（分钟）" :height="190" />
      </section>

      <section v-if="viz.history.length" class="card p-5">
        <h3 class="mb-1 text-sm font-semibold">训练曲线</h3>
        <p class="mb-3 text-xs text-gray-500">来自该算法在自己训练数据集上的训练记录（与本评测基准无关）：训练集 90% 训练、10% 验证，共 {{ viz.history.length }} 轮；验证损失最低在第 {{ lowestLoss?.epoch }} 轮<template v-if="savedEpoch">，实际保存的是验证集 F1 最高的第 {{ savedEpoch }} 轮</template>。</p>
        <SfLineChart :x="epochs" :series="lossSeries" :markers="epochMarkers" :y-min="0" :y-format="(v) => v.toFixed(2)" :tip-format="(v) => v.toFixed(4)" :x-format="(v) => `第 ${Math.round(v)} 轮`" :height="150" />
        <div class="mt-3">
          <SfLineChart :x="epochs" :series="f1Series" :markers="epochMarkers" :y-min="0" :y-max="100" :y-format="pct" :tip-format="(v) => `${v.toFixed(2)}%`" :x-format="(v) => `第 ${Math.round(v)} 轮`" x-label="训练轮次（epoch）" :height="150" />
          <p class="mt-1 text-[11px] text-gray-500">验证集 F1（%）</p>
        </div>
      </section>
    </div>
  </div>
</template>
