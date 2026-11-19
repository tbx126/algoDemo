<script setup lang="ts">
import type { EvalRun } from '@/types'
import { benchmarks } from '@/mock/benchmarks'
import { fmtDuration, fmtMetric, timeAgo } from '@/utils/format'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import StateView from '@/components/ui/StateView.vue'

defineProps<{ runs: EvalRun[]; hideAlgo?: boolean; hideBench?: boolean }>()

const bench = (id: string) => benchmarks.find((b) => b.id === id)
function primary(r: EvalRun) {
  const b = bench(r.benchmarkId)
  const m = b?.metrics.find((x) => x.primary)
  if (!m || r.metrics[m.key] == null) return null
  return { label: m.label, v: fmtMetric(r.metrics[m.key], m.unit) + (m.unit === '%' ? '%' : '') }
}
</script>

<template>
  <StateView :empty="!runs.length" empty-text="暂无评测记录">
    <div class="card overflow-x-auto">
      <table class="table-base">
        <thead>
          <tr>
            <th>任务 ID</th>
            <th v-if="!hideAlgo">算法</th>
            <th>版本</th>
            <th v-if="!hideBench">评测基准</th>
            <th>状态</th>
            <th>主指标</th>
            <th>耗时</th>
            <th>提交</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id" class="hover:bg-gray-50 dark:hover:bg-gray-900">
            <td><RouterLink :to="`/evals/${r.id}`" class="mono text-brand-600 hover:underline dark:text-brand-500">{{ r.id }}</RouterLink></td>
            <td v-if="!hideAlgo"><RouterLink :to="`/algorithms/${r.algorithmId}`" class="mono hover:underline">{{ r.algorithmId }}</RouterLink></td>
            <td class="mono">{{ r.algoVersion }}</td>
            <td v-if="!hideBench" class="whitespace-nowrap"><RouterLink :to="`/benchmarks/${r.benchmarkId}`" class="hover:underline">{{ bench(r.benchmarkId)?.displayName }}</RouterLink></td>
            <td>
              <div class="flex items-center gap-2">
                <StatusBadge :status="r.status" kind="eval" />
                <div v-if="r.status === 'running'" class="h-1.5 w-16 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                  <div class="h-full bg-sky-500" :style="{ width: r.progress + '%' }" />
                </div>
                <span v-if="r.status === 'succeeded' && !r.isLatestValid" class="text-[10px] text-gray-400" title="同一算法版本×基准已有更新的有效结果">已被覆盖</span>
              </div>
            </td>
            <td class="whitespace-nowrap">
              <template v-if="primary(r)"><span class="mono font-medium">{{ primary(r)!.v }}</span> <span class="text-xs text-gray-500">{{ primary(r)!.label }}</span></template>
              <span v-else class="text-gray-400">—</span>
            </td>
            <td class="whitespace-nowrap text-gray-500">{{ fmtDuration(r.durationSec) }}</td>
            <td class="whitespace-nowrap text-gray-500">{{ r.submittedBy }} · {{ timeAgo(r.submittedAt) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </StateView>
</template>
