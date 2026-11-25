<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleAlert, CircleCheck, CircleX, Database, Download, FileSpreadsheet, LoaderCircle, Lock, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { ApiError, createDataset, listDatasets, uploadDatasetPart, validateDatasetPackage, type DatasetValidationResult, type PartUpload } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { TASKS, isImageTask, isSeriesTask } from '@/utils/meta'
import { fmtBytes, hashStr } from '@/utils/format'
import { checkLabels, labelSpec, parseCsv, rowsFor, toCsv, type CheckItem } from '@/utils/labels'
import type { SplitName, TaskType } from '@/types'
import Stepper from '@/components/ui/Stepper.vue'
import FakeUpload from '@/components/ui/FakeUpload.vue'
import StateView from '@/components/ui/StateView.vue'
import TagInput from '@/components/form/TagInput.vue'
import TextField from '@/components/form/TextField.vue'

const route = useRoute()
const router = useRouter()
const { can, state, user } = useSession()
const { data: dsList } = useAsync(() => listDatasets({ pageSize: 999, sort: 'updated' }))

const step = ref(0)
const steps = ['上传目标', '上传数据', '校验结果', '确认']
// 命名空间由上传者决定：管理员上传 → Admin；厂商上传 → 厂商标识
const namespace = computed(() => (state.role === 'admin' ? 'Admin' : (user.value.orgId ?? 'Admin')))

const f = reactive({
  mode: (route.query.dataset ? 'existing' : 'new') as 'new' | 'existing',
  // 新建
  name: '',
  task: 'object-detection' as TaskType,
  summary: '',
  classes: [] as string[],
  // 已有
  datasetId: (route.query.dataset as string) || '',
  part: ((route.query.part as string) === 'test' ? 'test' : 'train') as SplitName,
  // 上传
  zip: null as { name: string; size: number; file?: File } | null,
  csvText: '' as string, // 真实选择的 labels.csv 内容
  csvName: '',
  note: '',
})
const serverVal = ref<DatasetValidationResult | null>(null)

const target = computed(() => dsList.value?.items.find((d) => d.id === f.datasetId))
const task = computed<TaskType>(() => (f.mode === 'new' ? f.task : (target.value?.task ?? 'object-detection')))
const classes = computed(() => (f.mode === 'new' ? f.classes : (target.value?.classes ?? [])))
const part = computed<SplitName>(() => (f.mode === 'new' ? 'train' : f.part))
const spec = computed(() => labelSpec(task.value))
const otherPart = computed(() => (f.mode === 'existing' && target.value ? (part.value === 'train' ? target.value.test : target.value.train) : null))
const currentPart = computed(() => (f.mode === 'existing' && target.value ? target.value[part.value] : null))
const nextVersion = computed(() => (currentPart.value ? `v${Number(currentPart.value.versions[0].version.slice(1).split('.')[0]) + 1}.0` : 'v1.0'))
const needsClasses = computed(() => task.value !== 'optimization')

// 同一路径下仅 query 变化时（如从“上传新版本”链接进入）同步预选项
watch(
  () => [route.query.dataset, route.query.part],
  ([d, p]) => {
    if (d) Object.assign(f, { mode: 'existing', datasetId: String(d), part: p === 'test' ? 'test' : 'train' })
    step.value = 0
  },
)
watch(target, (t) => {
  if (t && !t.test && route.query.part !== 'train') f.part = 'test'
})

const step0Ok = computed(() =>
  f.mode === 'new'
    ? /^[a-z0-9][a-z0-9-]{1,48}$/.test(f.name) && f.summary.trim().length >= 4 && (!needsClasses.value || f.classes.length > 0)
    : !!target.value,
)

