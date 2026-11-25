/**
 * API 服务层 —— 目前全部由本地 mock 实现。
 * 函数签名与返回结构按将来的 FastAPI REST 接口设计（注释中标注了对应路由），
 * 接入真实后端时只需把函数体替换为 fetch 调用。
 */
import { reactive, watch } from 'vue'
import type {
  Algorithm,
  AlgorithmDispatch,
  AlgoVersion,
  Benchmark,
  BusinessCategory,
  Dataset,
  EvalRun,
  Evaluator,
  InferenceResult,
  ListQuery,
  Org,
  Paginated,
  QueueStatus,
  RegionName,
  RegionTrialRequest,
  Role,
  TaskType,
  TrialRequestStatus,
  User,
  VendorProfile,
  DatasetPart,
  DatasetVersion,
  SplitName,
  AlgoDeclaration,
} from '@/types'
import { algorithms as A0 } from '@/mock/algorithms'
import { datasets as D0 } from '@/mock/datasets'
import { benchmarks as B0 } from '@/mock/benchmarks'
import { evalRuns as E0 } from '@/mock/evals'
import { evaluators as EV0 } from '@/mock/evaluators'
import { orgs as O0, users as U0 } from '@/mock/orgs'
import realBootstrapSnapshot from '@/mock/realBootstrapSnapshot.json'
import { useSession } from '@/stores/session'
import { fakeSha, hashStr, rng } from '@/utils/format'
import { algoFullLabel } from '@/utils/display'
import { REGIONS } from '@/utils/meta'

// ---------- 原型数据持久化 ----------
// 写操作（新建厂商、上传数据集、编辑信息等）保存到浏览器 localStorage，刷新后仍在。
// 恢复时就地替换 mock 数组的内容，直接引用 mock 的组件（如头像、基准名称）也能看到最新数据。
const STORE_KEY = 'algohub-db-v6'
const TAG_CLEAN_KEY = 'algohub-tags-cleaned-v1'
const DISPATCH_ALL_KEY = 'algohub-dispatch-all-v1'
const DISPATCH_ALL_REAL_KEY = 'algohub-dispatch-all-real-v3'
const DEFAULT_TAGS = ['真实部署', '基线算法', '高精度', '实时推理', '边缘端', '新能源场站', '可见光巡检', '表计读数', '状态识别']
const LEGACY_NOISY_TAGS = new Set([
  '猫狗识别', '图像分类', '安防周界', '图像去雾', '传统物理先验', '暗通道', 'CPU',
  '轻量物理CNN', '注意力CNN', '特征融合', '现代强基线', '细节增强',
  '随机基线', '全任务通用', '对照实验', 'DCP', 'AOD-Net', 'FFA-Net', 'DEA-Net',
  '红色LED数显', '避雷器电流表与放电计数', '柱状压板状态', 'GIS汇控状态灯', '旋钮档位', '主变油位',
])
const T0: string[] = [...DEFAULT_TAGS]
const DEL0: string[] = []
const DISP0: AlgorithmDispatch[] = A0.flatMap((a) =>
  REGIONS.map((region) => ({
    algorithmId: a.id,
    region,
    dispatchedAt: '2026-11-24T12:00:00+08:00',
    dispatchedBy: 'admin',
    source: 'direct' as const,
  })),
)
const TRIAL0: RegionTrialRequest[] = []
const SOURCES = { algorithms: A0, datasets: D0, benchmarks: B0, evals: E0, evaluators: EV0, orgs: O0, users: U0, tags: T0, deletedRealIds: DEL0, dispatches: DISP0, trialRequests: TRIAL0 }
type DbKey = keyof typeof SOURCES
try {
  const saved = JSON.parse(localStorage.getItem(STORE_KEY) ?? 'null') as Partial<Record<DbKey, unknown[]>> | null
  if (saved) {
    for (const k of Object.keys(SOURCES) as DbKey[]) if (Array.isArray(saved[k])) (SOURCES[k] as unknown[]).splice(0, SOURCES[k].length, ...saved[k]!)
  }
} catch {
  /* 数据损坏或不可用时使用默认 mock */
}
// 一次性精简历史冗余标签（清理与任务分类/算法名重复的旧标签）
try {
  if (!localStorage.getItem(TAG_CLEAN_KEY)) {
    const defaultById = new Map(A0.map((a) => [a.id, a.tags]))
    for (const a of SOURCES.algorithms) {
      if (defaultById.has(a.id)) a.tags = [...defaultById.get(a.id)!]
      else a.tags = a.tags.filter((t) => !LEGACY_NOISY_TAGS.has(t))
    }
    const kept = SOURCES.tags.filter((t) => !LEGACY_NOISY_TAGS.has(t))
    SOURCES.tags.splice(0, SOURCES.tags.length, ...new Set([...DEFAULT_TAGS, ...kept]))
    localStorage.setItem(TAG_CLEAN_KEY, '1')
  }
} catch {
  /* ignore */
}
// 兼容旧版 localStorage 数据：补齐缺失的 business 字段、自研标识、标签库与区域侧演示账号
const DEFAULT_SELF_DEVELOPED_IDS = new Set(['Admin/cat-dog-classifier', 'Admin/dehaze-dcp'])
for (const a of SOURCES.algorithms) {
  if (!a.business) a.business = 'inspection'
  if (!Array.isArray(a.files)) a.files = []
  if (a.selfDeveloped === undefined && DEFAULT_SELF_DEVELOPED_IDS.has(a.id)) a.selfDeveloped = true
  for (const v of a.versions ?? []) {
    if (v.gpuMem === undefined) v.gpuMem = a.id === 'Admin/power-dlinear' ? 0.1 : 1
    if (!Array.isArray(v.buildLog)) v.buildLog = []
    if (!v.baseImage) v.baseImage = 'pytorch/pytorch:2.4.1-cuda12.4-cudnn9-runtime'
    if (v.weightsSize === undefined) v.weightsSize = a.id === 'Admin/power-dlinear' ? 97346 : 0
  }
  if (a.id === 'Admin/power-dlinear' && a.files.length === 0) {
    a.files = [
      { path: 'power_dlinear.py', size: 9420, kind: 'code' },
      { path: 'weights/v1.0.0_power_dlinear.pt', size: 97346, kind: 'weights' },
      { path: 'algo.yaml', size: 486, kind: 'config' },
      { path: 'README.md', size: 960, kind: 'doc' },
    ]
    if (!a.algoYaml) {
      a.algoYaml = `name: power-dlinear\nversion: v1.0.0\ntask: power-forecast\nbusiness: production\nframework: PyTorch\nentrypoint: power_dlinear.py:predict\n`
    }
  }
}
for (const t of SOURCES.algorithms.flatMap((a) => a.tags)) if (t && !SOURCES.tags.includes(t)) SOURCES.tags.push(t)

/** 将给定算法列表全量授权至全部 14 区域，并清理重复待审批记录 */
function ensureAllRegionsDispatched(algos: Algorithm[], dispatches: AlgorithmDispatch[], trials: RegionTrialRequest[]) {
  const existing = new Set(dispatches.map((d) => `${d.algorithmId}::${d.region}`))
  const now = '2026-11-24T12:00:00+08:00'
  for (const a of algos) {
    for (const region of REGIONS) {
      const key = `${a.id}::${region}`
      if (!existing.has(key)) {
        dispatches.push({ algorithmId: a.id, region, dispatchedAt: now, dispatchedBy: 'admin', source: 'direct' })
        existing.add(key)
      }
    }
  }
  for (let i = trials.length - 1; i >= 0; i--) {
    if (trials[i].status === 'pending' && existing.has(`${trials[i].algorithmId}::${trials[i].region}`)) {
      trials.splice(i, 1)
    }
  }
}

// 一次性迁移：为全部 14 区域全量授权所有算法
try {
  if (!localStorage.getItem(DISPATCH_ALL_KEY)) {
    ensureAllRegionsDispatched(SOURCES.algorithms, SOURCES.dispatches, SOURCES.trialRequests)
    localStorage.setItem(DISPATCH_ALL_KEY, '1')
  }
} catch {
  /* ignore */
}
const regionalUser = SOURCES.users.find((u) => u.id === 'u4')
if (!regionalUser) {
  SOURCES.users.splice(1, 0, { id: 'u4', username: 'regional', displayName: '华中区域账号', email: 'huazhong@algohub.local', role: 'regional', orgId: null, region: '华中', active: true, createdAt: '2026-11-20T15:25:00+08:00', lastLoginAt: '' })
} else {
  if (!regionalUser.region) regionalUser.region = '华中'
  if (regionalUser.displayName === '区域侧账号') regionalUser.displayName = '华中区域账号'
}

/**
 * 将算法的任务分类、业务分类、推理框架、标签与简介同步更新到 algo.yaml，
 * 仅原地更新配置字段，不改动 version 字段，也不触发新版本发布。
 */
