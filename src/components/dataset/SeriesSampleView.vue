<script setup lang="ts">
/**
 * 时序标准数据集（服务器故障检测 / 功率预测）单个样本的折线图视图
 * 数据集详情页点击 labels.csv 某一行时使用，替代图像任务的「大图」预览
 */
import { ref, watch } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import SfCaseView from '@/components/serverfault/SfCaseView.vue'
import PfCaseView from '@/components/powerforecast/PfCaseView.vue'
import type { SfCase } from '@/components/serverfault/types'
import type { PfCase } from '@/components/powerforecast/types'

const props = defineProps<{ datasetId: string; part: 'train' | 'test'; fileName: string; task: string }>()

const data = ref<SfCase | PfCase | null>(null)
const loading = ref(false)
const error = ref('')

watch(
  () => [props.datasetId, props.part, props.fileName],
  async () => {
    data.value = null
    error.value = ''
    const file = props.fileName.split('/').pop()
    if (!file) return
    loading.value = true
    try {
      const r = await fetch(`/real-api/datasets/${props.datasetId}/series/${props.part}/${encodeURIComponent(file)}`)
      if (!r.ok) throw new Error('时序样本读取失败（后端未启动？）')
      data.value = await r.json()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <div>
    <div v-if="loading" class="flex items-center gap-2 py-10 text-sm text-gray-500"><LoaderCircle class="size-4 animate-spin" />读取时序窗口…</div>
    <p v-else-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{{ error }}</p>
    <template v-else-if="data">
      <SfCaseView v-if="task === 'server-fault'" :c="data as SfCase" narrow />
      <PfCaseView v-else :c="data as PfCase" compact />
    </template>
  </div>
</template>
