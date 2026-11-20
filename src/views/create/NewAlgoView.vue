<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Box, Check, CircleAlert, Plus, ShieldCheck, Sparkles, Trash2 } from 'lucide-vue-next'
import { ApiError, createAlgorithm, listTags } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { BUSINESS_CATEGORIES, TASKS } from '@/utils/meta'
import { orgs } from '@/mock/orgs'
import {
  AUDIO_FORMATS,
  CHECKLIST,
  CHIP_TYPES,
  CROSS_DIRECTIONS,
  DELIVERIES,
  INDUSTRY_CODES,
  PICTURE_FORMATS,
  POLYGON_TYPES,
  SOURCE_TYPES,
  VIDEO_ENCODE,
  VIDEO_PACKAGE,
  byteLen,
  managementJson,
  packageInfoXml,
  technicalJson,
} from '@/utils/standard'
import type { AlgoDeclaration, BusinessCategory, Framework, ManagementInfo, ParamSupport, SourceInfo, TaskType, TechnicalInfo } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import FormSection from '@/components/form/FormSection.vue'
import TextField from '@/components/form/TextField.vue'
import TagInput from '@/components/form/TagInput.vue'
import FileSlot from '@/components/form/FileSlot.vue'
import NecessityBadge from '@/components/form/NecessityBadge.vue'

type FileV = { name: string; size: number } | null
const router = useRouter()
const { can, user, state } = useSession()

const steps = ['基本信息', '封面与应用条件', '技术信息', '分析参数', '交付材料', '确认提交']
const step = ref(0)
const visited = ref(0)
const touched = reactive<boolean[]>(steps.map(() => false))

// 所属厂商：厂商账号固定为自己的厂商；管理员可代任意厂商或平台内部命名空间提交
const owners = computed(() => (state.role === 'admin' ? orgs : orgs.filter((o) => o.id === user.value.orgId)))
const { data: tagList } = useAsync(() => listTags())
const tagSuggestions = computed(() => (tagList.value ?? []).map((t) => t.name))
const f = reactive({
  owner: user.value.orgId ?? orgs.find((o) => o.kind === 'vendor')!.id,
  task: 'object-detection' as TaskType,
  business: 'inspection' as BusinessCategory,
  framework: 'PyTorch' as Framework,
  tags: [] as string[],
  // packageinfo / managementinfo
  id: '',
  version: '1.0.0',
  nameZh: '',
  nameEn: '',
  classifications: [] as string[],
  industry: 'GN',
  bizCode: '',
  places: [] as string[],
  descZh: '',
  descEn: '',
  covers: [{ type: 'picture', file: null }] as { type: 'picture' | 'video'; file: FileV }[],
  cond: { weather: '', light: '', pixel: '', baffle: '', image: '', other: '' },
  suit: [] as { desc: string; file: FileV }[],
  unsuit: [] as { desc: string; file: FileV }[],
  // technicalinfo
  sources: [{ type: 'picture', format: ['jpg', 'png'], min: '640*480', max: '4096*4096' }] as SourceInfo[],
  chip: 'NVIDIA GPU',
  useBase: false,
  base: { id: '', minorVersion: '', majorVersion: '', relatedPodImageName: '' },
  useDriver: false,
  driver: { type: '', minorVersion: '', majorVersion: '' },
  req: { videoMemory: 2048, disk: 4096, memory: 4096, AImemory: 0, CPU: 4 },
  abilities: [{ type: 'picture', specification: '1080P', ability: 10, taskAbility: 1 }],
  regulation: { input: '', output: '', eventCode: '' },
  featureModels: [] as { id: string; version: string }[],
  // 第二部分
  params: {
    generalParam: { enabled: true, sensitive: 50, alertConfThreshold: 60, duration: 3, triggerInterval: 60, maxTriggerEnabled: false, maxTriggerTimes: 10 },
    detectRegion: true,
    maskRegion: true,
    ruleRegion: { enabled: false, crossDirections: ['null'], polygonTypes: [2] },
    numberCondition: false,
    sizeFilter: true,
    eventTypes: [],
  } as ParamSupport,
  // 第四部分
  deliveries: Object.fromEntries(DELIVERIES.map((d) => [d.key, null])) as Record<string, FileV>,
  checklist: [] as string[],
  changelog: '首次发布',
})

