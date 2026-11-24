<script setup lang="ts">
/** [0x07] 数据集页：遥测窗口折线图预览（8 通道曲线 + 逐分钟 Ground Truth） */
import { computed, ref, watch } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import CaseView0x07 from './CaseView0x07.vue'
import { DATASET_0X07_ID, type Case0x07 } from './types'

const props = withDefaults(defineProps<{ rows: { file_name: string; label: string; row?: string[] }[]; part: 'train' | 'test'; max?: number }>(), { max: 24 })

const items = computed(() =>
  props.rows.slice(0, props.max).map((r) => ({
    file: r.file_name.split('/').pop()!,
    state: r.row?.[1] ?? r.label.split('（')[0],
    server: r.row?.[2] ?? '',
    onset: Number(r.row?.[4] ?? -1),
  })),
)
const current = ref('')
const data = ref<Case0x07 | null>(null)
const loading = ref(false)
const error = ref('')

watch(
  items,
  (list) => {
    if (list.length && !list.some((i) => i.file === current.value)) current.value = (list.find((i) => i.state !== '正常') ?? list[0]).file
  },
  { immediate: true },
)
watch(
  [current, () => props.part],
  async ([file, part]) => {
    if (!file) return
    loading.value = true
    error.value = ''
    try {
      const r = await fetch(`/real-api/datasets/${DATASET_0X07_ID}/series/${part}/${encodeURIComponent(file)}`)
      if (!r.ok) throw new Error('样本读取失败（后端未启动？）')
      data.value = await r.json()
    } catch (e) {
      data.value = null
      error.value = (e as Error).message
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)
const chipCls = (state: string, active: boolean) =>
  active
    ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900'
    : state === '正常'
      ? 'border-gray-200 text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:text-gray-300'
      : 'border-rose-200 text-rose-700 hover:border-rose-400 dark:border-rose-900 dark:text-rose-300'
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-1.5">
      <button v-for="it in items" :key="it.file" type="button" class="cursor-pointer rounded-full border px-2.5 py-0.5 text-[11px] transition" :class="chipCls(it.state, it.file === current)" :title="it.file" @click="current = it.file">
        {{ it.state }}<span class="opacity-60"> · {{ it.server.replace('-node', '') }}</span>
      </button>
    </div>
    <div v-if="loading && !data" class="flex items-center gap-2 py-10 text-sm text-gray-500"><LoaderCircle class="size-4 animate-spin" />读取遥测窗口…</div>
    <p v-else-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{{ error }}</p>
    <div v-else-if="data" :class="{ 'opacity-60': loading }">
      <p class="mono mb-2 text-[11px] text-gray-500">series/{{ data.file }}</p>
      <CaseView0x07 :c="data" />
    </div>
  </div>
</template>
