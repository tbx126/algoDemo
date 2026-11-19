<script setup lang="ts">
import { NECESSITY, type Necessity } from '@/utils/standard'

defineProps<{ n: Necessity }>()
</script>

<template>
  <span class="inline-flex shrink-0 items-center rounded border px-1.5 py-px text-[11px] font-medium" :class="NECESSITY[n].cls">{{ NECESSITY[n].label }}</span>
</template>
