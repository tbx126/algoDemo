<script setup lang="ts">
import { DialogClose, DialogContent, DialogDescription, DialogOverlay, DialogPortal, DialogRoot, DialogTitle } from 'reka-ui'
import { X } from 'lucide-vue-next'

const open = defineModel<boolean>('open', { required: true })
withDefaults(defineProps<{ title: string; description?: string; width?: string }>(), { width: 'max-w-lg' })
</script>

<template>
  <DialogRoot v-model:open="open">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-50 bg-black/40" />
      <DialogContent
        class="card fixed top-1/2 left-1/2 z-50 max-h-[88vh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto p-5 shadow-2xl focus:outline-none"
        :class="width"
      >
        <div class="mb-4 flex items-start justify-between gap-4">
          <div>
            <DialogTitle class="text-base font-semibold text-gray-900 dark:text-white">{{ title }}</DialogTitle>
            <DialogDescription v-if="description" class="mt-1 text-sm text-gray-500">{{ description }}</DialogDescription>
          </div>
          <DialogClose class="btn-ghost -mt-1 -mr-2 px-1.5" aria-label="关闭"><X class="size-4" /></DialogClose>
        </div>
        <slot />
        <div v-if="$slots.footer" class="mt-5 flex justify-end gap-2"><slot name="footer" /></div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
