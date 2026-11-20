/**
 * API 服务层 —— 目前全部由本地 mock 实现。
 * 函数签名与返回结构按将来的 FastAPI REST 接口设计（注释中标注了对应路由），
 * 接入真实后端时只需把函数体替换为 fetch 调用。
 */
import { reactive, watch } from 'vue'
import type {
  Algorithm,
  AlgoVersion,
  Benchmark,
  Dataset,
  EvalRun,
  InferenceResult,
  ListQuery,
  Org,
  Paginated,
  QueueStatus,
  Role,
  TaskType,
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
import { orgs as O0, users as U0 } from '@/mock/orgs'
import { useSession } from '@/stores/session'
import { fakeSha, hashStr, rng } from '@/utils/format'

// ---------- 原型数据持久化 ----------
// 写操作（新建厂商、上传数据集、编辑信息等）保存到浏览器 localStorage，刷新后仍在。
// 恢复时就地替换 mock 数组的内容，直接引用 mock 的组件（如头像、基准名称）也能看到最新数据。
const STORE_KEY = 'algohub-db-v3'
const SOURCES = { algorithms: A0, datasets: D0, benchmarks: B0, evals: E0, orgs: O0, users: U0 }
type DbKey = keyof typeof SOURCES
try {
  const saved = JSON.parse(localStorage.getItem(STORE_KEY) ?? 'null') as Partial<Record<DbKey, unknown[]>> | null
  if (saved) for (const k of Object.keys(SOURCES) as DbKey[]) if (Array.isArray(saved[k])) (SOURCES[k] as unknown[]).splice(0, SOURCES[k].length, ...saved[k]!)
} catch {
  /* 数据损坏或不可用时使用默认 mock */
}

// 用 reactive 包一层，使 mock “写操作” 能实时反映到页面上
const db = reactive(SOURCES)

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
    r = r.filter((x) => x.id.toLowerCase().includes(k) || x.summary.includes(q.q!) || x.tags.some((t) => t.toLowerCase().includes(k)))
  }
  if (q.task) r = r.filter((x) => x.task === q.task)
  if (q.license) r = r.filter((x) => 'license' in x && x.license === q.license)
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
  await delay()
  return clone(paginate(filterSort(db.algorithms, q), q))
}

