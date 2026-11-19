import type { Dataset, DatasetPart, DatasetVersion, SplitName, TaskType } from '@/types'
import { fakeSha, rng, hashStr } from '@/utils/format'
import { labelSpec } from '@/utils/labels'

interface Seed {
  org: string
  name: string
  task: TaskType
  summary: string
  classes: string[]
  counts: [number, number] // [训练集, 测试集] 文件数
  annPer: number // 平均每个文件的标注行数
  size: number // GB（训练集）
  versions: number
  tags: string[]
  conditions: string[] // labels.csv 中的可选条件列
  likes: number
  downloads: number
  updatedAt: string
  noTest?: boolean
}

const seeds: Seed[] = [
  { org: 'Admin', name: 'factory-defect-cls', task: 'image-classification', summary: '产线表面缺陷 6 分类数据集，覆盖划痕、凹坑、污渍等典型缺陷。', classes: ['正常', '划痕', '凹坑', '污渍', '裂纹', '气泡'], counts: [20400, 3600], annPer: 1, size: 4.2, versions: 3, tags: ['工业质检', '缺陷'], conditions: ['light'], likes: 86, downloads: 1240, updatedAt: '2026-11-10T10:00:00+08:00' },
  { org: 'Admin', name: 'street-objects-det', task: 'object-detection', summary: '城市街景通用目标检测，12 类常见目标。', classes: ['行人', '自行车', '汽车', '摩托车', '公交车', '卡车', '交通灯', '路牌', '狗', '背包', '雨伞', '手推车'], counts: [47000, 6000], annPer: 7.4, size: 18.6, versions: 4, tags: ['街景', '通用检测'], conditions: ['weather', 'light'], likes: 214, downloads: 3980, updatedAt: '2026-11-15T10:00:00+08:00' },
  { org: 'Admin', name: 'road-scene-seg', task: 'semantic-segmentation', summary: '道路场景语义分割，8 类像素级标注，1024×512 分辨率。', classes: ['道路', '人行道', '建筑', '植被', '天空', '车辆', '行人', '其他'], counts: [5500, 1000], annPer: 1, size: 9.8, versions: 2, tags: ['自动驾驶', '分割'], conditions: ['weather', 'light'], likes: 131, downloads: 1870, updatedAt: '2026-10-28T10:00:00+08:00' },
  { org: 'Admin', name: 'traffic-vehicles-det', task: 'object-detection', summary: '路口监控视角车辆检测，含大量小目标与夜间场景。', classes: ['轿车', 'SUV', '公交车', '货车', '两轮车', '三轮车'], counts: [29000, 4000], annPer: 11.2, size: 12.1, versions: 3, tags: ['交通', '小目标', '夜间'], conditions: ['weather', 'light', 'occlusion'], likes: 57, downloads: 640, updatedAt: '2026-11-18T10:00:00+08:00' },
  { org: 'Admin', name: 'cell-nuclei-seg', task: 'instance-segmentation', summary: '病理切片细胞核实例分割，专家逐个勾画。', classes: ['细胞核'], counts: [1350, 300], annPer: 1, size: 2.3, versions: 2, tags: ['医学', '病理', '实例分割'], conditions: [], likes: 22, downloads: 80, updatedAt: '2026-09-30T10:00:00+08:00' },
  { org: 'Admin', name: 'shelf-products-cls', task: 'image-classification', summary: '货架商品细粒度分类（示例 5 个 SKU）。', classes: ['SKU-001 矿泉水', 'SKU-002 可乐', 'SKU-003 薯片', 'SKU-004 饼干', 'SKU-005 方便面'], counts: [66000, 8000], annPer: 1, size: 7.5, versions: 2, tags: ['零售', '细粒度'], conditions: [], likes: 34, downloads: 290, updatedAt: '2026-11-02T10:00:00+08:00' },
  { org: 'Admin', name: 'pose-keypoints', task: 'keypoint-detection', summary: '人体检测与关键点数据集（框级标注）。', classes: ['人体'], counts: [16500, 2000], annPer: 2.1, size: 6.0, versions: 1, tags: ['姿态估计'], conditions: [], likes: 48, downloads: 520, updatedAt: '2026-08-21T10:00:00+08:00', noTest: true },
  { org: 'Admin', name: 'invoice-ocr', task: 'ocr', summary: '票据文字行检测，含行级文本框。', classes: ['文本行'], counts: [8800, 1200], annPer: 23, size: 3.1, versions: 2, tags: ['OCR', '票据'], conditions: [], likes: 29, downloads: 210, updatedAt: '2026-10-11T10:00:00+08:00' },
  { org: 'Admin', name: 'vibration-signals', task: 'signal-processing', summary: '旋转机械振动信号，正常 / 三类故障分类。', classes: ['正常', '内圈故障', '外圈故障', '滚动体故障'], counts: [4500, 1000], annPer: 1, size: 1.4, versions: 3, tags: ['故障诊断', '时序'], conditions: ['device', 'speed_rpm'], likes: 41, downloads: 330, updatedAt: '2026-11-06T10:00:00+08:00' },
  { org: 'Admin', name: 'vrp-instances', task: 'optimization', summary: '带时间窗车辆路径问题（VRPTW）实例集，含已知最优解。', classes: ['实例'], counts: [120, 300], annPer: 1, size: 0.05, versions: 1, tags: ['运筹优化', 'VRP'], conditions: ['vehicles'], likes: 19, downloads: 150, updatedAt: '2026-07-14T10:00:00+08:00' },
]

