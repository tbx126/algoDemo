/**
 * 《智能运维平台算法中心算法标准 1.0》相关常量、校验与描述文件生成。
 * 字段名、必选/可选与最大长度（字节）均取自标准原文。
 */
import type { AlgoDeclaration, ManagementInfo, SourceType, TechnicalInfo } from '@/types'

/** 标准中“最大长度”按字节计：使用 UTF-8 计算（中文 3 字节） */
export function byteLen(s: string | undefined): number {
  return s ? new TextEncoder().encode(s).length : 0
}

export type Necessity = 'required' | 'suggested' | 'optional'
export const NECESSITY: Record<Necessity, { label: string; cls: string }> = {
  required: { label: '必须', cls: 'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-900/30 dark:text-rose-300' },
  suggested: { label: '建议', cls: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-900/30 dark:text-amber-300' },
  optional: { label: '可选', cls: 'border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-400' },
}

// ---------------- 厂商（第四部分 1–7） ----------------
export const COMPANY_TYPES = ['有限责任公司', '股份有限公司', '国有企业', '外商投资企业', '个人独资企业', '合伙企业', '其他']
export const COMPANY_STATUS = ['存续', '正常开业']
/** 统一社会信用代码：18 位，数字与大写字母（不含 I、O、S、V、Z） */
export const CREDIT_CODE_RE = /^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$/

// ---------------- 算法（第一部分） ----------------
/**
 * 算法分类编码 = 行业编码 + 业务编码（≤10 字节）。
 * 标准未给出编码表，此处为示例，正式环境由平台配置。
 */
export const INDUSTRY_CODES = [
  { code: 'EP', label: '电力' },
  { code: 'TR', label: '交通' },
  { code: 'SF', label: '安防' },
  { code: 'IM', label: '工业制造' },
  { code: 'CM', label: '通信' },
  { code: 'ME', label: '医疗' },
  { code: 'RT', label: '零售' },
  { code: 'GN', label: '通用' },
]

export const SOURCE_TYPES: { v: SourceType; label: string }[] = [
  { v: 'picture', label: '图片 picture' },
  { v: 'video', label: '视频 video' },
  { v: 'audio', label: '音频 audio' },
  { v: 'featureModel', label: '特征模型 featureModel' },
  { v: 'text', label: '文本 text' },
]
export const PICTURE_FORMATS = ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'webp']
export const VIDEO_ENCODE = ['H.264', 'H.265', 'MJPEG']
export const VIDEO_PACKAGE = ['RTSP', 'MP4', 'FLV', 'TS', 'PS']
export const AUDIO_FORMATS = ['AAC', 'G.711A', 'G.711U', 'PCM', 'MP3']
export const CHIP_TYPES = ['NVIDIA GPU', 'Ascend 310', 'Ascend 910', 'Cambricon MLU', 'Hygon DCU', 'Kunlunxin XPU', 'x86 CPU', 'ARM CPU']
export const CROSS_DIRECTIONS = [
  { v: 'null', label: '不指定' },
  { v: 'bothDirection', label: '双向' },
  { v: 'leftToRight', label: '从左往右' },
  { v: 'rightToLeft', label: '从右往左' },
] as const
export const POLYGON_TYPES = [
  { v: 1, label: '折线' },
  { v: 2, label: '多边形' },
  { v: 3, label: '矩形' },
] as const

/** 第四部分：算法交付材料（8–17） */
export const DELIVERIES: { key: string; name: string; necessity: Necessity; content: string; accept: string; hint?: string }[] = [
  { key: 'basicForm', name: '算法基础信息申报表', necessity: 'required', content: '算法全称、简称、版本、适配场景、检测目标、运行环境资源要求、接口规范概述、开发语言、算法类型', accept: '.doc,.docx,.pdf', hint: 'Word / PDF，加盖企业公章' },
  { key: 'manual', name: '算法说明文档', necessity: 'required', content: '功能概述、适用场景、性能指标（准确率、召回率、帧率）、功能边界、局限性、使用禁忌、更新迭代记录', accept: '.doc,.docx,.pdf,.md', hint: '需标注支持的分辨率、检测速度、误差范围' },
  { key: 'whitepaper', name: '算法原理白皮书', necessity: 'optional', content: '核心原理、技术架构、网络结构、创新点、运行逻辑', accept: '.doc,.docx,.pdf' },
  { key: 'modelDoc', name: '模型说明文件', necessity: 'required', content: '模型结构、参数规模、训练数据集、精度、泛化能力、适配设备', accept: '.doc,.docx,.pdf,.md', hint: '需标注模型大小、推理耗时、适配系统' },
  { key: 'inferencePack', name: '完整模型推理包', necessity: 'required', content: '推理主程序、功能脚本、配套工具文件，解压即可运行', accept: '.zip,.tar,.gz', hint: '命名：算法名称-版本号-推理包' },
  { key: 'weights', name: '模型权重文件', necessity: 'required', content: '最终上线使用的最优权重文件', accept: '.pth,.pt,.onnx,.h5,.engine,.om,.bin,.safetensors' },
  { key: 'deps', name: '依赖环境清单', necessity: 'required', content: '系统、语言、框架、第三方库、驱动及版本号；区分必装与可选', accept: '.txt,.md,.pdf,.docx,.yaml,.yml' },
  { key: 'deployManual', name: '部署手册', necessity: 'suggested', content: '环境搭建、部署流程、启动命令、常见问题与排查、验收标准', accept: '.doc,.docx,.pdf,.md' },
  { key: 'tuning', name: '参数调优说明', necessity: 'suggested', content: '可调参数清单、取值范围、场景配置方案、调优效果对比', accept: '.doc,.docx,.pdf,.md' },
  { key: 'apiDoc', name: '接口技术文档', necessity: 'required', content: 'API 地址、请求方式、入参出参、鉴权、错误码（表 C.1）、调用示例', accept: '.doc,.docx,.pdf,.md' },
]

