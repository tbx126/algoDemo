<script setup lang="ts">
import { computed, useId } from 'vue'
import { byteLen } from '@/utils/standard'

/**
 * 文本输入：必填星号、标识符提示、按 UTF-8 字节计数（标准中的“最大长度(字节)”）。
 */
const props = withDefaults(
  defineProps<{
    label: string
    required?: boolean
    maxBytes?: number
    field?: string // 标准中的标识符，如 name.zh_CN
    multiline?: boolean
    rows?: number
    placeholder?: string
    hint?: string
    mono?: boolean
    type?: string
    error?: string // 外部校验错误
    touched?: boolean
  }>(),
  { rows: 3, type: 'text' },
)
const model = defineModel<string>({ default: '' })
const id = useId()
const bytes = computed(() => byteLen(model.value))
const over = computed(() => !!props.maxBytes && bytes.value > props.maxBytes)
const missing = computed(() => props.touched && props.required && !model.value.trim())
const msg = computed(() => (over.value ? `超出 ${bytes.value - props.maxBytes!} 字节` : missing.value ? '必填' : props.touched ? props.error : ''))
</script>

<template>
  <div>
    <label :for="id" class="label flex min-w-0 items-baseline gap-1.5">
      <span class="shrink-0">{{ label }}<span v-if="required" class="ml-0.5 text-rose-500">*</span></span>
      <code v-if="field" class="mono truncate text-[11px] font-normal text-gray-400" :title="field">{{ field }}</code>
    </label>
    <textarea v-if="multiline" :id="id" v-model="model" :rows="rows" class="input" :class="[mono && 'mono', msg && 'border-rose-400']" :placeholder="placeholder" :aria-invalid="!!msg" />
    <input v-else :id="id" v-model="model" :type="type" class="input" :class="[mono && 'mono', msg && 'border-rose-400']" :placeholder="placeholder" :aria-invalid="!!msg" />
    <div v-if="msg || hint || maxBytes" class="hint flex gap-2">
      <span v-if="msg" class="text-rose-600">{{ msg }}</span>
      <span v-else-if="hint">{{ hint }}</span>
      <span v-if="maxBytes" class="mono ml-auto shrink-0" :class="over ? 'text-rose-600' : 'text-gray-400'">{{ bytes }}/{{ maxBytes }} 字节</span>
    </div>
  </div>
</template>
