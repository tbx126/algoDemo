<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { TaskType } from '@/types'
import { drawAnnotations, drawScene, sceneLayout, type SynthScene } from '@/utils/synth'

const props = withDefaults(
  defineProps<{
    seed: number
    task: TaskType
    classes: string[]
    annotate?: boolean
    width?: number
    height?: number
    sampleImages?: Record<string, string[]>
  }>(),
  {
    annotate: false,
    width: 320,
    height: 240,
  },
)
const emit = defineEmits<{ scene: [SynthScene] }>()
const canvas = ref<HTMLCanvasElement>()

const resolved = computed(() => {
  if (!props.sampleImages) return null
  const scene = sceneLayout(props.seed, props.task, props.classes.length)
  const label = props.classes[scene.label] ?? ''
  const pool = props.sampleImages[label]
  if (!pool?.length) return null
  return { scene, label, src: pool[Math.abs(props.seed) % pool.length] }
})

function render() {
  if (resolved.value) {
    emit('scene', resolved.value.scene)
    return
  }
  const c = canvas.value
  if (!c) return
  const ctx = c.getContext('2d', { willReadFrequently: true })!
  const scene = drawScene(ctx, props.width, props.height, props.seed, props.task, props.classes.length)
  if (props.annotate) drawAnnotations(ctx, props.width, props.height, scene, props.task, props.classes)
  emit('scene', scene)
}
onMounted(render)
watch(() => [props.seed, props.annotate, props.task, props.sampleImages], render)
</script>

<template>
  <div v-if="resolved" class="relative overflow-hidden bg-gray-100 dark:bg-gray-900">
    <img :src="resolved.src" :alt="resolved.label" class="block aspect-[4/3] w-full object-cover" loading="lazy" />
    <span
      v-if="annotate && resolved.label"
      class="pointer-events-none absolute top-1.5 left-1.5 rounded bg-gray-900/75 px-1.5 py-0.5 text-[11px] font-medium text-white backdrop-blur-xs"
    >
      {{ resolved.label }}
    </span>
  </div>
  <canvas v-else ref="canvas" :width="width" :height="height" class="block h-auto w-full" />
</template>
