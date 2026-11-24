<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuPortal, DropdownMenuRoot, DropdownMenuSeparator, DropdownMenuTrigger } from 'reka-ui'
import { Box, ChevronDown, Database, FlaskConical, LogOut, MapPin, Menu, Moon, Plus, ShieldCheck, Sun, Trophy, Workflow, X, Check } from 'lucide-vue-next'
import { useSession } from '@/stores/session'
import { REGIONS, ROLES } from '@/utils/meta'
import type { RegionName, Role } from '@/types'
import GlobalSearch from './GlobalSearch.vue'
import UserAvatar from '@/components/ui/UserAvatar.vue'
import { toast } from '@/stores/toast'

const { state, user, can } = useSession()
const route = useRoute()
const mobileOpen = ref(false)

const nav = [
  { to: '/algorithms', label: '算法', icon: Box },
  { to: '/datasets', label: '数据集', icon: Database },
  { to: '/benchmarks', label: '评测基准', icon: Trophy },
  { to: '/evals', label: '评测任务', icon: FlaskConical },
  { to: '/studio', label: '编排实验', icon: Workflow, beta: true },
]
const isActive = (to: string) => route.path.startsWith(to)
const roleList = Object.entries(ROLES) as [Role, (typeof ROLES)[Role]][]

const createItems = computed(() =>
  [
    { to: '/algorithms/new', label: can.value.needsReview ? '提交算法（需审核）' : '新建算法', show: can.value.createAlgorithm },
    { to: '/vendors/new', label: '新建厂商', show: can.value.admin },
    { to: '/datasets/new', label: '上传数据集', show: can.value.createDataset },
    { to: '/benchmarks/new', label: '新建评测基准', show: can.value.createBenchmark },
    { to: '/evals/new', label: '发起评测', show: can.value.runEval },
  ].filter((x) => x.show),
)

function switchRole(r: Role) {
  state.role = r
  toast(r === 'regional' ? `已切换为「区域侧 · ${state.region}」身份` : `已切换为「${ROLES[r].label}」身份`, 'info')
}

function switchRegion(rg: RegionName) {
  state.region = rg
  if (state.role !== 'regional') state.role = 'regional'
  toast(`已切换至「${rg}」区域侧视角`, 'info')
}
</script>

