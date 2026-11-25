<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { BookOpen, Download, Pencil, Eye, EyeOff, FlaskConical, GitCommitVertical, Heart, Lock, Table2, Trash2, Trophy, Upload } from 'lucide-vue-next'
import { ApiError, REAL_DS_IDS, deleteDataset, getDataset, getRealDatasetPart, listBenchmarks, type RealDatasetRow } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { fmtBytes, fmtNum, timeAgo } from '@/utils/format'
import { toast } from '@/stores/toast'
import { fileNameOf, labelSpec, rowsFor } from '@/utils/labels'
import type { DatasetPart, SplitName } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import TaskBadge from '@/components/ui/TaskBadge.vue'
import HashText from '@/components/ui/HashText.vue'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import DocOutline from '@/components/ui/DocOutline.vue'
import type { TocItem } from '@/utils/markdown'
import SynthImage from '@/components/ui/SynthImage.vue'
import Modal from '@/components/ui/Modal.vue'
import EditDatasetModal from '@/components/admin/EditDatasetModal.vue'
import SfSeriesPreview from '@/components/serverfault/SfSeriesPreview.vue'
import PfSeriesPreview from '@/components/powerforecast/PfSeriesPreview.vue'
import { SF_TASK } from '@/components/serverfault/types'
import SeriesSampleView from '@/components/dataset/SeriesSampleView.vue'
import { isSeriesTask } from '@/utils/meta'

const route = useRoute()
const router = useRouter()
const { can } = useSession()
const id = computed(() => `${route.params.org}/${route.params.name}`)
const tab = computed(() => (route.query.tab as string) || 'card')
const setTab = (t: string) => router.replace({ query: t === 'card' ? {} : { tab: t } })

const { data: ds, loading, error } = useAsync(() => getDataset(id.value))
const editOpen = ref(false)
const deleteOpen = ref(false)
const deleting = ref(false)
async function doDelete() {
  if (!ds.value || deleting.value) return
  deleting.value = true
  try {
    await deleteDataset(ds.value.id)
    toast(`数据集「${ds.value.id}」已删除`, 'info')
    deleteOpen.value = false
    router.push('/datasets')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '删除失败', 'error')
  } finally {
    deleting.value = false
  }
}
const toc = ref<TocItem[]>([])
const { data: allBench } = useAsync(() => listBenchmarks())
const benches = computed(() => allBench.value?.filter((b) => b.datasetId === id.value) ?? [])
const liked = ref(false)
const spec = computed(() => (ds.value ? labelSpec(ds.value.task) : null))
const PART_LABEL: Record<SplitName, string> = { train: '训练集', test: '测试集' }

// ---------- 当前查看的部分 ----------
const partName = computed<SplitName>(() => (tab.value === 'test' ? 'test' : 'train'))
const part = computed<DatasetPart | null>(() => (ds.value ? ds.value[partName.value] : null))
/** 测试集内容（样本与 labels.csv）仅管理员可见 */
const locked = computed(() => partName.value === 'test' && !can.value.testAccess)
const version = ref('')
watch(part, (p) => (version.value = p?.versions[0].version ?? ''), { immediate: true })
const ver = computed(() => part.value?.versions.find((v) => v.version === version.value) ?? part.value?.versions[0])
const offset = computed(() => (partName.value === 'train' ? 0 : 90000) + (part.value ? part.value.versions.findIndex((v) => v.version === version.value) * 7 : 0))

const showAnn = ref(true)
const count = ref(18)
watch(partName, () => (count.value = 18))

// 真实后端数据集分片（如 Admin/cat-dog-dataset、Admin/dehaze-dataset）：直接读取真实 labels.csv 与真实图片
const isRealDataset = computed(() => REAL_DS_IDS.has(ds.value?.id ?? ''))
const realRows = ref<RealDatasetRow[]>([])
watch(
  [() => ds.value?.id, isRealDataset, partName, locked],
  async ([dsId, isReal, p, isLocked]) => {
    if (!dsId || !isReal || isLocked) {
      realRows.value = []
      return
    }
    const res = await getRealDatasetPart(dsId, p, 500)
    realRows.value = res?.rows ?? []
  },
  { immediate: true },
)

