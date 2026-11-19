<script setup lang="ts">
import type { TaskType } from '@/types'
import { TASKS } from '@/utils/meta'
import TaskIcon from './TaskIcon.vue'

defineProps<{ task: TaskType }>()
</script>

<template>
  <span class="chip">
    <TaskIcon :task="task" class="size-3.5" :class="TASKS[task].color" />
    {{ TASKS[task].label }}
  </span>
</template>