function syncAlgoYaml(a: Pick<Algorithm, 'algoYaml' | 'task' | 'business' | 'framework' | 'tags' | 'summary'>): string {
  const lines = (a.algoYaml ?? '').replace(/\r\n/g, '\n').trimEnd().split('\n').filter((l, _i, arr) => !(arr.length === 1 && l === ''))

  const setScalar = (key: string, val: string, afterKeys: string[]) => {
    const idx = lines.findIndex((l) => new RegExp(`^${key}:`).test(l))
    const line = `${key}: ${val}`
    if (idx >= 0) {
      lines[idx] = line
      return
    }
    let insertAt = -1
    for (const ak of afterKeys) {
      const i = lines.findIndex((l) => new RegExp(`^${ak}:`).test(l))
      if (i >= 0) {
        insertAt = i + 1
        break
      }
    }
    if (insertAt >= 0) lines.splice(insertAt, 0, line)
    else lines.push(line)
  }

  const setList = (key: string, items: string[], afterKeys: string[]) => {
    const start = lines.findIndex((l) => new RegExp(`^${key}:`).test(l))
    if (start >= 0) {
      let end = start + 1
      while (end < lines.length && /^\s+-\s/.test(lines[end])) end++
      lines.splice(start, end - start)
    }
    if (!items.length) return
    const block = [`${key}:`, ...items.map((x) => `  - ${x}`)]
    if (start >= 0) {
      lines.splice(start, 0, ...block)
      return
    }
    let insertAt = -1
    for (const ak of afterKeys) {
      const i = lines.findIndex((l) => new RegExp(`^${ak}:`).test(l))
      if (i >= 0) {
        insertAt = i + 1
        break
      }
    }
    if (insertAt >= 0) lines.splice(insertAt, 0, ...block)
    else lines.push(...block)
  }

  setScalar('task', a.task, ['version', 'name'])
  setScalar('business', a.business, ['task', 'version', 'name'])
  setScalar('framework', a.framework, ['business', 'task', 'version'])
  setList('tags', a.tags, ['framework', 'business', 'task'])
  if (a.summary) {
    const safeSummary = /[:#\n"']/.test(a.summary) ? JSON.stringify(a.summary) : a.summary
    setScalar('summary', safeSummary, ['name'])
  }
  return lines.join('\n') + '\n'
}

// 用 reactive 包一层，使 mock “写操作” 能实时反映到页面上
const db = reactive(SOURCES)

// ---------- 真实后端同步（猫狗、图像去雾、时序功率预测数据集/算法/评测与随机基线完全走 FastAPI + PyTorch） ----------
const REAL_ALGO_ID = 'Admin/cat-dog-classifier'
const REAL_DEHAZE_IDS = new Set(['Admin/dehaze-dcp', 'Admin/dehaze-aodnet', 'Admin/dehaze-ffanet', 'Admin/dehaze-deanet'])
const REAL_POWER_ALGO_ID = 'Admin/power-dlinear'
const REAL_0X6E_ALGO_ID = 'Admin/0x6E'
const REAL_RANDOM_ID = 'Admin/random'
const REAL_0X07_ALGO_ID = 'Admin/0x07' // 服务器故障检测标准算法
const REAL_ALGO_IDS = new Set([REAL_ALGO_ID, ...REAL_DEHAZE_IDS, REAL_POWER_ALGO_ID, REAL_0X6E_ALGO_ID, REAL_0X07_ALGO_ID, REAL_RANDOM_ID])
const LEGACY_REAL_ALGO_IDS = new Set(['Admin/dehaze'])
const REAL_DS_ID = 'Admin/cat-dog-dataset'
const REAL_DEHAZE_DS_ID = 'Admin/dehaze-dataset'
const REAL_OCR_DS_ID = 'Admin/sroie-ocr-dataset'
const REAL_POWER_DS_ID = 'Admin/wind-solar-power-dataset'
const REAL_0X07_DS_ID = 'Admin/0x07-server-telemetry-dataset' // 服务器故障检测标准数据集
const REAL_0X6E_DS_ID = 'Admin/0x6E-server-telemetry'
export const REAL_DS_IDS = new Set([REAL_DS_ID, REAL_DEHAZE_DS_ID, REAL_OCR_DS_ID, REAL_POWER_DS_ID, REAL_0X6E_DS_ID, REAL_0X07_DS_ID])
const REAL_BENCH_ID = 'cat-dog-cls-bench'
const REAL_DEHAZE_BENCH_ID = 'dehaze-bench'
const REAL_POWER_BENCH_ID = 'power-forecast-bench'
const REAL_0X07_BENCH_ID = '0x07-server-fault-bench' // 服务器故障检测标准基准
const REAL_0X6E_BENCH_ID = '0x6E-server-fault-bench'
const REAL_BENCH_IDS = new Set([REAL_BENCH_ID, REAL_DEHAZE_BENCH_ID, REAL_POWER_BENCH_ID, REAL_0X6E_BENCH_ID, REAL_0X07_BENCH_ID])

let realSynced = false
let realBackendAvailable = false
let realSyncPromise: Promise<void> | null = null
let realWarmContainers: QueueStatus['warmContainers'] = []

function applyRealBootstrap(payload: {
  algorithm: Algorithm
  algorithms?: Algorithm[]
  dataset: Dataset
  datasets?: Dataset[]
  benchmark: Benchmark
  benchmarks?: Benchmark[]
  evals: EvalRun[]
  realAlgoIds?: string[]
  realDatasetIds?: string[]
  realBenchmarkIds?: string[]
  warmContainers?: QueueStatus['warmContainers']
}) {
  if (payload.realAlgoIds) for (const id of payload.realAlgoIds) REAL_ALGO_IDS.add(id)
  if (payload.realDatasetIds) for (const id of payload.realDatasetIds) REAL_DS_IDS.add(id)
  if (payload.realBenchmarkIds) for (const id of payload.realBenchmarkIds) REAL_BENCH_IDS.add(id)

  const incoming = payload.algorithms?.length ? payload.algorithms : [payload.algorithm]
  for (const algo of incoming) {
    if (db.deletedRealIds.includes(algo.id)) continue
    const ai = db.algorithms.findIndex((a) => a.id === algo.id)
    if (ai >= 0) {
      const prev = db.algorithms[ai]
      // 服务器故障检测标准算法：任务类型与卡片（含跨数据集标准评测结果表）以后端为准，旧缓存不能覆盖
      const isStd = algo.task === 'server-fault'
      const merged: Algorithm = {
        ...algo,
        task: isStd ? algo.task : prev.task || algo.task,
        business: prev.business || algo.business,
        framework: prev.framework || algo.framework,
        selfDeveloped: prev.selfDeveloped ?? algo.selfDeveloped ?? DEFAULT_SELF_DEVELOPED_IDS.has(algo.id),
        tags: algo.tags.length ? algo.tags : prev.tags,
        summary: isStd ? algo.summary : prev.summary || algo.summary,
        readme: isStd ? algo.readme : prev.readme || algo.readme,
      }
      merged.algoYaml = syncAlgoYaml(merged)
      db.algorithms[ai] = merged
      for (const t of merged.tags) if (t && !db.tags.includes(t)) db.tags.push(t)
    } else {
      if (algo.selfDeveloped === undefined && DEFAULT_SELF_DEVELOPED_IDS.has(algo.id)) algo.selfDeveloped = true
      algo.algoYaml = syncAlgoYaml(algo)
      db.algorithms.unshift(algo)
      for (const t of algo.tags) if (t && !db.tags.includes(t)) db.tags.push(t)
    }
  }

  const incomingDs = payload.datasets?.length ? payload.datasets : [payload.dataset]
  for (const ds of incomingDs) {
    if (db.deletedRealIds.includes(ds.id)) continue
    const di = db.datasets.findIndex((d) => d.id === ds.id)
    if (di >= 0) db.datasets[di] = ds
    else db.datasets.unshift(ds)
  }

  const incomingBenches = payload.benchmarks?.length ? payload.benchmarks : [payload.benchmark]
  for (const bench of incomingBenches) {
    if (db.deletedRealIds.includes(bench.datasetId) || db.deletedRealIds.includes(bench.id)) continue
    const bi = db.benchmarks.findIndex((b) => b.id === bench.id)
    if (bi >= 0) db.benchmarks[bi] = bench
    else db.benchmarks.unshift(bench)
  }

  // 清理已拆分的旧版合并算法缓存（如 Admin/dehaze）
  for (let i = db.algorithms.length - 1; i >= 0; i--) {
    if (LEGACY_REAL_ALGO_IDS.has(db.algorithms[i].id)) db.algorithms.splice(i, 1)
  }

  // 用真实后端评测记录替换真实算法的评测记录（跳过已被删除的算法/基准）
  for (let i = db.evals.length - 1; i >= 0; i--) {
    if (REAL_ALGO_IDS.has(db.evals[i].algorithmId) || LEGACY_REAL_ALGO_IDS.has(db.evals[i].algorithmId)) db.evals.splice(i, 1)
  }
  const activeEvals = payload.evals.filter((e) => !db.deletedRealIds.includes(e.algorithmId) && !db.deletedRealIds.includes(e.benchmarkId))
  db.evals.unshift(...activeEvals)
  pruneUnusedTags()
  // 真实后端算法同步后，同步补齐 14 区域全量授权（一次性迁移）
  try {
    if (!localStorage.getItem(DISPATCH_ALL_REAL_KEY)) {
      ensureAllRegionsDispatched(db.algorithms, db.dispatches, db.trialRequests)
      localStorage.setItem(DISPATCH_ALL_REAL_KEY, '1')
    }
  } catch {
    /* ignore */
  }
  if (payload.warmContainers) realWarmContainers = payload.warmContainers
}

async function syncRealBackend(force = false): Promise<void> {
  if (realSynced && !force) return
  if (realSyncPromise && !force) return realSyncPromise
  realSyncPromise = (async () => {
    try {
      const resp = await fetch('/real-api/bootstrap')
      if (!resp.ok) throw new Error('real backend unavailable')
      const payload = await resp.json()
      applyRealBootstrap(payload)
      realBackendAvailable = true
      realSynced = true
    } catch {
      /* 后端未启动或纯静态部署时，回退到内置的后端数据快照 */
      realBackendAvailable = false
      if (!realSynced) {
        applyRealBootstrap(realBootstrapSnapshot as unknown as Parameters<typeof applyRealBootstrap>[0])
        realSynced = true
      }
    } finally {
      realSyncPromise = null
    }
  })()
  return realSyncPromise
}

export interface RealDatasetRow {
  file_name: string
  label: string
  url: string
  row?: string[]
}

export async function getRealDatasetPart(
  datasetId: string,
  part: SplitName,
  limit = 200,
): Promise<{ part: SplitName; columns: string[]; total: number; rows: RealDatasetRow[] } | null> {
  try {
    const resp = await fetch(`/real-api/datasets/${datasetId}/part/${part}?limit=${limit}`)
    if (!resp.ok) return null
    return await resp.json()
  } catch {
    return null
  }
}

let saveTimer: ReturnType<typeof setTimeout> | undefined
watch(
  db,
  () => {
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      try {
        localStorage.setItem(STORE_KEY, JSON.stringify(db))
      } catch {
        /* 存储不可用时仅在内存中生效 */
      }
    }, 300)
  },
  { deep: true },
)

/** 管理后台：清除本地修改，恢复初始演示数据 */
export function resetPrototypeData() {
  try {
    localStorage.removeItem(STORE_KEY)
    localStorage.removeItem(DISPATCH_ALL_KEY)
    localStorage.removeItem(DISPATCH_ALL_REAL_KEY)
  } catch {
    /* ignore */
  }
  location.reload()
}

