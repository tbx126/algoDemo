/**
 * 入库算法：浙江锋云深蓝科技有限公司《六项巡检算法入库材料》（2026-11-18）
 * 数据来源：01 厂商材料与算法基础信息申报表、02 算法说明与使用边界、03 算法接口对接说明、
 *          04 模型说明与权重文件清单、05 部署运维与配置说明、06 六项算法原理说明。
 * 材料中未提供的信息（如算法分类编码、封面、性能压测、权重与镜像文件）保持为空，不做虚构。
 */
import type { AlgoDeclaration, AlgoFile, AlgoVersion, Algorithm, TaskType } from '@/types'
import { fakeSha } from '@/utils/format'

export const VENDOR_ID = 'FengyunShenlan'
const VENDOR_ZH = '锋云深蓝'
const SUBMITTED_AT = '2026-11-18T10:00:00+08:00'
const SUBMITTER = 'zhang.ll'
const IMAGE_TAG = 'inspection-six:0.1.0-cu126-20261118'
const MiB = 1024 * 1024

/** 六项算法共用的交付文档（入库材料包中的实际文件与大小） */
const DOCS: { key: string; file: string; size: number }[] = [
  { key: 'basicForm', file: '01_厂商材料与算法基础信息申报表.docx', size: 60425 },
  { key: 'manual', file: '02_算法说明与使用边界.docx', size: 48397 },
  { key: 'apiDoc', file: '03_算法接口对接说明.docx', size: 51691 },
  { key: 'modelDoc', file: '04_模型说明与12个权重文件清单.docx', size: 56024 },
  { key: 'deployManual', file: '05_部署运维与配置说明.docx', size: 54318 },
  { key: 'whitepaper', file: '06_六项算法原理说明.docx', size: 44898 },
]

/** 共用的输入与场景条件（02 说明“输入与场景条件”） */
const CONDITIONS = {
  pixel: '尚未确定生产适用的最小/最大分辨率与目标像素阈值',
  baffle: '目标完整、无遮挡；每个识别区域对应一个目标',
  image: '清晰；避免严重反光、过曝、运动模糊、强透视和过度缩图',
}

const REQUEST_EXAMPLE = '{"recognition_areas":[{"area_id":"1","x1":225,"y1":75,"x2":431,"y2":145}]}'

interface Seed {
  serviceCode: string
  fullName: string
  shortName: string
  target: string
  method: string
  task: TaskType
  output: string
  limit: string
  extraFields: string // 响应中的可选附加字段
  code: string[]
  models: { file: string; mib: number; structure: string; params: string; preprocess: string }[]
  outputMapping: string
  metrics: { name: string; value: string }[]
  labels: string[]
  resultExample: string
}

