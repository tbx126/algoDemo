// 领域模型 —— 与将来 FastAPI 后端的响应结构保持一致

export type TaskType =
  | 'image-classification'
  | 'image-dehazing'
  | 'object-detection'
  | 'semantic-segmentation'
  | 'instance-segmentation'
  | 'keypoint-detection'
  | 'ocr'
  | 'power-forecast'
  | 'server-fault'
  | 'signal-processing'
  | 'optimization'
  | 'custom'

/** 算法业务分类 */
export type BusinessCategory = 'security' | 'inspection' | 'fire-safety' | 'env-control' | 'production' | 'other'

/** 四类账号：管理员（平台运营）、区域侧（查看已审核算法/训练集/评测）、演示账号（只读展示）、厂商账号（算法供应商） */
export type Role = 'admin' | 'regional' | 'demo' | 'vendor'

/** 14 个区域侧节点 */
export type RegionName = '华北' | '蒙古' | '河北' | '山东' | '东北' | '华中' | '华东' | '甘肃' | '新疆' | '宁夏' | '西南' | '南方' | '云南' | '贵州'

export interface AlgorithmDispatch {
  algorithmId: string
  region: RegionName
  dispatchedAt: string
  dispatchedBy: string
  source: 'direct' | 'approved_request'
}

export type TrialRequestStatus = 'pending' | 'approved' | 'rejected'

export interface RegionTrialRequest {
  id: string
  algorithmId: string
  region: RegionName
  applicant: string
  reason: string
  status: TrialRequestStatus
  createdAt: string
  reviewedAt?: string
  reviewedBy?: string
  reviewNote?: string
}


export type Framework = 'PyTorch' | 'ONNX' | 'TensorRT' | 'OpenCV' | 'NumPy' | 'Paddle'

export interface Org {
  id: string
  name: string
  displayName: string
  description: string
  color: string // 头像底色
  members: number
  kind: 'team' | 'vendor' // 平台内部命名空间（数据集与基线算法） / 厂商
  enName?: string // 厂商英文名称（vendor.en_US）
  profile?: VendorProfile // 厂商入库申报信息（仅 vendor）
}

/** 厂商入库申报信息 —— 对应《算法标准 1.0》第四部分第 1–7 项 */
export interface VendorProfile {
  company: { fullName: string; creditCode: string; address: string; type: string; foundedAt: string; capital: string; status: string; licenseFile?: string }
  contact: { phone: string; email: string; website: string; officeAddress: string }
  liaison: { name: string; title: string; phone: string }
  /** 行业资质：合并为一个文件上传；noQualification=true 时为无资质情况说明 */
  qualification?: { file: string; noQualification: boolean }
  // 软著 / 专利 / 其他知识产权：各合并为一个文件上传
  copyrightFile?: string
  patentFile?: string
  otherIpFile?: string
  createdAt: string
}

export interface User {
  id: string
  username: string
  displayName: string
  email: string
  role: Role
  /** 所属厂商；管理员与演示账号不属于任何组织（null） */
  orgId: string | null
  /** 所属区域（仅区域侧账号） */
  region?: RegionName | null
  active: boolean
  createdAt: string
  lastLoginAt: string
}

/** 算法版本状态机：已提交 → 待审核（仅外部） → 构建中 → 可用 / 构建失败；审核也可能被驳回 */
export type AlgoVersionStatus = 'submitted' | 'pending_review' | 'rejected' | 'building' | 'ready' | 'failed'

export interface AlgoVersion {
  version: string // v1.2.0
  status: AlgoVersionStatus
  createdAt: string
  createdBy: string
  changelog: string
  imageDigest?: string // sha256:...
  weightsHash?: string
  weightsSize: number // bytes
  baseImage: string // 平台官方基础镜像
  gpuMem: number // GB，algo.yaml 中声明
  buildLog: string[]
  reviewNote?: string
}

export interface AlgoFile {
  path: string
  size: number
  kind: 'code' | 'config' | 'weights' | 'doc'
}