const delay = (ms = 220) => new Promise((r) => setTimeout(r, ms + Math.random() * 120))
const clone = <T>(x: T): T => JSON.parse(JSON.stringify(x))

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

/** 可见性：算法按身份过滤（厂商只见自己的），数据集对所有人可见 */
function visible<T extends Algorithm | Dataset>(list: T[]): T[] {
  const { canSeeAlgo } = useSession()
  return list.filter((x) => !('framework' in x) || canSeeAlgo(x))
}

function paginate<T>(list: T[], q: ListQuery): Paginated<T> {
  const page = q.page ?? 1
  const pageSize = q.pageSize ?? 12
  return { items: list.slice((page - 1) * pageSize, page * pageSize), total: list.length, page, pageSize }
}

function filterSort<T extends Algorithm | Dataset>(list: T[], q: ListQuery): T[] {
  let r = visible(list)
  if (q.q) {
    const k = q.q.toLowerCase()
    r = r.filter(
      (x) =>
        x.id.toLowerCase().includes(k) ||
        ('framework' in x && algoFullLabel(x).toLowerCase().includes(k)) ||
        x.summary.includes(q.q!) ||
        x.tags.some((t) => t.toLowerCase().includes(k)),
    )
  }
  if (q.task) r = r.filter((x) => x.task === q.task)
  if (q.business) r = r.filter((x) => 'business' in x && x.business === q.business)
  if (q.selfDeveloped === 'only') r = r.filter((x) => 'framework' in x && !!x.selfDeveloped)
  else if (q.selfDeveloped === 'external') r = r.filter((x) => 'framework' in x && !x.selfDeveloped)
  if (q.tags?.length) r = r.filter((x) => q.tags!.every((tag) => x.tags.includes(tag)))
  if (q.org) r = r.filter((x) => x.org === q.org)
  if (q.framework) r = r.filter((x) => 'framework' in x && x.framework === q.framework)
  const sort = q.sort ?? 'trending'
  r = [...r].sort((a, b) => {
    if (sort === 'updated') return b.updatedAt.localeCompare(a.updatedAt)
    if (sort === 'likes') return b.likes - a.likes
    if (sort === 'evals') return ('evalCount' in b ? b.evalCount : 0) - ('evalCount' in a ? a.evalCount : 0)
    // trending：点赞 + 新鲜度
    const score = (x: T) => x.likes * 0.6 + (new Date(x.updatedAt).getTime() / 86400000) * 4
    return score(b) - score(a)
  })
  return r
}

// ============ 算法  GET /api/algorithms ============
export async function listAlgorithms(q: ListQuery = {}): Promise<Paginated<Algorithm>> {
  await syncRealBackend()
  await delay()
  return clone(paginate(filterSort(db.algorithms, q), q))
}

// GET /api/algorithms/{org}/{name}
export async function getAlgorithm(id: string): Promise<Algorithm> {
  await syncRealBackend(REAL_ALGO_IDS.has(id))
  await delay()
  const a = db.algorithms.find((x) => x.id === id)
  if (!a) throw new ApiError(404, '算法不存在')
  if (!useSession().canSeeAlgo(a)) throw new ApiError(403, '无权访问该算法')
  return clone(a)
}

// POST /api/algorithms
export async function createAlgorithm(input: {
  org: string
  name: string
  task: TaskType
  business: BusinessCategory
  framework: Algorithm['framework']
  summary: string
  version: string
  gpuMem: number
  weightsSize: number
  readme?: string
  tags?: string[]
  files?: Algorithm['files']
  declaration?: AlgoDeclaration
}): Promise<Algorithm> {
  await delay(600)
  const { can, user } = useSession()
  const id = `${input.org}/${input.name}`
  if (db.algorithms.some((a) => a.id === id)) throw new ApiError(409, '同名算法已存在')
  const status: AlgoVersion['status'] = can.value.needsReview ? 'pending_review' : 'building'
  const tags = [...new Set((input.tags ?? (can.value.needsReview ? ['厂商提交'] : ['新提交'])).map((t) => t.trim()).filter(Boolean))]
  for (const t of tags) if (!db.tags.includes(t)) db.tags.push(t)
  const algo: Algorithm = {
    id,
    org: input.org,
    name: input.name,
    task: input.task,
    business: input.business,
    framework: input.framework,
    tags,
    summary: input.summary,
    declaration: input.declaration,
    readme: input.readme ?? `# ${input.name}\n\n${input.summary}\n\n> 由 ${user.value.displayName} 创建，README 可在提交后编辑。`,
    likes: 0,
    evalCount: 0,
    updatedAt: new Date().toISOString(),
    labels: ['目标'],
    algoYaml: `name: ${input.name}\nversion: ${input.version}\ntask: ${input.task}\nentry: predictor:Predictor\nresources:\n  gpu_mem: ${input.gpuMem}GB\n`,
    files: input.files ?? [
      { path: 'algo.yaml', size: 400, kind: 'config' },
      { path: 'predictor.py', size: 2000, kind: 'code' },
    ],
    versions: [
      {
        version: `v${input.version}`,
        status,
        createdAt: new Date().toISOString(),
        createdBy: user.value.username,
        changelog: '首次发布',
        weightsHash: 'sha256:' + fakeSha(id),
        weightsSize: input.weightsSize,
        baseImage: 'algohub/pytorch:2.4-cuda12.1',
        gpuMem: input.gpuMem,
        buildLog: status === 'pending_review' ? ['[review] 厂商提交，等待管理员审核后开始构建'] : ['[build] 已进入构建队列'],
      },
    ],
  }
  db.algorithms.unshift(algo)
  return clone(algo)
}

// ============ 数据集  GET /api/datasets ============
export async function listDatasets(q: ListQuery = {}): Promise<Paginated<Dataset>> {
  await syncRealBackend()
  await delay()
  return clone(paginate(filterSort(db.datasets, q), q))
}

export async function getDataset(id: string): Promise<Dataset> {
  await syncRealBackend(REAL_DS_IDS.has(id))
  await delay()
  const d = db.datasets.find((x) => x.id === id)
  if (!d) throw new ApiError(404, '数据集不存在')
  return clone(d)
}

export interface PartUpload {
  columns: string[]
  files: number
  rows: number
  sizeBytes: number
  note: string
  classCounts: Record<string, number>
  zipFile?: File
}

export interface DatasetValidationResult {
  ok: boolean
  checks: { level: 'ok' | 'warn' | 'error'; text: string }[]
  header: string[]
  previewRows: string[][]
  rows: number
  files: number
  classCounts: Record<string, number>
  sizeBytes: number
  contentHash: string
}

export async function validateDatasetPackage(
  zipFile: File,
  task: TaskType,
  part: SplitName,
  classes: string[],
  datasetId?: string,
): Promise<DatasetValidationResult> {
  const fd = new FormData()
  fd.append('zip_file', zipFile, zipFile.name)
  fd.append('task', task)
  fd.append('part', part)
  fd.append('classes_json', JSON.stringify(classes))
  if (datasetId) fd.append('dataset_id', datasetId)
  const resp = await fetch('/real-api/datasets/validate', { method: 'POST', body: fd })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '服务端数据集校验失败' }))
    throw new ApiError(resp.status, err.detail || '服务端数据集校验失败')
  }
  return await resp.json()
}

export interface AlgoValidationResult {
  ok: boolean
  checks: { level: 'ok' | 'warn' | 'error'; text: string }[]
  smokeLatencyMs?: number
  smokeOutput?: unknown
  files?: { path: string; size: number; kind: 'code' | 'config' | 'weights' | 'doc' }[]
  weightsSize?: number
  weightsHash?: string
}

export async function validateAlgorithmPackage(file: File, task: TaskType): Promise<AlgoValidationResult> {
  const fd = new FormData()
  fd.append('task', task)
  fd.append('package_file', file, file.name)
  const resp = await fetch('/real-api/algorithms/validate', { method: 'POST', body: fd })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '算法包校验失败' }))
    throw new ApiError(resp.status, err.detail || '算法包校验失败')
  }
  return await resp.json()
}

export async function uploadRealAlgorithm(
  meta: {
    org: string
    name: string
    displayName: string
    task: TaskType
    business: BusinessCategory
    framework: Algorithm['framework']
    version: string
    tags: string[]
    summary: string
    changelog: string
    gpuMem: number
    labels?: string[]
    declaration?: AlgoDeclaration
  },
  packageFile: File,
): Promise<Algorithm> {
  const { user, state } = useSession()
  const fd = new FormData()
  fd.append('metadata_json', JSON.stringify(meta))
  fd.append('created_by', user.value.username)
  fd.append('role', state.role)
  fd.append('package_file', packageFile, packageFile.name)
  const resp = await fetch('/real-api/algorithms', { method: 'POST', body: fd })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '算法包上传失败' }))
    throw new ApiError(resp.status, err.detail || '算法包上传失败')
  }
  const algo = (await resp.json()) as Algorithm
  REAL_ALGO_IDS.add(algo.id)
  const idx = db.algorithms.findIndex((a) => a.id === algo.id)
  if (idx >= 0) db.algorithms[idx] = algo
  else db.algorithms.unshift(algo)
  return clone(algo)
}

function newVersion(prev: DatasetPart | null, up: PartUpload, seed: string): DatasetVersion {
  const n = prev ? Number(prev.versions[0].version.slice(1).split('.')[0]) + 1 : 1
  return {
    version: `v${n}.0`,
    createdAt: new Date().toISOString(),
    createdBy: useSession().user.value.username,
    contentHash: 'sha256:' + fakeSha(seed + n),
    sizeBytes: up.sizeBytes,
    note: up.note || (n === 1 ? '首个版本' : '更新'),
    files: up.files,
    rows: up.rows,
  }
}