// ---------- 校验（逐步） ----------
const B = byteLen
const over = (s: string, n: number) => B(s) > n
const errs = computed<string[][]>(() => {
  const e: string[][] = steps.map(() => [])
  // 0 基本信息
  if (!/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(f.id) || over(f.id, 30)) e[0].push('算法标识 id：字母开头，可含字母数字 _ -，≤30 字节')
  if (!/^\d+\.\d+\.\d+$/.test(f.version) || over(f.version, 30)) e[0].push('版本号 version：x.y.z 格式')
  if (!f.nameZh.trim() || over(f.nameZh, 50)) e[0].push('算法中文名称 name.zh_CN：必填，≤50 字节')
  if (over(f.nameEn, 150)) e[0].push('算法英文名称 name.en_US：≤150 字节')
  if (!f.classifications.length) e[0].push('算法分类 classifications：至少一项')
  if (!f.places.length) e[0].push('适用场所 places：至少一项')
  if (!f.descZh.trim() || over(f.descZh, 1000)) e[0].push('算法功能中文说明 description.zh_CN：必填，≤1000 字节')
  if (over(f.descEn, 1500)) e[0].push('算法功能英文说明 description.en_US：≤1500 字节')
  // 1 封面与应用条件
  if (!f.covers.length || f.covers.some((c) => !c.file)) e[1].push('封面信息 cover：至少一项，且需上传文件')
  if (f.covers.some((c) => c.file && over(c.file.name, 50))) e[1].push('封面文件名 fileName：≤50 字节')
  for (const k of ['pixel', 'baffle', 'image'] as const) if (!f.cond[k].trim()) e[1].push(`使用要求 ${k}：必填`)
  for (const k of Object.keys(f.cond) as (keyof typeof f.cond)[]) if (over(f.cond[k], 100)) e[1].push(`使用要求 ${k}：≤100 字节`)
  for (const [list, n] of [[f.suit, '适用场景'], [f.unsuit, '不适用场景']] as const)
    if (list.some((s) => !s.desc.trim() || !s.file || over(s.desc, 1000) || over(s.file?.name ?? '', 50))) e[1].push(`${n}：描述必填（≤1000 字节）且需上传场景文件（文件名 ≤50 字节）`)
  // 2 技术信息
  if (!f.sources.length) e[2].push('数据类型 analysisSources：至少一项')
  f.sources.forEach((s, i) => {
    const n = `数据类型 ${i + 1}`
    if (s.type === 'picture' && !s.format?.length) e[2].push(`${n}：图片需填写 format`)
    if (s.type === 'video' && (!s.encodeFormat?.length || !s.packageFormat?.length || !s.frameRate)) e[2].push(`${n}：视频需填写 encodeFormat、packageFormat、frameRate`)
    if ((s.type === 'picture' || s.type === 'video') && (!s.min || !s.max)) e[2].push(`${n}：需填写分辨率下限 / 上限`)
    if ((s.type === 'audio' || s.type === 'video') && (!s.audioFormat?.length || !s.sampleRate || !s.sampleBit || !s.maxSize)) e[2].push(`${n}：音频 / 视频需填写 audioFormat、sampleRate、sampleBit、maxSize`)
    if (s.type === 'featureModel' && (!s.id || !s.version)) e[2].push(`${n}：特征模型需填写 id、version`)
  })
  if (!f.chip.trim() || over(f.chip, 20)) e[2].push('芯片类型 environment.chip：必填，≤20 字节')
  if (f.useBase && (!f.base.id || !f.base.minorVersion || !f.base.majorVersion)) e[2].push('基础环境 basePackage：id、最低 / 最高版本必填')
  if (f.useDriver && (!f.driver.type || !f.driver.minorVersion || !f.driver.majorVersion)) e[2].push('驱动 driver：类型、最低 / 最高版本必填')
  for (const [k, v] of Object.entries(f.req)) if (!Number.isInteger(v) || v < 0) e[2].push(`占用系统资源 ${k}：需为非负整数`)
  if (!f.abilities.length) e[2].push('性能规格 abilityInfos：至少一项')
  if (f.abilities.some((a) => !a.type || !a.specification || over(a.specification, 20) || a.ability < 0 || a.ability > 100 || !Number.isInteger(a.taskAbility) || a.taskAbility < 1))
    e[2].push('性能规格：数据类型、规格（≤20 字节）必填；算力使用量 0–100%；单路处理速度为正整数')
  if (!f.regulation.input.trim() || over(f.regulation.input, 5000)) e[2].push('参数 regulation.input：必填，≤5000 字节')
  if (!f.regulation.output.trim() || over(f.regulation.output, 5000)) e[2].push('目标属性 regulation.output：必填，≤5000 字节')
  if (!f.regulation.eventCode.trim() || over(f.regulation.eventCode, 50)) e[2].push('事件信息 regulation.eventCode：必填，≤50 字节')
  if (f.featureModels.some((m) => !m.id || !m.version || over(m.id, 20) || over(m.version, 20))) e[2].push('特征模型：id、version 必填，各 ≤20 字节')
  // 3 分析参数
  if (!f.params.eventTypes.length) e[3].push('事件类型 eventType：至少声明一个（B.7 必选）')
  if (f.params.ruleRegion.enabled && !f.params.ruleRegion.crossDirections.length) e[3].push('区域规则：至少选择一种跨线方向')
  // 4 交付材料
  for (const d of DELIVERIES) if (d.necessity === 'required' && !f.deliveries[d.key]) e[4].push(`${d.name}：必须提交`)
  for (const c of CHECKLIST) if (c.necessity === 'required' && !f.checklist.includes(c.key)) e[4].push(`内容自查「${c.name}」：必须项需确认`)
  return e
})
const totalErrs = computed(() => errs.value.reduce((s, x) => s + x.length, 0))

function go(i: number) {
  if (i > visited.value) return
  step.value = i
}
function next() {
  touched[step.value] = true
  if (errs.value[step.value].length) {
    toast(`本步还有 ${errs.value[step.value].length} 项未完成`, 'error')
    return
  }
  step.value++
  visited.value = Math.max(visited.value, step.value)
  window.scrollTo({ top: 0 })
}

// ---------- 分类编码 ----------
const classCode = computed(() => f.industry + f.bizCode.trim().toUpperCase())
function addClass() {
  if (!/^[A-Z0-9]{1,8}$/.test(f.bizCode.trim().toUpperCase())) return toast('业务编码为 1–8 位字母或数字', 'error')
  if (B(classCode.value) > 10) return toast('分类编码不能超过 10 字节', 'error')
  if (!f.classifications.includes(classCode.value)) f.classifications.push(classCode.value)
  f.bizCode = ''
}
const industryOf = (code: string) => INDUSTRY_CODES.find((x) => code.startsWith(x.code))?.label ?? ''

// ---------- 数据类型 ----------
function setSourceType(s: SourceInfo, t: SourceInfo['type']) {
  for (const k of Object.keys(s)) delete (s as unknown as Record<string, unknown>)[k]
  Object.assign(s, { type: t })
  if (t === 'picture') Object.assign(s, { format: ['jpg', 'png'], min: '640*480', max: '4096*4096' })
  if (t === 'video') Object.assign(s, { encodeFormat: ['H.264'], packageFormat: ['RTSP'], frameRate: 25, min: '640*480', max: '1920*1080', audioFormat: ['AAC'], sampleRate: '16000', sampleBit: 16, maxSize: 512 })
  if (t === 'audio') Object.assign(s, { audioFormat: ['PCM'], sampleRate: '16000', sampleBit: 16, maxSize: 50 })
  if (t === 'featureModel') Object.assign(s, { id: '', version: '' })
}

// ---------- 生成描述文件 ----------
const vendorOrg = computed(() => orgs.find((o) => o.id === f.owner))
const declaration = computed<AlgoDeclaration>(() => {
  const management: ManagementInfo = {
    id: f.id,
    name: { zh_CN: f.nameZh.trim(), en_US: f.nameEn.trim() || undefined },
    classifications: f.classifications,
    places: f.places,
    description: { zh_CN: f.descZh.trim(), en_US: f.descEn.trim() || undefined },
    cover: f.covers.filter((c) => c.file).map((c) => ({ type: c.type, fileName: c.file!.name })),
    conditions: {
      description: { zh_CN: { weather: f.cond.weather || undefined, light: f.cond.light || undefined, pixel: f.cond.pixel, baffle: f.cond.baffle, image: f.cond.image, other: f.cond.other || undefined } },
      suitabilities: f.suit.map((s) => ({ description: { zh_CN: s.desc }, fileName: s.file?.name ?? '' })),
      unsuitabilities: f.unsuit.map((s) => ({ description: { zh_CN: s.desc }, fileName: s.file?.name ?? '' })),
    },
  }
  const technical: TechnicalInfo = {
    version: f.version,
    analysisSources: f.sources,
    environment: { chip: f.chip, basePackage: f.useBase ? { ...f.base } : undefined, driver: f.useDriver ? { ...f.driver } : undefined },
    requirement: { ...f.req },
    abilityInfos: f.abilities,
    regulation: { ...f.regulation },
    featureModel: f.featureModels,
  }
  return {
    packageInfo: { id: f.id, version: f.version, vendor: { id: vendorOrg.value?.id ?? '', zh_CN: vendorOrg.value?.displayName ?? '', en_US: vendorOrg.value?.enName } },
    management,
    technical,
    params: f.params,
    deliveries: DELIVERIES.filter((d) => f.deliveries[d.key]).map((d) => ({ key: d.key, fileName: f.deliveries[d.key]!.name, size: f.deliveries[d.key]!.size })),
    checklist: f.checklist,
  }
})
const previewTab = ref<'pkg' | 'mgmt' | 'tech'>('mgmt')
const preview = computed(() => (previewTab.value === 'pkg' ? packageInfoXml(declaration.value.packageInfo) : previewTab.value === 'mgmt' ? managementJson(declaration.value.management) : technicalJson(declaration.value.technical)))
const packNameHint = computed(() => `${f.nameZh || '算法名称'}-${f.version}-推理包.zip`)

