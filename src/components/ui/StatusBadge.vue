<script setup lang="ts">
import { computed } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import type { AlgoVersionStatus, EvalStatus } from '@/types'
import { EVAL_STATUS, VERSION_STATUS } from '@/utils/meta'

const props = defineProps<{ status: AlgoVersionStatus | EvalStatus; kind?: 'version' | 'eval' }>()
const meta = computed(() => (props.kind === 'eval' ? EVAL_STATUS[props.status as EvalStatus] : VERSION_STATUS[props.status as AlgoVersionStatus]))
const spinning = computed(() => props.status === 'building' || props.status === 'running')
</script>

<template>
  <span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap" :class="meta.cls">
    <LoaderCircle v-if="spinning" class="size-3 animate-spin" />
    <span v-else class="size-1.5 rounded-full bg-current opacity-70" />
    {{ meta.label }}
  </span>
</template>