// POST /api/datasets —— 新建数据集时先上传训练集；测试集随后单独上传（有真实 zipFile 时直接落盘后端）
export async function createDataset(input: Pick<Dataset, 'org' | 'name' | 'task' | 'summary' | 'classes'> & { train: PartUpload }): Promise<Dataset> {
  if (!useSession().can.value.createDataset) throw new ApiError(403, '仅管理员可以上传数据集')
  if (input.train.zipFile) {
    const fd = new FormData()
    fd.append('org', input.org)
    fd.append('name', input.name)
    fd.append('task', input.task)
    fd.append('summary', input.summary)
    fd.append('classes_json', JSON.stringify(input.classes))
    fd.append('note', input.train.note || '首个版本')
    fd.append('created_by', useSession().user.value.username)
    fd.append('zip_file', input.train.zipFile, input.train.zipFile.name)
    const resp = await fetch('/real-api/datasets', { method: 'POST', body: fd })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '真实数据集上传失败' }))
      throw new ApiError(resp.status, err.detail || '真实数据集上传失败')
    }
    const d = (await resp.json()) as Dataset
    REAL_DS_IDS.add(d.id)
    const idx = db.datasets.findIndex((x) => x.id === d.id)
    if (idx >= 0) db.datasets[idx] = d
    else db.datasets.unshift(d)
    return clone(d)
  }
  await delay(600)
  const id = `${input.org}/${input.name}`
  if (db.datasets.some((d) => d.id === id)) throw new ApiError(409, '同名数据集已存在')
  const { train, ...meta } = input
  const fence = '```'
  const d: Dataset = {
    ...meta,
    id,
    tags: ['新上传'],
    readme: `# ${input.name}\n\n${input.summary}\n\n## labels.csv\n\n${fence}\n${train.columns.join(',')}\n${fence}\n`,
    train: { name: 'train', columns: train.columns, versions: [newVersion(null, train, id + 'train')], classCounts: train.classCounts },
    test: null,
    likes: 0,
    downloads: 0,
    updatedAt: new Date().toISOString(),
    previewSeed: hashStr(id) % 5000,
  }
  db.datasets.unshift(d)
  return clone(d)
}

// POST /api/datasets/{id}/{part}/versions —— 上传训练集或测试集的新版本（有真实 zipFile 时直接落盘后端）
export async function uploadDatasetPart(id: string, partName: SplitName, up: PartUpload): Promise<Dataset> {
  if (!useSession().can.value.createDataset) throw new ApiError(403, '仅管理员可以上传数据')
  if (up.zipFile && REAL_DS_IDS.has(id)) {
    const fd = new FormData()
    fd.append('note', up.note || '增量更新')
    fd.append('created_by', useSession().user.value.username)
    fd.append('zip_file', up.zipFile, up.zipFile.name)
    const resp = await fetch(`/real-api/datasets/${id}/${partName}`, { method: 'POST', body: fd })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '真实分片上传失败' }))
      throw new ApiError(resp.status, err.detail || '真实分片上传失败')
    }
    const d = (await resp.json()) as Dataset
    const idx = db.datasets.findIndex((x) => x.id === d.id)
    if (idx >= 0) db.datasets[idx] = d
    else db.datasets.unshift(d)
    return clone(d)
  }
  await delay(600)
  const d = db.datasets.find((x) => x.id === id)
  if (!d) throw new ApiError(404, '数据集不存在')
  const prev = d[partName]
  const other = partName === 'train' ? d.test : d.train
  if (other && other.columns.join(',') !== up.columns.join(',')) throw new ApiError(400, `labels.csv 表头需与${partName === 'train' ? '测试集' : '训练集'}一致：${other.columns.join(',')}`)
  const v = newVersion(prev, up, id + partName)
  if (prev) {
    prev.versions.unshift(v)
    prev.classCounts = up.classCounts
  } else d[partName] = { name: partName, columns: up.columns, versions: [v], classCounts: up.classCounts }
  d.updatedAt = v.createdAt
  return clone(d)
}

// ============ Benchmark ============
export async function listBenchmarks(q: { task?: TaskType | ''; q?: string } = {}): Promise<Benchmark[]> {
  await syncRealBackend()
  await delay()
  return clone(
    db.benchmarks.filter((b) => {
      if (q.task && b.task !== q.task) return false
      if (q.q && !(b.displayName.includes(q.q) || b.name.includes(q.q.toLowerCase()))) return false
      return true
    }),
  )
}

export async function getBenchmark(id: string): Promise<Benchmark> {
  await syncRealBackend(REAL_BENCH_IDS.has(id))
  await delay()
  const b = db.benchmarks.find((x) => x.id === id)
  if (!b) throw new ApiError(404, 'Benchmark 不存在')
  return clone(b)
}

export async function createBenchmark(
  input: Omit<Benchmark, 'id' | 'createdAt' | 'split'> & { evaluatorScript?: File },
): Promise<Benchmark> {
  if (REAL_DS_IDS.has(input.datasetId)) {
    const { evaluatorScript, ...meta } = input
    const fd = new FormData()
    fd.append('metadata_json', JSON.stringify(meta))
    if (evaluatorScript) fd.append('evaluator_script', evaluatorScript, evaluatorScript.name)
    const resp = await fetch('/real-api/benchmarks', { method: 'POST', body: fd })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '真实评测基准创建失败' }))
      throw new ApiError(resp.status, err.detail || '真实评测基准创建失败')
    }
    const b = (await resp.json()) as Benchmark
    REAL_BENCH_IDS.add(b.id)
    const idx = db.benchmarks.findIndex((x) => x.id === b.id)
    if (idx >= 0) db.benchmarks[idx] = b
    else db.benchmarks.unshift(b)
    return clone(b)
  }
  await delay(500)
  if (db.benchmarks.some((b) => b.name === input.name)) throw new ApiError(409, '同名 Benchmark 已存在')
  const { evaluatorScript: _, ...rest } = input
  const b: Benchmark = { ...rest, id: input.name, split: 'test', createdAt: new Date().toISOString() }
  db.benchmarks.unshift(b)
  return clone(b)
}

export interface LeaderboardRow {
  rank: number
  run: EvalRun
  algorithm: Pick<Algorithm, 'id' | 'org' | 'name' | 'framework'>
}

// GET /api/benchmarks/{id}/leaderboard —— 每个“算法版本”只取最新有效结果；
// 名次按全部上榜结果计算，厂商账号只返回自己的行（看得到自己的名次，看不到其他厂商）
export async function getLeaderboard(benchId: string): Promise<LeaderboardRow[]> {
  await syncRealBackend(REAL_BENCH_IDS.has(benchId))
  await delay()
  const b = db.benchmarks.find((x) => x.id === benchId)!
  const primary = b.metrics.find((m) => m.primary)!
  const { canSeeAlgo } = useSession()
  const rows = db.evals
    .filter((r) => r.benchmarkId === benchId && r.isLatestValid)
    .map((run) => ({ run, algorithm: db.algorithms.find((a) => a.id === run.algorithmId)! }))
    .filter((x) => x.algorithm)
    .sort((x, y) => (primary.higherIsBetter ? 1 : -1) * ((y.run.metrics[primary.key] ?? 0) - (x.run.metrics[primary.key] ?? 0)))
    .map((x, i) => ({ ...x, rank: i + 1 }))
    .filter((x) => canSeeAlgo(x.algorithm))
  return clone(rows.map((x) => ({ rank: x.rank, run: x.run, algorithm: { id: x.algorithm.id, org: x.algorithm.org, name: x.algorithm.name, framework: x.algorithm.framework } })))
}

// ============ 评测任务 ============
export async function listEvals(f: { algorithmId?: string; benchmarkId?: string; status?: string; mine?: boolean } = {}): Promise<EvalRun[]> {
  await syncRealBackend(true)
  await delay()
  const { canSeeAlgo, user } = useSession()
  return clone(
    db.evals
      .filter((r) => {
        const a = db.algorithms.find((x) => x.id === r.algorithmId)
        if (!a || !canSeeAlgo(a)) return false
        if (f.algorithmId && r.algorithmId !== f.algorithmId) return false
        if (f.benchmarkId && r.benchmarkId !== f.benchmarkId) return false
        if (f.status && r.status !== f.status) return false
        if (f.mine && r.submittedBy !== user.value.username) return false
        return true
      })
      .sort((a, b) => b.submittedAt.localeCompare(a.submittedAt)),
  )
}

export async function getEval(id: string): Promise<EvalRun> {
  if (id.startsWith('ev-real-') || id.startsWith('ev-dehaze-') || id.startsWith('ev-custom-') || id.startsWith('ev-power-') || id.startsWith('ev-sf-')) {
    await syncRealBackend(!realBackendAvailable)
    if (realBackendAvailable) {
      const resp = await fetch(`/real-api/evals/${encodeURIComponent(id)}`)
      if (resp.ok) {
        const live = (await resp.json()) as EvalRun
        const idx = db.evals.findIndex((x) => x.id === id)
        if (idx >= 0) db.evals[idx] = live
        else db.evals.unshift(live)
        return clone(live)
      }
    }
  }
  await syncRealBackend()
  await delay()
  const r = db.evals.find((x) => x.id === id)
  if (!r) throw new ApiError(404, '评测记录不存在')
  const a = db.algorithms.find((x) => x.id === r.algorithmId)
  if (a && !useSession().canSeeAlgo(a)) throw new ApiError(403, '无权查看该评测记录')
  return clone(r)
}

