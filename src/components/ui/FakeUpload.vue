<script setup lang="ts">
import { ref } from 'vue'
import { CircleCheck, FileUp, LoaderCircle, X } from 'lucide-vue-next'
import { fmtBytes } from '@/utils/format'

/** 文件选择与上传槽：保留原始 File 对象供真实后端上传 */
defineProps<{ accept?: string; hint?: string; label: string }>()
const file = defineModel<{ name: string; size: number; file?: File } | null>({ default: null })
const progress = ref(100)
const el = ref<HTMLInputElement>()
const over = ref(false)

function start(f?: File) {
  if (!f) return
  file.value = { name: f.name, size: f.size, file: f }
  progress.value = 100
}
</script>

<template>
  <div>
    <div
      v-if="!file"
      class="flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border-2 border-dashed px-4 py-7 text-center text-sm"
      :class="over ? 'border-brand-500 bg-brand-50 dark:bg-brand-600/10' : 'border-gray-200 hover:border-gray-300 dark:border-gray-700'"
      role="button"
      tabindex="0"
      @click="el?.click()"
      @keydown.enter="el?.click()"
      @dragover.prevent="over = true"
      @dragleave="over = false"
      @drop.prevent="over = false; start($event.dataTransfer?.files?.[0])"
    >
      <FileUp class="size-6 text-gray-400" />
      <span>{{ label }}</span>
      <span v-if="hint" class="text-xs text-gray-400">{{ hint }}</span>
    </div>
    <div v-else class="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
      <div class="flex items-center gap-2 text-sm">
        <CircleCheck v-if="progress >= 100" class="size-4 text-emerald-500" />
        <LoaderCircle v-else class="size-4 animate-spin text-gray-400" />
        <span class="mono truncate">{{ file.name }}</span>
        <span class="ml-auto shrink-0 text-xs text-gray-500">{{ fmtBytes(file.size) }}</span>
        <button type="button" class="btn-ghost px-1 py-0.5" aria-label="移除文件" @click="file = null"><X class="size-3.5" /></button>
      </div>
      <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        <div class="h-full rounded-full bg-brand-500 transition-all" :style="{ width: progress + '%' }" />
      </div>
    </div>
    <input ref="el" type="file" class="hidden" :accept="accept" @change="start(($event.target as HTMLInputElement).files?.[0])" />
  </div>
</template>
