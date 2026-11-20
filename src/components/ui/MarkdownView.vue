<script setup lang="ts">
import { computed, watch } from 'vue'
import { renderMarkdown, type TocItem } from '@/utils/markdown'

const props = defineProps<{ source: string }>()
const emit = defineEmits<{ toc: [TocItem[]] }>()
const rendered = computed(() => renderMarkdown(props.source))
watch(rendered, (r) => emit('toc', r.toc), { immediate: true })
</script>

<template>
  <article class="prose-readme" v-html="rendered.html" />
</template>
