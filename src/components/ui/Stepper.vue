<script setup lang="ts">
import { Check } from 'lucide-vue-next'

defineProps<{ steps: string[]; current: number }>()
</script>

<template>
  <ol class="flex items-center gap-2 overflow-x-auto pb-1 text-sm">
    <li v-for="(s, i) in steps" :key="s" class="flex shrink-0 items-center gap-2">
      <span
        class="flex size-6 items-center justify-center rounded-full text-xs font-semibold"
        :class="i < current ? 'bg-emerald-500 text-white' : i === current ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900' : 'bg-gray-100 text-gray-500 dark:bg-gray-800'"
      >
        <Check v-if="i < current" class="size-3.5" />
        <template v-else>{{ i + 1 }}</template>
      </span>
      <span :class="i === current ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-500'">{{ s }}</span>
      <span v-if="i < steps.length - 1" class="h-px w-6 bg-gray-200 sm:w-10 dark:bg-gray-700" />
    </li>
  </ol>
</template>