const SEEDS: Seed[] = [
  {
    serviceCode: 'LEDmeter',
    fullName: '红色LED数显识别',
    shortName: '红色数显',
    target: '红色LED数字及小数点',
    method: '数字定向框检测与横向排序',
    task: 'ocr',
    output: '数字字符串，保留小数点与前导零',
    limit: '需要清晰完整的数字窗口；反光、断笔或小数点过小可能漏检。',
    extraFields: '不返回置信度',
    code: ['Code/LED_algorithm.py'],
    models: [{ file: 'Model/LED_red.pt', mib: 5.41, structure: 'OBBModel', params: '2,663,652', preprocess: '按区域裁剪BGR图像，等比例缩放至高160，再由Ultralytics OBB预测器预处理；推理尺寸160。' }],
    outputMapping: '定向框、类别ID、检测置信度；以横向位置排序拼接。类别0～9为数字、10为point并映射为“.”。未检出为失败，不补0。',
    metrics: [{ name: '红色LED数显', value: 'P 97.14%；R 99.38%；mAP50 99.39%；mAP50–95 96.70%' }],
    labels: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '.'],
    resultExample: '"41.14"',
  },
  {
    serviceCode: 'lightningmetermechnicalcount',
    fullName: '避雷器电流表与放电计数识别',
    shortName: '电流表及计数',
    target: '避雷器电流指针表盘和放电计数窗口',
    method: '表盘检测与OCR几何读数；计数数字检测',
    task: 'ocr',
    output: '电流表为数值；放电计数为数字字符串',
    limit: '需分别配置完整表盘和计数窗口；现有计数样图014被识别为04。',
    extraFields: '不返回置信度',
    code: ['Code/full_algorithm_lightning.py', 'Code/mechanical_algorithm.py'],
    models: [
      { file: 'Model/lightning_meter.pt', mib: 5.62, structure: 'OBBModel（电流表检测）', params: '2,662,092', preprocess: '整表盘区域送入YOLO OBB；conf=0.3、iou=0.6。' },
      { file: 'Model/lightning_meter.pth', mib: 200.58, structure: 'ResCRNN（电流表OCR）', params: '17,512,310', preprocess: '文字框包围区域裁剪，BGR转RGB再灰度化；Resize为32×128；均值0.5、标准差0.5归一化，输入N×1×32×128。' },
      { file: 'Model/mechnical.pt', mib: 5.36, structure: 'OBBModel（放电计数）', params: '2,663,457', preprocess: '按区域裁剪，等比例缩放至高256；推理尺寸256。' },
    ],
    outputMapping: '表盘检测类别0=pointer、1=scale、2=text；OCR贪心CTC解码。计数类别0～9为数字，按横向位置拼接。',
    metrics: [
      { name: '避雷器电流表', value: 'P 96.82%；R 97.26%；mAP50 98.00%；mAP50–95 78.51%' },
      { name: '放电计数', value: 'P 89.32%；R 94.76%；mAP50 96.12%；mAP50–95 90.78%' },
    ],
    labels: ['pointer', 'scale', 'text'],
    resultExample: '0.42',
  },
  {
    serviceCode: 'terminalblock',
    fullName: '柱状压板状态识别',
    shortName: '柱状压板',
    target: '柱状压板投退外观',
    method: '图像分类',
    task: 'image-classification',
    output: 'On=1，Off=0，其他标签=2；附标签与分类置信度',
    limit: '一处区域对应一个压板；分类结果不能用作设备存在性判断。',
    extraFields: 'label、confidence',
    code: ['Code/terminal_block.py'],
    models: [{ file: 'Model/terminal_block.pt', mib: 2.83, structure: 'ClassificationModel', params: '1,440,850', preprocess: '区域BGR数组由Ultralytics分类预测器进行颜色转换、缩放/裁剪及张量处理；模型尺寸224。' }],
    outputMapping: '类别概率向量；0=Off、1=On，取top1；业务On→1、Off→0，其他标签→2。',
    metrics: [{ name: '柱状压板', value: 'Top-1 100.00%' }],
    labels: ['On', 'Off'],
    resultExample: '1',
  },
  {
    serviceCode: 'LEDlight',
    fullName: 'GIS汇控状态灯亮灭识别',
    shortName: 'GIS状态灯',
    target: 'GIS汇控柜指示灯',
    method: '图像分类与颜色亮灭解析',
    task: 'image-classification',
    output: '亮=1、灭=0；附颜色、原始标签和置信度',
    limit: '过曝、反光或环境光可能混淆亮灭；on/off标签对应空颜色字符串。',
    extraFields: 'label、color、confidence',
    code: ['Code/LED_light.py'],
    models: [{ file: 'Model/LED_light.pt', mib: 2.85, structure: 'ClassificationModel', params: '1,451,098', preprocess: '区域BGR数组由Ultralytics分类预测器处理；模型尺寸224。' }],
    outputMapping: '类别依次为greenoff、greenon、off、on、redoff、redon、whiteoff、whiteon、yellowoff、yellowon；解析末尾on/off，剩余前缀为color。',
    metrics: [{ name: 'GIS状态灯', value: 'Top-1 100.00%' }],
    labels: ['greenoff', 'greenon', 'off', 'on', 'redoff', 'redon', 'whiteoff', 'whiteon', 'yellowoff', 'yellowon'],
    resultExample: '1',
  },
  {
    serviceCode: 'openandcloseknob',
    fullName: '旋钮档位状态识别',
    shortName: '旋钮档位',
    target: '五类外观旋钮',
    method: '定向框检测与角度分档',
    task: 'object-detection',
    output: '从0开始的档位编号；附角度与检测置信度',
    limit: '外观模型与knobtype分别配置，档位文字含义需点位确认。',
    extraFields: 'angle、confidence',
    code: ['Code/knobrecognition.py'],
    models: [{ file: 'Model/knobopenandclose.pt', mib: 7.7, structure: 'OBBModel', params: '2,661,702', preprocess: '区域送入Ultralytics OBB，conf=0.5；各外观尺寸配置见模型结构与参数核对.json。' }],
    outputMapping: '每区域选择最高置信度框，几何长边计算角度，按knobtype阈值分档；结果等于严格大于阈值的数量。',
    metrics: [{ name: '开合旋钮', value: 'P 96.91%；R 97.06%；mAP50 98.28%；mAP50–95 97.53%' }],
    labels: ['旋钮'],
    resultExample: '1',
  },
  {
    serviceCode: 'outsideliquid',
    fullName: '主变油位识别',
    shortName: '主变油位',
    target: '主变油位显示区域',
    method: 'ResNet18类网络分类与偏移回归',
    task: 'image-classification',
    output: '一位小数读数；附类别、基础刻度、偏移和分类置信度',
    limit: '需现场核定刻度和单位；当前结果不自动转换为百分比或体积。',
    extraFields: 'class_id、class_value、offset、confidence',
    code: ['Code/liquidmeter_continuous_outside.py'],
    models: [{ file: 'Model/outsideliquid.pt', mib: 42.99, structure: 'GaugeResNet18', params: '11,251,026', preprocess: 'BGR转RGB；等比例缩放填充到128×320（BICUBIC，背景RGB(30,34,30)）；/255后按ImageNet均值方差归一化，输入N×3×320×128。' }],
    outputMapping: '输出logits[N,17]与offset[N,1]；类别对应1.0～9.0（步长0.5），偏移截断到[-0.7,0.7]，读数=基础刻度+偏移×0.5，保留一位小数。',
    metrics: [{ name: '主变油位', value: 'P 95.2%' }],
    labels: Array.from({ length: 17 }, (_, i) => (1 + i * 0.5).toFixed(1)),
    resultExample: '4.6',
  },
]

