<script setup lang="ts">
import { computed } from 'vue'
import { AudioWaveform, Bone, Box, ScanText, Shapes, SquareDashedMousePointer, Tags, Route, Puzzle } from 'lucide-vue-next'
import type { TaskType } from '@/types'

const props = defineProps<{ task: TaskType }>()
const icon = computed(
  () =>
    ({
      'image-classification': Tags,
      'object-detection': SquareDashedMousePointer,
      'semantic-segmentation': Shapes,
      'instance-segmentation': Box,
      'keypoint-detection': Bone,
      ocr: ScanText,
      'signal-processing': AudioWaveform,
      optimization: Route,
      custom: Puzzle,
    })[props.task],
)
</script>

<template>
  <component :is="icon" />
</template>
