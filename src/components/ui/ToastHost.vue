<script setup lang="ts">
import { CircleCheck, CircleX, Info } from 'lucide-vue-next'
import { toasts } from '@/stores/toast'
</script>

<template>
  <div class="pointer-events-none fixed right-4 bottom-4 z-[100] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
    <TransitionGroup enter-from-class="translate-y-2 opacity-0" enter-active-class="transition" leave-to-class="opacity-0" leave-active-class="transition">
      <div v-for="t in toasts" :key="t.id" class="card pointer-events-auto flex items-start gap-2 px-3 py-2.5 text-sm shadow-lg">
        <CircleCheck v-if="t.kind === 'success'" class="mt-0.5 size-4 shrink-0 text-emerald-500" />
        <CircleX v-else-if="t.kind === 'error'" class="mt-0.5 size-4 shrink-0 text-rose-500" />
        <Info v-else class="mt-0.5 size-4 shrink-0 text-sky-500" />
        <span>{{ t.text }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>
