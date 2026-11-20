<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Info } from 'lucide-vue-next'

const router = useRouter()
const username = ref('')
const password = ref('')
const loading = ref(false)
// 静态登录页：原型中不校验密码，提交后直接进入首页
function submit() {
  loading.value = true
  setTimeout(() => router.push('/'), 500)
}
</script>

<template>
  <div class="flex min-h-screen">
    <div class="relative hidden flex-1 overflow-hidden bg-gray-950 lg:block">
      <div class="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(99,102,241,.45),transparent_50%),radial-gradient(ellipse_at_80%_80%,rgba(6,182,212,.3),transparent_45%)]" />
      <div class="relative flex h-full flex-col justify-between p-12 text-white">
        <div class="flex items-center gap-2 text-lg font-semibold"><img src="/logo.png" alt="" class="size-8 rounded-md bg-white/95 object-contain p-0.5" />总部算法平台</div>
        <div>
          <p class="text-3xl leading-snug font-bold">同一份数据，同一套评测，<br />可比较、可复现的结果。</p>
          <p class="mt-4 max-w-md text-sm text-gray-300">数据集与算法版本化管理 · 隔离容器评测 · 测试集标注不出平台 · 在线单图推理</p>
        </div>
        <p class="text-xs text-gray-500">内部平台 · 账号由管理员开通</p>
      </div>
    </div>
    <div class="flex flex-1 items-center justify-center px-4 py-12">
      <form class="w-full max-w-sm space-y-5" @submit.prevent="submit">
        <div class="flex items-center gap-2 lg:hidden"><img src="/logo.png" alt="" class="size-8 rounded-md object-contain" /><span class="text-lg font-semibold">总部算法平台</span></div>
        <div>
          <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">登录</h1>
          <p class="mt-1 text-sm text-gray-500">使用管理员为你开通的账号</p>
        </div>
        <div>
          <label class="label" for="l-u">用户名或邮箱</label>
          <input id="l-u" v-model="username" class="input py-2" autocomplete="username" required />
        </div>
        <div>
          <div class="flex items-center justify-between">
            <label class="label" for="l-p">密码</label>
            <span class="text-xs text-gray-400">忘记密码请联系管理员</span>
          </div>
          <input id="l-p" v-model="password" type="password" class="input py-2" autocomplete="current-password" required />
        </div>
        <button type="submit" class="btn-primary w-full py-2" :disabled="loading">{{ loading ? '登录中…' : '登录' }}</button>
        <p class="flex items-start gap-1.5 rounded-lg bg-gray-50 p-3 text-xs text-gray-500 dark:bg-gray-900">
          <Info class="mt-0.5 size-3.5 shrink-0" />前端原型：此页为静态展示，任意输入即可进入。进入后可在右上角切换演示身份。
        </p>
        <p class="text-center text-sm text-gray-500">没有账号？平台不开放注册，请通过所在团队或对接人向管理员申请。</p>
      </form>
    </div>
  </div>
</template>