// POST /api/evals
export async function createEval(input: { algorithmId: string; algoVersion: string; benchmarkId: string; params: EvalRun['params'] }): Promise<EvalRun> {
  const { user, can, canSeeAlgo } = useSession()
  await syncRealBackend(!realBackendAvailable)
  const a = db.algorithms.find((x) => x.id === input.algorithmId)!
  if (!can.value.runEval || !canSeeAlgo(a)) throw new ApiError(403, '只能评测自己的算法')
  const v = a.versions.find((x) => x.version === input.algoVersion)!
  if (v.status !== 'ready') throw new ApiError(400, '该算法版本尚不可用（未通过构建或审核）')
  const b = db.benchmarks.find((x) => x.id === input.benchmarkId)!
  if (input.algorithmId !== REAL_RANDOM_ID && a.task !== b.task) throw new ApiError(400, '算法任务类型与 Benchmark 不匹配')

  // 所有真实后端算法（内置或自助上传）× 所有真实后端评测基准：统一走真实后端评测引擎
  if (realBackendAvailable && REAL_ALGO_IDS.has(input.algorithmId) && REAL_BENCH_IDS.has(input.benchmarkId)) {
    const resp = await fetch('/real-api/evals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...input, submittedBy: user.value.username }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '真实评测提交失败' }))
      throw new ApiError(resp.status, err.detail || '真实评测提交失败')
    }
    const run = (await resp.json()) as EvalRun
    db.evals.unshift(run)
    return clone(run)
  }

  // Admin/random 在其他任意任务基准上：立即生成对应指标结构的随机基线评测结果
  if (input.algorithmId === REAL_RANDOM_ID) {
    await delay(300)
    const now = new Date().toISOString()
    const metrics: Record<string, number> = {}
    for (const m of b.metrics) {
      metrics[m.key] = m.unit === '%' ? +(15 + Math.random() * 45).toFixed(2) : +(Math.random() * 100).toFixed(2)
    }
    for (const other of db.evals) {
      if (other.algorithmId === REAL_RANDOM_ID && other.algoVersion === input.algoVersion && other.benchmarkId === b.id) other.isLatestValid = false
    }
    const run: EvalRun = {
      id: `ev-rand-${1100 + db.evals.length}`,
      ...input,
      status: 'succeeded',
      progress: 100,
      submittedBy: user.value.username,
      submittedAt: now,
      startedAt: now,
      finishedAt: now,
      metrics,
      imageDigest: v.imageDigest ?? '',
      weightsHash: v.weightsHash ?? '',
      evaluatorVersion: b.evaluatorVersion,
      hardware: 'CPU · Python random',
      durationSec: 1,
      peakGpuMemGB: 0,
      latencyMs: 0.1,
      isLatestValid: true,
      logs: [`[runner] Admin/random 在 ${b.displayName}（${b.task}）上完成全随机基线评测`, `[evaluator] ${JSON.stringify(metrics)}`],
    }
    db.evals.unshift(run)
    return clone(run)
  }

  await delay(300)
  const id = `ev-${1100 + db.evals.length}`
  const now = new Date().toISOString()
  const run: EvalRun = {
    id,
    ...input,
    status: 'queued',
    progress: 10,
    submittedBy: user.value.username,
    submittedAt: now,
    metrics: {},
    imageDigest: v.imageDigest ?? '',
    weightsHash: v.weightsHash ?? '',
    evaluatorVersion: b.evaluatorVersion,
    hardware: 'NVIDIA RTX 4060 Laptop (8GB) · i9-13900H · CUDA 12.4',
    isLatestValid: false,
    logs: [`[scheduler] 任务入队，声明显存 ${v.gpuMem ?? 0} GB`, '[scheduler] 正在分配推理容器并挂载测试集…'],
  }
  db.evals.unshift(run)

  // 离线模拟模式下自动推进任务进度，避免永久停留在「排队中」
  setTimeout(() => {
    const target = db.evals.find((x) => x.id === id)
    if (!target || target.status !== 'queued') return
    target.status = 'running'
    target.startedAt = new Date().toISOString()
    target.progress = 55
    target.logs.push(`[runner] 加载 ${a.id}@${v.version}，开始在 ${b.datasetId}@${b.datasetVersion} 测试集上推理…`)
  }, 600)

  setTimeout(() => {
    const target = db.evals.find((x) => x.id === id)
    if (!target || target.status === 'canceled') return
    const seed = hashStr(`${a.id}:${v.version}:${b.id}:${db.evals.length}`)
    const r = rng(seed)
    const metrics: Record<string, number> = {}
    for (const m of b.metrics) {
      if (m.key === 'accuracy_rate') metrics[m.key] = +(74 + r() * 6).toFixed(2)
      else if (m.key === 'rmse') metrics[m.key] = +(20 + r() * 6).toFixed(2)
      else if (m.key === 'mae') metrics[m.key] = +(13 + r() * 4).toFixed(2)
      else metrics[m.key] = m.unit === '%' ? +(78 + r() * 16).toFixed(2) : +(22 + r() * 8).toFixed(2)
    }
    for (const other of db.evals) {
      if (other.id !== id && other.algorithmId === input.algorithmId && other.algoVersion === input.algoVersion && other.benchmarkId === b.id) {
        other.isLatestValid = false
      }
    }
    target.status = 'succeeded'
    target.progress = 100
    target.finishedAt = new Date().toISOString()
    target.metrics = metrics
    target.durationSec = 1.4
    target.peakGpuMemGB = Math.max(0.1, v.gpuMem ?? 0.1)
    target.latencyMs = 1.5
    target.isLatestValid = true
    target.logs.push(`[done] 评测完成：${JSON.stringify(metrics)}`)
  }, 1500)

  return clone(run)
}

export async function cancelEval(id: string): Promise<void> {
  await delay()
  const r = db.evals.find((x) => x.id === id)
  if (r && (r.status === 'queued' || r.status === 'running')) {
    r.status = 'canceled'
    r.logs.push('[scheduler] 用户取消任务')
  }
}

// GET /api/scheduler/status
export async function getQueueStatus(): Promise<QueueStatus> {
  await syncRealBackend()
  await delay(120)
  return {
    gpuName: 'RTX 4060 Laptop',
    gpuMemTotal: 8,
    gpuMemUsed: realWarmContainers.reduce((s, w) => s + w.memGB, 0),
    running: db.evals.filter((r) => r.status === 'running').length,
    queued: db.evals.filter((r) => r.status === 'queued').length,
    warmContainers: clone(realWarmContainers),
  }
}

// ============ 单图推理  POST /api/algorithms/{id}/infer ============
const PALETTE = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16', '#06b6d4', '#a855f7', '#eab308']

export async function infer(algorithmId: string, version: string, input: { dataUrl?: string; file?: File; fileName: string; size: number; task?: TaskType }): Promise<InferenceResult> {
  // Admin/random：走后端全任务随机推理（忽略输入，每次输出永远随机）
  if (realBackendAvailable && algorithmId === REAL_RANDOM_ID) {
    const fd = new FormData()
    fd.append('task', input.task ?? 'image-classification')
    const resp = await fetch(`/real-api/algorithms/${REAL_RANDOM_ID}/infer`, { method: 'POST', body: fd })
    if (!resp.ok) throw new ApiError(resp.status, '随机推理服务调用失败')
    return await resp.json()
  }
  // 所有真实后端算法（内置或自助上传）：统一走真实 PyTorch/NumPy 后端推理
  if (realBackendAvailable && REAL_ALGO_IDS.has(algorithmId)) {
    const fd = new FormData()
    fd.append('version', version)
    if (input.file) {
      fd.append('file', input.file, input.fileName)
    } else if (input.dataUrl?.startsWith('/real-api/')) {
      fd.append('sample_path', input.dataUrl)
    } else if (input.dataUrl) {
      const blob = await (await fetch(input.dataUrl)).blob()
      fd.append('file', blob, input.fileName)
    }
    const resp = await fetch(`/real-api/algorithms/${algorithmId}/infer`, { method: 'POST', body: fd })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: '真实推理服务调用失败' }))
      throw new ApiError(resp.status, err.detail || '真实推理服务调用失败')
    }
    return await resp.json()
  }
  const a = db.algorithms.find((x) => x.id === algorithmId)!
  const warm = false // 原型：每次推理按冷启动处理
  const queuedMs = warm ? 0 : 1800 // 冷启动
  await delay(warm ? 650 : 1500)
  const seed = hashStr((input.dataUrl ?? input.fileName).slice(-4096) + input.size + algorithmId + version)
  const r = rng(seed)
  const labels = a.labels?.length ? a.labels : ['目标']
  const base = { task: a.task, latencyMs: +(8 + r() * 40).toFixed(1), queuedMs, device: a.framework === 'NumPy' ? 'CPU' : 'cuda:0 (RTX 4060 Laptop)' }

  if (a.task === 'image-classification' || a.task === 'signal-processing') {
    const logits = labels.map(() => r() ** 3)
    const fname = input.fileName.toLowerCase()
    const hinted =
      (fname.includes('cat') ? labels.indexOf('猫') : -1) >= 0
        ? labels.indexOf('猫')
        : fname.includes('dog')
          ? labels.indexOf('狗')
          : -1
    const top = hinted >= 0 ? hinted : Math.floor(r() * labels.length)
    logits[top] += hinted >= 0 ? 18 : 2.5
    const sum = logits.reduce((s, x) => s + x, 0)
    const items = labels.map((l, i) => ({ label: l, score: logits[i] / sum })).sort((x, y) => y.score - x.score)
    return { ...base, classification: items.slice(0, 5), raw: { predictions: items.slice(0, 5).map((x) => ({ label: x.label, score: +x.score.toFixed(4) })) } }
  }
  if (a.task === 'object-detection' || a.task === 'keypoint-detection' || a.task === 'ocr') {
    const n = 3 + Math.floor(r() * 6)
    const dets = Array.from({ length: n }, () => {
      const w = 0.08 + r() * 0.28
      const h = 0.08 + r() * 0.3
      return { label: labels[Math.floor(r() * labels.length)], score: 0.35 + r() * 0.64, box: [r() * (1 - w), r() * (1 - h), w, h] as [number, number, number, number] }
    }).sort((x, y) => y.score - x.score)
    return { ...base, detections: dets, raw: { detections: dets.map((d) => ({ label: d.label, score: +d.score.toFixed(3), bbox_xywh_norm: d.box.map((v) => +v.toFixed(4)) })) } }
  }
  if (a.task === 'semantic-segmentation' || a.task === 'instance-segmentation') {
    const n = a.task === 'instance-segmentation' ? 8 + Math.floor(r() * 8) : 4 + Math.floor(r() * 3)
    const segs = Array.from({ length: n }, (_, i) => {
      const cx = 0.1 + r() * 0.8
      const cy = 0.1 + r() * 0.8
      const rad = a.task === 'instance-segmentation' ? 0.03 + r() * 0.05 : 0.12 + r() * 0.22
      const pts: [number, number][] = Array.from({ length: 14 }, (_, k) => {
        const ang = (k / 14) * Math.PI * 2
        const rr = rad * (0.7 + r() * 0.5)
        return [Math.min(1, Math.max(0, cx + Math.cos(ang) * rr)), Math.min(1, Math.max(0, cy + Math.sin(ang) * rr))]
      })
      const label = a.task === 'instance-segmentation' ? labels[0] : labels[(i + Math.floor(r() * 3)) % labels.length]
      return { label, color: PALETTE[(a.task === 'instance-segmentation' ? i : labels.indexOf(label)) % PALETTE.length], polygon: pts }
    })
    return { ...base, segments: segs, raw: { segments: segs.map((s) => ({ label: s.label, polygon_norm: s.polygon.map((p) => p.map((v) => +v.toFixed(3))) })) } }
  }
  // 自定义任务（如优化求解）：原样返回 JSON
  return {
    ...base,
    raw: { instance: input.fileName, objective: +(800 + r() * 400).toFixed(2), vehicles: 5 + Math.floor(r() * 6), gap_to_best_known: `${(r() * 3).toFixed(2)}%`, routes: [[0, 12, 7, 3, 0], [0, 5, 9, 14, 2, 0]] },
  }
}

