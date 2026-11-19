<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Box, Database, Search, Trophy } from 'lucide-vue-next'
import { quickSearch } from '@/api'

const router = useRouter()
const q = ref('')
const open = ref(false)
const res = ref<Awaited<ReturnType<typeof quickSearch>>>()
let timer: ReturnType<typeof setTimeout>

watch(q, (v) => {
  clearTimeout(timer)
  if (!v.trim()) {
    res.value = undefined
    return
  }
  timer = setTimeout(async () => (res.value = await quickSearch(v.trim())), 150)
})

const empty = computed(() => res.value && !res.value.algorithms.length && !res.value.datasets.length && !res.value.benchmarks.length)

function go(path: string) {
  open.value = false
  q.value = ''
  router.push(path)
}
function submit() {
  if (!q.value.trim()) return
  go(`/algorithms?q=${encodeURIComponent(q.value.trim())}`)
}
</script>

<template>
  <div class="relative" @focusin="open = true" @focusout="open = false">
    <Search class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
    <input v-model="q" class="input pl-8" placeholder="搜索算法、数据集、评测基准…" aria-label="全局搜索" @keydown.enter="submit" @keydown.esc="open = false" />
    <div v-if="open && q.trim() && res" class="card absolute top-full right-0 left-0 z-50 mt-1 max-h-96 overflow-y-auto p-1 text-sm shadow-xl" @mousedown.prevent>
      <p v-if="empty" class="px-3 py-4 text-center text-gray-500">没有匹配“{{ q }}”的结果</p>
      <template v-if="res.algorithms.length">
        <p class="px-2.5 pt-1.5 pb-1 text-xs font-medium text-gray-400">算法</p>
        <button v-for="a in res.algorithms" :key="a.id" class="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800" @click="go(`/algorithms/${a.id}`)">
          <Box class="size-4 text-gray-400" /> <span class="mono truncate">{{ a.id }}</span>
        </button>
      </template>
      <template v-if="res.datasets.length">
        <p class="px-2.5 pt-1.5 pb-1 text-xs font-medium text-gray-400">数据集</p>
        <button v-for="d in res.datasets" :key="d.id" class="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800" @click="go(`/datasets/${d.id}`)">
          <Database class="size-4 text-gray-400" /> <span class="mono truncate">{{ d.id }}</span>
        </button>
      </template>
      <template v-if="res.benchmarks.length">
        <p class="px-2.5 pt-1.5 pb-1 text-xs font-medium text-gray-400">评测基准</p>
        <button v-for="b in res.benchmarks" :key="b.id" class="flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-gray-100 dark:hover:bg-gray-800" @click="go(`/benchmarks/${b.id}`)">
          <Trophy class="size-4 text-gray-400" /> {{ b.displayName }}
        </button>
      </template>
    </div>
  </div>
</template>