/** 06 六项算法原理说明（按算法摘录） */
const PRINCIPLES: Record<string, string> = {
  LEDmeter:
    '使用定向目标框检测数字。图像按固定高度等比例缩放，预测 conf=0.5、agnostic_nms=True，按检测框左侧横坐标排序，映射为字符并拼接；包含小数点类别。拼接后校验可形成有限数值，但返回字符串以保留前导零。没有补字、缺位纠正或固定长度填充，漏检可能形成合法但错误的数字串。',
  lightningmetermechnicalcount:
    '电流表：YOLO OBB 检测指针、刻度与文字，ResCRNN（残差卷积 + 双向 LSTM + LayerNorm，贪心 CTC 解码）识别刻度文本；通过刻度与文字的空间关系配对、拟合刻度圆弧、计算指针与刻度角度得到读数。指针候选按距图像中心距离选择；刻度不足、文字无法解析或几何条件不成立会影响结果；单位取决于表盘及点位语义，不做工程单位换算。放电计数：定向框检测数字，按横坐标排序拼接，只包含数字类别。',
  terminalblock:
    '对单目标区域做图像分类，取最高概率类别并映射 On / Off。分类概率仅描述给定输入上的类别响应，未训练设备存在性判定，非目标区域也可能得到高概率类别。',
  LEDlight:
    '对单目标区域做图像分类，以类别后缀 on / off 得到亮灭，以前缀得到颜色。分类概率仅描述给定输入上的类别响应，非目标区域也可能得到高概率类别。',
  openandcloseknob:
    '五个外观模型分别检测旋钮定向框，多个候选时取最高置信度目标；由定向框边长关系确定方向并计算角度，按 knobtype 阈值转换为从 0 开始的档位索引。不解析面板文字；相同角度规则不代表不同设备具有相同档位语义。',
  outsideliquid:
    'GaugeResNet18：卷积 stem 与四级残差块（每级两个 BasicBlock，通道 64/128/256/512），全局平均池化后分别接 17 类分类头与偏移回归头。分类头定位 0.5 间距的基础刻度，回归头在该刻度附近修正。模型不输出液体体积或百分比。',
}