const ADMINS = ['chen.wei', 'li.na', 'zhao.lei', 'wu.hao']

function readme(s: Seed, columns: string[]): string {
  const spec = labelSpec(s.task)
  return `# ${s.name}

${s.summary}

## 组成

| 部分 | 文件数 | 说明 |
| --- | --- | --- |
| 训练集 | ${s.counts[0].toLocaleString()} | 所有账号可下载 |
| 测试集 | ${s.noTest ? '未上传' : s.counts[1].toLocaleString()} | **仅管理员可查看与下载**，厂商只能在其上发起评测 |

## 文件结构

训练集与测试集结构一致：

\`\`\`
train/
├── images/          # ${spec.dataExt === 'jpg' ? '图片' : '数据文件'}
${s.task.includes('segmentation') ? '├── masks/           # 掩码 PNG，像素值为类别序号\n' : ''}└── labels.csv       # 真值
test/
└── （同上）
\`\`\`

## labels.csv

${spec.desc}。表头：

\`\`\`
${columns.join(',')}
\`\`\`

${s.conditions.length ? `其中 \`${s.conditions.join('`、`')}\` 为条件列，评测结果可按这些条件拆分。` : ''}

## 类别

${s.classes.map((c) => `- ${c}`).join('\n')}

## 采集与标注

- 采集时间：2025 年 Q3 – 2026 年 Q3
- 标注方式：双人独立标注 + 专家仲裁
- 训练集与测试集已按图片哈希去重，无重叠
`
}

function part(s: Seed, name: SplitName, i: number, columns: string[]): DatasetPart {
  const files = s.counts[name === 'train' ? 0 : 1]
  const versions: DatasetVersion[] = Array.from({ length: s.versions }, (_, k) => {
    const v = s.versions - k
    const shrink = 1 - k * 0.08
    return {
      version: `v${v}.0`,
      createdAt: new Date(new Date(s.updatedAt).getTime() - k * 86400000 * 47 - (name === 'test' ? 86400000 : 0)).toISOString(),
      createdBy: ADMINS[(i + k + (name === 'test' ? 1 : 0)) % ADMINS.length],
      contentHash: 'sha256:' + fakeSha(`${s.name}-${name}-${v}`),
      sizeBytes: Math.round(s.size * 1024 ** 3 * (name === 'train' ? 1 : files / s.counts[0]) * shrink),
      note: k === 0 ? (name === 'test' ? '补充夜间与遮挡难例' : '修正部分错误标注，新增难例样本') : k === s.versions - 1 ? '首个版本' : name === 'test' ? '扩充测试样本' : '扩充训练集',
      files: Math.round(files * shrink),
      rows: Math.round(files * s.annPer * shrink),
    }
  })
  // 类别分布：带一定长尾
  const r = rng(hashStr(s.name + name))
  const weights = s.classes.map((_, k) => (1 / (k + 1.2)) * (0.7 + r() * 0.6))
  const sum = weights.reduce((a, b) => a + b, 0)
  const total = versions[0].rows
  const classCounts = Object.fromEntries(s.classes.map((c, k) => [c, Math.round((weights[k] / sum) * total)]))
  return { name, columns, versions, classCounts }
}

export const datasets: Dataset[] = seeds.map((s, i) => {
  const spec = labelSpec(s.task)
  const columns = [...spec.required, ...s.conditions]
  return {
    id: `${s.org}/${s.name}`,
    org: s.org,
    name: s.name,
    task: s.task,
    tags: s.tags,
    summary: s.summary,
    readme: readme(s, columns),
    classes: s.classes,
    train: part(s, 'train', i, columns),
    test: s.noTest ? null : part(s, 'test', i, columns),
    likes: s.likes,
    downloads: s.downloads,
    updatedAt: s.updatedAt,
    previewSeed: 1000 + i * 37,
  }
})
