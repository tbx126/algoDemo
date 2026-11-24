<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, Plus, Search, Settings2, Sparkles, Tag, X } from 'lucide-vue-next'
import type { Algorithm, BusinessCategory, Dataset, ListQuery, TaskType } from '@/types'
import { listAlgorithms, listDatasets, listTags } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { BUSINESS_CATEGORIES, TASKS } from '@/utils/meta'
import { orgs } from '@/mock/orgs'
import { useSession } from '@/stores/session'
import TaskIcon from '@/components/ui/TaskIcon.vue'
import StateView from '@/components/ui/StateView.vue'
import AlgoCard from '@/components/algo/AlgoCard.vue'
import DatasetCard from '@/components/dataset/DatasetCard.vue'
import TagManagerModal from '@/components/algo/TagManagerModal.vue'

const props = defineProps<{ kind: 'algorithm' | 'dataset' }>()
const route = useRoute()
const router = useRouter()
const { can } = useSession()

const parseTags = (raw: unknown): string[] =>
  typeof raw === 'string' && raw.trim() ? raw.split(',').map((s) => s.trim()).filter(Boolean) : []

const q = computed<ListQuery>(() => ({
  q: (route.query.q as string) || '',
  task: ((route.query.task as string) || '') as TaskType | '',
  business: ((route.query.business as string) || '') as BusinessCategory | '',
  selfDeveloped: ((route.query.selfDeveloped as string) || '') as ListQuery['selfDeveloped'],
  tags: parseTags(route.query.tags),
  framework: (route.query.framework as string) || '',
  org: (route.query.org as string) || '',
  sort: ((route.query.sort as string) || 'trending') as ListQuery['sort'],
  page: Number(route.query.page) || 1,
  pageSize: 24,
}))

function setQ(patch: Partial<ListQuery>) {
  const next: Record<string, string> = {}
  const merged = { ...q.value, page: 1, ...patch }
  for (const [k, v] of Object.entries(merged)) {
    if (k === 'pageSize' || (k === 'page' && v === 1) || (k === 'sort' && v === 'trending')) continue
    if (Array.isArray(v)) {
      if (v.length) next[k] = v.join(',')
    } else if (v) {
      next[k] = String(v)
    }
  }
  router.replace({ query: next })
}

function toggleTag(name: string) {
  const cur = q.value.tags ?? []
  setQ({ tags: cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name] })
}

const search = ref(q.value.q ?? '')
let t: ReturnType<typeof setTimeout>
watch(search, (v) => {
  clearTimeout(t)
  t = setTimeout(() => setQ({ q: v }), 250)
})

const { data, loading, error, reload } = useAsync<{ items: (Algorithm | Dataset)[]; total: number }>(
  () => (props.kind === 'algorithm' ? listAlgorithms(q.value) : listDatasets(q.value)),
  [q],
)
const { data: tagList, reload: reloadTags } = useAsync(() => (props.kind === 'algorithm' ? listTags() : Promise.resolve([])))
const tagManagerOpen = ref(false)

function onTagsChanged() {
  reloadTags()
  reload()
}

const pages = computed(() => Math.max(1, Math.ceil((data.value?.total ?? 0) / 24)))

const groups = computed(() => {
  const g: Record<string, TaskType[]> = {}
  for (const [k, v] of Object.entries(TASKS)) (g[v.group] ??= []).push(k as TaskType)
  return g
})
const businessList = Object.entries(BUSINESS_CATEGORIES) as [BusinessCategory, (typeof BUSINESS_CATEGORIES)[BusinessCategory]][]
const frameworks = ['PyTorch', 'ONNX', 'TensorRT', 'OpenCV', 'NumPy', 'Paddle']

interface ActiveFilter {
  key: string
  label: string
  clear: () => void
}
const activeFilters = computed<ActiveFilter[]>(() => {
  const list: ActiveFilter[] = []
  if (q.value.task) list.push({ key: 'task', label: `任务：${TASKS[q.value.task as TaskType].label}`, clear: () => setQ({ task: '' }) })
  if (q.value.selfDeveloped) list.push({ key: 'selfDeveloped', label: q.value.selfDeveloped === 'only' ? '来源：平台自研' : '来源：非自研', clear: () => setQ({ selfDeveloped: '' }) })
  if (q.value.business) list.push({ key: 'business', label: `业务：${BUSINESS_CATEGORIES[q.value.business as BusinessCategory].label}`, clear: () => setQ({ business: '' }) })
  for (const tg of q.value.tags ?? []) {
    list.push({ key: `tag:${tg}`, label: `# ${tg}`, clear: () => toggleTag(tg) })
  }
  if (q.value.framework) list.push({ key: 'framework', label: q.value.framework, clear: () => setQ({ framework: '' }) })
  if (q.value.org) list.push({ key: 'org', label: orgs.find((o) => o.id === q.value.org)?.displayName ?? q.value.org, clear: () => setQ({ org: '' }) })
  return list
})