/** 第四部分 18–34：算法说明文档 / 模型说明文件 内容自查项 */
export const CHECKLIST: { group: string; key: string; name: string; necessity: Necessity }[] = [
  { group: '算法说明文档', key: 'm-overview', name: '算法概述', necessity: 'suggested' },
  { group: '算法说明文档', key: 'm-scene', name: '应用场景与识别目标', necessity: 'required' },
  { group: '算法说明文档', key: 'm-io', name: '算法输入输出定义', necessity: 'required' },
  { group: '算法说明文档', key: 'm-perf', name: '核心性能指标（准确率、精确率、召回率、单图推理耗时）', necessity: 'required' },
  { group: '算法说明文档', key: 'm-constraint', name: '适用与约束条件', necessity: 'suggested' },
  { group: '算法说明文档', key: 'm-env', name: '运行环境要求', necessity: 'required' },
  { group: '算法说明文档', key: 'm-limit', name: '已知缺陷与局限', necessity: 'suggested' },
  { group: '算法说明文档', key: 'm-changelog', name: '算法版本更新记录', necessity: 'optional' },
  { group: '模型说明文件', key: 'd-basic', name: '模型基础信息（名称、版本、训练时间、类别总数）', necessity: 'suggested' },
  { group: '模型说明文件', key: 'd-params', name: '模型核心参数（参数量、FLOPs）', necessity: 'suggested' },
  { group: '模型说明文件', key: 'd-dataset', name: '训练数据集说明', necessity: 'optional' },
  { group: '模型说明文件', key: 'd-weights', name: '模型权重文件说明', necessity: 'required' },
  { group: '模型说明文件', key: 'd-preprocess', name: '图像预处理规则（缩放、归一化、通道顺序）', necessity: 'required' },
  { group: '模型说明文件', key: 'd-output', name: '模型输出说明（输出张量、类别映射）', necessity: 'required' },
  { group: '模型说明文件', key: 'd-accuracy', name: '模型精度指标', necessity: 'suggested' },
  { group: '模型说明文件', key: 'd-quant', name: '模型量化与兼容性（FP32 / FP16 / INT8）', necessity: 'required' },
  { group: '模型说明文件', key: 'd-files', name: '模型文件清单', necessity: 'required' },
]

// ---------------- 描述文件生成 ----------------
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;')

/** A.1 packageinfo.xml */
export function packageInfoXml(d: AlgoDeclaration['packageInfo']): string {
  return `<?xml version="1.0" encoding="utf-8"?>
<packageinfo docVersion="0.5.0">
  <package type="algorithmPack" id="${esc(d.id)}" version="${esc(d.version)}" />
  <params>
    <param id="vendor.id" value="${esc(d.vendor.id)}" />
    <param id="vendor.zh_CN" value="${esc(d.vendor.zh_CN)}" />
    <param id="vendor.en_US" value="${esc(d.vendor.en_US ?? '')}" />
  </params>
</packageinfo>
`
}

/** 去掉空字符串 / 空数组 / undefined，生成更干净的 JSON */
function prune<T>(v: T): T {
  if (Array.isArray(v)) return v.map(prune).filter((x) => x !== undefined) as T
  if (v && typeof v === 'object') {
    const o: Record<string, unknown> = {}
    for (const [k, x] of Object.entries(v)) {
      const p = prune(x)
      if (p === undefined || p === '' || (Array.isArray(p) && !p.length) || (p && typeof p === 'object' && !Array.isArray(p) && !Object.keys(p).length)) continue
      o[k] = p
    }
    return o as T
  }
  return v
}

export const managementJson = (m: ManagementInfo) => JSON.stringify(prune(m), null, 2)
export const technicalJson = (t: TechnicalInfo) => JSON.stringify(prune(t), null, 2)
