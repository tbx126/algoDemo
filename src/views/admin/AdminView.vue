<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, Check, ClipboardCheck, Pencil, Plus, RotateCcw, ShieldCheck, Tag, Trash2, UserPlus, Users, X } from 'lucide-vue-next'
import { ApiError, createTag, createUser, deleteTag, listOrgs, listReviewQueue, listTags, listUsers, renameTag, resetPrototypeData, reviewVersion, setUserActive, updateUser } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { ROLES, TASKS } from '@/utils/meta'
import { fmtBytes, fmtDate, timeAgo } from '@/utils/format'
import { algoFullLabel } from '@/utils/display'
import type { Role, User } from '@/types'
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
const { data: tagList, reload: reloadTags } = useAsync(() => listTags())

// ---- 标签管理 ----
const newTag = ref('')
const editingTag = ref<string | null>(null)
const editTagDraft = ref('')
const tagBusy = ref(false)
async function addTag() {
  const v = newTag.value.trim()
  if (!v || tagBusy.value) return
  tagBusy.value = true
  try {
    await createTag(v)
    newTag.value = ''
    toast(`已添加标签「${v}」`)
    reloadTags()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '添加失败', 'error')
  } finally {
    tagBusy.value = false
  }
}
async function saveTagRename(oldName: string) {
  const next = editTagDraft.value.trim()
  if (!next) {
    toast('标签名称不能为空', 'error')
    return
  }
  if (next === oldName) {
    editingTag.value = null
    return
  }
  tagBusy.value = true
  try {
    await renameTag(oldName, next)
    editingTag.value = null
    toast(`已将「${oldName}」重命名为「${next}」`)
    reloadTags()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '修改失败', 'error')
  } finally {
    tagBusy.value = false
  }
}
async function removeTag(name: string) {
  if (tagBusy.value) return
  tagBusy.value = true
  try {
    await deleteTag(name)
    toast(`已删除标签「${name}」`, 'info')
    if (editingTag.value === name) editingTag.value = null
    reloadTags()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '删除失败', 'error')
  } finally {
    tagBusy.value = false
  }
}

// ---- 用户 ----
const userQ = ref('')
const filteredUsers = computed(() => (users.value ?? []).filter((u) => !userQ.value || u.username.includes(userQ.value) || u.displayName.includes(userQ.value)))
const createOpen = ref(false)
const nu = reactive({ username: '', displayName: '', email: '', role: 'vendor' as Role, orgId: '' })
const vendors = computed(() => (orgList.value ?? []).filter((o) => o.kind === 'vendor'))
const orgName = (id: string | null) => (id ? (orgList.value?.find((o) => o.id === id)?.displayName ?? id) : '')
const created = ref<{ username: string; tempPassword: string } | null>(null)
// 默认选中第一个厂商
watch(vendors, (v) => !nu.orgId && v[0] && (nu.orgId = v[0].id), { immediate: true })
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
    Object.assign(nu, { username: '', displayName: '', email: '', role: 'vendor', orgId: vendors.value[0]?.id ?? '' })
  }
}
// ---- 编辑用户 ----
const editing = ref<User | null>(null)
const eu = reactive({ displayName: '', email: '', role: 'vendor' as Role, orgId: '' })
const editOpen = computed({ get: () => !!editing.value, set: (v) => !v && (editing.value = null) })
function openEdit(u: User) {
  editing.value = u
  Object.assign(eu, { displayName: u.displayName, email: u.email, role: u.role, orgId: u.orgId ?? vendors.value[0]?.id ?? '' })
}
async function saveEdit() {
  if (!editing.value) return
  try {
    await updateUser(editing.value.id, { displayName: eu.displayName.trim(), email: eu.email.trim(), role: eu.role, orgId: eu.role === 'vendor' ? eu.orgId : null })
    toast('账号信息已保存')
    editing.value = null
    reloadUsers()
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'error')
  }
}

