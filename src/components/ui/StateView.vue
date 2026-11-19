<script setup lang="ts">
import { LoaderCircle, ShieldAlert, SearchX, TriangleAlert } from 'lucide-vue-next'

defineProps<{ loading?: boolean; error?: { status: number; message: string } | null; empty?: boolean; emptyText?: string }>()
</script>

<template>
  <div v-if="loading" class="flex items-center justify-center gap-2 py-16 text-sm text-gray-500">
    <LoaderCircle class="size-4 animate-spin" /> 加载中…
  </div>
  <div v-else-if="error" class="flex flex-col items-center justify-center gap-2 py-16 text-center">
    <ShieldAlert v-if="error.status === 403" class="size-8 text-amber-500" />
    <SearchX v-else-if="error.status === 404" class="size-8 text-gray-400" />
    <TriangleAlert v-else class="size-8 text-rose-500" />
    <p class="font-medium">{{ error.message }}</p>
    <p v-if="error.status === 403" class="text-sm text-gray-500">当前身份没有访问权限，可在右上角切换身份查看。</p>
    <RouterLink to="/" class="btn-default mt-2">返回首页</RouterLink>
  </div>
  <div v-else-if="empty" class="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-gray-200 py-14 text-sm text-gray-500 dark:border-gray-800">
    <SearchX class="size-6 text-gray-400" />
    {{ emptyText ?? '暂无数据' }}
    <slot name="empty" />
  </div>
  <slot v-else />
</template>