export interface Algorithm {
  id: string // org/name
  org: string
  name: string
  displayName?: string // 算法中文名称
  task: TaskType
  business: BusinessCategory
  framework: Framework
  /** 是否为平台自研算法 */
  selfDeveloped?: boolean
  tags: string[]
  summary: string
  readme: string // markdown
  paperUrl?: string
  codeUrl?: string
  likes: number
  evalCount: number
  updatedAt: string
  versions: AlgoVersion[]
  files: AlgoFile[]
  algoYaml: string
  labels?: string[] // 推理组件用的类别名
  sampleImages?: string[] // 在线推理示例图片（真实图片路径）
  declaration?: AlgoDeclaration // 按《算法标准 1.0》提交的申报信息
}

// ---------- 《智能运维平台算法中心算法标准 1.0》 ----------
export interface I18nText {
  zh_CN: string
  en_US?: string
}
export interface CoverInfo {
  type: 'picture' | 'video'
  fileName: string
}
export interface SceneInfo {
  description: { zh_CN: string }
  fileName: string
}
export type SourceType = 'picture' | 'video' | 'audio' | 'featureModel' | 'text'
export interface SourceInfo {
  type: SourceType
  format?: string[]
  encodeFormat?: string[]
  packageFormat?: string[]
  frameRate?: number
  min?: string
  max?: string
  audioFormat?: string[]
  sampleRate?: string
  sampleBit?: number
  maxSize?: number
  id?: string
  version?: string
}
export interface AbilityInfo {
  type: string
  specification: string
  ability: number // 0–100（%）
  taskAbility: number
}

/** managementinfo.json —— 算法属性信息（表 A.1–A.3） */
export interface ManagementInfo {
  id: string
  name: I18nText
  classifications: string[]
  places: string[]
  description: I18nText
  cover: CoverInfo[]
  conditions: {
    description: { zh_CN: { weather?: string; light?: string; pixel: string; baffle: string; image: string; other?: string } }
    suitabilities?: SceneInfo[]
    unsuitabilities?: SceneInfo[]
  }
}

/** technicalinfo.json —— 算法技术信息（表 A.4–A.7） */
export interface TechnicalInfo {
  version: string
  analysisSources: SourceInfo[]
  environment: {
    chip: string
    basePackage?: { id: string; minorVersion: string; majorVersion: string; relatedPodImageName?: string }
    driver?: { type: string; minorVersion: string; majorVersion: string }
  }
  requirement: { videoMemory: number; disk: number; memory: number; AImemory: number; CPU: number }
  abilityInfos: AbilityInfo[]
  regulation: { input: string; output: string; eventCode: string }
  featureModel?: { id: string; version: string }[]
}

/** 第二部分：算法支持的分析参数（运行时由业务配置） */
export interface ParamSupport {
  generalParam: { enabled: boolean; sensitive?: number; alertConfThreshold?: number; duration?: number; triggerInterval?: number; maxTriggerEnabled?: boolean; maxTriggerTimes?: number }
  detectRegion: boolean
  maskRegion: boolean
  ruleRegion: { enabled: boolean; crossDirections: ('null' | 'bothDirection' | 'leftToRight' | 'rightToLeft')[]; polygonTypes: (1 | 2 | 3)[] }
  numberCondition: boolean
  sizeFilter: boolean
  eventTypes: string[]
}

export interface DeliveryFile {
  key: string
  fileName: string
  size: number
}

export interface AlgoDeclaration {
  packageInfo: { id: string; version: string; vendor: { id: string; zh_CN: string; en_US?: string } }
  management: ManagementInfo
  technical: TechnicalInfo
  params: ParamSupport
  deliveries: DeliveryFile[]
  checklist: string[] // 已自查的内容项
}

/**
 * 数据集 = 训练集 + 测试集，两部分分开上传、各自有版本；内部结构一致：
 *   images/      具体数据（图片 / 信号文件等）
 *   labels.csv   真值，必有 file_name 列，其余列由任务类型决定（见 utils/labels.ts）
 * 训练集所有人可下载；测试集仅管理员可查看、下载、上传，厂商只能在其上评测。
 */
export type SplitName = 'train' | 'test'

export interface DatasetVersion {
  version: string
  createdAt: string
  createdBy: string
  contentHash: string
  sizeBytes: number
  note: string
  files: number // images/ 下的文件数
  rows: number // labels.csv 行数（检测等任务一个目标一行）
}

export interface DatasetPart {
  name: SplitName
  columns: string[] // labels.csv 表头
  versions: DatasetVersion[] // 最新在前
  classCounts: Record<string, number> // 各类别标注数
}