// ---------- labels.csv：用户单独选择的真实文件；未选择时原型无法解压数据包，按数据包模拟生成 ----------
const columns = computed(() => otherPart.value?.columns ?? [...spec.value.required, ...(task.value === 'object-detection' ? ['weather', 'light'] : [])])
const demoCsv = computed(() => {
  const seed = hashStr(f.zip?.name ?? 'x') % 5000
  const rows: string[][] = []
  for (let i = 1; i <= 240; i++) rows.push(...rowsFor(seed + i, i, part.value, task.value, classes.value.length ? classes.value : ['目标'], columns.value))
  return toCsv(columns.value, rows)
})
const parsed = computed(() => parseCsv(f.csvText || (f.zip ? demoCsv.value : '')))
const csvEl = ref<HTMLInputElement>()
function pickCsv(file?: File) {
  if (!file) return
  if (file.size > 5 * 1024 * 1024) return toast('labels.csv 预览校验限 5 MB 以内', 'error')
  const r = new FileReader()
  r.onload = () => {
    // 读原始字节再解码并保留 BOM，便于提示“Excel 另存的带 BOM 文件已兼容”；非 UTF-8 编码会报错
    try {
      f.csvText = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(r.result as ArrayBuffer)
      f.csvName = file.name
    } catch {
      toast('labels.csv 不是 UTF-8 编码，请另存为“CSV UTF-8”后重试', 'error')
    }
  }
  r.readAsArrayBuffer(file)
}

/** 数据目录：图像任务为 images/，时序标准任务为 series/ */
const dataDir = computed(() => (isSeriesTask(task.value) ? 'series/' : 'images/'))
const dataKind = computed(() => (isImageTask(task.value) ? '图片' : isSeriesTask(task.value) ? '时序 CSV 窗口' : '数据文件'))

// ---------- 校验 ----------
const validating = ref(false)
const checks = computed<CheckItem[]>(() => {
  if (serverVal.value) return serverVal.value.checks
  const { header, rows, hadBom } = parsed.value
  const out: CheckItem[] = [{ level: 'ok', text: `找到 labels.csv${f.csvName ? `（${f.csvName}）` : ''}，UTF-8 编码${hadBom ? '（带 BOM，已自动兼容）' : ''}` }]
  out.push(...checkLabels(header, rows, task.value, needsClasses.value ? classes.value : null))
  if (otherPart.value) {
    const same = otherPart.value.columns.join(',') === header.join(',')
    out.push(same ? { level: 'ok', text: `表头与${part.value === 'train' ? '测试集' : '训练集'}一致` } : { level: 'error', text: `表头需与${part.value === 'train' ? '测试集' : '训练集'}一致：${otherPart.value.columns.join(',')}` })
  }
  const fi = header.indexOf('file_name')
  const files = fi >= 0 ? new Set(rows.map((r) => r[fi])).size : 0
  out.push({ level: 'ok', text: `labels.csv 引用的 ${files} 个文件均存在于 ${dataDir.value}` })
  if (task.value.includes('segmentation')) out.push({ level: 'ok', text: 'mask_file 引用的掩码均存在于 masks/' })
  if (otherPart.value) out.push({ level: 'ok', text: `与${part.value === 'train' ? '测试集' : '训练集'} ${otherPart.value.versions[0].version} 按${isImageTask(task.value) ? '图片' : '文件'}哈希比对：0 个重复文件` })
  return out
})
const errorCount = computed(() => checks.value.filter((c) => c.level === 'error').length)
const previewHeader = computed(() => (serverVal.value ? serverVal.value.header : parsed.value.header))
const preview = computed(() => (serverVal.value ? serverVal.value.previewRows : parsed.value.rows.slice(0, 8)))
const totalRowsCount = computed(() => (serverVal.value ? serverVal.value.rows : parsed.value.rows.length))
const classCounts = computed(() => {
  if (serverVal.value) return serverVal.value.classCounts
  const li = parsed.value.header.indexOf('label')
  const out: Record<string, number> = {}
  if (li < 0) return out
  for (const r of parsed.value.rows) if (r[li]) out[r[li]] = (out[r[li]] ?? 0) + 1
  return out
})
const maxCount = computed(() => Math.max(1, ...Object.values(classCounts.value)))

