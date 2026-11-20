<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, ClipboardList, Pencil, ExternalLink, FileCode, FileCog, FileText, FlaskConical, FolderTree, Heart, HardDrive, ScrollText, Trophy, Weight } from 'lucide-vue-next'
import { getAlgorithm, listBenchmarks, listEvals } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { fmtBytes, fmtDate, fmtMetric, timeAgo } from '@/utils/format'
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
import InferenceWidget from '@/components/algo/InferenceWidget.vue'
import EvalTable from '@/components/benchmark/EvalTable.vue'
import DeclarationView from '@/components/algo/DeclarationView.vue'

const route = useRoute()
const router = useRouter()
const { can } = useSession()
const id = computed(() => `${route.params.org}/${route.params.name}`)
const tab = computed(() => (route.query.tab as string) || 'card')
const setTab = (t: string) => router.replace({ query: t === 'card' ? {} : { tab: t } })

const { data: algo, loading, error } = useAsync(() => getAlgorithm(id.value))
const orgName = (oid: string) => orgs.find((o) => o.id === oid)?.displayName ?? oid
const editOpen = ref(false)
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
const totalSize = computed(() => algo.value?.files.reduce((s, f) => s + f.size, 0) ?? 0)
</script>

<template>
  <StateView :loading="loading" :error="error">
    <template v-if="algo">
      <!-- 头部 -->
      <div class="border-b border-gray-100 bg-gradient-to-t from-gray-50/80 to-white pt-8 dark:border-gray-800 dark:from-gray-900/60 dark:to-gray-950">
        <div class="container-page">
          <div class="flex flex-wrap items-center gap-2 text-lg">
            <OrgAvatar :org="algo.org" :size="22" />
            <RouterLink :to="`/orgs/${algo.org}`" class="text-gray-500 hover:text-brand-600">{{ algo.org }}</RouterLink>
            <span class="text-gray-300">/</span>
            <h1 class="mono font-semibold text-gray-900 dark:text-white">{{ algo.name }}</h1>
            <HashText :value="algo.id" :short="99" class="hidden [&_code]:hidden sm:inline-flex" />
            <button class="btn-default ml-1 px-2 py-0.5 text-xs" :aria-pressed="liked" @click="liked = !liked">
              <Heart class="size-3.5" :class="liked ? 'fill-rose-500 text-rose-500' : ''" />{{ algo.likes + (liked ? 1 : 0) }}
            </button>
            <button v-if="can.admin" class="btn-default ml-auto text-sm" @click="editOpen = true"><Pencil class="size-4" />编辑</button>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-1.5">
            <TaskBadge :task="algo.task" />
            <span class="chip">{{ algo.framework }}</span>
            <span v-for="t in algo.tags" :key="t" class="chip">{{ t }}</span>
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
        <!-- 算法卡片 -->
        <div v-if="tab === 'card'" class="flex flex-col gap-8 lg:flex-row">
          <aside class="hidden w-52 shrink-0 xl:block">
            <div class="sticky top-20"><DocOutline :items="toc" /></div>
          </aside>
          <div class="min-w-0 flex-1">
            <MarkdownView :source="algo.readme" @toc="toc = $event" />
          </div>
          <aside class="order-first w-full shrink-0 space-y-5 lg:order-none lg:w-[400px]">
            <InferenceWidget :algo="algo" />

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
              <div class="flex justify-between gap-3"><span class="text-gray-500">标识</span><span class="mono truncate">{{ algo.name }}</span></div>
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
                    <td class="whitespace-nowrap">{{ v.gpuMem }} GB</td>
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
                <h2 class="section-title">文件 <span class="text-sm font-normal text-gray-400">· {{ algo.versions[0].version }}</span></h2>
                <span class="flex items-center gap-1 text-xs text-gray-500"><HardDrive class="size-3.5" />{{ fmtBytes(totalSize) }}</span>
              </div>
              <div class="card divide-y divide-gray-100 dark:divide-gray-800">
                <div v-for="f in algo.files" :key="f.path" class="flex items-center gap-2 px-3 py-2 text-sm">
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
      <EditAlgorithmModal v-model:open="editOpen" :algo="algo" @saved="algo = $event" />
    </template>
  </StateView>
</template>
