<script setup lang="ts">
/** 新能源功率预测标准：数据集详情页时序窗口折线图预览（对标 SfSeriesPreview） */
import { computed, ref, watch } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import PfCaseView from './PfCaseView.vue'
import type { PfCase } from './types'

const props = withDefaults(
  defineProps<{ datasetId: string; rows: { file_name: string; label: string; row?: string[] }[]; part: 'train' | 'test'; max?: number }>(),
  { max: 24 },
)

const items = computed(() => {
  // 尽量覆盖全部 6 座场站，按场站均匀抽取最多 max 个样例
  const all = props.rows.map((r) => ({
    file: r.file_name.split('/').pop()!,
    station: r.row?.[2] ?? '场站',
    weather: r.row?.[3] ?? '',
    value: r.row?.[1] ?? '',
  }))
  const bySt = new Map<string, typeof all>()
  for (const it of all) {
    const arr = bySt.get(it.station) ?? []
    arr.push(it)
    bySt.set(it.station, arr)
  }
  const picked: typeof all = []
  let round = 0
  while (picked.length < props.max && picked.length < all.length) {
    let added = false
    for (const arr of bySt.values()) {
      if (round < arr.length && picked.length < props.max) {
        picked.push(arr[round])
        added = true
      }
    }
    if (!added) break
    round++
  }
  return picked
})

const current = ref('')
const data = ref<PfCase | null>(null)
const loading = ref(false)
const error = ref('')

watch(
  items,
  (list) => {
    if (list.length && !list.some((i) => i.file === current.value)) current.value = list[0].file
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
      const r = await fetch(`/real-api/datasets/${props.datasetId}/series/${part}/${encodeURIComponent(file)}`)
      if (!r.ok) throw new Error('时序样本读取失败（后端未启动？）')
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
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-1.5">
      <button
        v-for="it in items"
        :key="it.file"
        type="button"
        class="cursor-pointer rounded-full border px-2.5 py-0.5 text-[11px] transition"
        :class="
          it.file === current
            ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900'
            : 'border-gray-200 text-gray-600 hover:border-gray-400 dark:border-gray-700 dark:text-gray-300'
        "
        :title="it.file"
        @click="current = it.file"
      >
        {{ it.station }}<span class="opacity-65"> · {{ it.weather }}</span>
      </button>
    </div>

    <div v-if="loading && !data" class="flex items-center gap-2 py-10 text-sm text-gray-500">
      <LoaderCircle class="size-4 animate-spin" />读取功率时序窗口…
    </div>
    <p v-else-if="error" class="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">{{ error }}</p>
    <div v-else-if="data" :class="{ 'opacity-60': loading }">
      <PfCaseView :c="data" />
    </div>
  </div>
</template>