// ============ 组织 / 用户 / 审核 ============
export async function listOrgs(): Promise<Org[]> {
  await delay(100)
  return clone(db.orgs)
}

export async function getOrg(id: string): Promise<Org> {
  await delay()
  const o = db.orgs.find((x) => x.id === id)
  if (!o) throw new ApiError(404, '组织不存在')
  const { state, user } = useSession()
  if (state.role === 'vendor' && o.kind === 'vendor' && o.id !== user.value.orgId) throw new ApiError(403, '无权查看其他厂商')
  return clone(o)
}

export async function listUsers(): Promise<User[]> {
  await delay()
  return clone(db.users)
}

// POST /api/admin/users —— 外部用户账号由管理员创建
export async function createUser(input: { username: string; displayName: string; email: string; role: Role; orgId: string | null; region?: RegionName | null }): Promise<{ user: User; tempPassword: string }> {
  await delay(400)
  if (db.users.some((u) => u.username === input.username)) throw new ApiError(409, '用户名已存在')
  if (input.role === 'regional' && !input.region) throw new ApiError(400, '区域侧账号必须选择所属区域')
  const user: User = {
    ...input,
    orgId: input.role === 'vendor' ? input.orgId : null,
    region: input.role === 'regional' ? (input.region ?? '华中') : null,
    id: 'u' + (db.users.length + 1),
    active: true,
    createdAt: new Date().toISOString(),
    lastLoginAt: '',
  }
  db.users.push(user)
  return { user: clone(user), tempPassword: fakeSha(input.username, 12) }
}

// POST /api/admin/vendors —— 新建厂商（《算法标准 1.0》第四部分 1–7 项），可同时为对接人开通厂商账号
export async function createVendor(input: {
  id: string
  zh_CN: string
  en_US?: string
  description: string
  profile: Omit<VendorProfile, 'createdAt'>
  account?: { username: string; email: string }
}): Promise<{ org: Org; account?: { username: string; tempPassword: string } }> {
  await delay(500)
  // 允许大小写，但判重不区分大小写，避免 HuiyanAI 与 huiyanai 并存
  if (db.orgs.some((o) => o.id.toLowerCase() === input.id.toLowerCase())) throw new ApiError(409, '厂商标识已存在（不区分大小写）')
  if (input.account && db.users.some((u) => u.username === input.account!.username)) throw new ApiError(409, '账号用户名已存在')
  const palette = ['#7c3aed', '#be123c', '#0f766e', '#b45309', '#1d4ed8', '#9333ea', '#c2410c']
  const org: Org = {
    id: input.id,
    name: input.id,
    displayName: input.zh_CN,
    enName: input.en_US || undefined,
    description: input.description || '算法厂商',
    color: palette[hashStr(input.id) % palette.length],
    members: input.account ? 1 : 0,
    kind: 'vendor',
    profile: { ...input.profile, createdAt: new Date().toISOString() },
  }
  db.orgs.push(org)
  let account: { username: string; tempPassword: string } | undefined
  if (input.account) {
    db.users.push({ id: 'u' + (db.users.length + 100), username: input.account.username, displayName: input.profile.liaison.name, email: input.account.email, role: 'vendor', orgId: org.id, active: true, createdAt: new Date().toISOString(), lastLoginAt: '' })
    account = { username: input.account.username, tempPassword: fakeSha(input.account.username, 12) }
  }
  return clone({ org, account })
}

// ============ 管理员编辑（管理员可修改所有数据） ============
function requireAdmin() {
  if (!useSession().can.value.admin) throw new ApiError(403, '仅管理员可以修改')
}

// PUT /api/admin/vendors/{id} —— 修改厂商信息；修改标识时同步更新其算法、账号与评测记录
export async function updateVendor(
  oldId: string,
  input: { id: string; zh_CN: string; en_US?: string; description: string; profile: Omit<VendorProfile, 'createdAt'> },
): Promise<Org> {
  await delay(400)
  requireAdmin()
  const org = db.orgs.find((o) => o.id === oldId && o.kind === 'vendor')
  if (!org) throw new ApiError(404, '厂商不存在')
  const newId = input.id
  if (newId !== oldId && db.orgs.some((o) => o !== org && o.id.toLowerCase() === newId.toLowerCase())) throw new ApiError(409, '厂商标识已存在（不区分大小写）')
  if (newId !== oldId) {
    // 级联：算法 ID（org/name）、算法申报中的 vendor.id、评测记录、厂商账号
    const idMap = new Map<string, string>()
    for (const a of db.algorithms.filter((x) => x.org === oldId)) {
      const nid = `${newId}/${a.name}`
      idMap.set(a.id, nid)
      a.id = nid
      a.org = newId
      if (a.declaration) a.declaration.packageInfo.vendor.id = newId
    }
    for (const r of db.evals) if (idMap.has(r.algorithmId)) r.algorithmId = idMap.get(r.algorithmId)!
    for (const u of db.users) if (u.orgId === oldId) u.orgId = newId
    for (const d of db.datasets) if (d.org === oldId) (d.org = newId), (d.id = `${newId}/${d.name}`)
    org.id = newId
    org.name = newId
  }
  org.displayName = input.zh_CN
  org.enName = input.en_US || undefined
  org.description = input.description || org.description
  org.profile = { ...input.profile, createdAt: org.profile?.createdAt ?? new Date().toISOString() }
  for (const a of db.algorithms) if (a.org === org.id && a.declaration) Object.assign(a.declaration.packageInfo.vendor, { zh_CN: org.displayName, en_US: org.enName })
  return clone(org)
}

// PATCH /api/algorithms/{id} —— 原地更新算法信息与 algo.yaml，不触发大版本更新
export async function updateAlgorithm(id: string, patch: Partial<Pick<Algorithm, 'summary' | 'tags' | 'task' | 'business' | 'framework' | 'readme' | 'selfDeveloped'>>): Promise<Algorithm> {
  await delay(300)
  requireAdmin()
  const a = db.algorithms.find((x) => x.id === id)
  if (!a) throw new ApiError(404, '算法不存在')
  if (patch.tags) {
    patch.tags = [...new Set(patch.tags.map((t) => t.trim()).filter(Boolean))]
    for (const t of patch.tags) if (!db.tags.includes(t)) db.tags.push(t)
  }
  Object.assign(a, patch, { updatedAt: new Date().toISOString() })
  a.algoYaml = syncAlgoYaml(a)
  if (patch.tags) pruneUnusedTags()
  return clone(a)
}

// PATCH /api/algorithms/{id}/tags —— 管理员或该算法所属厂商可快捷增删标签（同步更新 algo.yaml）
export async function updateAlgorithmTags(id: string, tags: string[]): Promise<Algorithm> {
  await delay(200)
  const { can, canSeeAlgo } = useSession()
  const a = db.algorithms.find((x) => x.id === id)
  if (!a) throw new ApiError(404, '算法不存在')
  if (!can.value.createAlgorithm || !canSeeAlgo(a)) throw new ApiError(403, '无权修改该算法标签')
  const cleaned = [...new Set(tags.map((t) => t.trim()).filter(Boolean))]
  for (const t of cleaned) if (!db.tags.includes(t)) db.tags.push(t)
  a.tags = cleaned
  a.algoYaml = syncAlgoYaml(a)
  a.updatedAt = new Date().toISOString()
  pruneUnusedTags()
  return clone(a)
}

// ============ 评测器管理 ============
export async function listEvaluators(q: { task?: TaskType | ''; kind?: '' | 'builtin' | 'custom'; status?: Evaluator['status'] | ''; q?: string } = {}): Promise<Evaluator[]> {
  await delay(100)
  const k = q.q?.trim().toLowerCase() ?? ''
  return clone(
    db.evaluators.filter((ev) => {
      if (q.task && ev.task !== q.task) return false
      if (q.kind && ev.kind !== q.kind) return false
      if (q.status && ev.status !== q.status) return false
      if (k && !(ev.id.toLowerCase().includes(k) || ev.name.toLowerCase().includes(k) || ev.description.toLowerCase().includes(k))) return false
      return true
    }),
  )
}

export async function getEvaluator(id: string): Promise<Evaluator> {
  await delay(100)
  const ev = db.evaluators.find((x) => x.id === id)
  if (!ev) throw new ApiError(404, '评测器不存在')
  return clone(ev)
}

export async function createEvaluator(
  input: Pick<Evaluator, 'id' | 'name' | 'version' | 'task' | 'description' | 'entrypoint' | 'runtime' | 'supportedMetrics' | 'config' | 'script'> & { kind?: Evaluator['kind'] },
): Promise<Evaluator> {
  await delay(300)
  requireAdmin()
  const id = input.id.trim()
  if (!/^[a-z0-9][a-z0-9-_]{1,63}$/.test(id)) throw new ApiError(400, '评测器标识需由小写字母、数字、- 或 _ 组成（2–64 位）')
  if (db.evaluators.some((x) => x.id === id)) throw new ApiError(409, '同名评测器标识已存在')
  const ev: Evaluator = {
    ...input,
    id,
    kind: input.kind ?? 'custom',
    status: 'uninitialized',
    updatedAt: new Date().toISOString(),
    updatedBy: useSession().user.value.username,
  }
  db.evaluators.unshift(ev)
  return clone(ev)
}

/** 初始化（或重新初始化）评测器：校验入口、脚本与指标定义，通过后置为 ready */
export async function initializeEvaluator(id: string): Promise<Evaluator> {
  await delay(450)
  requireAdmin()
  const ev = db.evaluators.find((x) => x.id === id)
  if (!ev) throw new ApiError(404, '评测器不存在')
  if (!ev.entrypoint.trim()) throw new ApiError(400, '初始化失败：缺少入口函数（entrypoint）')
  if (!ev.supportedMetrics.length) throw new ApiError(400, '初始化失败：至少需定义一项评测指标')
  if (!ev.script.trim()) throw new ApiError(400, '初始化失败：评测脚本不能为空')
  ev.status = 'ready'
  ev.updatedAt = new Date().toISOString()
  ev.updatedBy = useSession().user.value.username
  return clone(ev)
}

