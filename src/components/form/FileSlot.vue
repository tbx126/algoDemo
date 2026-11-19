<script setup lang="ts">
import { ref } from 'vue'
import { CircleCheck, Paperclip, X } from 'lucide-vue-next'
import { fmtBytes } from '@/utils/format'

/** 紧凑的单文件选择（模拟上传，只记录文件名与大小） */
withDefaults(defineProps<{ accept?: string; label?: string; invalid?: boolean }>(), { label: '上传文件' })
const model = defineModel<{ name: string; size: number } | null>({ default: null })
const el = ref<HTMLInputElement>()
function pick(f?: File) {
  if (f) model.value = { name: f.name, size: f.size }
}
</script>

<template>
  <div class="flex min-w-0 items-center gap-2">
    <template v-if="model">
      <CircleCheck class="size-4 shrink-0 text-emerald-500" />
      <span class="mono min-w-0 truncate text-xs">{{ model.name }}</span>
      <span v-if="model.size" class="shrink-0 text-[11px] text-gray-400">{{ fmtBytes(model.size) }}</span>
      <button type="button" class="btn-ghost shrink-0 px-1 py-0.5" aria-label="移除文件" @click="model = null"><X class="size-3.5" /></button>
    </template>
    <template v-else>
      <button type="button" class="btn-default shrink-0 py-1 text-xs" :class="invalid ? 'border-rose-400 text-rose-600' : ''" @click="el?.click()"><Paperclip class="size-3.5" />{{ label }}</button>
    </template>
    <input ref="el" type="file" class="hidden" :accept="accept" @change="pick(($event.target as HTMLInputElement).files?.[0])" />
  </div>
</template>
