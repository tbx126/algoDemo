<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, ClipboardCheck, ShieldCheck, UserPlus, Users } from 'lucide-vue-next'
import { ApiError, createUser, listOrgs, listReviewQueue, listUsers, reviewVersion, setUserActive } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { ROLES, TASKS } from '@/utils/meta'
import { fmtBytes, fmtDate, timeAgo } from '@/utils/format'
import type { Role } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import Modal from '@/components/ui/Modal.vue'
import HashText from '@/components/ui/HashText.vue'

const route = useRoute()
const router = useRouter()
const { can } = useSession()
const tab = computed(() => (route.params.tab as string) || 'users')

const { data: users, reload: reloadUsers } = useAsync(() => listUsers())
const { data: reviews, reload: reloadReviews } = useAsync(() => listReviewQueue())
const { data: orgList } = useAsync(() => listOrgs())

// ---- 用户 ----
const userQ = ref('')
const filteredUsers = computed(() => (users.value ?? []).filter((u) => !userQ.value || u.username.includes(userQ.value) || u.displayName.includes(userQ.value)))
const createOpen = ref(false)
const nu = reactive({ username: '', displayName: '', email: '', role: 'vendor' as Role, orgId: 'partner-xyz' })
const vendors = computed(() => (orgList.value ?? []).filter((o) => o.kind === 'vendor'))
const orgName = (id: string | null) => (id ? (orgList.value?.find((o) => o.id === id)?.displayName ?? id) : '')
const created = ref<{ username: string; tempPassword: string } | null>(null)
async function doCreate() {
  try {
    const r = await createUser({ ...nu, orgId: nu.role === 'vendor' ? nu.orgId : null })
    created.value = { username: r.user.username, tempPassword: r.tempPassword }
    reloadUsers()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '创建失败', 'error')
  }
}
function closeCreate(v: boolean) {
  createOpen.value = v
  if (!v) {
    created.value = null
    Object.assign(nu, { username: '', displayName: '', email: '', role: 'vendor', orgId: 'partner-xyz' })
  }
}
async function toggleActive(id: string, active: boolean) {
  await setUserActive(id, active)
  toast(active ? '账号已启用' : '账号已停用', 'info')
  reloadUsers()
}

// ---- 审核 ----
const notes = reactive<Record<string, string>>({})
async function review(algoId: string, version: string, approve: boolean) {
  const k = algoId + version
  if (!approve && !notes[k]?.trim()) {
    toast('驳回时请填写原因', 'error')
    return
  }
  await reviewVersion(algoId, version, approve, notes[k] ?? '')
  toast(approve ? '已通过，开始构建' : '已驳回，提交者会收到通知')
  reloadReviews()
}
</script>

