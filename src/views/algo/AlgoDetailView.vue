<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, CheckCircle2, ClipboardList, Clock, Pencil, ExternalLink, FileCode, FileCog, FileText, FlaskConical, FolderTree, Heart, HardDrive, Lock, MapPin, Plus, ScrollText, Send, Sparkles, Tag, Trash2, Trophy, Weight } from 'lucide-vue-next'
import { ApiError, deleteAlgorithm, getAlgorithm, getDispatchedRegions, getRegionTrialRequest, isDispatchedToRegion, listBenchmarks, listEvals, listTags, submitTrialRequest, updateAlgorithmTags } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { BUSINESS_CATEGORIES, REGIONS } from '@/utils/meta'
import { fmtBytes, fmtDate, fmtMetric, timeAgo } from '@/utils/format'
import { algoName, orgLabel } from '@/utils/display'
import { orgs } from '@/mock/orgs'
import type { AlgoVersion } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import TaskBadge from '@/components/ui/TaskBadge.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import HashText from '@/components/ui/HashText.vue'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import DocOutline from '@/components/ui/DocOutline.vue'
import type { TocItem } from '@/utils/markdown'
import Modal from '@/components/ui/Modal.vue'
import EditAlgorithmModal from '@/components/admin/EditAlgorithmModal.vue'
import DispatchModal from '@/components/admin/DispatchModal.vue'
import TagInput from '@/components/form/TagInput.vue'
import InferenceWidget from '@/components/algo/InferenceWidget.vue'
import EvalTable from '@/components/benchmark/EvalTable.vue'
import DeclarationView from '@/components/algo/DeclarationView.vue'

const route = useRoute()
const router = useRouter()
const { state, currentRegion, can } = useSession()
const id = computed(() => `${route.params.org}/${route.params.name}`)
const tab = computed(() => (route.query.tab as string) || 'card')
const setTab = (t: string) => router.replace({ query: t === 'card' ? {} : { tab: t } })

const { data: algo, loading, error } = useAsync(() => getAlgorithm(id.value))
const orgName = (oid: string) => orgs.find((o) => o.id === oid)?.displayName ?? oid
const editOpen = ref(false)
const dispatchOpen = ref(false)
const trialOpen = ref(false)
const trialReason = ref('')
const trialSubmitting = ref(false)

const dispatchedRegions = computed(() => (algo.value ? getDispatchedRegions(algo.value.id) : []))
const regionalAuthorized = computed(() => (algo.value ? isDispatchedToRegion(algo.value.id, currentRegion.value) : false))
const regionalReq = computed(() => (algo.value ? getRegionTrialRequest(algo.value.id, currentRegion.value) : undefined))
const regionalInferenceLock = computed(() => {
  if (state.role !== 'regional' || regionalAuthorized.value) return ''
  return `该算法尚未下发至「${currentRegion.value}」区域。您可免费查看全部已审核代码、配置与评测成绩，如需运行或调用请向总部提交试用申请。`
})

async function doApplyTrial() {
  if (!algo.value || !currentRegion.value || trialSubmitting.value) return
  if (!trialReason.value.trim()) {
    toast('请填写试用场景与申请理由', 'error')
    return
  }
  trialSubmitting.value = true
  try {
    await submitTrialRequest(algo.value.id, currentRegion.value, trialReason.value)
    toast(`已以「${currentRegion.value}」区域身份提交试用申请，等待总部审批下发`)
    trialReason.value = ''
    trialOpen.value = false
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '申请提交失败', 'error')
  } finally {
    trialSubmitting.value = false
  }
}
const deleteOpen = ref(false)
const deleting = ref(false)
async function doDelete() {
  if (!algo.value || deleting.value) return
  deleting.value = true
  try {
    await deleteAlgorithm(algo.value.id)
    toast(`算法「${algo.value.id}」已删除`, 'info')
    deleteOpen.value = false
    router.push('/algorithms')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '删除失败', 'error')
  } finally {
    deleting.value = false
  }
}
const tagOpen = ref(false)
const tagDraft = ref<string[]>([])
const tagSuggestions = ref<string[]>([])
const tagSaving = ref(false)
async function openTagModal() {
  if (!algo.value) return
  tagDraft.value = [...algo.value.tags]
  tagOpen.value = true
  tagSuggestions.value = (await listTags()).map((t) => t.name)
}
async function saveTags() {
  if (!algo.value) return
  tagSaving.value = true
  try {
    algo.value = await updateAlgorithmTags(algo.value.id, tagDraft.value)
    toast('标签已更新')
    tagOpen.value = false
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'error')
  } finally {
    tagSaving.value = false
  }
}
const toc = ref<TocItem[]>([])
const { data: runs } = useAsync(() => listEvals({ algorithmId: id.value }))
const { data: benches } = useAsync(() => listBenchmarks())