/** 修改评测器信息、配置参数、指标定义、脚本或启停状态 */
export async function updateEvaluator(
  id: string,
  patch: Partial<Pick<Evaluator, 'name' | 'version' | 'task' | 'status' | 'description' | 'entrypoint' | 'runtime' | 'supportedMetrics' | 'config' | 'script'>>,
): Promise<Evaluator> {
  await delay(250)
  requireAdmin()
  const ev = db.evaluators.find((x) => x.id === id)
  if (!ev) throw new ApiError(404, '评测器不存在')
  Object.assign(ev, patch, { updatedAt: new Date().toISOString(), updatedBy: useSession().user.value.username })
  // 同步更新引用该评测器的 Benchmark 版本号
  if (patch.version) {
    for (const b of db.benchmarks) if (b.evaluator === id) b.evaluatorVersion = patch.version
  }
  return clone(ev)
}

export async function deleteEvaluator(id: string): Promise<void> {
  await delay(250)
  requireAdmin()
  const idx = db.evaluators.findIndex((x) => x.id === id)
  if (idx < 0) throw new ApiError(404, '评测器不存在')
  if (db.evaluators[idx].kind === 'builtin') throw new ApiError(400, '平台内置评测器不可删除')
  if (db.benchmarks.some((b) => b.evaluator === id)) throw new ApiError(400, '该评测器正被评测基准引用，无法删除')
  db.evaluators.splice(idx, 1)
}

// ============ 标签管理 ============
export interface TagSummary {
  name: string
  count: number
}

// 清理数量为 0 的闲置标签（只保留至少被 1 个算法引用的标签）
function pruneUnusedTags() {
  const used = new Set(db.algorithms.flatMap((a) => a.tags))
  for (let i = db.tags.length - 1; i >= 0; i--) {
    if (!used.has(db.tags[i])) db.tags.splice(i, 1)
  }
}

// GET /api/tags
export async function listTags(includeEmpty = false): Promise<TagSummary[]> {
  await delay(80)
  const algos = visible(db.algorithms)
  const names = [...new Set([...db.tags, ...algos.flatMap((a) => a.tags)])]
  return names
    .map((name) => ({ name, count: algos.filter((a) => a.tags.includes(name)).length }))
    .filter((t) => includeEmpty || t.count > 0)
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, 'zh-CN'))
}

// POST /api/tags
export async function createTag(rawName: string): Promise<string> {
  await delay(150)
  if (!useSession().can.value.createAlgorithm) throw new ApiError(403, '当前账号无权管理标签')
  const name = rawName.trim()
  if (!name) throw new ApiError(400, '标签名称不能为空')
  if (db.tags.includes(name)) throw new ApiError(409, '标签已存在')
  db.tags.push(name)
  return name
}

// PATCH /api/tags/{oldName} —— 修改标签名称并同步到所有算法与数据集
export async function renameTag(oldName: string, rawNewName: string): Promise<string> {
  await delay(200)
  if (!useSession().can.value.createAlgorithm) throw new ApiError(403, '当前账号无权管理标签')
  const newName = rawNewName.trim()
  if (!newName) throw new ApiError(400, '标签名称不能为空')
  if (newName === oldName) return newName
  if (db.tags.includes(newName)) throw new ApiError(409, `标签「${newName}」已存在`)
  const idx = db.tags.indexOf(oldName)
  if (idx >= 0) db.tags[idx] = newName
  else db.tags.push(newName)
  for (const a of db.algorithms) {
    if (a.tags.includes(oldName)) {
      a.tags = [...new Set(a.tags.map((t) => (t === oldName ? newName : t)))]
      a.algoYaml = syncAlgoYaml(a)
    }
  }
  for (const d of db.datasets) {
    if (d.tags.includes(oldName)) d.tags = [...new Set(d.tags.map((t) => (t === oldName ? newName : t)))]
  }
  return newName
}

// DELETE /api/tags/{name} —— 删除标签并从所有算法移除
export async function deleteTag(name: string): Promise<void> {
  await delay(200)
  if (!useSession().can.value.createAlgorithm) throw new ApiError(403, '当前账号无权管理标签')
  const idx = db.tags.indexOf(name)
  if (idx >= 0) db.tags.splice(idx, 1)
  for (const a of db.algorithms) {
    if (a.tags.includes(name)) {
      a.tags = a.tags.filter((t) => t !== name)
      a.algoYaml = syncAlgoYaml(a)
    }
  }
}

// DELETE /api/algorithms/{id} —— 管理员删除算法及其关联评测记录
export async function deleteAlgorithm(id: string): Promise<void> {
  await delay(250)
  requireAdmin()
  const idx = db.algorithms.findIndex((x) => x.id === id)
  if (idx < 0) throw new ApiError(404, '算法不存在')
  if (REAL_ALGO_IDS.has(id)) {
    await fetch(`/real-api/algorithms/${id}`, { method: 'DELETE' }).catch(() => {})
  }
  db.algorithms.splice(idx, 1)
  for (let i = db.evals.length - 1; i >= 0; i--) {
    if (db.evals[i].algorithmId === id) db.evals.splice(i, 1)
  }
  if (REAL_ALGO_IDS.has(id) && !db.deletedRealIds.includes(id)) db.deletedRealIds.push(id)
  pruneUnusedTags()
}

// DELETE /api/datasets/{id} —— 管理员删除数据集及其关联评测基准与评测记录
export async function deleteDataset(id: string): Promise<void> {
  await delay(250)
  requireAdmin()
  const idx = db.datasets.findIndex((x) => x.id === id)
  if (idx < 0) throw new ApiError(404, '数据集不存在')
  if (REAL_DS_IDS.has(id)) {
    await fetch(`/real-api/datasets/${id}`, { method: 'DELETE' }).catch(() => {})
  }
  db.datasets.splice(idx, 1)
  const removedBenches = new Set<string>()
  for (let i = db.benchmarks.length - 1; i >= 0; i--) {
    if (db.benchmarks[i].datasetId === id) {
      removedBenches.add(db.benchmarks[i].id)
      if (!db.deletedRealIds.includes(db.benchmarks[i].id)) db.deletedRealIds.push(db.benchmarks[i].id)
      db.benchmarks.splice(i, 1)
    }
  }
  for (let i = db.evals.length - 1; i >= 0; i--) {
    if (removedBenches.has(db.evals[i].benchmarkId)) db.evals.splice(i, 1)
  }
  if (REAL_DS_IDS.has(id) && !db.deletedRealIds.includes(id)) db.deletedRealIds.push(id)
}

// PATCH /api/datasets/{id}
export async function updateDataset(id: string, patch: Partial<Pick<Dataset, 'summary' | 'tags' | 'classes' | 'readme'>>): Promise<Dataset> {
  await delay(300)
  requireAdmin()
  const d = db.datasets.find((x) => x.id === id)
  if (!d) throw new ApiError(404, '数据集不存在')
  Object.assign(d, patch, { updatedAt: new Date().toISOString() })
  return clone(d)
}

// PATCH /api/benchmarks/{id}
export async function updateBenchmark(id: string, patch: Partial<Pick<Benchmark, 'displayName' | 'description' | 'metrics' | 'datasetVersion'>>): Promise<Benchmark> {
  await delay(300)
  requireAdmin()
  const b = db.benchmarks.find((x) => x.id === id)
  if (!b) throw new ApiError(404, '评测基准不存在')
  Object.assign(b, patch)
  return clone(b)
}

// PATCH /api/admin/users/{id}
export async function updateUser(id: string, patch: Partial<Pick<User, 'displayName' | 'email' | 'role' | 'orgId' | 'region'>>): Promise<User> {
  await delay(300)
  requireAdmin()
  const u = db.users.find((x) => x.id === id)
  if (!u) throw new ApiError(404, '用户不存在')
  const next = { ...u, ...patch }
  if (next.role === 'vendor' && !next.orgId) throw new ApiError(400, '厂商账号必须选择所属厂商')
  if (next.role === 'regional' && !next.region) throw new ApiError(400, '区域侧账号必须选择所属区域')
  if (next.role !== 'vendor') next.orgId = null
  if (next.role !== 'regional') next.region = null
  Object.assign(u, next)
  return clone(u)
}

export async function setUserActive(id: string, active: boolean): Promise<void> {
  await delay()
  const u = db.users.find((x) => x.id === id)
  if (u) u.active = active
}

export interface ReviewItem {
  algorithm: Pick<Algorithm, 'id' | 'org' | 'name' | 'task' | 'framework' | 'summary'>
  version: AlgoVersion
}

export async function listReviewQueue(): Promise<ReviewItem[]> {
  await delay()
  const out: ReviewItem[] = []
  for (const a of db.algorithms) for (const v of a.versions) if (v.status === 'pending_review') out.push({ algorithm: { id: a.id, org: a.org, name: a.name, task: a.task, framework: a.framework, summary: a.summary }, version: v })
  return clone(out)
}

// POST /api/admin/reviews/{algoId}/{version}
export async function reviewVersion(algoId: string, version: string, approve: boolean, note: string): Promise<void> {
  await delay(300)
  const v = db.algorithms.find((a) => a.id === algoId)?.versions.find((x) => x.version === version)
  if (!v) throw new ApiError(404, '版本不存在')
  if (approve && REAL_ALGO_IDS.has(algoId)) {
    const fd = new FormData()
    fd.append('version', version)
    const resp = await fetch(`/real-api/algorithms/${algoId}/approve`, { method: 'POST', body: fd })
    if (resp.ok) {
      const updated = (await resp.json()) as AlgoVersion
      Object.assign(v, updated, { reviewNote: note })
      return
    }
  }
  v.status = approve ? 'building' : 'rejected'
  v.reviewNote = note
  if (approve) {
    v.buildLog.push(`[review] 审核通过：${note || '无备注'}`, '[build] 已进入构建队列')
    // 原型：模拟构建（导入镜像、加载权重、冒烟测试）几秒后完成
    setTimeout(() => {
      v.status = 'ready'
      v.imageDigest = 'sha256:' + fakeSha(algoId + version + 'image')
      v.weightsHash = v.weightsHash ?? 'sha256:' + fakeSha(algoId + version + 'weights')
      v.buildLog.push(`[build] 导入镜像 ${v.baseImage}`, '[build] 校验权重与 algo.yaml …… OK', '[build] 冒烟测试 …… OK（原型模拟）', '[build] 完成，版本可用')
    }, 3000)
  } else v.buildLog.push(`[review] 已驳回：${note}`)
}