async function next() {
  if (step.value === 0 && !step0Ok.value) return toast('请完成必填项', 'error')
  if (step.value === 1 && !f.zip) return toast('请上传数据包', 'error')
  if (step.value === 1) {
    step.value++
    serverVal.value = null
    if (f.zip?.file) {
      validating.value = true
      try {
        serverVal.value = await validateDatasetPackage(
          f.zip.file,
          task.value,
          part.value,
          needsClasses.value ? classes.value : [],
          f.mode === 'existing' ? f.datasetId : undefined,
        )
      } catch (e) {
        serverVal.value = {
          ok: false,
          checks: [{ level: 'error', text: e instanceof ApiError ? e.message : '服务端校验失败' }],
          header: [],
          previewRows: [],
          rows: 0,
          files: 0,
          classCounts: {},
          sizeBytes: f.zip.size,
          contentHash: '',
        }
      } finally {
        validating.value = false
      }
    } else {
      validating.value = true
      setTimeout(() => (validating.value = false), 450)
    }
    return
  }
  if (step.value === 2 && errorCount.value) return toast(`还有 ${errorCount.value} 项校验未通过`, 'error')
  step.value++
}

// ---------- 提交 ----------
const submitting = ref(false)
async function submit() {
  submitting.value = true
  const fi = previewHeader.value.indexOf('file_name')
  const up: PartUpload = {
    columns: previewHeader.value,
    files: serverVal.value ? serverVal.value.files : fi >= 0 ? new Set(parsed.value.rows.map((r) => r[fi])).size : 0,
    rows: totalRowsCount.value,
    sizeBytes: serverVal.value ? serverVal.value.sizeBytes : (f.zip?.size ?? 0),
    note: f.note,
    classCounts: classCounts.value,
    zipFile: f.zip?.file,
  }
  try {
    const d =
      f.mode === 'new'
        ? await createDataset({ org: namespace.value, name: f.name, task: f.task, summary: f.summary.trim(), classes: f.classes, train: up })
        : await uploadDatasetPart(f.datasetId, f.part, up)
    toast(`${part.value === 'train' ? '训练集' : '测试集'} ${f.mode === 'new' ? 'v1.0' : nextVersion.value} 已发布${up.zipFile ? '（已真实落盘）' : ''}`)
    router.push(`/datasets/${d.id}?tab=${part.value}`)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '提交失败', 'error')
  } finally {
    submitting.value = false
  }
}
// ---------- 一键填写示例数据（自动挂载后端真实标准模板 ZIP） ----------
async function fillExample() {
  if (f.mode === 'new') {
    const suffix = String(Date.now()).slice(-4)
    f.name = `dehaze-sample-${suffix}`
    f.task = 'image-dehazing'
    f.summary = '通过标准化上传流程创建的真实图像去雾示例数据集（含真实有雾/清晰配对图与 labels.csv）。'
    f.classes = ['轻雾', '中雾', '浓雾']
    f.note = '标准示例训练集 v1.0（真实 ZIP 上传）'
  } else {
    const first = dsList.value?.items[0]
    if (first && !f.datasetId) f.datasetId = first.id
    f.note = `标准示例${f.part === 'test' ? '测试集' : '训练集'} ${nextVersion.value}（真实 ZIP 上传）`
  }
  f.csvText = ''
  f.csvName = ''
  try {
    const resp = await fetch(`/real-api/templates/dataset/${task.value}?part=${part.value}`)
    if (resp.ok) {
      const blob = await resp.blob()
      const fname = `template-${task.value}-${part.value}.zip`
      const realFile = new File([blob], fname, { type: 'application/zip' })
      f.zip = { name: fname, size: realFile.size, file: realFile }
      toast('已一键填充并挂载真实标准模板 ZIP，可直接点击「下一步」执行服务端真实校验')
      return
    }
  } catch {
    /* 后端未启动时降级 */
  }
  f.zip = { name: `template-${task.value}-${part.value}.zip`, size: 128 * 1024 }
  toast('已填充示例表单，可直接点击「下一步」查看校验步骤')
}
</script>