const seedOf = (i: number) => (ds.value?.previewSeed ?? 0) + offset.value + i
const csvRows = computed(() => {
  if (isRealDataset.value && realRows.value.length) {
    return realRows.value.slice(0, 12).map((r, i) => ({ idx: i + 1, row: r.row ?? [r.file_name, r.label] }))
  }
  if (!ds.value || !part.value) return []
  const out: { idx: number; row: string[] }[] = []
  for (let i = 1; out.length < 12 && i < 40; i++) for (const row of rowsFor(seedOf(i), i, partName.value, ds.value.task, ds.value.classes, part.value.columns)) out.push({ idx: i, row })
  return out.slice(0, 12)
})
const classMax = computed(() => Math.max(1, ...Object.values(part.value?.classCounts ?? {})))

// 单个样本详情
const zoom = ref<number | null>(null)
const zoomOpen = computed({ get: () => zoom.value !== null, set: (v) => !v && (zoom.value = null) })
const zoomReal = computed(() => (isRealDataset.value && zoom.value !== null ? realRows.value[zoom.value - 1] ?? null : null))
const zoomRows = computed(() => {
  if (zoomReal.value) return [zoomReal.value.row ?? [zoomReal.value.file_name, zoomReal.value.label]]
  return ds.value && part.value && zoom.value !== null ? rowsFor(seedOf(zoom.value), zoom.value, partName.value, ds.value.task, ds.value.classes, part.value.columns) : []
})

function download(p: SplitName) {
  if (isRealDataset.value) {
    // 大体积真实数据集使用原生 <a> 流式下载，避免浏览器 JS 内存缓存数百 MB Blob
    const a = document.createElement('a')
    a.href = `/real-api/datasets/${ds.value!.id}/download/${p}`
    a.download = `${ds.value!.name}-${p}-v1.0.zip`
    document.body.appendChild(a)
    a.click()
    a.remove()
    toast(`已开始下载真实${PART_LABEL[p]}压缩包（${isSeriesTask(ds.value!.task) ? 'series/ + labels.csv' : 'images/ + labels.csv'}）`)
    return
  }
  toast(`已生成${PART_LABEL[p]} ${ds.value?.[p]?.versions[0].version} 的下载链接（images/ + labels.csv，模拟）`)
}
</script>