// ============ 总部算法下发 & 区域试用申请审批 ============
/** 同步读取某算法当前已下发的区域列表（响应式，供卡片与详情页实时展示） */
export function getDispatchedRegions(algorithmId: string): RegionName[] {
  return db.dispatches.filter((d) => d.algorithmId === algorithmId).map((d) => d.region)
}

export function isDispatchedToRegion(algorithmId: string, region: RegionName | null): boolean {
  if (!region) return false
  return db.dispatches.some((d) => d.algorithmId === algorithmId && d.region === region)
}

export function getRegionTrialRequest(algorithmId: string, region: RegionName | null): RegionTrialRequest | undefined {
  if (!region) return undefined
  return db.trialRequests.find((r) => r.algorithmId === algorithmId && r.region === region)
}

export function getPendingTrialRegionsForAlgo(algorithmId: string): RegionName[] {
  return db.trialRequests.filter((r) => r.algorithmId === algorithmId && r.status === 'pending').map((r) => r.region)
}

export async function listDispatches(): Promise<AlgorithmDispatch[]> {
  await delay(80)
  return clone(db.dispatches)
}

/** 总部管理员配置某算法的下发区域（勾选即下发、取消勾选即收回；新下发的区域若有待审批试用申请则自动通过） */
export async function setAlgorithmDispatches(algorithmId: string, regions: RegionName[]): Promise<RegionName[]> {
  await delay(200)
  requireAdmin()
  const algo = db.algorithms.find((a) => a.id === algorithmId)
  if (!algo) throw new ApiError(404, '算法不存在')
  const targetSet = new Set(regions)
  const now = new Date().toISOString()
  const operator = useSession().user.value.username

  // 移除被取消的区域
  for (let i = db.dispatches.length - 1; i >= 0; i--) {
    if (db.dispatches[i].algorithmId === algorithmId && !targetSet.has(db.dispatches[i].region)) {
      db.dispatches.splice(i, 1)
    }
  }
  // 追加新增的区域
  for (const rg of targetSet) {
    if (!db.dispatches.some((d) => d.algorithmId === algorithmId && d.region === rg)) {
      db.dispatches.push({ algorithmId, region: rg, dispatchedAt: now, dispatchedBy: operator, source: 'direct' })
    }
    // 若该区域存在待审批申请，同步标记为已通过
    for (const req of db.trialRequests) {
      if (req.algorithmId === algorithmId && req.region === rg && req.status === 'pending') {
        req.status = 'approved'
        req.reviewedAt = now
        req.reviewedBy = operator
        req.reviewNote = '总部已直接下发至该区域'
      }
    }
  }
  return getDispatchedRegions(algorithmId)
}

export async function listTrialRequests(filter: { status?: TrialRequestStatus; region?: RegionName; algorithmId?: string } = {}): Promise<RegionTrialRequest[]> {
  await delay(80)
  return clone(
    db.trialRequests.filter((r) => {
      if (filter.status && r.status !== filter.status) return false
      if (filter.region && r.region !== filter.region) return false
      if (filter.algorithmId && r.algorithmId !== filter.algorithmId) return false
      return true
    }),
  )
}

/** 区域侧账号对未下发的已审核算法提交试用申请 */
export async function submitTrialRequest(algorithmId: string, region: RegionName, reason: string): Promise<RegionTrialRequest> {
  await delay(250)
  const { user } = useSession()
  const algo = db.algorithms.find((a) => a.id === algorithmId)
  if (!algo) throw new ApiError(404, '算法不存在')
  if (isDispatchedToRegion(algorithmId, region)) throw new ApiError(400, `该算法已下发至「${region}」区域，无需重复申请`)
  if (db.trialRequests.some((r) => r.algorithmId === algorithmId && r.region === region && r.status === 'pending')) {
    throw new ApiError(409, `「${region}」区域已提交试用申请，请等待总部审批`)
  }
  const trimmed = reason.trim()
  if (!trimmed) throw new ApiError(400, '请填写试用场景与申请理由')
  const req: RegionTrialRequest = {
    id: `tr-${Date.now().toString().slice(-6)}`,
    algorithmId,
    region,
    applicant: user.value.displayName,
    reason: trimmed,
    status: 'pending',
    createdAt: new Date().toISOString(),
  }
  db.trialRequests.unshift(req)
  return clone(req)
}

/** 总部管理员审批区域试用申请：通过时自动下发至申请区域 */
export async function reviewTrialRequest(requestId: string, approve: boolean, note: string): Promise<RegionTrialRequest> {
  await delay(250)
  requireAdmin()
  const req = db.trialRequests.find((r) => r.id === requestId)
  if (!req) throw new ApiError(404, '试用申请不存在')
  if (req.status !== 'pending') throw new ApiError(400, '该申请已处理')
  if (!approve && !note.trim()) throw new ApiError(400, '驳回时请填写原因')
  const now = new Date().toISOString()
  const operator = useSession().user.value.username
  req.status = approve ? 'approved' : 'rejected'
  req.reviewedAt = now
  req.reviewedBy = operator
  req.reviewNote = note.trim() || (approve ? '审批通过，已下发' : '')
  if (approve && !db.dispatches.some((d) => d.algorithmId === req.algorithmId && d.region === req.region)) {
    db.dispatches.push({
      algorithmId: req.algorithmId,
      region: req.region,
      dispatchedAt: now,
      dispatchedBy: operator,
      source: 'approved_request',
    })
  }
  return clone(req)
}

// ============ 全局搜索 ============
export async function quickSearch(q: string) {
  await delay(80)
  const k = q.toLowerCase()
  const { canSeeAlgo } = useSession()
  return {
    algorithms: db.algorithms
      .filter((a) => canSeeAlgo(a) && (a.id.toLowerCase().includes(k) || algoFullLabel(a).toLowerCase().includes(k)))
      .slice(0, 5)
      .map((a) => ({ id: a.id, task: a.task })),
    datasets: db.datasets.filter((d) => d.id.toLowerCase().includes(k)).slice(0, 4).map((d) => ({ id: d.id, task: d.task })),
    benchmarks: db.benchmarks.filter((b) => b.displayName.includes(q) || b.name.includes(k)).slice(0, 3).map((b) => ({ id: b.id, displayName: b.displayName })),
  }
}

export interface Overview {
  algorithms: { total: number; versions: number; readyVersions: number; newLast30d: number; selfDeveloped: number }
  datasets: { total: number; samples: number; bytes: number }
  benchmarks: { total: number; leaderboardEntries: number }
  evals: { total: number; succeeded: number; last7d: number; running: number; queued: number }
  pendingReview: number
  pendingTrialRequests: number
  trend: { date: string; succeeded: number; failed: number }[] // 近 30 天每日评测完成数
  byTask: { task: TaskType; algorithms: number; datasets: number }[]
  evalStatus: Record<EvalRun['status'], number>
}

// GET /api/overview —— 首页总览（按当前身份的可见范围统计）
export async function overview(): Promise<Overview> {
  await syncRealBackend(true)
  await delay(120)
  const { canSeeAlgo } = useSession()
  const now = Date.now()
  const DAY = 86400000
  const algos = db.algorithms.filter(canSeeAlgo)
  const dss = db.datasets
  const visibleIds = new Set(algos.map((a) => a.id))
  const runs = db.evals.filter((r) => visibleIds.has(r.algorithmId))

  const trend = Array.from({ length: 30 }, (_, i) => {
    const d = new Date(now - (29 - i) * DAY)
    return { date: `${d.getMonth() + 1}/${d.getDate()}`, succeeded: 0, failed: 0, _start: new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() }
  })
  for (const r of runs) {
    if (r.status !== 'succeeded' && r.status !== 'failed') continue
    const t = new Date(r.finishedAt ?? r.submittedAt).getTime()
    const slot = trend.find((x) => t >= x._start && t < x._start + DAY) ?? (t >= trend[29]._start ? trend[29] : undefined)
    if (slot) slot[r.status]++
  }

  const tasks = [...new Set([...algos.map((a) => a.task), ...dss.map((d) => d.task)])]
  const byTask = tasks
    .map((task) => ({ task, algorithms: algos.filter((a) => a.task === task).length, datasets: dss.filter((d) => d.task === task).length }))
    .sort((a, b) => b.algorithms - a.algorithms || b.datasets - a.datasets)

  const evalStatus = { queued: 0, running: 0, succeeded: 0, failed: 0, canceled: 0 } as Overview['evalStatus']
  for (const r of runs) evalStatus[r.status]++

  return {
    algorithms: {
      total: algos.length,
      versions: algos.reduce((s, a) => s + a.versions.length, 0),
      readyVersions: algos.reduce((s, a) => s + a.versions.filter((v) => v.status === 'ready').length, 0),
      newLast30d: algos.filter((a) => now - new Date(a.versions[a.versions.length - 1].createdAt).getTime() < 30 * DAY).length,
      selfDeveloped: algos.filter((a) => !!a.selfDeveloped).length,
    },
    datasets: { total: dss.length, samples: dss.reduce((s, d) => s + d.train.versions[0].files + (d.test?.versions[0].files ?? 0), 0), bytes: dss.reduce((s, d) => s + d.train.versions[0].sizeBytes + (d.test?.versions[0].sizeBytes ?? 0), 0) },
    benchmarks: { total: db.benchmarks.length, leaderboardEntries: runs.filter((r) => r.isLatestValid).length },
    evals: { total: runs.length, succeeded: evalStatus.succeeded, last7d: runs.filter((r) => now - new Date(r.submittedAt).getTime() < 7 * DAY).length, running: evalStatus.running, queued: evalStatus.queued },
    pendingReview: db.algorithms.reduce((s, a) => s + a.versions.filter((v) => v.status === 'pending_review').length, 0),
    pendingTrialRequests: db.trialRequests.filter((r) => r.status === 'pending').length,
    trend: trend.map(({ date, succeeded, failed }) => ({ date, succeeded, failed })),
    byTask,
    evalStatus,
  }
}
