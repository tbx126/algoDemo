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
  <div class="flex flex-col" :class="route.meta.fullBleed ? 'h-screen overflow-hidden' : 'min-h-screen'">
    <template v-if="!route.meta.bare">
      <AppHeader />
      <main :class="route.meta.fullBleed ? 'flex-1 min-h-0 overflow-hidden' : 'flex-1'">
        <RouterView :key="route.path + '|' + state.role + '|' + state.region" />
      </main>
      <AppFooter v-if="!route.meta.fullBleed" />
    </template>
    <RouterView v-else />
    <ToastHost />
  </div>
</template>