<template>
  <div class="container-page pt-8">
    <StateView v-if="!can.admin" :error="{ status: 403, message: '仅管理员可访问管理后台' }" />
    <template v-else>
      <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><ShieldCheck class="size-6 text-brand-600" />管理后台</h1>
      <div class="mt-4 mb-6 flex gap-1 no-scrollbar overflow-x-auto overflow-y-hidden border-b border-gray-100 dark:border-gray-800">
        <button class="tab" :class="{ 'tab-active': tab === 'users' }" @click="router.replace('/admin/users')"><Users class="size-4" />用户与账号</button>
        <button class="tab" :class="{ 'tab-active': tab === 'reviews' }" @click="router.replace('/admin/reviews')">
          <ClipboardCheck class="size-4" />审核队列<span v-if="reviews?.length" class="rounded-full bg-amber-500 px-1.5 text-[10px] text-white">{{ reviews.length }}</span>
        </button>
        <button class="tab" :class="{ 'tab-active': tab === 'vendors' }" @click="router.replace('/admin/vendors')"><Building2 class="size-4" />厂商</button>
      </div>

      <!-- 用户 -->
      <div v-if="tab === 'users'">
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <input v-model="userQ" class="input w-64" placeholder="搜索用户名 / 姓名" aria-label="搜索用户" />
          <p class="text-sm text-gray-500">平台不开放注册：厂商与演示账号均由管理员创建。</p>
          <button class="btn-primary ml-auto" @click="createOpen = true"><UserPlus class="size-4" />新建账号</button>
        </div>
        <StateView :loading="!users">
          <div class="card overflow-x-auto">
            <table class="table-base">
              <thead><tr><th>用户</th><th>邮箱</th><th>角色</th><th>所属厂商</th><th>最近登录</th><th>状态</th><th></th></tr></thead>
              <tbody>
                <tr v-for="u in filteredUsers" :key="u.id" :class="{ 'opacity-50': !u.active }">
                  <td><span class="font-medium">{{ u.displayName }}</span> <span class="mono text-gray-500">@{{ u.username }}</span></td>
                  <td class="text-gray-500">{{ u.email }}</td>
                  <td><span class="chip" :class="ROLES[u.role].chip">{{ ROLES[u.role].label }}</span></td>
                  <td><span v-if="u.orgId" class="flex items-center gap-1.5"><OrgAvatar :org="u.orgId" :size="16" />{{ orgName(u.orgId) }}</span><span v-else class="text-xs text-gray-400">不属于任何组织</span></td>
                  <td class="whitespace-nowrap text-gray-500">{{ u.lastLoginAt ? timeAgo(u.lastLoginAt) : '从未登录' }}</td>
                  <td>{{ u.active ? '启用' : '已停用' }}</td>
                  <td class="text-right"><button class="btn-ghost px-2 py-1 text-xs" @click="toggleActive(u.id, !u.active)">{{ u.active ? '停用' : '启用' }}</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </StateView>
      </div>

      <!-- 审核 -->
      <div v-else-if="tab === 'reviews'">
        <StateView :loading="!reviews" :empty="reviews && !reviews.length" empty-text="没有待审核的提交">
          <div class="space-y-4">
            <div v-for="r in reviews" :key="r.algorithm.id + r.version.version" class="card p-5">
              <div class="flex flex-wrap items-center gap-2">
                <OrgAvatar :org="r.algorithm.org" :size="20" />
                <RouterLink :to="`/algorithms/${r.algorithm.id}?tab=files`" class="mono font-medium hover:text-brand-600">{{ r.algorithm.id }}</RouterLink>
                <span class="mono text-gray-500">{{ r.version.version }}</span>
                <span class="chip">{{ TASKS[r.algorithm.task].label }}</span>
                <span class="chip">{{ r.algorithm.framework }}</span>
                <span class="chip">许可证 {{ r.algorithm.license }}</span>
                <span class="ml-auto text-xs text-gray-500">{{ r.version.createdBy }} 提交于 {{ fmtDate(r.version.createdAt) }}</span>
              </div>
              <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">{{ r.algorithm.summary }}</p>
              <div class="mt-3 grid gap-3 text-sm sm:grid-cols-4">
                <div><p class="text-xs text-gray-500">变更说明</p>{{ r.version.changelog }}</div>
                <div><p class="text-xs text-gray-500">基础镜像</p><code class="mono">{{ r.version.baseImage }}</code></div>
                <div><p class="text-xs text-gray-500">声明显存 / 权重</p>{{ r.version.gpuMem }} GB · {{ fmtBytes(r.version.weightsSize) }}</div>
                <div><p class="text-xs text-gray-500">权重哈希</p><HashText :value="r.version.weightsHash ?? ''" /></div>
              </div>
              <ul class="mt-3 space-y-1 rounded-lg bg-gray-50 p-3 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
                <li>✓ 自动扫描：requirements.txt 未发现已知恶意包</li>
                <li>✓ 运行约束：评测容器断网、只读挂载、资源受限</li>
                <li>⚠ 许可证为 {{ r.algorithm.license }}，请确认是否允许在平台内运行与展示</li>
              </ul>
              <div class="mt-3 flex flex-col gap-2 sm:flex-row">
                <input v-model="notes[r.algorithm.id + r.version.version]" class="input flex-1" placeholder="审核备注（驳回时必填）" aria-label="审核备注" />
                <button class="btn-danger" @click="review(r.algorithm.id, r.version.version, false)">驳回</button>
                <button class="btn-brand" @click="review(r.algorithm.id, r.version.version, true)">通过并构建</button>
              </div>
            </div>
          </div>
        </StateView>
      </div>

      <!-- 厂商 -->
      <div v-else>
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <p class="text-sm text-gray-500">厂商按《算法标准 1.0》第四部分完成入库申报后，才能为其开通厂商账号、提交算法。</p>
          <RouterLink to="/vendors/new" class="btn-primary ml-auto"><Building2 class="size-4" />新建厂商</RouterLink>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <RouterLink v-for="o in vendors" :key="o.id" :to="`/orgs/${o.id}`" class="card flex gap-3 p-4 hover:border-gray-300 dark:hover:border-gray-700">
            <OrgAvatar :org="o.id" :size="40" />
            <div class="min-w-0">
              <p class="font-medium">{{ o.displayName }} <span v-if="o.enName" class="text-xs font-normal text-gray-500">{{ o.enName }}</span></p>
              <p class="mono text-xs text-gray-500">vendor.id = {{ o.id }} · {{ (users ?? []).filter((u) => u.orgId === o.id).length }} 个账号</p>
              <p class="mt-1 line-clamp-2 text-sm text-gray-600 dark:text-gray-400">{{ o.description }}</p>
            </div>
          </RouterLink>
        </div>
      </div>

      <Modal :open="createOpen" title="新建账号" description="账号创建后，将临时密码通过线下渠道告知用户，首次登录强制修改。" @update:open="closeCreate">
        <div v-if="created" class="space-y-3 text-sm">
          <p>账号 <b class="mono">{{ created.username }}</b> 已创建。</p>
          <div class="rounded-lg bg-amber-50 p-3 dark:bg-amber-900/20">
            <p class="text-xs text-amber-800 dark:text-amber-300">临时密码（仅显示一次，演示数据）</p>
            <HashText :value="created.tempPassword" :short="40" />
          </div>
        </div>
        <form v-else id="nu-form" class="space-y-3" @submit.prevent="doCreate">
          <div class="grid gap-3 sm:grid-cols-2">
            <div><label class="label" for="nu-u">用户名</label><input id="nu-u" v-model.trim="nu.username" class="input mono" required pattern="[a-z0-9._-]{3,32}" /></div>
            <div><label class="label" for="nu-d">姓名</label><input id="nu-d" v-model="nu.displayName" class="input" required /></div>
          </div>
          <div><label class="label" for="nu-e">邮箱</label><input id="nu-e" v-model.trim="nu.email" type="email" class="input" required /></div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <label class="label" for="nu-r">角色</label>
              <select id="nu-r" v-model="nu.role" class="input">
                <option v-for="(v, k) in ROLES" :key="k" :value="k">{{ v.label }}</option>
              </select>
            </div>
            <div v-if="nu.role === 'vendor'">
              <label class="label" for="nu-o">所属厂商</label>
              <select id="nu-o" v-model="nu.orgId" class="input" required>
                <option v-for="o in vendors" :key="o.id" :value="o.id">{{ o.displayName }}</option>
              </select>
            </div>
            <p v-else class="self-end pb-2 text-xs text-gray-500">{{ ROLES[nu.role].label }}不属于任何组织</p>
          </div>
        </form>
        <template #footer>
          <button class="btn-default" @click="closeCreate(false)">{{ created ? '完成' : '取消' }}</button>
          <button v-if="!created" type="submit" form="nu-form" class="btn-brand">创建账号</button>
        </template>
      </Modal>
    </template>
  </div>
</template>