const title = computed(() => (props.kind === 'algorithm' ? '算法' : '数据集'))
const createTo = computed(() => (props.kind === 'algorithm' ? (can.value.createAlgorithm ? '/algorithms/new' : '') : can.value.createDataset ? '/datasets/new' : ''))
const showAllTags = ref(false)
const visibleTags = computed(() => {
  const list = tagList.value ?? []
  if (showAllTags.value || list.length <= 8) return list
  const selected = new Set(q.value.tags ?? [])
  const top = list.slice(0, 8)
  const extra = list.slice(8).filter((t) => selected.has(t.name))
  return [...top, ...extra]
})
</script>

<template>
  <div class="container-page flex flex-col gap-6 pt-6 lg:flex-row lg:gap-8">
    <!-- 筛选侧栏 -->
    <aside class="shrink-0 lg:w-72">
      <div class="lg:sticky lg:top-20">
        <h3 class="mb-2 text-sm font-medium text-gray-500">任务分类</h3>
        <div v-for="(tasks, g) in groups" :key="g" class="mb-3">
          <p class="mb-1.5 text-xs text-gray-400">{{ g }}</p>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="tk in tasks"
              :key="tk"
              class="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2 py-1 text-xs transition"
              :class="q.task === tk ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900' : 'border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'"
              @click="setQ({ task: q.task === tk ? '' : tk })"
            >
              <TaskIcon :task="tk" class="size-3.5" :class="q.task === tk ? '' : TASKS[tk].color" />{{ TASKS[tk].label }}
            </button>
          </div>
        </div>

        <template v-if="kind === 'algorithm'">
          <h3 class="mt-5 mb-2 text-sm font-medium text-gray-500">来源属性</h3>
          <div class="flex flex-wrap gap-1.5">
            <button
              class="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2.5 py-1 text-xs transition"
              :class="q.selfDeveloped === 'only' ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'"
              @click="setQ({ selfDeveloped: q.selfDeveloped === 'only' ? '' : 'only' })"
            >
              <Sparkles class="size-3" :class="q.selfDeveloped === 'only' ? '' : 'text-brand-500'" />平台自研
            </button>
            <button
              class="cursor-pointer rounded-lg border px-2.5 py-1 text-xs transition"
              :class="q.selfDeveloped === 'external' ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900' : 'border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'"
              @click="setQ({ selfDeveloped: q.selfDeveloped === 'external' ? '' : 'external' })"
            >
              外部 / 厂商
            </button>
          </div>

          <h3 class="mt-5 mb-2 text-sm font-medium text-gray-500">业务分类</h3>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="[bk, bv] in businessList"
              :key="bk"
              class="cursor-pointer rounded-lg border px-2.5 py-1 text-xs transition"
              :class="q.business === bk ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900' : 'border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'"
              @click="setQ({ business: q.business === bk ? '' : bk })"
            >
              {{ bv.label }}
            </button>
          </div>

          <div class="mt-5 mb-2 flex items-center justify-between">
            <h3 class="text-sm font-medium text-gray-500">标签 <span v-if="tagList?.length" class="text-xs font-normal text-gray-400">({{ tagList.length }})</span></h3>
            <button
              v-if="can.createAlgorithm"
              type="button"
              class="inline-flex cursor-pointer items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
              @click="tagManagerOpen = true"
            >
              <Settings2 class="size-3" />管理
            </button>
          </div>
          <div v-if="tagList?.length" class="flex flex-wrap gap-1.5">
            <button
              v-for="tg in visibleTags"
              :key="tg.name"
              class="inline-flex cursor-pointer items-center gap-1 rounded-lg border px-2 py-1 text-xs transition"
              :class="(q.tags ?? []).includes(tg.name) ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900' : 'border-gray-200 text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'"
              @click="toggleTag(tg.name)"
            >
              <Tag class="size-3 opacity-60" />
              <span>{{ tg.name }}</span>
              <span class="text-[10px] opacity-60">{{ tg.count }}</span>
            </button>
            <button
              v-if="tagList.length > 8"
              type="button"
              class="cursor-pointer rounded-lg px-2 py-1 text-xs text-brand-600 hover:bg-brand-50 dark:text-brand-400 dark:hover:bg-brand-950/40"
              @click="showAllTags = !showAllTags"
            >
              {{ showAllTags ? '收起' : `展开全部 (${tagList.length})` }}
            </button>
          </div>
          <p v-else class="text-xs text-gray-400">暂无标签</p>

          <h3 class="mt-5 mb-2 text-sm font-medium text-gray-500">框架</h3>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="f in frameworks"
              :key="f"
              class="cursor-pointer rounded-lg border px-2 py-1 text-xs"
              :class="q.framework === f ? 'border-gray-900 bg-gray-900 text-white dark:border-white dark:bg-white dark:text-gray-900' : 'border-gray-200 text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-300 dark:hover:bg-gray-900'"
              @click="setQ({ framework: q.framework === f ? '' : f })"
            >
              {{ f }}
            </button>
          </div>
        </template>

        <template v-if="can.seeOthersOnBoard">
          <h3 class="mt-5 mb-2 text-sm font-medium text-gray-500">组织 / 厂商</h3>
          <select class="input" :value="q.org" aria-label="按组织筛选" @change="setQ({ org: ($event.target as HTMLSelectElement).value })">
            <option value="">全部组织</option>
            <option v-for="o in orgs" :key="o.id" :value="o.id">{{ o.displayName }}{{ o.kind === 'vendor' ? '（厂商）' : '' }}</option>
          </select>
        </template>
      </div>
    </aside>

    <!-- 列表 -->
    <section class="min-w-0 flex-1">
      <div class="mb-4 flex flex-wrap items-center gap-3">
        <h1 class="text-xl font-semibold text-gray-900 dark:text-white">{{ title }}</h1>
        <span class="text-gray-400">{{ data?.total ?? '…' }}</span>
        <div class="relative ml-0 w-full sm:ml-4 sm:w-64">
          <Search class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-gray-400" />
          <input v-model="search" class="input pl-8" :placeholder="`按名称、标签筛选${title}`" :aria-label="`筛选${title}`" />
        </div>
        <div class="ml-auto flex items-center gap-2">
          <select class="input w-auto" :value="q.sort" aria-label="排序" @change="setQ({ sort: ($event.target as HTMLSelectElement).value as ListQuery['sort'] })">
            <option value="trending">排序：热门</option>
            <option value="updated">排序：最近更新</option>
            <option value="likes">排序：最多收藏</option>
            <option v-if="kind === 'algorithm'" value="evals">排序：评测最多</option>
          </select>
          <RouterLink v-if="createTo" :to="createTo" class="btn-primary"><Plus class="size-4" />{{ kind === 'algorithm' ? '新建算法' : '上传数据集' }}</RouterLink>
        </div>
      </div>
      <div v-if="activeFilters.length" class="mb-4 flex flex-wrap items-center gap-1.5">
        <button v-for="f in activeFilters" :key="f.key" class="chip cursor-pointer hover:border-gray-400" @click="f.clear()">{{ f.label }}<X class="size-3" /></button>
        <button class="cursor-pointer text-xs text-gray-500 underline-offset-2 hover:underline" @click="router.replace({ query: {} }); search = ''">清除全部</button>
      </div>

      <StateView :loading="loading && !data" :error="error" :empty="data && !data.items.length" :empty-text="`没有符合条件的${title}`">
        <div class="grid grid-cols-1 gap-3 xl:grid-cols-2" :class="{ 'opacity-60': loading }">
          <template v-if="kind === 'algorithm'">
            <AlgoCard v-for="a in data!.items as Algorithm[]" :key="a.id" :a="a" />
          </template>
          <template v-else>
            <DatasetCard v-for="d in data!.items as Dataset[]" :key="d.id" :d="d" />
          </template>
        </div>
        <div v-if="pages > 1" class="mt-6 flex items-center justify-center gap-2">
          <button class="btn-default px-2" :disabled="q.page === 1" aria-label="上一页" @click="setQ({ page: (q.page ?? 1) - 1 })"><ChevronLeft class="size-4" /></button>
          <span class="text-sm text-gray-500">{{ q.page }} / {{ pages }}</span>
          <button class="btn-default px-2" :disabled="q.page === pages" aria-label="下一页" @click="setQ({ page: (q.page ?? 1) + 1 })"><ChevronRight class="size-4" /></button>
        </div>
      </StateView>
    </section>

    <TagManagerModal v-if="kind === 'algorithm'" v-model:open="tagManagerOpen" @changed="onTagsChanged" />
  </div>
</template>
