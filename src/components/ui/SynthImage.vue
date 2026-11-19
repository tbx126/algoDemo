<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { TaskType } from '@/types'
import { drawAnnotations, drawScene, type SynthScene } from '@/utils/synth'

const props = withDefaults(defineProps<{ seed: number; task: TaskType; classes: string[]; annotate?: boolean; width?: number; height?: number }>(), {
  annotate: false,
  width: 320,
  height: 240,
})
const emit = defineEmits<{ scene: [SynthScene] }>()
const canvas = ref<HTMLCanvasElement>()

function render() {
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d', { willReadFrequently: true })!
  const scene = drawScene(ctx, props.width, props.height, props.seed, props.task, props.classes.length)
  if (props.annotate) drawAnnotations(ctx, props.width, props.height, scene, props.task, props.classes)
  emit('scene', scene)
}
onMounted(render)
watch(() => [props.seed, props.annotate, props.task], render)
</script>

<template>
  <canvas ref="canvas" :width="width" :height="height" class="block h-auto w-full" />
</template>
