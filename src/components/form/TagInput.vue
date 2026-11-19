<script setup lang="ts">
import { ref, useId } from 'vue'
import { X } from 'lucide-vue-next'
import { byteLen } from '@/utils/standard'

/** 字符串数组输入：回车添加，可选快捷建议；每项按字节限长 */
const props = defineProps<{ label: string; required?: boolean; field?: string; maxBytes?: number; suggestions?: string[]; placeholder?: string; hint?: string; touched?: boolean }>()
const model = defineModel<string[]>({ default: () => [] })
const id = useId()
const draft = ref('')
const err = ref('')

function add(v = draft.value) {
  const t = v.trim()
  err.value = ''
  if (!t) return
  if (props.maxBytes && byteLen(t) > props.maxBytes) {
    err.value = `单项不能超过 ${props.maxBytes} 字节（当前 ${byteLen(t)}）`
    return
  }
  if (!model.value.includes(t)) model.value = [...model.value, t]
  draft.value = ''
}
const remove = (t: string) => (model.value = model.value.filter((x) => x !== t))
</script>

<template>
  <div>
    <label :for="id" class="label flex min-w-0 items-baseline gap-1.5">
      <span class="shrink-0">{{ label }}<span v-if="required" class="ml-0.5 text-rose-500">*</span></span>
      <code v-if="field" class="mono truncate text-[11px] font-normal text-gray-400">{{ field }}</code>
      <span v-if="maxBytes" class="ml-auto shrink-0 text-[11px] font-normal text-gray-400">每项 ≤{{ maxBytes }} 字节</span>
    </label>
    <div class="input flex min-h-9 flex-wrap items-center gap-1.5 py-1" :class="touched && required && !model.length ? 'border-rose-400' : ''">
      <span v-for="t in model" :key="t" class="chip">
        {{ t }}<button type="button" class="cursor-pointer text-gray-400 hover:text-gray-700" :aria-label="`移除 ${t}`" @click="remove(t)"><X class="size-3" /></button>
      </span>
      <input
        :id="id"
        v-model="draft"
        class="min-w-24 flex-1 bg-transparent text-sm outline-none"
        :placeholder="model.length ? '' : placeholder ?? '输入后回车添加'"
        @keydown.enter.prevent="add()"
        @blur="add()"
      />
    </div>
    <div v-if="suggestions?.length" class="mt-1.5 flex flex-wrap gap-1">
      <button v-for="s in suggestions.filter((x) => !model.includes(x))" :key="s" type="button" class="cursor-pointer rounded border border-dashed border-gray-300 px-1.5 py-px text-xs text-gray-500 hover:border-gray-400 hover:text-gray-800 dark:border-gray-700 dark:hover:text-gray-200" @click="add(s)">+ {{ s }}</button>
    </div>
    <p v-if="err" class="hint text-rose-600">{{ err }}</p>
    <p v-else-if="touched && required && !model.length" class="hint text-rose-600">至少填写一项</p>
    <p v-else-if="hint" class="hint">{{ hint }}</p>
  </div>
</template>