/**
 * 算法卡片 = 面向使用者的说明文档：做什么、怎么调用、输出什么、效果如何、模型细节、已知局限。
 * 名称 / 标识 / 版本 / 厂商、使用要求与已知局限、运行环境与资源、性能规格属于结构化信息，只在“申报信息”中展示，这里不重复。
 */
function readme(s: Seed): string {
  const knob = s.serviceCode === 'openandcloseknob'
  return `# ${s.fullName}

识别${s.target}，返回${s.output}。

## 工作原理

${PRINCIPLES[s.serviceCode] ?? s.method}

## 调用方式

\`POST /Inspection_service_visible_light\`（multipart/form-data），按点位矩形区域逐区域返回结果；\`GET /health\` 查看服务状态与已加载模型。

| 字段 | 说明 |
| --- | --- |
| image | 当前图像，建议 JPEG / PNG |
| serviceCode | \`${s.serviceCode}\`（区分大小写） |
| recognition_config | JSON，含非空 recognition_areas 列表；区域编号不可重复 |
| tempImage | 可选模板图；提供时区域坐标基于模板，confidence=low 时需人工复核 |
${knob ? '| knobtype | 必填，0～6，角度分档规则（见下表） |\n' : ''}
\`\`\`json
${REQUEST_EXAMPLE}
\`\`\`

## 输出

\`\`\`json
{"code":200,"message":null,"success":true,"data":[{"area_id":"1","status":200,"result":${s.resultExample},"message":"识别成功"}]}
\`\`\`

- result：${s.output}；失败为 null（禁止默认记为 0）
- 可选附加字段：${s.extraFields}
- success 仅表示所有区域都返回了结果，不等于读数已通过真值核验
${
  knob
    ? `
### knobtype 角度分档

| knobtype | 角度阈值（度） | 结果范围 |
| --- | --- | --- |
| 0 | 30 | 0～1 |
| 1 | 0 | 0～1 |
| 2 | -30、30 | 0～2 |
| 3 | -15、15 | 0～2 |
| 4 | -23、23、65 | 0～3 |
| 5 | -67、-23、23、65 | 0～4 |
| 6 | -30 | 0～1 |

结果等于严格大于阈值的数量；恰等于阈值时归入较低档位。档位名称须由点位配置建立。
`
    : ''
}
## 性能

> 厂商自测指标，未经平台评测复核；平台评测成绩见右侧。

| 算法或子类型 | 指标 |
| --- | --- |
${s.metrics.map((m) => `| ${m.name} | ${m.value} |`).join('\n')}


## 模型

| 权重文件 | 结构 | 参数个数 |
| --- | --- | --- |
${s.models.map((m) => `| \`${m.file.replace('Model/', '')}\` | ${m.structure} | ${m.params} |`).join('\n')}

- 预处理：${s.models.map((m) => m.preprocess).join(' ')}
- 输出解析：${s.outputMapping}
- 精度：float32；未交付 FP16 / INT8 量化模型、ONNX 或 TensorRT 文件

