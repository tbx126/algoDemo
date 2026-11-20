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

// 数据集：入库材料未提供数据集，暂为空；管理员可在“上传数据集”中添加（放在 Admin 命名空间）
const seeds: Seed[] = []

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
