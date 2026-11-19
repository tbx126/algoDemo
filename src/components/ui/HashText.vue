<script setup lang="ts">
import { ref } from 'vue'
import { Check, Copy } from 'lucide-vue-next'

const props = withDefaults(defineProps<{ value: string; short?: number }>(), { short: 19 })
const copied = ref(false)
async function copy() {
  try {
    await navigator.clipboard.writeText(props.value)
  } catch {
    /* 剪贴板不可用时忽略 */
  }
  copied.value = true
  setTimeout(() => (copied.value = false), 1200)
}
</script>

<template>
  <span class="inline-flex max-w-full items-center gap-1 align-middle">
    <code class="mono truncate text-gray-600 dark:text-gray-400" :title="value">{{ value.length > short ? value.slice(0, short) + '…' : value }}</code>
    <button v-if="value" type="button" class="shrink-0 cursor-pointer rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800" :aria-label="'复制 ' + value" @click.stop="copy">
      <Check v-if="copied" class="size-3.5 text-emerald-500" />
      <Copy v-else class="size-3.5" />
    </button>
  </span>
</template>