// ---------- 提交 ----------
const submitting = ref(false)
async function submit() {
  steps.forEach((_, i) => (touched[i] = true))
  const first = errs.value.findIndex((x) => x.length)
  if (first >= 0) {
    step.value = first
    toast(`还有 ${totalErrs.value} 项未完成`, 'error')
    return
  }
  submitting.value = true
  try {
    const d = declaration.value
    // 算法卡片 = 使用说明；标识、版本、分类、使用要求、运行环境等结构化信息只在“申报信息”中展示
    const fence = '```'
    const readme = `# ${f.nameZh}${f.nameEn ? `（${f.nameEn}）` : ''}

${f.descZh}

## 工作原理

> 待补充：可参考交付的《算法原理白皮书》。

## 调用方式

${fence}json
${f.regulation.input}
${fence}

## 输出

${fence}json
${f.regulation.output}
${fence}

事件信息：\`${f.regulation.eventCode}\`

## 性能

> 待补充：厂商自测指标；平台评测成绩见右侧。

`
    const a = await createAlgorithm({
      org: f.owner,
      name: f.id.replace(/([a-z0-9])([A-Z])/g, '$1-$2').replace(/_/g, '-').toLowerCase(), // helmetDetect → helmet-detect
      task: f.task,
      business: f.business,
      framework: f.framework,
      summary: f.descZh.slice(0, 120),
      version: f.version,
      gpuMem: +(f.req.videoMemory / 1024).toFixed(1),
      weightsSize: f.deliveries.weights?.size ?? 0,
      readme,
      tags: f.tags.length ? f.tags : [...(can.value.needsReview ? ['厂商提交'] : []), ...f.places.slice(0, 2)],
      files: [
        { path: 'packageinfo.xml', size: packageInfoXml(d.packageInfo).length, kind: 'config' },
        { path: 'managementinfo.json', size: managementJson(d.management).length, kind: 'config' },
        { path: 'technicalinfo.json', size: technicalJson(d.technical).length, kind: 'config' },
        ...d.deliveries.map((x) => ({ path: (x.key === 'weights' ? 'weights/' : x.key === 'inferencePack' ? '' : 'docs/') + x.fileName, size: x.size, kind: (x.key === 'weights' ? 'weights' : x.key === 'inferencePack' ? 'code' : 'doc') as 'weights' | 'code' | 'doc' })),
      ],
      declaration: d,
    })
    toast(can.value.needsReview ? '已提交，等待管理员审核' : '已创建，开始构建')
    router.push(`/algorithms/${a.id}?tab=declaration`)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '提交失败', 'error')
  } finally {
    submitting.value = false
  }
}

// ---------- 一键填写示例数据（便于管理员快速浏览各步骤所需填写与上传项） ----------
function fillExample() {
  f.owner = owners.value.find((o) => o.id === 'Admin')?.id ?? owners.value[0]?.id ?? f.owner
  f.task = 'object-detection'
  f.business = 'security'
  f.framework = 'PyTorch'
  f.tags = ['安全帽检测', '周界安防', '示例算法']
  f.id = 'helmetDetectDemo'
  f.version = '1.0.0'
  f.nameZh = '安全帽佩戴检测（示例）'
  f.nameEn = 'Safety Helmet Detection Demo'
  f.classifications = ['GN01']
  f.places = ['新能源场站', '变电站室内外']
  f.descZh = '识别施工与运维场景中人员是否佩戴安全帽，输出人员与安全帽边界框及告警事件，适用于可见光监控画面实时检测。'
  f.descEn = 'Detect safety helmet wearing status in power station and construction scenes.'
  f.covers = [{ type: 'picture', file: { name: 'helmet_cover_demo.jpg', size: 245760 } }]
  f.cond = {
    weather: '晴、阴、小雨',
    light: '白天及夜间补光场景',
    pixel: '目标头部像素 ≥ 24×24，建议 1080P 画面',
    baffle: '目标遮挡不超过 30%',
    image: '画面清晰，无严重运动模糊与过曝',
    other: '示例算法数据，可自由修改各字段',
  }
  f.suit = [{ desc: '人员正面或侧面清晰可见的常规监控画面', file: { name: 'suit_scene_01.jpg', size: 184320 } }]
  f.unsuit = [{ desc: '极端逆光或严重遮挡画面', file: { name: 'unsuit_scene_01.jpg', size: 163840 } }]
  f.sources = [{ type: 'picture', format: ['jpg', 'png'], min: '640*480', max: '3840*2160' }]
  f.chip = 'NVIDIA GPU'
  f.req = { videoMemory: 2048, disk: 4096, memory: 4096, AImemory: 0, CPU: 4 }
  f.abilities = [{ type: 'picture', specification: '1080P', ability: 15, taskAbility: 4 }]
  f.regulation = {
    input: '{"image":"base64_or_url","conf_threshold":0.5}',
    output: '{"detections":[{"label":"no_helmet","score":0.93,"bbox":[120,85,210,195]}]}',
    eventCode: 'HELMET_MISSING_ALERT',
  }
  f.params.eventTypes = ['helmet', 'no_helmet']
  for (const d of DELIVERIES) {
    if (d.necessity === 'required') {
      f.deliveries[d.key] = { name: `demo_${d.key}.zip`, size: d.key === 'weights' ? 48 * 1024 * 1024 : 512 * 1024 }
    }
  }
  f.checklist = CHECKLIST.filter((c) => c.necessity === 'required').map((c) => c.key)
  f.changelog = '示例首次发布（一键填充）'
  visited.value = steps.length - 1
  toast('已一键填充全流程示例数据，可直接点击「下一步」或任意步骤查看所需上传内容')
}

</script>