> 使用要求与已知局限、运行环境与资源见“申报信息”；权重文件与镜像见“文件与版本”。
`
}

function declaration(s: Seed): AlgoDeclaration {
  return {
    packageInfo: { id: s.serviceCode, version: '0.1', vendor: { id: VENDOR_ID, zh_CN: VENDOR_ZH } },
    management: {
      id: s.serviceCode,
      name: { zh_CN: s.fullName },
      classifications: [], // 材料中“厂商及平台登记编码”为空，待平台分配
      places: ['新能源场站'],
      description: { zh_CN: `识别对象：${s.target}。技术路线：${s.method}。输出：${s.output}。` },
      cover: [], // 材料未提供封面
      conditions: { description: { zh_CN: { ...CONDITIONS, other: s.limit } } },
    },
    technical: {
      version: '0.1',
      analysisSources: [{ type: 'picture', format: ['jpg', 'png'] }],
      environment: {
        chip: 'NVIDIA GPU',
        basePackage: { id: 'cuda', minorVersion: '12.6', majorVersion: '12.6', relatedPodImageName: IMAGE_TAG },
        driver: { type: 'nvidia', minorVersion: 'R560', majorVersion: '' },
      },
      requirement: { videoMemory: 8192, disk: 40960, memory: 8192, AImemory: 0, CPU: 4 },
      abilityInfos: [], // 尚未完成目标 GPU 服务器压测
      regulation: { input: REQUEST_EXAMPLE, output: `{"area_id":"1","status":200,"result":${s.resultExample},"message":"识别成功"}`, eventCode: s.serviceCode },
    },
    params: {
      // 03 接口说明：未实现标准多边形、屏蔽区与规则区，也未限制区域数量
      generalParam: { enabled: false },
      detectRegion: false,
      maskRegion: false,
      ruleRegion: { enabled: false, crossDirections: [], polygonTypes: [] },
      numberCondition: false,
      sizeFilter: false,
      eventTypes: [s.serviceCode],
    },
    deliveries: DOCS.map((d) => ({ key: d.key, fileName: d.file, size: d.size })),
    checklist: ['m-overview', 'm-scene', 'm-io', 'm-perf', 'm-env', 'm-limit', 'd-params', 'd-weights', 'd-preprocess', 'd-output', 'd-quant', 'd-files'],
  }
}

function files(s: Seed): AlgoFile[] {
  return [
    ...s.code.map((p) => ({ path: p, size: 0, kind: 'code' as const })),
    ...s.models.map((m) => ({ path: m.file, size: Math.round(m.mib * MiB), kind: 'weights' as const })),
    ...DOCS.map((d) => ({ path: `docs/${d.file}`, size: d.size, kind: 'doc' as const })),
  ]
}

function version(s: Seed): AlgoVersion {
  return {
    version: 'v0.1',
    status: 'pending_review',
    createdAt: SUBMITTED_AT,
    createdBy: SUBMITTER,
    changelog: '首次入库（六项巡检算法入库材料 2026-11-18）',
    weightsSize: Math.round(s.models.reduce((a, m) => a + m.mib, 0) * MiB),
    baseImage: IMAGE_TAG,
    gpuMem: 8,
    buildLog: [
      '[review] 厂商入库材料已登记，等待管理员审核',
      `[review] 交付方式：GPU Docker 离线镜像 ${IMAGE_TAG}；本次材料包仅含 6 份文档，未包含镜像 tar 与权重文件`,
      '[review] 厂商说明：未执行本地 GPU 验证，尚未完成目标服务器压测',
    ],
  }
}

const CAT_DOG_ALGO: Algorithm = {
  id: 'Admin/cat-dog-classifier',
  org: 'Admin',
  name: 'cat-dog-classifier',
  task: 'image-classification',
  business: 'security',
  framework: 'PyTorch',
  tags: ['猫狗识别', '图像分类', '基线算法', '安防周界'],
  summary: '猫狗二分类图像识别算法，用于周界安防小动物误报过滤与宠物识别，提供 MobileNetV3 / ResNet-50+SE / ConvNeXt-Tiny 三个演进版本。',
  readme: `# 猫狗图像识别（cat-dog-classifier）

