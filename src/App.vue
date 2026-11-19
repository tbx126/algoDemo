<script setup lang="ts">
import { useRoute } from 'vue-router'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppFooter from '@/components/layout/AppFooter.vue'
import ToastHost from '@/components/ui/ToastHost.vue'
import { useSession } from '@/stores/session'

const route = useRoute()
// 切换身份时重新挂载页面，模拟“换账号后重新请求数据”
const { state } = useSession()
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <template v-if="!route.meta.bare">
      <AppHeader />
      <main class="flex-1">
        <RouterView :key="route.path + '|' + state.role" />
      </main>
      <AppFooter />
    </template>
    <RouterView v-else />
    <ToastHost />
  </div>
</template>
