<script setup lang="ts">
import { computed } from 'vue'
import { orgs } from '@/mock/orgs'

const props = withDefaults(defineProps<{ org: string | null | undefined; size?: number }>(), { size: 20 })
const o = computed(() => orgs.find((x) => x.id === props.org))
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center rounded-md font-semibold text-white uppercase"
    :style="{ width: size + 'px', height: size + 'px', background: o?.color ?? '#64748b', fontSize: size * 0.48 + 'px' }"
    :title="o?.displayName ?? org ?? ''"
    >{{ (o?.name ?? org ?? '?').slice(0, 1) }}</span
  >
</template>