<template>
  <div class="container-page max-w-5xl pt-8">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 flex-1">
        <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><Box class="size-6 text-brand-600" />{{ can.needsReview ? '提交算法' : '新建算法' }}</h1>
        <p class="mt-1 text-sm text-gray-500">按《智能运维平台算法中心算法标准 1.0》填写，提交后自动生成 packageinfo.xml、managementinfo.json、technicalinfo.json。带 <span class="text-rose-500">*</span> 为必选项，长度按 UTF-8 字节计算。</p>
      </div>
      <button v-if="can.admin" type="button" class="btn-default shrink-0" @click="fillExample">
        <Sparkles class="size-4 text-amber-500" />一键填写示例数据
      </button>
    </div>

    <StateView v-if="!can.createAlgorithm" :error="{ status: 403, message: '演示账号不能提交算法' }" />
    <template v-else>
      <div v-if="can.needsReview" class="mt-4 flex gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-900/20 dark:text-amber-300">
        <ShieldCheck class="size-4 shrink-0" />厂商提交的算法需经管理员审核后才会构建和运行；提交后仅你所在厂商与管理员、演示账号可见。
      </div>

      <!-- 步骤条 -->
      <ol class="no-scrollbar mt-6 flex items-center gap-1 overflow-x-auto pb-1 text-sm">
        <li v-for="(s, i) in steps" :key="s" class="flex shrink-0 items-center gap-1">
          <button type="button" class="flex items-center gap-2 rounded-lg px-2 py-1" :class="i <= visited ? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900' : 'cursor-default'" :disabled="i > visited" @click="go(i)">
            <span
              class="flex size-6 items-center justify-center rounded-full text-xs font-semibold"
              :class="i === step ? 'bg-gray-900 text-white dark:bg-white dark:text-gray-900' : touched[i] && errs[i].length ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300' : i < visited ? 'bg-emerald-500 text-white' : 'bg-gray-100 text-gray-500 dark:bg-gray-800'"
            >
              <template v-if="touched[i] && errs[i].length && i !== step">{{ errs[i].length }}</template>
              <Check v-else-if="i < visited && !errs[i].length && i !== step" class="size-3.5" />
              <template v-else>{{ i + 1 }}</template>
            </span>
            <span :class="i === step ? 'font-medium text-gray-900 dark:text-white' : 'text-gray-500'">{{ s }}</span>
          </button>
          <span v-if="i < steps.length - 1" class="h-px w-4 bg-gray-200 sm:w-6 dark:bg-gray-700" />
        </li>
      </ol>

      <form class="card mt-4 space-y-6 p-6" novalidate @submit.prevent>
        <!-- ============ 0 基本信息 ============ -->
        <template v-if="step === 0">
          <FormSection title="归属与平台分类" desc="任务分类、业务分类、标签与推理框架用于平台检索、筛选、评测基准匹配及运行镜像构建。">
            <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label class="label" for="a-owner">所属厂商<span class="ml-0.5 text-rose-500">*</span></label>
                <select id="a-owner" v-model="f.owner" class="input" :disabled="owners.length === 1">
                  <optgroup v-if="owners.some((o) => o.kind === 'vendor')" label="厂商">
                    <option v-for="o in owners.filter((x) => x.kind === 'vendor')" :key="o.id" :value="o.id">{{ o.displayName }}（{{ o.id }}）</option>
                  </optgroup>
                  <optgroup v-if="owners.some((o) => o.kind === 'team')" label="平台内部（基线算法）">
                    <option v-for="o in owners.filter((x) => x.kind === 'team')" :key="o.id" :value="o.id">{{ o.displayName }}</option>
                  </optgroup>
                </select>
                <p class="hint">写入 packageinfo 的 vendor.*</p>
              </div>
              <div>
                <label class="label" for="a-task">任务分类<span class="ml-0.5 text-rose-500">*</span></label>
                <select id="a-task" v-model="f.task" class="input">
                  <option v-for="(v, k) in TASKS" :key="k" :value="k">{{ v.label }}</option>
                </select>
              </div>
              <div>
                <label class="label" for="a-biz">业务分类<span class="ml-0.5 text-rose-500">*</span></label>
                <select id="a-biz" v-model="f.business" class="input">
                  <option v-for="(v, k) in BUSINESS_CATEGORIES" :key="k" :value="k">{{ v.label }}</option>
                </select>
              </div>
              <div>
                <label class="label" for="a-fw">推理框架<span class="ml-0.5 text-rose-500">*</span></label>
                <select id="a-fw" v-model="f.framework" class="input">
                  <option v-for="x in ['PyTorch', 'ONNX', 'TensorRT', 'OpenCV', 'NumPy', 'Paddle']" :key="x">{{ x }}</option>
                </select>
              </div>
            </div>
            <TagInput v-model="f.tags" label="算法标签" :suggestions="tagSuggestions" placeholder="输入标签名回车添加，或点选下方已有标签" />
          </FormSection>

          <FormSection title="算法包信息" source="A.1 packageinfo.xml">
            <div class="grid gap-4 sm:grid-cols-[1fr_180px]">
              <TextField v-model="f.id" label="算法标识" field="package.id" required :max-bytes="30" mono hint="字母开头，可含字母、数字、_ 与 -" :touched="touched[0] || !!f.id" :error="errs[0].find((x) => x.startsWith('算法标识'))" />
              <TextField v-model="f.version" label="版本号" field="package.version" required :max-bytes="30" mono :touched="touched[0]" :error="errs[0].find((x) => x.startsWith('版本号'))" />
            </div>
          </FormSection>

          <FormSection title="算法属性" source="A.2 managementinfo.json · 表 A.1">
            <div class="grid gap-4 sm:grid-cols-2">
              <TextField v-model="f.nameZh" label="算法中文名称" field="name.zh_CN" required :max-bytes="50" :touched="touched[0]" />
              <TextField v-model="f.nameEn" label="算法英文名称" field="name.en_US" :max-bytes="150" />
            </div>

            <div>
              <p class="label flex items-baseline gap-1.5">算法分类<span class="text-rose-500">*</span><code class="mono text-[11px] font-normal text-gray-400">classifications</code><span class="ml-auto text-[11px] font-normal text-gray-400">每项 ≤10 字节 · 行业编码 + 业务编码</span></p>
              <div class="flex flex-wrap items-center gap-2">
                <select v-model="f.industry" class="input w-36" aria-label="行业编码">
                  <option v-for="x in INDUSTRY_CODES" :key="x.code" :value="x.code">{{ x.code }} · {{ x.label }}</option>
                </select>
                <span class="text-gray-400">+</span>
                <input v-model="f.bizCode" class="input mono w-36" placeholder="业务编码" aria-label="业务编码" @keydown.enter.prevent="addClass" />
                <button type="button" class="btn-default" @click="addClass"><Plus class="size-4" />添加 <code class="mono text-xs">{{ classCode }}</code></button>
              </div>
              <div class="mt-2 flex flex-wrap gap-1.5">
                <span v-for="c in f.classifications" :key="c" class="chip">
                  <code class="mono">{{ c }}</code><span class="text-gray-400">{{ industryOf(c) }}</span>
                  <button type="button" class="cursor-pointer text-gray-400 hover:text-gray-700" :aria-label="`移除 ${c}`" @click="f.classifications = f.classifications.filter((x) => x !== c)">×</button>
                </span>
                <span v-if="touched[0] && !f.classifications.length" class="text-xs text-rose-600">至少添加一个分类</span>
              </div>
              <p class="hint">标准未给出编码表，下拉中的行业编码为示例，正式环境由平台维护。</p>
            </div>

            <TagInput v-model="f.places" label="适用场所" field="places" required :max-bytes="30" :suggestions="['变电站', '输电线路', '机房', '施工现场', '厂区出入口', '道路路口', '仓库']" :touched="touched[0]" />
            <TextField v-model="f.descZh" label="算法功能中文说明" field="description.zh_CN" required multiline :rows="4" :max-bytes="1000" :touched="touched[0]" />
            <TextField v-model="f.descEn" label="算法功能英文说明" field="description.en_US" multiline :rows="3" :max-bytes="1500" />
          </FormSection>
        </template>

        <!-- ============ 1 封面与应用条件 ============ -->
        <template v-else-if="step === 1">
          <FormSection title="封面信息" source="cover · 表 A.2" necessity="required" desc="文件存放到 cover 目录下；类型为 picture（图片）或 video（视频）；文件名 ≤50 字节。">
            <div v-for="(c, i) in f.covers" :key="i" class="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 p-3 dark:border-gray-800">
              <select v-model="c.type" class="input w-36" aria-label="封面类型">
                <option value="picture">图片 picture</option>
                <option value="video">视频 video</option>
              </select>
              <FileSlot v-model="c.file" class="min-w-0 flex-1" :accept="c.type === 'picture' ? 'image/*' : 'video/*'" label="上传封面" :invalid="touched[1] && !c.file" />
              <button v-if="f.covers.length > 1" type="button" class="btn-ghost px-2" aria-label="删除封面" @click="f.covers.splice(i, 1)"><Trash2 class="size-4" /></button>
            </div>
            <button type="button" class="btn-default text-xs" @click="f.covers.push({ type: 'picture', file: null })"><Plus class="size-3.5" />添加封面</button>
          </FormSection>

          <FormSection title="使用要求（中文）" source="conditions.description.zh_CN" necessity="required" desc="每项 ≤100 字节。">
            <div class="grid gap-4 sm:grid-cols-3">
              <TextField v-model="f.cond.pixel" label="目标像素要求" field="pixel" required :max-bytes="100" :touched="touched[1]" />
              <TextField v-model="f.cond.baffle" label="目标遮挡粘贴" field="baffle" required :max-bytes="100" :touched="touched[1]" />
              <TextField v-model="f.cond.image" label="画面质量" field="image" required :max-bytes="100" :touched="touched[1]" />
              <TextField v-model="f.cond.weather" label="天气要求" field="weather" :max-bytes="100" />
              <TextField v-model="f.cond.light" label="光线要求" field="light" :max-bytes="100" />
              <TextField v-model="f.cond.other" label="其他要求" field="other" :max-bytes="100" />
            </div>
          </FormSection>

          <FormSection v-for="[key, title, field] in ([['suit', '适用场景', 'suitabilities'], ['unsuit', '不适用场景', 'unsuitabilities']] as const)" :key="key" :title="title" :source="`conditions.${field} · 表 A.3`" necessity="optional" desc="场景描述 ≤1000 字节；场景文件存放到 condition 目录下，文件名 ≤50 字节。">
            <div v-for="(s, i) in f[key]" :key="i" class="space-y-2 rounded-lg border border-gray-100 p-3 dark:border-gray-800">
              <div class="flex items-start gap-2">
                <TextField v-model="s.desc" class="flex-1" label="场景描述" field="description.zh_CN" required multiline :rows="2" :max-bytes="1000" :touched="touched[1]" />
                <button type="button" class="btn-ghost mt-6 px-2" aria-label="删除场景" @click="f[key].splice(i, 1)"><Trash2 class="size-4" /></button>
              </div>
              <FileSlot v-model="s.file" accept="image/*,video/*" label="场景文件" :invalid="touched[1] && !s.file" />
            </div>
            <button type="button" class="btn-default text-xs" @click="f[key].push({ desc: '', file: null })"><Plus class="size-3.5" />添加{{ title }}</button>
          </FormSection>
        </template>

        <!-- ============ 2 技术信息 ============ -->
        <template v-else-if="step === 2">
          <FormSection title="版本号" source="A.3 technicalinfo.json · version">
            <p class="text-sm">与算法包版本一致：<code class="mono">{{ f.version }}</code></p>
          </FormSection>

          <FormSection title="数据类型" source="analysisSources · 表 A.5" necessity="required" desc="按数据类型填写对应的必选字段。">
            <div v-for="(s, i) in f.sources" :key="i" class="space-y-3 rounded-lg border border-gray-100 p-3 dark:border-gray-800">
              <div class="flex items-center gap-2">
                <span class="text-xs text-gray-500">数据类型 {{ i + 1 }}</span>
                <select :value="s.type" class="input w-52" aria-label="数据类型" @change="setSourceType(s, ($event.target as HTMLSelectElement).value as SourceInfo['type'])">
                  <option v-for="t in SOURCE_TYPES" :key="t.v" :value="t.v">{{ t.label }}</option>
                </select>
                <button v-if="f.sources.length > 1" type="button" class="btn-ghost ml-auto px-2" aria-label="删除数据类型" @click="f.sources.splice(i, 1)"><Trash2 class="size-4" /></button>
              </div>
              <div class="grid gap-3 sm:grid-cols-2">
                <TagInput v-if="s.type === 'picture'" v-model="s.format" label="图片格式" field="format" required :suggestions="PICTURE_FORMATS" :touched="touched[2]" />
                <TagInput v-if="s.type === 'video'" v-model="s.encodeFormat" label="视频编码格式" field="encodeFormat" required :suggestions="VIDEO_ENCODE" :touched="touched[2]" />
                <TagInput v-if="s.type === 'video'" v-model="s.packageFormat" label="视频封装格式" field="packageFormat" required :suggestions="VIDEO_PACKAGE" :touched="touched[2]" />
                <div v-if="s.type === 'video'">
                  <label class="label">视频帧率<span class="ml-0.5 text-rose-500">*</span> <code class="mono text-[11px] font-normal text-gray-400">frameRate</code></label>
                  <input v-model.number="s.frameRate" type="number" min="1" class="input" aria-label="视频帧率" />
                </div>
                <template v-if="s.type === 'picture' || s.type === 'video'">
                  <div class="grid grid-cols-2 gap-3 sm:col-span-2">
                    <TextField :model-value="s.min ?? ''" label="分辨率下限" field="min" required :max-bytes="20" mono @update:model-value="s.min = $event" />
                    <TextField :model-value="s.max ?? ''" label="分辨率上限" field="max" required :max-bytes="20" mono @update:model-value="s.max = $event" />
                  </div>
                </template>
                <template v-if="s.type === 'audio' || s.type === 'video'">
                  <TagInput v-model="s.audioFormat" label="音频编码格式" field="audioFormat" required :suggestions="AUDIO_FORMATS" :touched="touched[2]" />
                  <TextField :model-value="s.sampleRate ?? ''" label="音频采样率" field="sampleRate" required :max-bytes="20" mono @update:model-value="s.sampleRate = $event" />
                  <div>
                    <label class="label">音频采样位数<span class="ml-0.5 text-rose-500">*</span> <code class="mono text-[11px] font-normal text-gray-400">sampleBit</code></label>
                    <input v-model.number="s.sampleBit" type="number" min="1" class="input" aria-label="音频采样位数" />
                  </div>
                  <div>
                    <label class="label">文件大小上限（MB）<span class="ml-0.5 text-rose-500">*</span> <code class="mono text-[11px] font-normal text-gray-400">maxSize</code></label>
                    <input v-model.number="s.maxSize" type="number" min="1" class="input" aria-label="文件大小上限" />
                  </div>
                </template>
                <template v-if="s.type === 'featureModel'">
                  <TextField :model-value="s.id ?? ''" label="特征信息标识" field="id" required :max-bytes="20" mono @update:model-value="s.id = $event" />
                  <TextField :model-value="s.version ?? ''" label="特征信息版本" field="version" required :max-bytes="20" mono @update:model-value="s.version = $event" />
                </template>
                <p v-if="s.type === 'text'" class="text-xs text-gray-500 sm:col-span-2">文本类型无附加字段。</p>
              </div>
            </div>
            <button type="button" class="btn-default text-xs" @click="f.sources.push({ type: 'picture', format: ['jpg'], min: '640*480', max: '4096*4096' })"><Plus class="size-3.5" />添加数据类型</button>
          </FormSection>

          <FormSection title="运行环境" source="environment" necessity="required">
            <div>
              <label class="label" for="t-chip">芯片类型<span class="ml-0.5 text-rose-500">*</span> <code class="mono text-[11px] font-normal text-gray-400">chip · ≤20 字节</code></label>
              <input id="t-chip" v-model="f.chip" class="input sm:w-72" list="chip-list" />
              <datalist id="chip-list"><option v-for="c in CHIP_TYPES" :key="c" :value="c" /></datalist>
            </div>
            <label class="flex items-center gap-2 text-sm"><input v-model="f.useBase" type="checkbox" class="size-4 accent-brand-600" />声明基础环境信息 <code class="mono text-xs text-gray-400">basePackage（可选）</code></label>
            <div v-if="f.useBase" class="grid gap-3 sm:grid-cols-4">
              <TextField v-model="f.base.id" label="标识" field="id" required :max-bytes="20" mono :touched="touched[2]" />
              <TextField v-model="f.base.minorVersion" label="最低版本" field="minorVersion" required :max-bytes="20" mono :touched="touched[2]" />
              <TextField v-model="f.base.majorVersion" label="最高版本" field="majorVersion" required :max-bytes="20" mono :touched="touched[2]" />
              <TextField v-model="f.base.relatedPodImageName" label="镜像名称" field="relatedPodImageName" :max-bytes="100" mono />
            </div>
            <label class="flex items-center gap-2 text-sm"><input v-model="f.useDriver" type="checkbox" class="size-4 accent-brand-600" />声明驱动信息 <code class="mono text-xs text-gray-400">driver（可选）</code></label>
            <div v-if="f.useDriver" class="grid gap-3 sm:grid-cols-3">
              <TextField v-model="f.driver.type" label="驱动类型" field="type" required :max-bytes="20" mono :touched="touched[2]" />
              <TextField v-model="f.driver.minorVersion" label="驱动最低版本" field="minorVersion" required :max-bytes="20" mono :touched="touched[2]" />
              <TextField v-model="f.driver.majorVersion" label="驱动最高版本" field="majorVersion" required :max-bytes="20" mono :touched="touched[2]" />
            </div>
          </FormSection>

          <FormSection title="占用系统资源" source="requirement" necessity="required" desc="均为整数。标准未规定单位，本平台约定：显存 / 磁盘 / 内存 / 智能内存为 MB，CPU 为核数。">
            <div class="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <div v-for="[k, l, u] in ([['videoMemory', '显存', 'MB'], ['disk', '磁盘空间', 'MB'], ['memory', '内存', 'MB'], ['AImemory', '智能内存', 'MB'], ['CPU', 'CPU 核心', '核']] as const)" :key="k">
                <label class="label">{{ l }}<span class="ml-0.5 text-rose-500">*</span> <code class="mono text-[11px] font-normal text-gray-400">{{ k }}</code></label>
                <div class="relative">
                  <input v-model.number="f.req[k]" type="number" min="0" step="1" class="input pr-10" :aria-label="l" />
                  <span class="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-xs text-gray-400">{{ u }}</span>
                </div>
              </div>
            </div>
          </FormSection>

          <FormSection title="性能规格" source="abilityInfos · 表 A.6" necessity="required">
            <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
              <table class="table-base">
                <thead>
                  <tr><th>数据类型 type</th><th>规格 specification</th><th>芯片算力使用量 ability（%）</th><th>单路处理速度 taskAbility</th><th></th></tr>
                </thead>
                <tbody>
                  <tr v-for="(a, i) in f.abilities" :key="i">
                    <td>
                      <select v-model="a.type" class="input py-1" aria-label="数据类型">
                        <option v-for="t in SOURCE_TYPES" :key="t.v" :value="t.v">{{ t.v }}</option>
                      </select>
                    </td>
                    <td><input v-model="a.specification" class="input mono py-1" aria-label="规格" /></td>
                    <td><input v-model.number="a.ability" type="number" min="0" max="100" step="0.1" class="input py-1" aria-label="芯片算力使用量" /></td>
                    <td><input v-model.number="a.taskAbility" type="number" min="1" step="1" class="input py-1" aria-label="单路处理速度" /></td>
                    <td><button v-if="f.abilities.length > 1" type="button" class="btn-ghost px-1.5" aria-label="删除规格" @click="f.abilities.splice(i, 1)"><Trash2 class="size-3.5" /></button></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p class="hint">ability：一个并发任务占用的芯片算力百分比（0–100%）；taskAbility：一个任务的数据量，图片张数、视频路数一般为 1。</p>
            <button type="button" class="btn-default text-xs" @click="f.abilities.push({ type: 'picture', specification: '', ability: 10, taskAbility: 1 })"><Plus class="size-3.5" />添加规格</button>
          </FormSection>

          <FormSection title="参数和输出" source="regulation" necessity="required">
            <TextField v-model="f.regulation.input" label="参数" field="input" required multiline :rows="4" mono :max-bytes="5000" :touched="touched[2]" />
            <TextField v-model="f.regulation.output" label="目标属性" field="output" required multiline :rows="4" mono :max-bytes="5000" :touched="touched[2]" />
            <TextField v-model="f.regulation.eventCode" label="事件信息" field="eventCode" required :max-bytes="50" mono :touched="touched[2]" />
          </FormSection>

          <FormSection title="特征模型" source="featureModel · 表 A.7" necessity="optional">
            <div v-for="(m, i) in f.featureModels" :key="i" class="flex items-start gap-3">
              <TextField v-model="m.id" class="flex-1" label="特性信息标识" field="id" required :max-bytes="20" mono :touched="touched[2]" />
              <TextField v-model="m.version" class="flex-1" label="特性信息版本" field="version" required :max-bytes="20" mono :touched="touched[2]" />
              <button type="button" class="btn-ghost mt-6 px-2" aria-label="删除特征模型" @click="f.featureModels.splice(i, 1)"><Trash2 class="size-4" /></button>
            </div>
            <button type="button" class="btn-default text-xs" @click="f.featureModels.push({ id: '', version: '' })"><Plus class="size-3.5" />添加特征模型</button>
          </FormSection>
        </template>

        <!-- ============ 3 分析参数 ============ -->
        <template v-else-if="step === 3">
          <p class="rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-400">第二部分规定的参数由业务在下发任务时配置。此处声明算法<b>支持哪些参数</b>及默认值，平台据此生成任务配置界面。</p>

          <FormSection title="事件类型" source="B.7 ruleParam.eventType" necessity="required" desc="算法可上报的事件类型，每项 ≤32 字节。">
            <TagInput v-model="f.params.eventTypes" label="事件类型" field="eventType" required :max-bytes="32" :touched="touched[3]" />
          </FormSection>

          <FormSection title="通用参数" source="B.1 generalParam" necessity="optional">
            <label class="flex items-center gap-2 text-sm"><input v-model="f.params.generalParam.enabled" type="checkbox" class="size-4 accent-brand-600" />支持通用参数</label>
            <div v-if="f.params.generalParam.enabled" class="grid gap-3 sm:grid-cols-4">
              <div v-for="[k, l, u] in ([['sensitive', '灵敏度', ''], ['alertConfThreshold', '置信度', ''], ['duration', '持续时间', '秒'], ['triggerInterval', '报警间隔', '秒']] as const)" :key="k">
                <label class="label">{{ l }} 默认值 <code class="mono text-[11px] font-normal text-gray-400">{{ k }}</code></label>
                <div class="relative">
                  <input v-model.number="f.params.generalParam[k]" type="number" min="0" step="1" class="input" :aria-label="l" />
                  <span v-if="u" class="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-xs text-gray-400">{{ u }}</span>
                </div>
              </div>
              <label class="flex items-center gap-2 text-sm sm:col-span-2"><input v-model="f.params.generalParam.maxTriggerEnabled" type="checkbox" class="size-4 accent-brand-600" />最大报警数启用 <code class="mono text-xs text-gray-400">maxTriggerEnabled</code></label>
              <div v-if="f.params.generalParam.maxTriggerEnabled">
                <label class="label">报警次数 <code class="mono text-[11px] font-normal text-gray-400">maxTriggerTimes</code></label>
                <input v-model.number="f.params.generalParam.maxTriggerTimes" type="number" min="1" class="input" aria-label="报警次数" />
              </div>
            </div>
          </FormSection>

          <FormSection title="区域与过滤" source="B.2–B.6" necessity="optional">
            <div class="grid gap-2 sm:grid-cols-2">
              <label class="flex gap-2 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700"><input v-model="f.params.detectRegion" type="checkbox" class="mt-0.5 size-4 accent-brand-600" /><span><b class="font-medium">检测区域</b> <code class="mono text-xs text-gray-400">detectRegionList</code><br /><span class="text-xs text-gray-500">仅分析区域内内容；多边形 ≤16 个，每个 ≤10 条边，归一化坐标</span></span></label>
              <label class="flex gap-2 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700"><input v-model="f.params.maskRegion" type="checkbox" class="mt-0.5 size-4 accent-brand-600" /><span><b class="font-medium">屏蔽区域</b> <code class="mono text-xs text-gray-400">maskRegionList</code><br /><span class="text-xs text-gray-500">过滤区域内的目标事件；多边形 ≤16 个，每个 ≤10 条边</span></span></label>
              <label class="flex gap-2 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700"><input v-model="f.params.numberCondition" type="checkbox" class="mt-0.5 size-4 accent-brand-600" /><span><b class="font-medium">目标数量过滤</b> <code class="mono text-xs text-gray-400">numberCondition</code><br /><span class="text-xs text-gray-500">最小 / 最大目标数 + 触发条件（1–4）</span></span></label>
              <label class="flex gap-2 rounded-lg border border-gray-200 p-3 text-sm dark:border-gray-700"><input v-model="f.params.sizeFilter" type="checkbox" class="mt-0.5 size-4 accent-brand-600" /><span><b class="font-medium">目标尺寸过滤</b> <code class="mono text-xs text-gray-400">sizeFilter</code><br /><span class="text-xs text-gray-500">目标最大 / 最小宽度、高度</span></span></label>
            </div>
            <div class="rounded-lg border border-gray-200 p-3 dark:border-gray-700">
              <label class="flex items-center gap-2 text-sm"><input v-model="f.params.ruleRegion.enabled" type="checkbox" class="size-4 accent-brand-600" /><b class="font-medium">区域规则</b> <code class="mono text-xs text-gray-400">ruleRegionList · 不超过 16 个</code></label>
              <div v-if="f.params.ruleRegion.enabled" class="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <p class="label">支持的跨线方向 <code class="mono text-[11px] font-normal text-gray-400">crossDirection</code></p>
                  <div class="flex flex-wrap gap-3 text-sm">
                    <label v-for="d in CROSS_DIRECTIONS" :key="d.v" class="flex items-center gap-1.5"><input v-model="f.params.ruleRegion.crossDirections" type="checkbox" :value="d.v" class="accent-brand-600" />{{ d.label }}</label>
                  </div>
                </div>
                <div>
                  <p class="label">支持的区域类型 <code class="mono text-[11px] font-normal text-gray-400">polygonType</code></p>
                  <div class="flex flex-wrap gap-3 text-sm">
                    <label v-for="d in POLYGON_TYPES" :key="d.v" class="flex items-center gap-1.5"><input v-model="f.params.ruleRegion.polygonTypes" type="checkbox" :value="d.v" class="accent-brand-600" />{{ d.label }}</label>
                  </div>
                </div>
              </div>
            </div>
          </FormSection>
        </template>

        <!-- ============ 4 交付材料 ============ -->
        <template v-else-if="step === 4">
          <FormSection title="算法交付材料" source="第四部分 8–17" desc="“必须”项缺失无法提交；“建议”项缺失会影响部署与使用效率。">
            <div class="divide-y divide-gray-100 rounded-lg border border-gray-200 dark:divide-gray-800 dark:border-gray-700">
              <div v-for="d in DELIVERIES" :key="d.key" class="grid gap-2 p-3 sm:grid-cols-[1fr_300px] sm:items-center">
                <div class="min-w-0">
                  <p class="flex items-center gap-2 text-sm font-medium">{{ d.name }}<NecessityBadge :n="d.necessity" /></p>
                  <p class="mt-0.5 text-xs text-gray-500">{{ d.content }}<template v-if="d.hint"> · {{ d.hint }}</template></p>
                  <p v-if="d.key === 'inferencePack' && f.deliveries.inferencePack && !f.deliveries.inferencePack.name.startsWith(`${f.nameZh}-${f.version}-推理包`)" class="mt-1 flex items-center gap-1 text-xs text-amber-600"><CircleAlert class="size-3.5" />建议命名为 {{ packNameHint }}</p>
                </div>
                <FileSlot v-model="f.deliveries[d.key]" :accept="d.accept" label="上传" :invalid="touched[4] && d.necessity === 'required' && !f.deliveries[d.key]" />
              </div>
            </div>
          </FormSection>

          <FormSection title="文档内容自查" source="第四部分 18–34" desc="请确认算法说明文档与模型说明文件已包含以下内容；“必须”项需全部勾选。">
            <div v-for="g in ['算法说明文档', '模型说明文件']" :key="g">
              <p class="mb-1.5 text-xs font-medium text-gray-500">{{ g }}</p>
              <div class="grid gap-1 sm:grid-cols-2">
                <label v-for="c in CHECKLIST.filter((x) => x.group === g)" :key="c.key" class="flex items-center gap-2 rounded-md px-2 py-1 text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50" :class="touched[4] && c.necessity === 'required' && !f.checklist.includes(c.key) ? 'text-rose-600' : ''">
                  <input v-model="f.checklist" type="checkbox" :value="c.key" class="size-4 shrink-0 accent-brand-600" />
                  <span class="min-w-0 flex-1">{{ c.name }}</span>
                  <NecessityBadge :n="c.necessity" />
                </label>
              </div>
            </div>
          </FormSection>

          <TextField v-model="f.changelog" label="本版本变更说明" />
        </template>

        <!-- ============ 5 确认 ============ -->
        <template v-else>
          <div class="grid gap-6 lg:grid-cols-[280px_1fr]">
            <dl class="space-y-2.5 text-sm">
              <div><dt class="text-xs text-gray-500">厂商</dt><dd>{{ vendorOrg?.displayName }} <code class="mono text-xs text-gray-400">{{ vendorOrg?.id }}</code></dd></div>
              <div><dt class="text-xs text-gray-500">算法</dt><dd>{{ f.nameZh }} <code class="mono text-xs text-gray-400">{{ f.id }}@{{ f.version }}</code></dd></div>
              <div><dt class="text-xs text-gray-500">任务 / 业务 / 框架</dt><dd>{{ TASKS[f.task].label }} · {{ BUSINESS_CATEGORIES[f.business].label }} · {{ f.framework }}</dd></div>
              <div><dt class="text-xs text-gray-500">分类 / 场所</dt><dd>{{ f.classifications.join('、') }} · {{ f.places.join('、') }}</dd></div>
              <div><dt class="text-xs text-gray-500">资源</dt><dd>显存 {{ f.req.videoMemory }} MB · CPU {{ f.req.CPU }} 核 · {{ f.chip }}</dd></div>
              <div><dt class="text-xs text-gray-500">交付材料</dt><dd>{{ declaration.deliveries.length }} / {{ DELIVERIES.length }} 项</dd></div>
              <div v-if="totalErrs" class="rounded-lg bg-rose-50 p-3 text-xs text-rose-700 dark:bg-rose-900/20 dark:text-rose-300">
                <p class="mb-1 font-medium">还有 {{ totalErrs }} 项未完成：</p>
                <ul class="list-inside list-disc space-y-0.5">
                  <template v-for="(list, i) in errs" :key="i"><li v-for="e in list" :key="e"><button type="button" class="cursor-pointer text-left underline-offset-2 hover:underline" @click="step = i">{{ steps[i] }} · {{ e }}</button></li></template>
                </ul>
              </div>
              <p v-else class="flex items-center gap-1.5 rounded-lg bg-emerald-50 p-3 text-xs text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300"><Check class="size-4" />所有必选项已完成</p>
            </dl>
            <div class="min-w-0">
              <div class="no-scrollbar mb-2 flex gap-1 overflow-x-auto border-b border-gray-100 dark:border-gray-800">
                <button type="button" class="tab" :class="{ 'tab-active': previewTab === 'pkg' }" @click="previewTab = 'pkg'">packageinfo.xml</button>
                <button type="button" class="tab" :class="{ 'tab-active': previewTab === 'mgmt' }" @click="previewTab = 'mgmt'">managementinfo.json</button>
                <button type="button" class="tab" :class="{ 'tab-active': previewTab === 'tech' }" @click="previewTab = 'tech'">technicalinfo.json</button>
              </div>
              <pre class="scroll-thin max-h-[480px] overflow-auto rounded-lg bg-gray-900 p-3 text-xs leading-relaxed text-gray-100">{{ preview }}</pre>
            </div>
          </div>
        </template>

        <!-- 本步错误 -->
        <div v-if="touched[step] && errs[step]?.length && step < 5" class="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-900/20 dark:text-rose-300">
          <p class="mb-1 font-medium">本步还有 {{ errs[step].length }} 项需要处理：</p>
          <ul class="list-inside list-disc space-y-0.5"><li v-for="e in errs[step]" :key="e">{{ e }}</li></ul>
        </div>

        <div class="flex justify-between border-t border-gray-100 pt-4 dark:border-gray-800">
          <button type="button" class="btn-default" @click="step ? step-- : router.back()">{{ step ? '上一步' : '取消' }}</button>
          <button v-if="step < steps.length - 1" type="button" class="btn-primary" @click="next">下一步</button>
          <button v-else type="button" class="btn-brand" :disabled="submitting" @click="submit">{{ submitting ? '提交中…' : can.needsReview ? '提交审核' : '创建并构建' }}</button>
        </div>
      </form>
    </template>
  </div>
</template>