基于深度卷积网络的猫狗二分类算法，面向场站周界安防误报过滤与通用图像识别场景，支持输出 \`猫\` / \`狗\` 类别与置信度。

## 版本路线说明

本算法包含三个依次演进的版本，涵盖轻量化基线、注意力改进与现代主干网络三条技术路线：

| 版本 | 技术路线 | 输入尺寸 | 显存占用 | 评测状态 |
| --- | --- | --- | --- | --- |
| \`v1.0.0\` | MobileNetV3-Large 轻量级基线 | 224×224 | 1.5 GB | 已评测 |
| \`v2.0.0\` | ResNet-50 + SE 通道注意力 + 光照/裁剪增强 | 256×256 | 3.2 GB | 已评测 |
| \`v3.0.0\` | ConvNeXt-Tiny + Mixup / 余弦退火（夜间与遮挡优化） | 288×288 | 4.0 GB | 暂未评测 |

## 调用方式

输入单张 RGB 图像（JPEG / PNG），返回按置信度降序排列的类别概率。

\`\`\`python
from predictor import Predictor

model = Predictor(weights="weights/convnext_tiny_catdog_v3.pt")
result = model.predict("sample.jpg")
# {"predictions": [{"label": "猫", "score": 0.9842}, {"label": "狗", "score": 0.0158}]}
\`\`\`

## 输出格式

\`\`\`json
{
  "predictions": [
    { "label": "猫", "score": 0.9842 },
    { "label": "狗", "score": 0.0158 }
  ]
}
\`\`\`

## 适用边界

- 建议目标主体占画面面积不低于 10%，避免极端运动模糊；
- \`v3.0.0\` 针对弱光与局部遮挡场景进行了数据增强，待平台评测基准验证后作为推荐生产版本。
`,
  likes: 12,
  evalCount: 2,
  updatedAt: '2026-11-20T09:30:00+08:00',
  labels: ['猫', '狗'],
  sampleImages: ['/datasets/cat-dog/cat_01.jpg', '/datasets/cat-dog/dog_01.jpg', '/datasets/cat-dog/cat_02.jpg'],
  versions: [
    {
      version: 'v3.0.0',
      status: 'ready',
      createdAt: '2026-11-20T09:30:00+08:00',
      createdBy: 'admin',
      changelog: '切换至 ConvNeXt-Tiny 主干网络，引入 Mixup / CutMix 与余弦退火调度，重点优化夜间低照度与遮挡场景识别（暂未评测）',
      imageDigest: 'sha256:' + fakeSha('Admin/cat-dog-classifier-v3.0.0-image'),
      weightsHash: 'sha256:' + fakeSha('Admin/cat-dog-classifier-v3.0.0-weights'),
      weightsSize: Math.round(112.4 * MiB),
      baseImage: 'algohub/pytorch:2.4-cuda12.1',
      gpuMem: 4,
      buildLog: [
        '[build] 管理员提交 v3.0.0，免审核直接进入构建队列',
        '[build] 导入镜像 algohub/pytorch:2.4-cuda12.1',
        '[build] 校验权重 weights/convnext_tiny_catdog_v3.pt 与 algo.yaml …… OK',
        '[build] 冒烟测试（288×288 FP32 推理） …… OK',
        '[build] 构建完成，版本可用（尚未发起评测）',
      ],
    },
    {
      version: 'v2.0.0',
      status: 'ready',
      createdAt: '2026-11-19T14:20:00+08:00',
      createdBy: 'admin',
      changelog: '升级主干为 ResNet-50 + SE 通道注意力模块，增加随机裁剪与光照抖动数据增强，显著提升复杂背景下的分类精度',
      imageDigest: 'sha256:' + fakeSha('Admin/cat-dog-classifier-v2.0.0-image'),
      weightsHash: 'sha256:' + fakeSha('Admin/cat-dog-classifier-v2.0.0-weights'),
      weightsSize: Math.round(98.6 * MiB),
      baseImage: 'algohub/pytorch:2.4-cuda12.1',
      gpuMem: 3.2,
      buildLog: [
        '[build] 管理员提交 v2.0.0，免审核直接进入构建队列',
        '[build] 导入镜像 algohub/pytorch:2.4-cuda12.1',
        '[build] 校验权重 weights/resnet50_se_catdog_v2.pt 与 algo.yaml …… OK',
        '[build] 冒烟测试（256×256 FP32 推理） …… OK',
        '[build] 构建完成，版本可用',
      ],
    },
    {
      version: 'v1.0.0',
      status: 'ready',
      createdAt: '2026-11-18T16:00:00+08:00',
      createdBy: 'admin',
      changelog: '初始基线版本：采用 MobileNetV3-Large 轻量级卷积网络，主打低显存占用与边缘端高速推理',
      imageDigest: 'sha256:' + fakeSha('Admin/cat-dog-classifier-v1.0.0-image'),
      weightsHash: 'sha256:' + fakeSha('Admin/cat-dog-classifier-v1.0.0-weights'),
      weightsSize: Math.round(21.5 * MiB),
      baseImage: 'algohub/pytorch:2.4-cuda12.1',
      gpuMem: 1.5,
      buildLog: [
        '[build] 管理员提交 v1.0.0，免审核直接进入构建队列',
        '[build] 导入镜像 algohub/pytorch:2.4-cuda12.1',
        '[build] 校验权重 weights/mobilenetv3_catdog_v1.pt 与 algo.yaml …… OK',
        '[build] 冒烟测试（224×224 FP32 推理） …… OK',
        '[build] 构建完成，版本可用',
      ],
    },
  ],
  files: [
    { path: 'algo.yaml', size: 468, kind: 'config' },
    { path: 'predictor.py', size: 3420, kind: 'code' },
    { path: 'models/convnext_tiny.py', size: 6180, kind: 'code' },
    { path: 'weights/convnext_tiny_catdog_v3.pt', size: Math.round(112.4 * MiB), kind: 'weights' },
    { path: 'README.md', size: 1580, kind: 'doc' },
  ],
  algoYaml: `name: cat-dog-classifier
version: 3.0.0
task: image-classification
business: security
framework: PyTorch
entry: predictor:Predictor
base_image: algohub/pytorch:2.4-cuda12.1
input:
  size: [288, 288]
  channels: 3
resources:
  gpu_mem: 4GB
  cpu: 4
  memory: 8GB
weights:
  - weights/convnext_tiny_catdog_v3.pt
`,
}

export const algorithms: Algorithm[] = [
  CAT_DOG_ALGO,
  ...SEEDS.map((s) => ({
    id: `${VENDOR_ID}/${s.serviceCode}`,
    org: VENDOR_ID,
    name: s.serviceCode,
    task: s.task,
    business: 'inspection' as const,
    framework: 'PyTorch' as const,
    tags: ['新能源场站', '可见光巡检', s.shortName],
    summary: `${s.fullName}：${s.method}，输出${s.output}。`,
    readme: readme(s),
    likes: 0,
    evalCount: 0,
    updatedAt: SUBMITTED_AT,
    versions: [version(s)],
    files: files(s),
    algoYaml: `name: ${s.serviceCode}
version: 0.1
task: ${s.task}
framework: PyTorch
entry: service.py
service_code: ${s.serviceCode}
base_image: ${IMAGE_TAG}
http:
  port: 6899
  path: /Inspection_service_visible_light
resources:
  gpu_mem: 8GB
  cpu: 4
  memory: 8GB
  disk: 40GB
weights:
${s.models.map((m) => `  - ${m.file}  # ${m.mib} MiB`).join('\n')}
`,
    labels: s.labels,
    declaration: declaration(s),
  })),
]