<template>
  <header class="sticky top-0 z-40 border-b border-gray-100 bg-white/90 backdrop-blur dark:border-gray-800 dark:bg-gray-950/90">
    <div class="container-page flex h-14 items-center gap-4">
      <RouterLink to="/" class="flex shrink-0 items-center gap-2 font-semibold text-gray-900 dark:text-white">
        <img src="/logo.png" alt="总部算法平台" class="size-7 rounded-md object-contain" />
        <span class="text-[17px] tracking-tight">总部算法平台</span>
      </RouterLink>

      <GlobalSearch class="hidden w-64 md:block xl:w-80" />

      <nav class="ml-auto hidden items-center gap-1 xl:flex">
        <RouterLink
          v-for="n in nav"
          :key="n.to"
          :to="n.to"
          class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm whitespace-nowrap transition-colors"
          :class="isActive(n.to) ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'"
        >
          <component :is="n.icon" class="size-4" :class="isActive(n.to) ? 'text-brand-600 dark:text-brand-500' : 'text-gray-400'" />
          {{ n.label }}
          <span v-if="'beta' in n && n.beta" class="rounded bg-amber-100 px-1 py-0.2 text-[10px] font-medium text-amber-700 dark:bg-amber-900/50 dark:text-amber-300">Beta</span>
        </RouterLink>
        <RouterLink
          v-if="can.admin"
          to="/admin"
          class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm"
          :class="isActive('/admin') ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white'"
        >
          <ShieldCheck class="size-4 text-gray-400" /> 管理
        </RouterLink>
      </nav>

      <div class="ml-auto flex items-center gap-1.5 xl:ml-2">
        <DropdownMenuRoot v-if="createItems.length">
          <DropdownMenuTrigger class="btn-default hidden px-2 sm:inline-flex" aria-label="新建"><Plus class="size-4" /> 新建</DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent align="end" :side-offset="6" class="card z-50 min-w-44 p-1 shadow-lg">
              <DropdownMenuItem v-for="c in createItems" :key="c.to" as-child>
                <RouterLink :to="c.to" class="block cursor-pointer rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">{{ c.label }}</RouterLink>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>

        <button class="btn-ghost px-2" :aria-label="state.dark ? '切换到亮色' : '切换到暗色'" @click="state.dark = !state.dark">
          <Sun v-if="state.dark" class="size-4" />
          <Moon v-else class="size-4" />
        </button>

        <!-- 身份切换器（原型演示用） -->
        <DropdownMenuRoot>
          <DropdownMenuTrigger class="flex cursor-pointer items-center gap-2 rounded-lg border border-gray-200 py-1 pr-2 pl-1 text-sm hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800">
            <UserAvatar :user="user" :size="24" />
            <span class="hidden flex-col items-start leading-tight sm:flex">
              <span class="text-xs font-medium">{{ user.displayName }}</span>
              <span class="text-[10px] text-gray-500">{{ state.role === 'regional' ? `区域侧 · ${state.region}` : ROLES[state.role].label }}</span>
            </span>
            <ChevronDown class="size-3.5 text-gray-400" />
          </DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent align="end" :side-offset="6" class="card z-50 w-72 p-1 shadow-lg">
              <DropdownMenuLabel class="px-2.5 pt-1.5 pb-1 text-xs text-gray-500">演示：切换当前身份</DropdownMenuLabel>
              <DropdownMenuItem
                v-for="[k, r] in roleList"
                :key="k"
                class="flex cursor-pointer items-start gap-2 rounded-md px-2.5 py-1.5 outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800"
                @select="switchRole(k)"
              >
                <Check class="mt-0.5 size-4 shrink-0" :class="state.role === k ? 'text-brand-600' : 'invisible'" />
                <span>
                  <span class="block text-sm font-medium">{{ r.label }}</span>
                  <span class="block text-xs text-gray-500">{{ r.desc }}</span>
                </span>
              </DropdownMenuItem>
              <DropdownMenuSeparator class="my-1 h-px bg-gray-100 dark:bg-gray-800" />
              <div v-if="state.role === 'regional'" class="px-2.5 py-1.5">
                <p class="mb-1.5 flex items-center gap-1 text-[11px] font-medium text-gray-500">
                  <MapPin class="size-3 text-emerald-500" />切换当前演示区域（{{ REGIONS.length }} 区域）
                </p>
                <div class="grid grid-cols-4 gap-1">
                  <button
                    v-for="rg in REGIONS"
                    :key="rg"
                    type="button"
                    class="cursor-pointer rounded px-1.5 py-0.5 text-[11px] transition"
                    :class="
                      state.region === rg
                        ? 'bg-emerald-600 font-medium text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
                    "
                    @click.stop="switchRegion(rg)"
                  >
                    {{ rg }}
                  </button>
                </div>
              </div>
              <DropdownMenuSeparator v-if="state.role === 'regional'" class="my-1 h-px bg-gray-100 dark:bg-gray-800" />
              <DropdownMenuItem v-if="user.orgId" as-child>
                <RouterLink :to="`/orgs/${user.orgId}`" class="block cursor-pointer rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800">我的厂商主页</RouterLink>
              </DropdownMenuItem>
              <DropdownMenuItem as-child>
                <RouterLink to="/login" class="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-sm outline-none data-[highlighted]:bg-gray-100 dark:data-[highlighted]:bg-gray-800"><LogOut class="size-4" /> 退出登录</RouterLink>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>

        <button class="btn-ghost px-2 xl:hidden" aria-label="菜单" @click="mobileOpen = !mobileOpen">
          <X v-if="mobileOpen" class="size-5" />
          <Menu v-else class="size-5" />
        </button>
      </div>
    </div>

    <!-- 移动端 / 平板菜单 -->
    <div v-if="mobileOpen" class="border-t border-gray-100 xl:hidden dark:border-gray-800" @click="mobileOpen = false">
      <div class="container-page space-y-1 py-3">
        <GlobalSearch class="mb-2 md:hidden" @click.stop />
        <RouterLink v-for="n in nav" :key="n.to" :to="n.to" class="flex items-center gap-2 rounded-lg px-2 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-900">
          <component :is="n.icon" class="size-4 text-gray-400" /> {{ n.label }}
        </RouterLink>
        <RouterLink v-if="can.admin" to="/admin" class="flex items-center gap-2 rounded-lg px-2 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-900"><ShieldCheck class="size-4 text-gray-400" /> 管理</RouterLink>
        <RouterLink v-for="c in createItems" :key="c.to" :to="c.to" class="flex items-center gap-2 rounded-lg px-2 py-2 text-sm hover:bg-gray-50 sm:hidden dark:hover:bg-gray-900"><Plus class="size-4 text-gray-400" /> {{ c.label }}</RouterLink>
      </div>
    </div>
  </header>
</template>