const liked = ref(false)
const logOf = ref<AlgoVersion | null>(null)
const logOpen = computed({ get: () => !!logOf.value, set: (v) => !v && (logOf.value = null) })

/** 右侧“评测成绩”：每个 Benchmark 取该算法最好的有效成绩 */
const scores = computed(() => {
  if (!runs.value || !benches.value) return []
  const out: { benchId: string; name: string; metric: string; value: number; unit?: string; version: string }[] = []
  for (const b of benches.value) {
    const pm = b.metrics.find((m) => m.primary)!
    const rs = runs.value.filter((r) => r.benchmarkId === b.id && r.isLatestValid)
    if (!rs.length) continue
    const best = rs.reduce((x, y) => ((y.metrics[pm.key] ?? 0) > (x.metrics[pm.key] ?? 0) ? y : x))
    out.push({ benchId: b.id, name: b.displayName, metric: pm.label, value: best.metrics[pm.key], unit: pm.unit, version: best.algoVersion })
  }
  return out
})
const fileIcon = (k: string) => (k === 'weights' ? Weight : k === 'config' ? FileCog : k === 'doc' ? FileText : FileCode)
const totalSize = computed(() => (algo.value?.files ?? []).reduce((s, f) => s + (f.size ?? 0), 0))
</script>

