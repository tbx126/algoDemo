import type { AlgoVersion, AlgoVersionStatus, Algorithm, Framework, TaskType } from '@/types'
import { datasets } from './datasets'
import { fakeSha } from '@/utils/format'

interface Seed {
  org: string
  name: string
  task: TaskType
  framework: Framework
  license: string
  summary: string
  tags: string[]
  likes: number
  updatedAt: string
  versions: [string, AlgoVersionStatus][] // 最新在前
  gpuMem: number
  weightsMB: number
  datasetId?: string // 训练所用数据集，决定推理组件的类别
  paper?: string
}

const S: Seed[] = [
  { org: 'vision-lab', name: 'resnet50-defect', task: 'image-classification', framework: 'PyTorch', license: 'Apache-2.0', summary: 'ResNet-50 基线，ImageNet 预训练后在缺陷数据上微调。', tags: ['基线', '工业质检'], likes: 64, updatedAt: '2026-11-12T10:00:00+08:00', versions: [['v1.2.0', 'ready'], ['v1.1.0', 'ready'], ['v1.0.0', 'ready']], gpuMem: 1.6, weightsMB: 98, datasetId: 'Admin/factory-defect-cls', paper: 'https://arxiv.org/abs/1512.03385' },
  { org: 'vision-lab', name: 'efficientnet-b3-defect', task: 'image-classification', framework: 'PyTorch', license: 'Apache-2.0', summary: 'EfficientNet-B3，精度与速度均衡，适合产线边缘部署。', tags: ['轻量', '工业质检'], likes: 41, updatedAt: '2026-11-08T10:00:00+08:00', versions: [['v2.0.0', 'ready'], ['v1.0.0', 'ready']], gpuMem: 1.4, weightsMB: 47, datasetId: 'Admin/factory-defect-cls', paper: 'https://arxiv.org/abs/1905.11946' },
  { org: 'vision-lab', name: 'vit-small-defect', task: 'image-classification', framework: 'PyTorch', license: 'Apache-2.0', summary: 'ViT-S/16，自监督预训练，对细微缺陷更敏感。', tags: ['Transformer', '工业质检'], likes: 23, updatedAt: '2026-11-16T10:00:00+08:00', versions: [['v0.3.0', 'building'], ['v0.2.0', 'ready']], gpuMem: 2.2, weightsMB: 86, datasetId: 'Admin/factory-defect-cls', paper: 'https://arxiv.org/abs/2010.11929' },
  { org: 'univ-cvlab', name: 'convnext-t-defect', task: 'image-classification', framework: 'PyTorch', license: 'MIT', summary: '启明视觉提交的 ConvNeXt-T 方案，加入纹理增强。', tags: ['厂商提交', '工业质检'], likes: 12, updatedAt: '2026-11-18T10:00:00+08:00', versions: [['v1.1.0', 'pending_review'], ['v1.0.0', 'ready']], gpuMem: 2.0, weightsMB: 110, datasetId: 'Admin/factory-defect-cls', paper: 'https://arxiv.org/abs/2201.03545' },
  { org: 'vision-lab', name: 'mobilenetv3-defect', task: 'image-classification', framework: 'ONNX', license: 'Apache-2.0', summary: 'MobileNetV3-Large 导出 ONNX，CPU 也可实时推理。', tags: ['轻量', 'ONNX'], likes: 30, updatedAt: '2026-10-20T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 0.6, weightsMB: 21, datasetId: 'Admin/factory-defect-cls' },
  { org: 'vision-lab', name: 'yolo-lite-s', task: 'object-detection', framework: 'PyTorch', license: 'Apache-2.0', summary: '单阶段 Anchor-free 检测器 S 规格，团队通用检测基线。', tags: ['实时', '基线'], likes: 152, updatedAt: '2026-11-17T10:00:00+08:00', versions: [['v3.1.0', 'ready'], ['v3.0.0', 'ready'], ['v2.0.0', 'ready']], gpuMem: 2.4, weightsMB: 36, datasetId: 'Admin/street-objects-det' },
  { org: 'vision-lab', name: 'rtdetr-r18', task: 'object-detection', framework: 'PyTorch', license: 'Apache-2.0', summary: '实时 DETR 类检测器，ResNet-18 骨干，无需 NMS。', tags: ['DETR', '实时'], likes: 98, updatedAt: '2026-11-14T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 3.1, weightsMB: 80, datasetId: 'Admin/street-objects-det', paper: 'https://arxiv.org/abs/2304.08069' },
  { org: 'vision-lab', name: 'faster-rcnn-r50-fpn', task: 'object-detection', framework: 'PyTorch', license: 'Apache-2.0', summary: '经典两阶段检测器，作为精度参照。', tags: ['两阶段', '基线'], likes: 77, updatedAt: '2026-09-02T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 3.8, weightsMB: 167, datasetId: 'Admin/street-objects-det', paper: 'https://arxiv.org/abs/1506.01497' },
  { org: 'smart-city', name: 'yolo-lite-n-traffic', task: 'object-detection', framework: 'TensorRT', license: 'Internal', summary: '面向路口摄像头的 N 规格检测器，TensorRT FP16 部署。', tags: ['交通', 'TensorRT', '边缘'], likes: 45, updatedAt: '2026-11-18T10:00:00+08:00', versions: [['v2.2.0', 'ready'], ['v2.1.0', 'ready']], gpuMem: 1.1, weightsMB: 12, datasetId: 'Admin/traffic-vehicles-det' },
  { org: 'deepsee', name: 'tiled-small-det', task: 'object-detection', framework: 'PyTorch', license: 'Internal', summary: '深鉴智能提交：切片推理 + 融合策略，专攻远距离小目标。', tags: ['厂商提交', '小目标', '交通'], likes: 28, updatedAt: '2026-11-11T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 4.6, weightsMB: 140, datasetId: 'Admin/traffic-vehicles-det' },
  { org: 'partner-xyz', name: 'xy-det-tiny', task: 'object-detection', framework: 'ONNX', license: 'Proprietary', summary: '星衍科技提交的轻量检测模型（ONNX）。', tags: ['厂商提交', 'ONNX'], likes: 9, updatedAt: '2026-11-19T08:30:00+08:00', versions: [['v1.1.0', 'pending_review'], ['v1.0.0', 'ready']], gpuMem: 0.9, weightsMB: 18, datasetId: 'Admin/street-objects-det' },
  { org: 'partner-xyz', name: 'xy-seg-lite', task: 'semantic-segmentation', framework: 'ONNX', license: 'Proprietary', summary: '星衍科技提交的轻量道路分割模型，面向车载边缘设备。', tags: ['厂商提交', '分割', '边缘'], likes: 6, updatedAt: '2026-11-15T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 0.8, weightsMB: 14, datasetId: 'Admin/road-scene-seg' },
  { org: 'vision-lab', name: 'unet-r34-road', task: 'semantic-segmentation', framework: 'PyTorch', license: 'MIT', summary: 'U-Net + ResNet-34 编码器的道路分割基线。', tags: ['基线', '分割'], likes: 58, updatedAt: '2026-10-25T10:00:00+08:00', versions: [['v1.1.0', 'ready'], ['v1.0.0', 'ready']], gpuMem: 2.0, weightsMB: 98, datasetId: 'Admin/road-scene-seg', paper: 'https://arxiv.org/abs/1505.04597' },
  { org: 'vision-lab', name: 'deeplabv3plus-r50', task: 'semantic-segmentation', framework: 'PyTorch', license: 'Apache-2.0', summary: 'DeepLabV3+，空洞卷积 + 解码器。', tags: ['分割'], likes: 66, updatedAt: '2026-10-30T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 3.4, weightsMB: 160, datasetId: 'Admin/road-scene-seg', paper: 'https://arxiv.org/abs/1802.02611' },
  { org: 'vision-lab', name: 'segformer-b2', task: 'semantic-segmentation', framework: 'PyTorch', license: 'Apache-2.0', summary: 'SegFormer-B2，层级 Transformer 编码器 + 轻量 MLP 解码。', tags: ['Transformer', '分割'], likes: 89, updatedAt: '2026-11-13T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 3.0, weightsMB: 105, datasetId: 'Admin/road-scene-seg', paper: 'https://arxiv.org/abs/2105.15203' },
  { org: 'smart-city', name: 'bisenet-v2-road', task: 'semantic-segmentation', framework: 'PyTorch', license: 'Internal', summary: '双分支实时分割网络，最新版本构建失败待修复。', tags: ['实时', '分割'], likes: 14, updatedAt: '2026-11-19T07:10:00+08:00', versions: [['v1.1.0', 'failed'], ['v1.0.0', 'ready']], gpuMem: 1.2, weightsMB: 25, datasetId: 'Admin/road-scene-seg' },
  { org: 'medical-ai', name: 'mask-rcnn-nuclei', task: 'instance-segmentation', framework: 'PyTorch', license: 'Internal', summary: 'Mask R-CNN 细胞核实例分割。', tags: ['医学', '实例分割'], likes: 8, updatedAt: '2026-09-29T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 3.6, weightsMB: 170, datasetId: 'Admin/cell-nuclei-seg' },
  { org: 'medical-ai', name: 'star-nuclei-net', task: 'instance-segmentation', framework: 'PyTorch', license: 'Internal', summary: '星形多边形表示的细胞核分割，对粘连核更鲁棒。', tags: ['医学', '实例分割'], likes: 11, updatedAt: '2026-10-05T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 1.8, weightsMB: 25, datasetId: 'Admin/cell-nuclei-seg' },
  { org: 'signal-team', name: 'fft-envelope-svm', task: 'signal-processing', framework: 'NumPy', license: 'Internal', summary: '包络谱特征 + SVM 的传统故障诊断方案，无需 GPU。', tags: ['传统算法', 'CPU'], likes: 21, updatedAt: '2026-11-05T10:00:00+08:00', versions: [['v2.0.0', 'ready'], ['v1.0.0', 'ready']], gpuMem: 0, weightsMB: 1, datasetId: 'Admin/vibration-signals' },
  { org: 'signal-team', name: 'cnn1d-fault', task: 'signal-processing', framework: 'PyTorch', license: 'Internal', summary: '一维卷积网络端到端故障分类。', tags: ['深度学习', '时序'], likes: 17, updatedAt: '2026-11-07T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 0.5, weightsMB: 4, datasetId: 'Admin/vibration-signals' },
  { org: 'signal-team', name: 'alns-vrptw', task: 'optimization', framework: 'NumPy', license: 'MIT', summary: '自适应大邻域搜索求解带时间窗车辆路径问题。', tags: ['运筹优化', '启发式'], likes: 15, updatedAt: '2026-07-20T10:00:00+08:00', versions: [['v1.0.0', 'ready']], gpuMem: 0, weightsMB: 0, datasetId: 'Admin/vrp-instances' },
]

const baseImage = (f: Framework) =>
  f === 'TensorRT' ? 'algohub/tensorrt:10.3-cuda12.4' : f === 'ONNX' ? 'algohub/onnxruntime-gpu:1.19-cuda12.1' : f === 'NumPy' ? 'algohub/python-cpu:3.11' : 'algohub/pytorch:2.4-cuda12.1'

function readme(s: Seed, labels: string[]): string {
  return `# ${s.name}

${s.summary}

## 模型说明

- **任务**：${s.task}
- **框架**：${s.framework}
- **输入**：RGB 图像（自动缩放），${s.task.includes('segmentation') ? '输出逐像素类别 / 实例掩码' : s.task === 'object-detection' ? '输出边界框、类别与置信度' : '输出类别概率'}
- **资源声明**：显存 ${s.gpuMem} GB（见 \`algo.yaml\`）
${s.paper ? `- **参考论文**：[${s.paper}](${s.paper})\n` : ''}
## 类别

${labels.slice(0, 8).map((l) => `\`${l}\``).join(' · ')}${labels.length > 8 ? ' …' : ''}

## 接口实现

本算法按平台 SDK 规范实现 \`load()\` 与 \`predict()\`，同一份代码同时用于 **批量评测** 与 **单图推理**：

\`\`\`python
from algohub_sdk import BasePredictor, Image

class Predictor(BasePredictor):
    def load(self, weights_dir: str):
        self.model = build_model(weights_dir)

    def predict(self, image: Image) -> dict:
        return self.model(image)
\`\`\`

## 训练细节

| 项 | 值 |
| --- | --- |
| 训练数据 | \`${s.datasetId ?? '—'}\` |
| 输入尺寸 | ${s.task === 'object-detection' ? '640×640' : s.task.includes('segmentation') ? '1024×512' : '224×224'} |
| 优化器 | AdamW, lr=1e-3, cosine |
| Epochs | ${s.task === 'object-detection' ? 300 : 100} |

## 已知局限

- 对极端光照、强反光场景的效果下降明显。
- 未在夜间红外图像上验证。
`
}

export const algorithms: Algorithm[] = S.map((s, i) => {
  const ds = datasets.find((d) => d.id === s.datasetId)
  const labels = ds ? ds.classes.filter((c) => !c.startsWith('……')) : ['目标']
  const versions: AlgoVersion[] = s.versions.map(([v, status], k) => {
    const created = new Date(new Date(s.updatedAt).getTime() - k * 86400000 * 23).toISOString()
    const hasImage = status === 'ready'
    const log = [
      `[build] 拉取基础镜像 ${baseImage(s.framework)}`,
      `[build] 校验 algo.yaml …… OK`,
      `[build] 安装依赖 requirements.txt（${12 + (i % 7)} 个包）`,
      `[build] 复制代码与入口 predictor:Predictor`,
    ]
    if (status === 'ready') log.push('[build] 冒烟测试：predict(sample.jpg) …… OK', `[build] 推送镜像 sha256:${fakeSha(s.name + v).slice(0, 12)}…`, '[build] 完成，用时 3m12s')
    if (status === 'failed') log.push('[build] 冒烟测试：predict(sample.jpg)', "[error] ModuleNotFoundError: No module named 'mmcv._ext'", '[error] 构建失败：请检查依赖版本是否与基础镜像 CUDA 版本匹配')
    if (status === 'building') log.push('[build] 安装依赖中 … (47%)')
    if (status === 'pending_review') log.splice(0, log.length, '[review] 外部提交，等待管理员审核后开始构建')
    return {
      version: v,
      status,
      createdAt: created,
      createdBy: s.org === 'partner-xyz' ? 'xy.liu' : s.org === 'univ-cvlab' ? 'qm.he' : s.org === 'deepsee' ? 'ds.zhang' : ['chen.wei', 'li.na', 'zhao.lei', 'wang.fang', 'sun.yu', 'wu.hao'][i % 6],
      changelog: k === 0 ? (status === 'failed' ? '升级到新版算子库' : '优化后处理阈值，提升召回') : k === s.versions.length - 1 ? '首次发布' : '数据增强策略调整',
      imageDigest: hasImage ? 'sha256:' + fakeSha(s.name + v) : undefined,
      weightsHash: 'sha256:' + fakeSha('w' + s.name + v),
      weightsSize: s.weightsMB * 1024 * 1024,
      baseImage: baseImage(s.framework),
      gpuMem: s.gpuMem,
      buildLog: log,
    }
  })
  const latest = s.versions[0][0].slice(1)
  const algoYaml = `name: ${s.name}
version: ${latest}
task: ${s.task}
framework: ${s.framework}
entry: predictor:Predictor
base_image: ${baseImage(s.framework)}
resources:
  gpu_mem: ${s.gpuMem}GB
  cpu: 4
  memory: 8GB
weights:
  - uri: store://weights/${s.org}/${s.name}/${latest}/model.${s.framework === 'ONNX' ? 'onnx' : s.framework === 'TensorRT' ? 'engine' : 'pth'}
    sha256: ${fakeSha('w' + s.name + s.versions[0][0]).slice(0, 16)}…
labels: [${labels.slice(0, 6).join(', ')}${labels.length > 6 ? ', …' : ''}]
`
  return {
    id: `${s.org}/${s.name}`,
    org: s.org,
    name: s.name,
    task: s.task,
    framework: s.framework,
    license: s.license,
    tags: s.tags,
    summary: s.summary,
    readme: readme(s, labels),
    paperUrl: s.paper,
    likes: s.likes,
    evalCount: 0,
    updatedAt: s.updatedAt,
    versions,
    algoYaml,
    labels,
    files: [
      { path: 'algo.yaml', size: 612, kind: 'config' },
      { path: 'README.md', size: 4200 + i * 31, kind: 'doc' },
      { path: 'predictor.py', size: 3100 + i * 57, kind: 'code' },
      { path: 'model/', size: 18000 + i * 200, kind: 'code' },
      { path: 'requirements.txt', size: 220, kind: 'config' },
      ...(s.weightsMB > 0 ? [{ path: `weights/model.${s.framework === 'ONNX' ? 'onnx' : s.framework === 'TensorRT' ? 'engine' : 'pth'}`, size: s.weightsMB * 1024 * 1024, kind: 'weights' as const }] : []),
    ],
  }
})

export const algoSeedsGpu = Object.fromEntries(S.map((s) => [`${s.org}/${s.name}`, s.gpuMem]))
