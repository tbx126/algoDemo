<script setup lang="ts">
import type { User } from '@/types'
import OrgAvatar from './OrgAvatar.vue'

/** 厂商账号显示所属厂商头像；管理员 / 演示账号不属于任何组织，显示姓名首字 */
withDefaults(defineProps<{ user: Pick<User, 'displayName' | 'role' | 'orgId'>; size?: number }>(), { size: 24 })
</script>

<template>
  <OrgAvatar v-if="user.orgId" :org="user.orgId" :size="size" />
  <span
    v-else
    class="inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white"
    :class="user.role === 'admin' ? 'bg-gray-900 dark:bg-gray-600' : 'bg-sky-600'"
    :style="{ width: size + 'px', height: size + 'px', fontSize: size * 0.46 + 'px' }"
    :title="user.displayName"
    >{{ user.displayName.slice(0, 1) }}</span
  >
</template>