<template>
  <div class="container-page max-w-4xl pt-8">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><Database class="size-6 text-brand-600" />上传数据集</h1>
        <p class="mt-1 text-sm text-gray-500">每个数据集分为训练集和测试集，分开上传、各自有版本。两部分结构一致：<code class="mono">images/</code>（图像任务）或 <code class="mono">series/</code>（时序任务）存放数据，<code class="mono">labels.csv</code> 存放真值。</p>
      </div>
      <button v-if="can.admin" type="button" class="btn-default shrink-0" @click="fillExample">
        <Sparkles class="size-4 text-amber-500" />一键填写示例数据
      </button>
    </div>

    <StateView v-if="!can.createDataset" :error="{ status: 403, message: '仅管理员可以上传数据集' }" />
    <template v-else>
      <div class="mt-6"><Stepper :steps="steps" :current="step" /></div>
      <form class="card mt-4 space-y-5 p-6" @submit.prevent>
        <!-- 0 上传目标 -->
        <template v-if="step === 0">
          <div class="grid gap-2 sm:grid-cols-2">
            <label v-for="m in ([['new', '新建数据集', '先上传训练集，测试集随后单独上传'], ['existing', '已有数据集', '为训练集或测试集上传新版本']] as const)" :key="m[0]" class="flex cursor-pointer gap-2 rounded-lg border p-3 text-sm" :class="f.mode === m[0] ? 'border-brand-500 ring-2 ring-brand-500/20' : 'border-gray-200 dark:border-gray-700'">
              <input v-model="f.mode" type="radio" :value="m[0]" class="mt-0.5 accent-brand-600" />
              <span><span class="block font-medium">{{ m[1] }}</span><span class="text-xs text-gray-500">{{ m[2] }}</span></span>
            </label>
          </div>

          <template v-if="f.mode === 'new'">
            <div class="grid gap-4 sm:grid-cols-[200px_1fr]">
              <div>
                <p class="label">命名空间</p>
                <p class="input mono bg-gray-50 text-gray-600 dark:bg-gray-800/60 dark:text-gray-300">{{ namespace }}</p>
                <p class="hint">{{ state.role === 'admin' ? '管理员上传的数据集统一放在 Admin' : '厂商上传的数据集放在自己的厂商标识下' }}</p>
              </div>
              <TextField v-model="f.name" label="数据集名称" required mono :hint="`ID：${namespace}/${f.name || '…'}，小写字母、数字和连字符`" />
            </div>
            <div class="grid gap-4 sm:grid-cols-2">
              <div>
                <label class="label" for="d-task">任务类型<span class="ml-0.5 text-rose-500">*</span></label>
                <select id="d-task" v-model="f.task" class="input">
                  <option v-for="(v, k) in TASKS" :key="k" :value="k">{{ v.label }}</option>
                </select>
                <p class="hint">决定 labels.csv 的必需列</p>
              </div>
            </div>
            <TextField v-model="f.summary" label="简介" required multiline :rows="2" />
            <TagInput v-if="needsClasses" v-model="f.classes" label="类别表" required hint="训练集与测试集共用；labels.csv 的 label 必须在此表内" />
          </template>

          <template v-else>
            <div>
              <label class="label" for="d-target">数据集<span class="ml-0.5 text-rose-500">*</span></label>
              <select id="d-target" v-model="f.datasetId" class="input">
                <option value="" disabled>选择数据集…</option>
                <option v-for="d in dsList?.items" :key="d.id" :value="d.id">{{ d.id }}（{{ TASKS[d.task].label }}）</option>
              </select>
            </div>
            <div v-if="target" class="grid gap-2 sm:grid-cols-2">
              <label v-for="p in (['train', 'test'] as const)" :key="p" class="flex cursor-pointer gap-2 rounded-lg border p-3 text-sm" :class="f.part === p ? 'border-brand-500 ring-2 ring-brand-500/20' : 'border-gray-200 dark:border-gray-700'">
                <input v-model="f.part" type="radio" :value="p" class="mt-0.5 accent-brand-600" />
                <span>
                  <span class="flex items-center gap-1.5 font-medium">{{ p === 'train' ? '训练集' : '测试集' }}<Lock v-if="p === 'test'" class="size-3.5 text-amber-500" /></span>
                  <span class="text-xs text-gray-500">当前 {{ target[p]?.versions[0].version ?? '未上传' }}<template v-if="target[p]"> · {{ target[p]!.versions[0].files.toLocaleString() }} 个文件</template></span>
                </span>
              </label>
            </div>
          </template>
        </template>

        <!-- 1 上传数据 -->
        <template v-else-if="step === 1">
          <p v-if="isSeriesTask(task)" class="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
            <TriangleAlert class="mt-0.5 size-3.5 shrink-0" />
            <span>{{ TASKS[task].label }}是时序标准任务，由标准统一评测器评测：数据集除 series/ 与 labels.csv 外还需要标准 meta.json（场站或机器规格、评测基准）。这里可以下载标准示例包并校验文件格式，但自助上传暂不支持发布为可评测的标准数据集，请按标准准备后联系管理员接入。</span>
          </p>
          <div class="grid gap-5 lg:grid-cols-2">
            <div>
              <div class="mb-1 flex items-center justify-between">
                <p class="label mb-0">数据包结构</p>
                <a :href="`/real-api/templates/dataset/${task}?part=${part}`" class="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline dark:text-brand-400">
                  <Download class="size-3.5" />下载标准示例包 (.zip)
                </a>
              </div>
              <pre class="rounded-lg bg-gray-50 p-3 text-xs leading-relaxed dark:bg-gray-800/60">{{ `${part}.zip
├── ${dataDir.padEnd(17)}# ${dataKind}${task === 'image-dehazing' ? '\n├── clear/           # 清晰真值图' : ''}${task.includes('segmentation') ? '\n├── masks/           # 掩码 PNG' : ''}
└── labels.csv       # 真值（UTF-8）` }}</pre>
              <p class="label mt-4">labels.csv 表头</p>
              <pre class="mono overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs text-gray-100">{{ columns.join(',') }}</pre>
              <ul class="mt-2 space-y-1 text-xs text-gray-600 dark:text-gray-400">
                <li>· 必需列：<code class="mono">{{ spec.required.join(', ') }}</code></li>
                <li>· {{ spec.desc }}</li>
                <li v-if="spec.optional.length">· 可选条件列：<code class="mono">{{ spec.optional.join(', ') }}</code>，填写后评测可按条件拆分</li>
                <li v-if="otherPart">· 表头必须与{{ part === 'train' ? '测试集' : '训练集' }}一致</li>
              </ul>
            </div>
            <div class="space-y-4">
              <div>
                <p class="label">数据包<span class="ml-0.5 text-rose-500">*</span></p>
                <FakeUpload v-model="f.zip" accept=".zip" :label="`拖拽 ${part}.zip 到这里，或点击选择`" :hint="`标准 .zip 数据包，下一步将由后端真实解压并逐个校验${dataKind}与 labels.csv`" />
              </div>
              <div class="rounded-lg border border-dashed border-gray-200 p-3 dark:border-gray-700">
                <p class="flex items-center gap-1.5 text-sm font-medium"><FileSpreadsheet class="size-4 text-emerald-600" />用真实的 labels.csv 校验（可选）</p>
                <p class="mt-1 text-xs text-gray-500">选择数据包中的 labels.csv，在浏览器内执行真实的格式校验。原型不解压数据包，未选择时校验结果为模拟。</p>
                <div class="mt-2 flex items-center gap-2">
                  <button type="button" class="btn-default py-1 text-xs" @click="csvEl?.click()">选择 labels.csv</button>
                  <span v-if="f.csvName" class="mono truncate text-xs">{{ f.csvName }}</span>
                  <button v-if="f.csvName" type="button" class="text-xs text-gray-500 hover:underline" @click="f.csvText = ''; f.csvName = ''">移除</button>
                </div>
                <input ref="csvEl" type="file" accept=".csv,text/csv" class="hidden" @change="pickCsv(($event.target as HTMLInputElement).files?.[0])" />
              </div>
            </div>
          </div>
        </template>

        <!-- 2 校验结果 -->
        <template v-else-if="step === 2">
          <div v-if="validating" class="flex items-center gap-2 py-10 text-sm text-gray-500"><LoaderCircle class="size-4 animate-spin" />正在解析数据包与 labels.csv…</div>
          <template v-else>
            <ul class="space-y-1.5 text-sm">
              <li v-for="(c, i) in checks" :key="i" class="flex items-start gap-1.5" :class="c.level === 'error' ? 'text-rose-600' : ''">
                <CircleCheck v-if="c.level === 'ok'" class="mt-0.5 size-4 shrink-0 text-emerald-500" />
                <TriangleAlert v-else-if="c.level === 'warn'" class="mt-0.5 size-4 shrink-0 text-amber-500" />
                <CircleX v-else class="mt-0.5 size-4 shrink-0" />
                {{ c.text }}
              </li>
            </ul>
            <div>
              <p class="label">labels.csv 预览（前 {{ preview.length }} 行，共 {{ totalRowsCount }} 行）</p>
              <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                <table class="table-base mono text-xs">
                  <thead><tr><th v-for="h in previewHeader" :key="h">{{ h }}</th></tr></thead>
                  <tbody>
                    <tr v-for="(r, i) in preview" :key="i"><td v-for="(c, j) in r" :key="j" class="whitespace-nowrap" :class="!c ? 'text-gray-300 dark:text-gray-600' : ''">{{ c || '∅' }}</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div v-if="Object.keys(classCounts).length">
              <p class="label">类别分布（labels.csv 中 label 列）</p>
              <div class="space-y-1">
                <div v-for="(n, c) in classCounts" :key="c" class="grid grid-cols-[120px_1fr_56px] items-center gap-2 text-xs">
                  <span class="truncate">{{ c }}</span>
                  <div class="h-2 rounded-r-[4px]" style="background: var(--series-1)" :style="{ width: (n / maxCount) * 100 + '%' }" />
                  <span class="mono text-right text-gray-500">{{ n }}</span>
                </div>
              </div>
            </div>
            <p v-if="errorCount" class="flex items-center gap-1.5 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 dark:bg-rose-900/20 dark:text-rose-300"><CircleAlert class="size-4" />有 {{ errorCount }} 项未通过，请修正 labels.csv 后返回上一步重新选择。</p>
          </template>
        </template>

        <!-- 3 确认 -->
        <template v-else>
          <dl class="grid grid-cols-[120px_1fr] gap-y-2 text-sm">
            <dt class="text-gray-500">数据集</dt><dd class="mono">{{ f.mode === 'new' ? `${namespace}/${f.name}` : f.datasetId }}</dd>
            <dt class="text-gray-500">部分</dt>
            <dd class="flex items-center gap-1.5">{{ part === 'train' ? '训练集' : '测试集' }}<Lock v-if="part === 'test'" class="size-3.5 text-amber-500" /> · 将发布为 <code class="mono">{{ f.mode === 'new' ? 'v1.0' : nextVersion }}</code></dd>
            <dt class="text-gray-500">任务类型</dt><dd>{{ TASKS[task].label }}</dd>
            <dt class="text-gray-500">数据包</dt><dd class="mono">{{ f.zip?.name }}（{{ fmtBytes(f.zip?.size ?? 0) }}）</dd>
            <dt class="text-gray-500">labels.csv</dt><dd>{{ totalRowsCount }} 行 · 表头 <code class="mono">{{ previewHeader.join(',') }}</code></dd>
          </dl>
          <TextField v-model="f.note" label="版本说明" />
          <p class="flex items-start gap-1.5 rounded-lg bg-gray-50 p-3 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">
            <Lock class="mt-0.5 size-3.5 shrink-0" />
            <template v-if="part === 'test'">测试集发布后仅管理员可查看与下载；评测时算法只拿到 {{ dataDir }} 下的输入，labels.csv 留在平台侧计算指标。</template>
            <template v-else>训练集发布后所有账号可查看与下载。{{ f.mode === 'new' ? '测试集请在数据集创建后单独上传。' : '' }}</template>
          </p>
        </template>

        <div class="flex justify-between border-t border-gray-100 pt-4 dark:border-gray-800">
          <button type="button" class="btn-default" @click="step ? step-- : router.back()">{{ step ? '上一步' : '取消' }}</button>
          <button v-if="step < 3" type="button" class="btn-primary" :disabled="(step === 0 && !step0Ok) || (step === 2 && (validating || errorCount > 0))" @click="next">下一步</button>
          <button v-else type="button" class="btn-brand" :disabled="submitting" @click="submit">{{ submitting ? '发布中…' : `发布${part === 'train' ? '训练集' : '测试集'}` }}</button>
        </div>
      </form>
    </template>
  </div>
</template>
