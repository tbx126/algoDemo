<script setup lang="ts">
import { computed } from 'vue'
import { AudioWaveform, Bone, Box, CloudSun, ScanText, Shapes, SquareDashedMousePointer, Tags, Route, Puzzle, ServerCrash, Zap } from 'lucide-vue-next'
import type { TaskType } from '@/types'

const props = defineProps<{ task: TaskType }>()
const icon = computed(
  () =>
    ({
      'image-classification': Tags,
      'image-dehazing': CloudSun,
      'object-detection': SquareDashedMousePointer,
      'semantic-segmentation': Shapes,
      'instance-segmentation': Box,
      'keypoint-detection': Bone,
      ocr: ScanText,
      'power-forecast': Zap,
      'server-fault': ServerCrash,
      'signal-processing': AudioWaveform,
      optimization: Route,
      custom: Puzzle,
    })[props.task],
)
</script>

<template>
  <component :is="icon" />
</template>