<template>
  <StateView :loading="loading" :error="error">
    <template v-if="ds">
      <div class="border-b border-gray-100 bg-gradient-to-t from-gray-50/80 to-white pt-8 dark:border-gray-800 dark:from-gray-900/60 dark:to-gray-950">
        <div class="container-page">
          <div class="flex flex-wrap items-center gap-2 text-lg">
            <span class="chip mr-1 text-[11px]">数据集</span>
            <OrgAvatar :org="ds.org" :size="22" />
            <RouterLink :to="`/orgs/${ds.org}`" class="text-gray-500 hover:text-brand-600">{{ ds.org }}</RouterLink>
            <span class="text-gray-300">/</span>
            <h1 class="mono font-semibold text-gray-900 dark:text-white">{{ ds.name }}</h1>
            <button class="btn-default ml-1 px-2 py-0.5 text-xs" :aria-pressed="liked" @click="liked = !liked">
              <Heart class="size-3.5" :class="liked ? 'fill-rose-500 text-rose-500' : ''" />{{ ds.likes + (liked ? 1 : 0) }}
            </button>
            <button v-if="can.admin" class="btn-default ml-auto text-sm" @click="editOpen = true"><Pencil class="size-4" />编辑</button>
            <button v-if="can.admin" class="btn-danger text-sm" @click="deleteOpen = true"><Trash2 class="size-4" />删除</button>
            <RouterLink v-if="can.createDataset" :to="`/datasets/new?dataset=${ds.id}`" class="btn-default text-sm" :class="{ 'ml-auto': !can.admin }"><Upload class="size-4" />上传新版本</RouterLink>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-1.5">
            <TaskBadge :task="ds.task" />
            <span class="chip">训练集 {{ fmtNum(ds.train.versions[0].files) }} · {{ ds.train.versions[0].version }}</span>
            <span class="chip"><Lock class="size-3" />测试集 {{ ds.test ? `${fmtNum(ds.test.versions[0].files)} · ${ds.test.versions[0].version}` : '未上传' }}</span>
            <span v-for="t in ds.tags" :key="t" class="chip">{{ t }}</span>
          </div>
          <div class="no-scrollbar mt-4 flex gap-1 overflow-x-auto overflow-y-hidden">
            <button class="tab" :class="{ 'tab-active': tab === 'card' }" @click="setTab('card')"><BookOpen class="size-4" />数据集卡片</button>
            <button class="tab" :class="{ 'tab-active': tab === 'train' }" @click="setTab('train')"><Table2 class="size-4" />训练集</button>
            <button class="tab" :class="{ 'tab-active': tab === 'test' }" @click="setTab('test')"><Lock class="size-4" />测试集</button>
            <button class="tab" :class="{ 'tab-active': tab === 'versions' }" @click="setTab('versions')"><GitCommitVertical class="size-4" />版本</button>
          </div>
        </div>
      </div>

      <div class="container-page pt-6">
        <!-- ========== 卡片 ========== -->
        <div v-if="tab === 'card'" class="flex flex-col gap-8 lg:flex-row">
          <div class="relative min-w-0 flex-1">
            <DocOutline :items="toc" />
            <div class="mb-6 overflow-hidden rounded-xl border border-gray-100 dark:border-gray-800">
              <div class="flex items-center justify-between border-b border-gray-100 px-3 py-2 text-sm dark:border-gray-800">
                <span class="font-medium">训练集预览</span>
                <button class="cursor-pointer text-xs text-brand-600 hover:underline" @click="setTab('train')">查看训练集 →</button>
              </div>
              <!-- 服务器故障检测标准数据集：折线图预览 -->
              <div v-if="ds.task === SF_TASK" class="p-3">
                <SfSeriesPreview :dataset-id="ds.id" part="train" :rows="ds.realPreview?.train ?? []" :max="12" />
              </div>
              <!-- 新能源功率预测标准数据集：48h 功率与 NWP 气象折线图预览 -->
              <div v-else-if="ds.task === 'power-forecast'" class="p-3">
                <PfSeriesPreview :dataset-id="ds.id" part="train" :rows="ds.realPreview?.train ?? []" :max="12" />
              </div>
              <div v-else-if="ds.realPreview?.train?.length" class="grid gap-1.5 p-1.5" :class="ds.task === 'ocr' ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-3 sm:grid-cols-6'">
                <div v-for="item in ds.realPreview.train" :key="item.file_name" class="relative overflow-hidden rounded-md border border-gray-100 bg-gray-100 dark:border-gray-800 dark:bg-gray-900">
                  <template v-if="ds.task === 'ocr'">
                    <div class="flex h-16 items-center justify-center bg-white p-1.5 dark:bg-gray-950">
                      <img :src="item.url" :alt="item.label" class="max-h-full max-w-full object-contain" loading="lazy" />
                    </div>
                    <div class="mono truncate border-t border-gray-100 bg-gray-50 px-2 py-1 text-[11px] font-medium text-gray-800 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200" :title="item.label">
                      {{ item.label }}
                    </div>
                  </template>
                  <template v-else>
                    <img :src="item.url" :alt="item.label" class="block aspect-[4/3] w-full object-cover" loading="lazy" />
                    <span class="pointer-events-none absolute top-1 left-1 max-w-[calc(100%-0.5rem)] truncate rounded bg-gray-900/75 px-1.5 py-0.5 text-[11px] font-medium text-white">{{ item.label }}</span>
                  </template>
                </div>
              </div>
              <div v-else class="grid grid-cols-3 gap-1 p-1 sm:grid-cols-6">
                <div v-for="i in 6" :key="i" class="overflow-hidden rounded-md">
                  <SynthImage :seed="ds.previewSeed + i" :task="ds.task" :classes="ds.classes" :sample-images="ds.sampleImages" annotate :width="240" :height="180" />
                </div>
              </div>
            </div>
            <MarkdownView :source="ds.readme" @toc="toc = $event" />
          </div>
          <aside class="w-full shrink-0 space-y-5 lg:w-[360px]">
            <div class="card divide-y divide-gray-100 dark:divide-gray-800">
              <div v-for="p in (['train', 'test'] as const)" :key="p" class="p-4">
                <div class="flex items-center gap-2">
                  <h3 class="flex items-center gap-1.5 text-sm font-semibold">{{ PART_LABEL[p] }}<Lock v-if="p === 'test'" class="size-3.5 text-amber-500" /></h3>
                  <span v-if="ds[p]" class="mono ml-auto text-xs text-gray-500">{{ ds[p]!.versions[0].version }}</span>
                </div>
                <template v-if="ds[p]">
                  <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">{{ fmtNum(ds[p]!.versions[0].files) }} 个文件 · {{ fmtNum(ds[p]!.versions[0].rows) }} 行标注 · {{ fmtBytes(ds[p]!.versions[0].sizeBytes) }}</p>
                  <p class="mt-1 text-xs text-gray-500">{{ p === 'train' ? '所有账号可查看与下载' : '仅管理员可查看与下载，厂商可在其上评测' }}</p>
                  <button v-if="p === 'train' || can.testAccess" class="btn-default mt-2 w-full text-xs" @click="download(p)"><Download class="size-3.5" />下载{{ PART_LABEL[p] }}</button>
                </template>
                <p v-else class="mt-1 text-sm text-gray-500">尚未上传<RouterLink v-if="can.createDataset" :to="`/datasets/new?dataset=${ds.id}&part=${p}`" class="ml-1 text-brand-600 hover:underline">去上传</RouterLink></p>
              </div>
            </div>
            <div class="card p-4">
              <h3 class="mb-2 text-sm font-semibold">labels.csv 表头</h3>
              <pre class="mono overflow-x-auto rounded-lg bg-gray-900 p-2.5 text-xs text-gray-100">{{ ds.train.columns.join(',') }}</pre>
              <p class="mt-2 text-xs text-gray-500">{{ spec?.desc }}。训练集与测试集表头一致。</p>
            </div>
            <div class="card p-4">
              <h3 class="mb-2 text-sm font-semibold">类别（{{ ds.classes.length }}）</h3>
              <div class="flex flex-wrap gap-1.5"><span v-for="c in ds.classes" :key="c" class="chip">{{ c }}</span></div>
            </div>
            <div class="card p-4">
              <div class="mb-2 flex items-center gap-2"><Trophy class="size-4 text-amber-500" /><h3 class="text-sm font-semibold">使用此测试集的评测基准</h3></div>
              <p v-if="!benches.length" class="text-sm text-gray-500">暂无</p>
              <RouterLink v-for="b in benches" :key="b.id" :to="`/benchmarks/${b.id}`" class="block rounded-lg px-2 py-1.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-800">
                {{ b.displayName }} <span class="text-xs text-gray-500">· 测试集 {{ b.datasetVersion }}</span>
              </RouterLink>
              <RouterLink v-if="can.createBenchmark && ds.test" :to="`/benchmarks/new?dataset=${ds.id}`" class="btn-default mt-2 w-full text-xs">基于此测试集新建评测基准</RouterLink>
            </div>
          </aside>
        </div>

        <!-- ========== 训练集 / 测试集 ========== -->
        <div v-else-if="tab === 'train' || tab === 'test'">
          <div v-if="!part" class="flex flex-col items-center gap-2 rounded-xl border border-dashed border-gray-200 py-16 text-center dark:border-gray-800">
            <p class="font-medium">尚未上传{{ PART_LABEL[partName] }}</p>
            <RouterLink v-if="can.createDataset" :to="`/datasets/new?dataset=${ds.id}&part=${partName}`" class="btn-primary mt-2"><Upload class="size-4" />上传{{ PART_LABEL[partName] }}</RouterLink>
          </div>

          <!-- 非管理员查看测试集：只给统计 -->
          <div v-else-if="locked" class="flex flex-col items-center gap-2 rounded-xl border border-dashed border-amber-300 bg-amber-50/50 px-6 py-16 text-center dark:border-amber-800 dark:bg-amber-900/10">
            <Lock class="size-8 text-amber-500" />
            <p class="font-medium text-gray-900 dark:text-white">测试集内容仅管理员可见</p>
            <p class="max-w-md text-sm text-gray-600 dark:text-gray-400">当前版本 {{ part.versions[0].version }} 共 {{ fmtNum(part.versions[0].files) }} 个文件。<template v-if="isSeriesTask(ds.task)">评测时算法只拿到 series/ 下的输入窗口，labels.csv 真值留在评测器内计算指标。</template><template v-else>评测时算法容器只读取 images/，labels.csv 留在平台侧计算指标。</template></p>
            <RouterLink v-if="can.runEval && benches.length" :to="'/evals/new?bench=' + benches[0].id" class="btn-default mt-2"><FlaskConical class="size-4" />在评测基准上发起评测</RouterLink>
          </div>

          <template v-else>
            <div class="mb-4 flex flex-wrap items-center gap-2">
              <select v-model="version" class="input w-auto" aria-label="选择版本">
                <option v-for="v in part.versions" :key="v.version" :value="v.version">{{ v.version }}{{ v === part.versions[0] ? '（最新）' : '' }}</option>
              </select>
              <span class="chip">{{ fmtNum(ver?.files ?? 0) }} 个文件</span>
              <span class="chip">{{ fmtNum(ver?.rows ?? 0) }} 行标注</span>
              <span class="chip">{{ fmtBytes(ver?.sizeBytes ?? 0) }}</span>
              <HashText v-if="ver" :value="ver.contentHash" />
              <span v-if="partName === 'test'" class="chip border-amber-300 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-300"><Lock class="size-3" />仅管理员可见</span>
              <div class="ml-auto flex gap-2">
                <RouterLink v-if="can.createDataset" :to="`/datasets/new?dataset=${ds.id}&part=${partName}`" class="btn-default"><Upload class="size-4" />上传新版本</RouterLink>
                <button class="btn-primary" @click="download(partName)"><Download class="size-4" />下载</button>
              </div>
            </div>

            <div class="grid gap-6 lg:grid-cols-[1fr_300px]">
              <div class="min-w-0">
                <div class="mb-2 flex items-center justify-between">
                  <h2 class="text-sm font-semibold">labels.csv <span class="font-normal text-gray-500">· 前 {{ csvRows.length }} 行，共 {{ fmtNum(ver?.rows ?? 0) }} 行</span></h2>
                </div>
                <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                  <table class="table-base mono text-xs">
                    <thead><tr><th v-for="h in part.columns" :key="h">{{ h }}</th></tr></thead>
                    <tbody>
                      <tr v-for="(r, i) in csvRows" :key="i" class="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900" @click="zoom = r.idx">
                        <td v-for="(c, j) in r.row" :key="j" class="whitespace-nowrap" :class="!c ? 'text-gray-300 dark:text-gray-600' : ''">{{ c || '∅' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div v-if="Object.keys(part.classCounts).length">
                <h2 class="mb-2 text-sm font-semibold">类别分布</h2>
                <div class="space-y-1.5">
                  <div v-for="(n, c) in part.classCounts" :key="c" class="grid grid-cols-[96px_1fr_52px] items-center gap-2 text-xs">
                    <span class="truncate" :title="String(c)">{{ c }}</span>
                    <div class="h-2 rounded-r-[4px]" style="background: var(--series-1)" :style="{ width: Math.max(2, (n / classMax) * 100) + '%' }" />
                    <span class="mono text-right text-gray-500">{{ fmtNum(n) }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 服务器故障检测标准数据集：series/ 折线图预览 -->
            <template v-if="ds.task === SF_TASK">
              <h2 class="mt-8 mb-3 text-sm font-semibold">series/ 折线图预览 <span class="font-normal text-gray-500">· 浅红色背景为 Ground Truth 故障段，浅黄色为故障前 10 分钟预警段</span></h2>
              <SfSeriesPreview :dataset-id="ds.id" :part="partName" :rows="realRows" :max="36" />
            </template>
            <!-- 新能源功率预测标准数据集：series/ 48h 功率与气象折线图预览 -->
            <template v-else-if="ds.task === 'power-forecast'">
              <h2 class="mt-8 mb-3 text-sm font-semibold">series/ 功率时序折线图预览 <span class="font-normal text-gray-500">· 灰线为前一天 24h 实测，蓝线为次日 24h 真实功率（GT），紫色虚线为 NWP + 名义功率曲线基线</span></h2>
              <PfSeriesPreview :dataset-id="ds.id" :part="partName" :rows="realRows" :max="24" />
            </template>
            <p v-if="isSeriesTask(ds.task) && !realRows.length" class="mt-3 text-sm text-gray-500">时序样本需连接后端读取，当前无法预览。</p>
            <template v-else>
            <div class="mt-8 mb-3 flex items-center gap-3">
              <h2 class="text-sm font-semibold">images/ 预览</h2>
              <button class="btn-default py-1 text-xs" @click="showAnn = !showAnn"><component :is="showAnn ? Eye : EyeOff" class="size-3.5" />{{ showAnn ? '叠加标注' : '原图' }}</button>
              <span class="text-xs text-gray-500">点击查看该样本在 labels.csv 中的行</span>
            </div>
            <div v-if="isRealDataset && realRows.length" class="grid gap-2" :class="ds.task === 'ocr' ? 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4' : 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6'">
              <button
                v-for="(item, idx) in realRows.slice(0, count)"
                :key="item.file_name"
                class="group cursor-pointer overflow-hidden rounded-lg border border-gray-100 text-left dark:border-gray-800"
                @click="zoom = idx + 1"
              >
                <template v-if="ds.task === 'ocr'">
                  <div class="flex h-20 items-center justify-center bg-white p-2 dark:bg-gray-950">
                    <img :src="item.url" :alt="item.label" class="max-h-full max-w-full object-contain transition group-hover:opacity-90" loading="lazy" />
                  </div>
                  <div v-if="showAnn" class="mono truncate border-t border-gray-100 bg-gray-50 px-2 py-1 text-xs font-medium text-gray-800 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-200" :title="item.label">
                    GT: {{ item.label }}
                  </div>
                  <div class="mono truncate px-2 py-1 text-[11px] text-gray-400">{{ item.file_name.replace('images/', '') }}</div>
                </template>
                <template v-else>
                  <div class="relative overflow-hidden bg-gray-100 dark:bg-gray-900">
                    <img :src="item.url" :alt="item.label" class="block aspect-[4/3] w-full object-cover transition group-hover:opacity-90" loading="lazy" />
                    <span v-if="showAnn" class="pointer-events-none absolute top-1.5 left-1.5 max-w-[calc(100%-0.75rem)] truncate rounded bg-gray-900/75 px-1.5 py-0.5 text-[11px] font-medium text-white">{{ item.label }}</span>
                  </div>
                  <div class="mono truncate px-2 py-1 text-[11px] text-gray-500">{{ item.file_name.replace('images/', '') }}</div>
                </template>
              </button>
            </div>
            <div v-else class="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-6">
              <button v-for="i in count" :key="partName + version + i" class="group cursor-pointer overflow-hidden rounded-lg border border-gray-100 text-left dark:border-gray-800" @click="zoom = i">
                <SynthImage :seed="seedOf(i)" :task="ds.task" :classes="ds.classes" :sample-images="ds.sampleImages" :annotate="showAnn" :width="240" :height="180" class="transition group-hover:opacity-90" />
                <div class="mono truncate px-2 py-1 text-[11px] text-gray-500">{{ fileNameOf(partName, i, spec?.dataExt).replace('images/', '') }}</div>
              </button>
            </div>
            <div class="mt-6 text-center">
              <button v-if="count < (isRealDataset ? realRows.length : 72)" class="btn-default" @click="count += 18">加载更多</button>
            </div>
            </template>
          </template>
        </div>

        <!-- ========== 版本 ========== -->
        <div v-else class="space-y-8">
          <p class="text-sm text-gray-500">训练集与测试集分别发布、各自编号；版本不可变。评测基准绑定测试集的具体版本，保证结果可复现。</p>
          <section v-for="p in (['train', 'test'] as const)" :key="p">
            <div class="mb-2 flex items-center gap-2">
              <h2 class="section-title flex items-center gap-1.5">{{ PART_LABEL[p] }}<Lock v-if="p === 'test'" class="size-4 text-amber-500" /></h2>
              <RouterLink v-if="can.createDataset" :to="`/datasets/new?dataset=${ds.id}&part=${p}`" class="btn-default ml-auto text-xs"><Upload class="size-3.5" />上传新版本</RouterLink>
            </div>
            <p v-if="!ds[p]" class="text-sm text-gray-500">尚未上传</p>
            <div v-else class="card overflow-x-auto">
              <table class="table-base">
                <thead><tr><th>版本</th><th>说明</th><th>文件 / 标注行</th><th>内容哈希</th><th>大小</th><th>发布</th><th v-if="p === 'test'">被评测基准引用</th></tr></thead>
                <tbody>
                  <tr v-for="v in ds[p]!.versions" :key="v.version">
                    <td class="mono font-medium">{{ v.version }}</td>
                    <td>{{ v.note }}</td>
                    <td class="whitespace-nowrap">{{ fmtNum(v.files) }} / {{ fmtNum(v.rows) }}</td>
                    <td><HashText :value="v.contentHash" /></td>
                    <td class="whitespace-nowrap">{{ fmtBytes(v.sizeBytes) }}</td>
                    <td class="whitespace-nowrap text-gray-500">{{ v.createdBy }} · {{ timeAgo(v.createdAt) }}</td>
                    <td v-if="p === 'test'">
                      <RouterLink v-for="b in benches.filter((x) => x.datasetVersion === v.version)" :key="b.id" :to="`/benchmarks/${b.id}`" class="chip mr-1 hover:border-gray-400"><Trophy class="size-3" />{{ b.name }}</RouterLink>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>

      <Modal v-model:open="zoomOpen" :title="zoomReal ? zoomReal.file_name : zoom !== null ? fileNameOf(partName, zoom, spec?.dataExt) : ''" :width="isSeriesTask(ds.task) ? 'max-w-5xl' : 'max-w-3xl'">
        <div v-if="zoom !== null && part" class="space-y-4">
          <SeriesSampleView v-if="isSeriesTask(ds.task) && zoomReal" :dataset-id="ds.id" :part="partName" :file-name="zoomReal.file_name" :task="ds.task" />
          <p v-else-if="isSeriesTask(ds.task)" class="text-sm text-gray-500">时序样本需连接后端读取，当前无法预览。</p>
          <div v-else class="overflow-hidden rounded-lg" :class="ds.task === 'ocr' ? 'flex min-h-[120px] items-center justify-center border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-950' : 'bg-gray-100 dark:bg-gray-900'">
            <img v-if="zoomReal" :src="zoomReal.url" :alt="zoomReal.label" class="mx-auto max-h-[60vh] w-auto object-contain" />
            <SynthImage v-else :seed="seedOf(zoom)" :task="ds.task" :classes="ds.classes" :sample-images="ds.sampleImages" annotate :width="960" :height="540" />
          </div>
          <div>
            <p class="mb-1 text-xs font-medium text-gray-500">labels.csv 中对应的 {{ zoomRows.length }} 行</p>
            <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
              <table class="table-base mono text-xs">
                <thead><tr><th v-for="h in part.columns" :key="h">{{ h }}</th></tr></thead>
                <tbody>
                  <tr v-for="(r, i) in zoomRows" :key="i"><td v-for="(c, j) in r" :key="j" class="whitespace-nowrap" :class="!c ? 'text-gray-300 dark:text-gray-600' : ''">{{ c || '∅' }}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </Modal>
      <Modal v-model:open="deleteOpen" :title="`删除数据集 · ${ds.id}`" :description="`确认删除数据集「${ds.id}」？${benches.length ? `同时会移除关联的 ${benches.length} 个评测基准及对应评测记录，` : ''}此操作无法撤销。`">
        <template #footer>
          <button type="button" class="btn-default" @click="deleteOpen = false">取消</button>
          <button type="button" class="btn-danger" :disabled="deleting" @click="doDelete">{{ deleting ? '删除中…' : '确认删除' }}</button>
        </template>
      </Modal>
      <EditDatasetModal v-model:open="editOpen" :ds="ds" @saved="ds = $event" />
    </template>
  </StateView>
</template>
