<script setup lang="ts">
import type { Necessity } from '@/utils/standard'
import NecessityBadge from './NecessityBadge.vue'

defineProps<{ title: string; necessity?: Necessity; source?: string; desc?: string }>()
</script>

<template>
  <section class="scroll-mt-20 space-y-4 border-t border-gray-100 pt-5 first:border-t-0 first:pt-0 dark:border-gray-800">
    <header>
      <div class="flex flex-wrap items-center gap-2">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">{{ title }}</h3>
        <NecessityBadge v-if="necessity" :n="necessity" />
        <span v-if="source" class="mono text-[11px] text-gray-400">{{ source }}</span>
        <slot name="actions" />
      </div>
      <p v-if="desc" class="mt-1 text-xs text-gray-500">{{ desc }}</p>
    </header>
    <slot />
  </section>
</template>