// ---- 重置演示数据 ----
const resetOpen = ref(false)

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
        <button class="tab" :class="{ 'tab-active': tab === 'tags' }" @click="router.replace('/admin/tags')">
          <Tag class="size-4" />标签<span v-if="tagList?.length" class="chip px-1 py-0 text-[10px]">{{ tagList.length }}</span>
        </button>
      </div>

      <!-- 用户 -->
      <div v-if="tab === 'users'">
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <input v-model="userQ" class="input w-64" placeholder="搜索用户名 / 姓名" aria-label="搜索用户" />
          <p class="text-sm text-gray-500">平台不开放注册：厂商与演示账号均由管理员创建。</p>
          <button class="btn-default ml-auto" title="清除本浏览器中保存的修改，恢复初始演示数据" @click="resetOpen = true"><RotateCcw class="size-4" />重置演示数据</button>
          <button class="btn-primary" @click="createOpen = true"><UserPlus class="size-4" />新建账号</button>
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
                  <td class="text-right whitespace-nowrap">
                    <div class="inline-flex items-center justify-end gap-1">
                      <button class="btn-ghost px-2 py-1 text-xs" @click="openEdit(u)"><Pencil class="size-3.5" />编辑</button>
                      <button class="btn-ghost px-2 py-1 text-xs" @click="toggleActive(u.id, !u.active)">{{ u.active ? '停用' : '启用' }}</button>
                    </div>
                  </td>
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
                <RouterLink :to="`/algorithms/${r.algorithm.id}?tab=files`" class="font-medium hover:text-brand-600">{{ algoFullLabel(r.algorithm.id) }}</RouterLink>
                <span class="mono text-gray-500">{{ r.version.version }}</span>
                <span class="chip">{{ TASKS[r.algorithm.task].label }}</span>
                <span class="chip">{{ r.algorithm.framework }}</span>
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
                <li>⚠ 请确认第三方组件与权重的授权范围是否允许在平台内运行与展示</li>
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
      <div v-else-if="tab === 'vendors'">
        <div class="mb-3 flex flex-wrap items-center gap-3">
          <p class="text-sm text-gray-500">厂商按《算法标准 1.0》第四部分完成入库申报后，才能为其开通厂商账号、提交算法。</p>
          <RouterLink to="/vendors/new" class="btn-primary ml-auto"><Building2 class="size-4" />新建厂商</RouterLink>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div v-for="o in vendors" :key="o.id" class="card flex gap-3 p-4">
            <OrgAvatar :org="o.id" :size="40" />
            <div class="min-w-0 flex-1">
              <p class="font-medium">{{ o.displayName }} <span v-if="o.enName" class="text-xs font-normal text-gray-500">{{ o.enName }}</span></p>
              <p class="mono text-xs text-gray-500">vendor.id = {{ o.id }} · {{ (users ?? []).filter((u) => u.orgId === o.id).length }} 个账号</p>
              <p class="mt-1 line-clamp-2 text-sm text-gray-600 dark:text-gray-400">{{ o.description }}</p>
              <div class="mt-2 flex gap-2">
                <RouterLink :to="`/orgs/${o.id}`" class="btn-default py-1 text-xs">查看</RouterLink>
                <RouterLink :to="`/vendors/${o.id}/edit`" class="btn-default py-1 text-xs"><Pencil class="size-3.5" />编辑</RouterLink>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 标签 -->
      <div v-else>
        <div class="mb-4 flex flex-wrap items-center gap-3">
          <form class="flex flex-1 flex-wrap items-center gap-2 sm:max-w-md" @submit.prevent="addTag">
            <input v-model="newTag" class="input flex-1" placeholder="输入新标签名称，回车添加" aria-label="新标签名称" />
            <button type="submit" class="btn-primary shrink-0" :disabled="tagBusy || !newTag.trim()"><Plus class="size-4" />添加标签</button>
          </form>
          <p class="text-sm text-gray-500">共 {{ tagList?.length ?? 0 }} 个标签；修改标签名称会同步更新所有关联算法。</p>
        </div>
        <StateView :loading="!tagList" :empty="tagList && !tagList.length" empty-text="暂无标签">
          <div class="card overflow-x-auto">
            <table class="table-base">
              <thead><tr><th>标签名称</th><th>关联算法数</th><th class="text-right">操作</th></tr></thead>
              <tbody>
                <tr v-for="t in tagList" :key="t.name">
                  <td>
                    <div v-if="editingTag === t.name" class="flex max-w-xs items-center gap-1.5">
                      <input
                        v-model="editTagDraft"
                        class="input h-7 py-0 text-sm"
                        aria-label="修改标签名称"
                        autofocus
                        @keydown.enter.prevent="saveTagRename(t.name)"
                        @keydown.esc.prevent="editingTag = null"
                      />
                      <button type="button" class="btn-ghost px-1.5 py-1 text-emerald-600" :disabled="tagBusy" @click="saveTagRename(t.name)"><Check class="size-4" /></button>
                      <button type="button" class="btn-ghost px-1.5 py-1 text-gray-400" @click="editingTag = null"><X class="size-4" /></button>
                    </div>
                    <RouterLink v-else :to="`/algorithms?tags=${encodeURIComponent(t.name)}`" class="inline-flex items-center gap-1.5 font-medium hover:text-brand-600">
                      <Tag class="size-3.5 text-gray-400" />{{ t.name }}
                    </RouterLink>
                  </td>
                  <td><span class="chip">{{ t.count }} 个算法</span></td>
                  <td class="text-right whitespace-nowrap">
                    <div class="inline-flex items-center justify-end gap-1">
                      <button type="button" class="btn-ghost px-2 py-1 text-xs" @click="editingTag = t.name; editTagDraft = t.name"><Pencil class="size-3.5" />重命名</button>
                      <button type="button" class="btn-ghost px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40" :disabled="tagBusy" @click="removeTag(t.name)"><Trash2 class="size-3.5" />删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </StateView>
      </div>

      <Modal v-model:open="editOpen" :title="`编辑账号 @${editing?.username ?? ''}`">
        <form id="eu-form" class="space-y-3" @submit.prevent="saveEdit">
          <div class="grid gap-3 sm:grid-cols-2">
            <div><label class="label" for="eu-d">姓名</label><input id="eu-d" v-model="eu.displayName" class="input" required /></div>
            <div><label class="label" for="eu-e">邮箱</label><input id="eu-e" v-model.trim="eu.email" type="email" class="input" required /></div>
          </div>
          <div class="grid gap-3 sm:grid-cols-2">
            <div>
              <label class="label" for="eu-r">角色</label>
              <select id="eu-r" v-model="eu.role" class="input">
                <option v-for="(v, k) in ROLES" :key="k" :value="k">{{ v.label }}</option>
              </select>
            </div>
            <div v-if="eu.role === 'vendor'">
              <label class="label" for="eu-o">所属厂商</label>
              <select id="eu-o" v-model="eu.orgId" class="input" required>
                <option v-for="o in vendors" :key="o.id" :value="o.id">{{ o.displayName }}</option>
              </select>
            </div>
            <p v-else class="self-end pb-2 text-xs text-gray-500">{{ ROLES[eu.role].label }}不属于任何组织</p>
          </div>
        </form>
        <template #footer>
          <button class="btn-default" @click="editing = null">取消</button>
          <button type="submit" form="eu-form" class="btn-brand">保存</button>
        </template>
      </Modal>

      <Modal v-model:open="resetOpen" title="重置演示数据" description="原型中的新建与修改保存在本浏览器里。重置会清除这些修改并恢复初始演示数据，无法撤销。">
        <template #footer>
          <button class="btn-default" @click="resetOpen = false">取消</button>
          <button class="btn-danger" @click="resetPrototypeData()">确认重置</button>
        </template>
      </Modal>

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