export interface Dataset {
  id: string
  org: string
  name: string
  task: TaskType
  tags: string[]
  summary: string
  readme: string
  classes: string[] // 类别表，训练集与测试集共用
  train: DatasetPart
  test: DatasetPart | null // 尚未上传测试集时为 null
  likes: number
  downloads: number
  updatedAt: string
  previewSeed: number
  /** 可选：按类别提供的真实示例图片路径，用于数据集预览 */
  sampleImages?: Record<string, string[]>
  /** 可选：由真实后端提供的真实预览样本（含真实文件名、标签与图片 URL） */
  realPreview?: {
    train: { file_name: string; label: string; url: string; row?: string[] }[]
    test: { file_name: string; label: string; url: string; row?: string[] }[]
  }
}

export interface MetricDef {
  key: string
  label: string
  higherIsBetter: boolean
  unit?: string
  primary?: boolean
}

export interface EvaluatorParamDef {
  key: string
  label: string
  type: 'number' | 'boolean' | 'string' | 'select'
  value: string | number | boolean
  options?: string[]
  desc?: string
}

export type EvaluatorStatus = 'ready' | 'uninitialized' | 'disabled'

export interface Evaluator {
  id: string
  name: string
  version: string
  kind: 'builtin' | 'custom'
  task: TaskType
  status: EvaluatorStatus
  description: string
  entrypoint: string
  runtime: string
  supportedMetrics: MetricDef[]
  config: EvaluatorParamDef[]
  script: string
  updatedAt: string
  updatedBy: string
}

export interface Benchmark {
  id: string
  name: string
  displayName: string
  description: string
  task: TaskType
  datasetId: string
  datasetVersion: string
  split: 'test'
  evaluator: string // 评测器名称
  evaluatorVersion: string
  metrics: MetricDef[]
  createdAt: string
  org: string
}

export type EvalStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'

export interface EvalRun {
  id: string
  algorithmId: string
  algoVersion: string
  benchmarkId: string
  status: EvalStatus
  progress: number // 0-100
  submittedBy: string
  submittedAt: string
  startedAt?: string
  finishedAt?: string
  metrics: Record<string, number>
  // 复现信息
  imageDigest: string
  weightsHash: string
  evaluatorVersion: string
  params: Record<string, string | number | boolean>
  hardware: string
  durationSec?: number
  peakGpuMemGB?: number
  latencyMs?: number // 单图平均推理耗时
  isLatestValid: boolean // 同一 算法版本×Benchmark 只有最新有效结果上榜
  perClass?: { label: string; value: number }[]
  /** 各类别分数的含义（缺省为「各类别 + 主指标」） */
  perClassLabel?: string
  /** 服务器故障检测标准：统一评测器输出的折线图数据 */
  vizServerFault?: import('@/components/serverfault/types').ServerFaultViz
  vizPowerForecast?: import('@/components/powerforecast/types').PfEvalVizData
  errorSamples?: { fileName: string; url: string; groundTruth: string; predicted: string; confidence: number }[]
  logs: string[]
  error?: string
}

// ---------- 推理 ----------
export interface DetBox {
  label: string
  score: number
  box: [number, number, number, number] // x, y, w, h（相对 0-1）
}
export interface ClsItem {
  label: string
  score: number
}
export interface SegRegion {
  label: string
  color: string
  polygon: [number, number][] // 相对 0-1
}
export interface InferenceResult {
  task: TaskType
  latencyMs: number
  queuedMs: number
  device: string
  classification?: ClsItem[]
  detections?: DetBox[]
  segments?: SegRegion[]
  outputImage?: string
  raw: unknown
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export interface ListQuery {
  q?: string
  task?: TaskType | ''
  business?: BusinessCategory | ''
  selfDeveloped?: 'only' | 'external' | ''
  tags?: string[]
  framework?: string
  org?: string
  sort?: 'trending' | 'updated' | 'likes' | 'evals'
  page?: number
  pageSize?: number
}

export interface QueueStatus {
  gpuName: string
  gpuMemTotal: number
  gpuMemUsed: number
  running: number
  queued: number
  warmContainers: { algorithmId: string; version: string; memGB: number; idleSec: number }[]
}