// GET /api/algorithms/{org}/{name}
export async function getAlgorithm(id: string): Promise<Algorithm> {
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
  framework: Algorithm['framework']
  license: string
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
  const algo: Algorithm = {
    id,
    org: input.org,
    name: input.name,
    task: input.task,
    framework: input.framework,
    license: input.license,
    tags: input.tags ?? (can.value.needsReview ? ['厂商提交'] : ['新提交']),
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
  await delay()
  return clone(paginate(filterSort(db.datasets, q), q))
}

export async function getDataset(id: string): Promise<Dataset> {
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

// POST /api/datasets —— 新建数据集时先上传训练集；测试集随后单独上传
export async function createDataset(input: Pick<Dataset, 'org' | 'name' | 'task' | 'summary' | 'classes'> & { train: PartUpload }): Promise<Dataset> {
  await delay(600)
  if (!useSession().can.value.createDataset) throw new ApiError(403, '仅管理员可以上传数据集')
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

// POST /api/datasets/{id}/{part}/versions —— 上传训练集或测试集的新版本（仅管理员）
export async function uploadDatasetPart(id: string, partName: SplitName, up: PartUpload): Promise<Dataset> {
  await delay(600)
  if (!useSession().can.value.createDataset) throw new ApiError(403, '仅管理员可以上传数据')
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
  await delay()
  const b = db.benchmarks.find((x) => x.id === id)
  if (!b) throw new ApiError(404, 'Benchmark 不存在')
  return clone(b)
}

export async function createBenchmark(input: Omit<Benchmark, 'id' | 'createdAt' | 'split'>): Promise<Benchmark> {
  await delay(500)
  if (db.benchmarks.some((b) => b.name === input.name)) throw new ApiError(409, '同名 Benchmark 已存在')
  const b: Benchmark = { ...input, id: input.name, split: 'test', createdAt: new Date().toISOString() }
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
  await delay()
  const r = db.evals.find((x) => x.id === id)
  if (!r) throw new ApiError(404, '评测记录不存在')
  const a = db.algorithms.find((x) => x.id === r.algorithmId)
  if (a && !useSession().canSeeAlgo(a)) throw new ApiError(403, '无权查看该评测记录')
  return clone(r)
}

// POST /api/evals
export async function createEval(input: { algorithmId: string; algoVersion: string; benchmarkId: string; params: EvalRun['params'] }): Promise<EvalRun> {
  await delay(500)
  const { user, can, canSeeAlgo } = useSession()
  const a = db.algorithms.find((x) => x.id === input.algorithmId)!
  if (!can.value.runEval || !canSeeAlgo(a)) throw new ApiError(403, '只能评测自己的算法')
  const v = a.versions.find((x) => x.version === input.algoVersion)!
  if (v.status !== 'ready') throw new ApiError(400, '该算法版本尚不可用（未通过构建或审核）')
  const b = db.benchmarks.find((x) => x.id === input.benchmarkId)!
  if (a.task !== b.task) throw new ApiError(400, '算法任务类型与 Benchmark 不匹配')
  const id = `ev-${1100 + db.evals.length}`
  const run: EvalRun = {
    id,
    ...input,
    status: 'queued',
    progress: 0,
    submittedBy: user.value.username,
    submittedAt: new Date().toISOString(),
    metrics: {},
    imageDigest: v.imageDigest!,
    weightsHash: v.weightsHash ?? '',
    evaluatorVersion: b.evaluatorVersion,
    hardware: 'NVIDIA RTX 4060 Laptop (8GB) · i9-13900H · CUDA 12.4',
    isLatestValid: false,
    logs: [`[scheduler] 任务入队，声明显存 ${v.gpuMem} GB`, '[scheduler] 前方 2 个任务，预计等待 6 分钟'],
  }
  db.evals.unshift(run)
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
  await delay(120)
  return {
    gpuName: 'RTX 4060 Laptop',
    gpuMemTotal: 8,
    gpuMemUsed: 0,
    running: db.evals.filter((r) => r.status === 'running').length,
    queued: db.evals.filter((r) => r.status === 'queued').length,
    warmContainers: [],
  }
}

// ============ 单图推理  POST /api/algorithms/{id}/infer ============
const PALETTE = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16', '#06b6d4', '#a855f7', '#eab308']

export async function infer(algorithmId: string, version: string, input: { dataUrl?: string; fileName: string; size: number }): Promise<InferenceResult> {
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
    const top = Math.floor(r() * labels.length)
    logits[top] += 2.5
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
export async function createUser(input: { username: string; displayName: string; email: string; role: Role; orgId: string | null }): Promise<{ user: User; tempPassword: string }> {
  await delay(400)
  if (db.users.some((u) => u.username === input.username)) throw new ApiError(409, '用户名已存在')
  const user: User = { ...input, id: 'u' + (db.users.length + 1), active: true, createdAt: new Date().toISOString(), lastLoginAt: '' }
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

// PATCH /api/algorithms/{id}
export async function updateAlgorithm(id: string, patch: Partial<Pick<Algorithm, 'summary' | 'tags' | 'license' | 'task' | 'framework' | 'readme'>>): Promise<Algorithm> {
  await delay(300)
  requireAdmin()
  const a = db.algorithms.find((x) => x.id === id)
  if (!a) throw new ApiError(404, '算法不存在')
  Object.assign(a, patch, { updatedAt: new Date().toISOString() })
  return clone(a)
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
export async function updateUser(id: string, patch: Partial<Pick<User, 'displayName' | 'email' | 'role' | 'orgId'>>): Promise<User> {
  await delay(300)
  requireAdmin()
  const u = db.users.find((x) => x.id === id)
  if (!u) throw new ApiError(404, '用户不存在')
  const next = { ...u, ...patch }
  if (next.role === 'vendor' && !next.orgId) throw new ApiError(400, '厂商账号必须选择所属厂商')
  if (next.role !== 'vendor') next.orgId = null
  Object.assign(u, next)
  return clone(u)
}

export async function setUserActive(id: string, active: boolean): Promise<void> {
  await delay()
  const u = db.users.find((x) => x.id === id)
  if (u) u.active = active
}

export interface ReviewItem {
  algorithm: Pick<Algorithm, 'id' | 'org' | 'name' | 'task' | 'framework' | 'license' | 'summary'>
  version: AlgoVersion
}

export async function listReviewQueue(): Promise<ReviewItem[]> {
  await delay()
  const out: ReviewItem[] = []
  for (const a of db.algorithms) for (const v of a.versions) if (v.status === 'pending_review') out.push({ algorithm: { id: a.id, org: a.org, name: a.name, task: a.task, framework: a.framework, license: a.license, summary: a.summary }, version: v })
  return clone(out)
}

// POST /api/admin/reviews/{algoId}/{version}
export async function reviewVersion(algoId: string, version: string, approve: boolean, note: string): Promise<void> {
  await delay(400)
  const v = db.algorithms.find((a) => a.id === algoId)?.versions.find((x) => x.version === version)
  if (!v) throw new ApiError(404, '版本不存在')
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

// ============ 全局搜索 ============
export async function quickSearch(q: string) {
  await delay(80)
  const k = q.toLowerCase()
  const { canSeeAlgo } = useSession()
  return {
    algorithms: db.algorithms.filter((a) => canSeeAlgo(a) && a.id.toLowerCase().includes(k)).slice(0, 5).map((a) => ({ id: a.id, task: a.task })),
    datasets: db.datasets.filter((d) => d.id.toLowerCase().includes(k)).slice(0, 4).map((d) => ({ id: d.id, task: d.task })),
    benchmarks: db.benchmarks.filter((b) => b.displayName.includes(q) || b.name.includes(k)).slice(0, 3).map((b) => ({ id: b.id, displayName: b.displayName })),
  }
}

export interface Overview {
  algorithms: { total: number; versions: number; readyVersions: number; newLast30d: number }
  datasets: { total: number; samples: number; bytes: number }
  benchmarks: { total: number; leaderboardEntries: number }
  evals: { total: number; succeeded: number; last7d: number; running: number; queued: number }
  pendingReview: number
  trend: { date: string; succeeded: number; failed: number }[] // 近 30 天每日评测完成数
  byTask: { task: TaskType; algorithms: number; datasets: number }[]
  evalStatus: Record<EvalRun['status'], number>
}

// GET /api/overview —— 首页总览（按当前身份的可见范围统计）
export async function overview(): Promise<Overview> {
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
    },
    datasets: { total: dss.length, samples: dss.reduce((s, d) => s + d.train.versions[0].files + (d.test?.versions[0].files ?? 0), 0), bytes: dss.reduce((s, d) => s + d.train.versions[0].sizeBytes + (d.test?.versions[0].sizeBytes ?? 0), 0) },
    benchmarks: { total: db.benchmarks.length, leaderboardEntries: runs.filter((r) => r.isLatestValid).length },
    evals: { total: runs.length, succeeded: evalStatus.succeeded, last7d: runs.filter((r) => now - new Date(r.submittedAt).getTime() < 7 * DAY).length, running: evalStatus.running, queued: evalStatus.queued },
    pendingReview: db.algorithms.reduce((s, a) => s + a.versions.filter((v) => v.status === 'pending_review').length, 0),
    trend: trend.map(({ date, succeeded, failed }) => ({ date, succeeded, failed })),
    byTask,
    evalStatus,
  }
}
