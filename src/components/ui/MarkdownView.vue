<script setup lang="ts">
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps<{ source: string }>()
// 原型中先转义原始 HTML；真实后端应在服务端做 HTML 清洗
const html = computed(() => marked.parse(props.source.replace(/</g, '&lt;'), { async: false }) as string)
</script>

<template>
  <article class="prose-readme" v-html="html" />
</template>