<template>
  <StateView :loading="loading" :error="error">
    <template v-if="algo">
      <!-- 头部 -->
      <div class="border-b border-gray-100 bg-gradient-to-t from-gray-50/80 to-white pt-8 dark:border-gray-800 dark:from-gray-900/60 dark:to-gray-950">
        <div class="container-page">
          <div class="flex flex-wrap items-center gap-2 text-lg">
            <OrgAvatar :org="algo.org" :size="22" />
            <RouterLink :to="`/orgs/${algo.org}`" class="text-gray-500 hover:text-brand-600">{{ orgLabel(algo.org) }}</RouterLink>
            <span class="text-gray-300">/</span>
            <h1 class="font-semibold text-gray-900 dark:text-white">{{ algoName(algo) }}</h1>
            <HashText :value="algo.id" :short="99" class="hidden [&_code]:hidden sm:inline-flex" />
            <button class="btn-default ml-1 px-2 py-0.5 text-xs" :aria-pressed="liked" @click="liked = !liked">
              <Heart class="size-3.5" :class="liked ? 'fill-rose-500 text-rose-500' : ''" />{{ algo.likes + (liked ? 1 : 0) }}
            </button>
            <div v-if="can.admin" class="ml-auto flex items-center gap-2">
              <button class="btn-brand text-sm" @click="dispatchOpen = true"><Send class="size-4" />下发区域 ({{ dispatchedRegions.length }}/{{ REGIONS.length }})</button>
              <button class="btn-default text-sm" @click="editOpen = true"><Pencil class="size-4" />编辑</button>
              <button class="btn-danger text-sm" @click="deleteOpen = true"><Trash2 class="size-4" />删除</button>
            </div>
            <div v-else-if="can.applyTrial" class="ml-auto flex items-center gap-2">
              <span
                v-if="regionalAuthorized"
                class="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300"
              >
                <CheckCircle2 class="size-4" />已下发至 {{ currentRegion }} 区域
              </span>
              <span
                v-else-if="regionalReq?.status === 'pending'"
                class="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-300"
              >
                <Clock class="size-4" />{{ currentRegion }} 区域试用审批中
              </span>
              <button v-else class="btn-brand text-sm" @click="trialOpen = true">
                <Send class="size-4" />{{ regionalReq?.status === 'rejected' ? '重新申请试用' : '申请试用' }}
              </button>
            </div>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-1.5">
            <TaskBadge :task="algo.task" />
            <RouterLink
              v-if="algo.selfDeveloped"
              to="/algorithms?selfDeveloped=only"
              class="chip border-brand-200 bg-brand-50 font-semibold text-brand-700 hover:opacity-85 dark:border-brand-800 dark:bg-brand-950/60 dark:text-brand-300"
            >
              <Sparkles class="size-3" />平台自研
            </RouterLink>
            <RouterLink
              v-if="BUSINESS_CATEGORIES[algo.business]"
              :to="`/algorithms?business=${algo.business}`"
              class="chip hover:opacity-85"
              :class="BUSINESS_CATEGORIES[algo.business].chip"
            >
              {{ BUSINESS_CATEGORIES[algo.business].label }}
            </RouterLink>
            <span class="chip">{{ algo.framework }}</span>
            <RouterLink
              v-for="t in algo.tags"
              :key="t"
              :to="`/algorithms?tags=${encodeURIComponent(t)}`"
              class="chip hover:border-gray-400"
            >
              <Tag class="size-3 text-gray-400" />{{ t }}
            </RouterLink>
            <button
              v-if="can.createAlgorithm"
              type="button"
              class="chip cursor-pointer border-dashed text-gray-500 hover:border-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
              @click="openTagModal"
            >
              <Plus class="size-3" />管理标签
            </button>
            <a v-if="algo.paperUrl" :href="algo.paperUrl" target="_blank" rel="noopener" class="chip hover:border-gray-400"><BookOpen class="size-3" />论文<ExternalLink class="size-3" /></a>
          </div>
          <div class="mt-4 flex gap-1 no-scrollbar overflow-x-auto overflow-y-hidden">
            <button class="tab" :class="{ 'tab-active': tab === 'card' }" @click="setTab('card')"><BookOpen class="size-4" />算法卡片</button>
            <button class="tab" :class="{ 'tab-active': tab === 'files' }" @click="setTab('files')">
              <FolderTree class="size-4" />文件与版本<span class="chip px-1 py-0 text-[10px]">{{ algo.versions.length }}</span>
            </button>
            <button class="tab" :class="{ 'tab-active': tab === 'evals' }" @click="setTab('evals')">
              <FlaskConical class="size-4" />评测记录<span class="chip px-1 py-0 text-[10px]">{{ runs?.length ?? 0 }}</span>
            </button>
            <button v-if="algo.declaration" class="tab" :class="{ 'tab-active': tab === 'declaration' }" @click="setTab('declaration')"><ClipboardList class="size-4" />申报信息</button>
          </div>
        </div>
      </div>

      <div class="container-page pt-6">
        <!-- 区域侧授权与试用状态提示条 -->
        <div
          v-if="state.role === 'regional'"
          class="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm"
          :class="
            regionalAuthorized
              ? 'border-emerald-200 bg-emerald-50/70 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200'
              : regionalReq?.status === 'pending'
                ? 'border-amber-200 bg-amber-50/70 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200'
                : regionalReq?.status === 'rejected'
                  ? 'border-rose-200 bg-rose-50/70 text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200'
                  : 'border-sky-200 bg-sky-50/70 text-sky-900 dark:border-sky-900 dark:bg-sky-950/30 dark:text-sky-200'
          "
        >
          <div class="flex items-start gap-2.5">
            <CheckCircle2 v-if="regionalAuthorized" class="mt-0.5 size-4 shrink-0 text-emerald-600" />
            <Clock v-else-if="regionalReq?.status === 'pending'" class="mt-0.5 size-4 shrink-0 text-amber-600" />
            <Lock v-else class="mt-0.5 size-4 shrink-0 opacity-75" />
            <div class="space-y-0.5">
              <p v-if="regionalAuthorized" class="font-medium">已获得「{{ currentRegion }}」区域使用授权，可直接在线推理与部署调用。</p>
              <template v-else-if="regionalReq?.status === 'pending'">
                <p class="font-medium">「{{ currentRegion }}」区域已提交试用申请，等待总部审批下发。</p>
                <p class="text-xs opacity-85">申请理由：{{ regionalReq.reason }} · 提交于 {{ fmtDate(regionalReq.createdAt) }}</p>
              </template>
              <template v-else-if="regionalReq?.status === 'rejected'">
                <p class="font-medium">「{{ currentRegion }}」区域上次试用申请未通过审批，您仍可查看全部已审核代码与文档。</p>
                <p class="text-xs opacity-85">总部意见：{{ regionalReq.reviewNote || '未填写' }}</p>
              </template>
              <p v-else class="font-medium">当前算法尚未下发至「{{ currentRegion }}」区域；您可浏览全部已审核代码、配置与评测报告，如需运行使用请向总部申请试用。</p>
            </div>
          </div>
          <button
            v-if="!regionalAuthorized && regionalReq?.status !== 'pending'"
            type="button"
            class="btn-brand shrink-0 py-1.5 text-xs"
            @click="trialOpen = true"
          >
            <Send class="size-3.5" />{{ regionalReq?.status === 'rejected' ? '重新申请试用' : '申请试用' }}
          </button>
        </div>

        <!-- 算法卡片 -->
        <div v-if="tab === 'card'" class="flex flex-col gap-8 lg:flex-row">
          <DocOutline :items="toc" />
          <div class="min-w-0 flex-1">
            <MarkdownView :source="algo.readme" @toc="toc = $event" />
          </div>
          <aside class="order-first w-full shrink-0 space-y-5 lg:order-none lg:w-[400px]">
            <InferenceWidget
              :algo="algo"
              :locked-reason="regionalInferenceLock"
              :pending-trial="regionalReq?.status === 'pending'"
              @apply-trial="trialOpen = true"
            />

            <!-- 总部侧：区域下发范围卡片 -->
            <div v-if="can.dispatch" class="card p-4">
              <div class="mb-2.5 flex items-center gap-2">
                <MapPin class="size-4 text-sky-500" />
                <h3 class="text-sm font-semibold">区域下发范围</h3>
                <span class="mono text-xs text-gray-400">{{ dispatchedRegions.length }}/{{ REGIONS.length }}</span>
                <button type="button" class="btn-default ml-auto py-1 text-xs" @click="dispatchOpen = true">配置下发</button>
              </div>
              <div v-if="dispatchedRegions.length" class="flex flex-wrap gap-1.5">
                <span
                  v-for="rg in dispatchedRegions"
                  :key="rg"
                  class="chip border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-300"
                >
                  {{ rg }}
                </span>
              </div>
              <p v-else class="text-xs text-gray-500">尚未下发至任何区域，点击「配置下发」勾选目标区域。</p>
            </div>

            <div class="card p-4">
              <div class="mb-3 flex items-center gap-2">
                <Trophy class="size-4 text-amber-500" />
                <h3 class="text-sm font-semibold">评测成绩</h3>
                <RouterLink v-if="can.runEval" :to="`/evals/new?algo=${algo.id}`" class="btn-default ml-auto py-1 text-xs">发起评测</RouterLink>
              </div>
              <p v-if="!scores.length" class="text-sm text-gray-500">暂无评测成绩</p>
              <RouterLink
                v-for="s in scores"
                :key="s.benchId"
                :to="`/benchmarks/${s.benchId}`"
                class="flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                <span class="min-w-0">
                  <span class="block truncate">{{ s.name }}</span>
                  <span class="text-xs text-gray-500">{{ s.version }}</span>
                </span>
                <span class="shrink-0 text-right">
                  <span class="mono block font-semibold text-gray-900 dark:text-white">{{ fmtMetric(s.value, s.unit) }}{{ s.unit === '%' ? '%' : '' }}</span>
                  <span class="text-xs text-gray-500">{{ s.metric }}</span>
                </span>
              </RouterLink>
            </div>

            <div class="card space-y-2 p-4 text-sm">
              <div class="flex justify-between gap-3"><span class="text-gray-500">厂商</span><RouterLink :to="`/orgs/${algo.org}`" class="truncate hover:text-brand-600">{{ orgName(algo.org) }}</RouterLink></div>
              <div class="flex justify-between gap-3">
                <span class="text-gray-500">来源属性</span>
                <span v-if="algo.selfDeveloped" class="chip border-brand-200 bg-brand-50 py-0 text-xs font-medium text-brand-700 dark:border-brand-800 dark:bg-brand-950/60 dark:text-brand-300">
                  <Sparkles class="size-3" />平台自研
                </span>
                <span v-else class="text-gray-600 dark:text-gray-300">外部 / 厂商</span>
              </div>
              <div class="flex justify-between gap-3"><span class="text-gray-500">标识</span><span class="mono truncate">{{ algo.name }}</span></div>
              <div v-if="BUSINESS_CATEGORIES[algo.business]" class="flex justify-between"><span class="text-gray-500">业务分类</span><span class="chip py-0 text-xs" :class="BUSINESS_CATEGORIES[algo.business].chip">{{ BUSINESS_CATEGORIES[algo.business].label }}</span></div>
              <div class="flex justify-between"><span class="text-gray-500">最新版本</span><span class="mono">{{ algo.versions[0].version }}</span></div>
              <div class="flex justify-between"><span class="text-gray-500">状态</span><StatusBadge :status="algo.versions[0].status" /></div>
              <div class="flex justify-between"><span class="text-gray-500">更新</span><span>{{ timeAgo(algo.updatedAt) }}</span></div>
              <div class="space-y-1 border-t border-gray-100 pt-2 text-xs dark:border-gray-800">
                <button v-if="algo.declaration" class="block cursor-pointer text-brand-600 hover:underline" @click="setTab('declaration')">适用条件、运行环境与资源 → 申报信息</button>
                <button class="block cursor-pointer text-brand-600 hover:underline" @click="setTab('files')">权重、镜像与构建日志 → 文件与版本</button>
              </div>
            </div>
          </aside>
        </div>

        <!-- 文件与版本 -->
        <div v-else-if="tab === 'files'" class="space-y-8">
          <section>
            <h2 class="section-title mb-3">版本</h2>
            <p class="mb-3 text-sm text-gray-500">每个版本不可变。厂商提交需管理员审核后才会构建；构建产物为镜像，权重单独存储并以哈希锁定。</p>
            <div class="card overflow-x-auto">
              <table class="table-base">
                <thead>
                  <tr>
                    <th>版本</th>
                    <th>状态</th>
                    <th>变更说明</th>
                    <th>镜像 digest</th>
                    <th>权重哈希</th>
                    <th>显存</th>
                    <th>提交</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="v in algo.versions" :key="v.version">
                    <td class="mono font-medium">{{ v.version }}</td>
                    <td><StatusBadge :status="v.status" /></td>
                    <td class="max-w-56 truncate text-gray-600 dark:text-gray-400" :title="v.changelog">{{ v.changelog }}</td>
                    <td><HashText v-if="v.imageDigest" :value="v.imageDigest" /><span v-else class="text-gray-400">—</span></td>
                    <td><HashText v-if="v.weightsHash" :value="v.weightsHash" /></td>
                    <td class="whitespace-nowrap">{{ v.gpuMem ? `${v.gpuMem} GB` : 'CPU (0 GB)' }}</td>
                    <td class="whitespace-nowrap text-gray-500">{{ v.createdBy }} · {{ timeAgo(v.createdAt) }}</td>
                    <td class="whitespace-nowrap text-right">
                      <button class="btn-ghost px-2 py-1 text-xs" @click="logOf = v"><ScrollText class="size-3.5" />{{ v.status === 'pending_review' ? '审核信息' : '构建日志' }}</button>
                      <RouterLink v-if="v.status === 'ready' && can.runEval" :to="`/evals/new?algo=${algo.id}&v=${v.version}`" class="btn-ghost px-2 py-1 text-xs"><FlaskConical class="size-3.5" />评测</RouterLink>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="grid gap-6 lg:grid-cols-2">
            <div>
              <div class="mb-3 flex items-center justify-between">
                <h2 class="section-title">文件 <span class="text-sm font-normal text-gray-400">· {{ algo.versions[0]?.version ?? 'v1.0.0' }}</span></h2>
                <span class="flex items-center gap-1 text-xs text-gray-500"><HardDrive class="size-3.5" />{{ fmtBytes(totalSize) }}</span>
              </div>
              <div class="card divide-y divide-gray-100 dark:divide-gray-800">
                <div v-for="f in algo.files ?? []" :key="f.path" class="flex items-center gap-2 px-3 py-2 text-sm">
                  <component :is="fileIcon(f.kind)" class="size-4 text-gray-400" />
                  <span class="mono">{{ f.path }}</span>
                  <span v-if="f.kind === 'weights'" class="chip text-[10px]">存储层 · 不入镜像</span>
                  <span class="ml-auto text-xs text-gray-500">{{ f.size ? fmtBytes(f.size) : '—' }}</span>
                </div>
              </div>
            </div>
            <div>
              <h2 class="section-title mb-3">algo.yaml</h2>
              <pre class="scroll-thin overflow-x-auto rounded-xl bg-gray-900 p-4 text-xs leading-relaxed text-gray-100">{{ algo.algoYaml }}</pre>
            </div>
          </section>
        </div>

        <!-- 申报信息 -->
        <DeclarationView v-else-if="tab === 'declaration' && algo.declaration" :d="algo.declaration" />

        <!-- 评测记录 -->
        <div v-else>
          <div class="mb-3 flex items-center justify-between">
            <h2 class="section-title">评测记录</h2>
            <RouterLink v-if="can.runEval" :to="`/evals/new?algo=${algo.id}`" class="btn-primary"><FlaskConical class="size-4" />发起评测</RouterLink>
          </div>
          <EvalTable :runs="runs ?? []" hide-algo />
        </div>
      </div>

      <Modal v-model:open="logOpen" :title="`${algo.name} ${logOf?.version ?? ''} · ${logOf?.status === 'pending_review' ? '审核信息' : '构建日志'}`" width="max-w-2xl">
        <div v-if="logOf" class="space-y-3">
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
            <span>基础镜像 <code class="mono">{{ logOf.baseImage }}</code></span>
            <span>提交于 {{ fmtDate(logOf.createdAt) }}</span>
          </div>
          <pre class="scroll-thin max-h-80 overflow-auto rounded-lg bg-gray-900 p-3 text-xs leading-relaxed text-gray-100"><span v-for="(l, i) in logOf.buildLog" :key="i" class="block" :class="l.startsWith('[error]') ? 'text-rose-400' : l.startsWith('[review]') ? 'text-amber-300' : ''">{{ l }}</span></pre>
          <p v-if="logOf.reviewNote" class="text-sm">审核备注：{{ logOf.reviewNote }}</p>
        </div>
      </Modal>
      <Modal v-model:open="tagOpen" :title="`管理标签 · ${algo.name}`" description="为算法选择已有标签，或直接输入新标签名称后回车添加。">
        <TagInput v-model="tagDraft" label="算法标签" :suggestions="tagSuggestions" placeholder="输入标签名回车添加，或点选下方已有标签" />
        <template #footer>
          <button type="button" class="btn-default" @click="tagOpen = false">取消</button>
          <button type="button" class="btn-brand" :disabled="tagSaving" @click="saveTags">{{ tagSaving ? '保存中…' : '保存' }}</button>
        </template>
      </Modal>
      <Modal v-model:open="deleteOpen" :title="`删除算法 · ${algo.id}`" :description="`确认删除算法「${algo.id}」？其全部版本与 ${runs?.length ?? 0} 条评测记录将一并移除，无法撤销。`">
        <template #footer>
          <button type="button" class="btn-default" @click="deleteOpen = false">取消</button>
          <button type="button" class="btn-danger" :disabled="deleting" @click="doDelete">{{ deleting ? '删除中…' : '确认删除' }}</button>
        </template>
      </Modal>
      <EditAlgorithmModal v-model:open="editOpen" :algo="algo" @saved="algo = $event" />
      <DispatchModal v-if="can.dispatch" v-model:open="dispatchOpen" :algorithm-id="algo.id" />
      <Modal
        v-model:open="trialOpen"
        :title="`申请试用算法 · ${algoName(algo)}`"
        :description="`将以「${currentRegion}」区域身份向总部提交试用申请，经总部审批通过后将自动下发授权。`"
      >
        <div class="space-y-3 text-sm">
          <div class="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2 text-xs dark:bg-gray-800/60">
            <span class="text-gray-500">申请区域</span>
            <span class="chip border-emerald-200 bg-emerald-50 font-medium text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-300">
              <MapPin class="size-3" />{{ currentRegion }}区域
            </span>
          </div>
          <div>
            <label class="label" for="trial-reason">试用场景与申请理由</label>
            <textarea
              id="trial-reason"
              v-model="trialReason"
              rows="3"
              class="input"
              placeholder="例如：拟在华中区域新能源场站巡检业务中开展小范围试点验证，评估准确率与推理耗时…"
            />
          </div>
        </div>
        <template #footer>
          <button type="button" class="btn-default" @click="trialOpen = false">取消</button>
          <button type="button" class="btn-brand" :disabled="trialSubmitting || !trialReason.trim()" @click="doApplyTrial">
            <Send class="size-3.5" />{{ trialSubmitting ? '提交中…' : '提交试用申请' }}
          </button>
        </template>
      </Modal>
    </template>
  </StateView>
</template>
