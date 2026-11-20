<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Building2, CircleAlert, CircleCheck, CircleDashed } from 'lucide-vue-next'
import { ApiError, createVendor, getOrg, updateVendor } from '@/api'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { COMPANY_STATUS, COMPANY_TYPES, CREDIT_CODE_RE, byteLen, type Necessity } from '@/utils/standard'
import StateView from '@/components/ui/StateView.vue'
import Modal from '@/components/ui/Modal.vue'
import HashText from '@/components/ui/HashText.vue'
import FormSection from '@/components/form/FormSection.vue'
import TextField from '@/components/form/TextField.vue'
import FileSlot from '@/components/form/FileSlot.vue'
import NecessityBadge from '@/components/form/NecessityBadge.vue'

type FileV = { name: string; size: number } | null
const route = useRoute()
const router = useRouter()
const { can } = useSession()
const touched = ref(false)
/** 编辑模式：/vendors/:id/edit */
const editId = computed(() => (route.params.id as string | undefined) ?? '')
const isEdit = computed(() => !!editId.value)
const loadingEdit = ref(false)

const f = reactive({
  // packageinfo.xml 中的厂商参数
  vendorId: '',
  zh: '',
  en: '',
  description: '',
  // 1 企业主体信息
  company: { fullName: '', creditCode: '', type: '有限责任公司', foundedAt: '', capital: '', status: '存续', address: '', license: null as FileV },
  // 2 企业联系方式
  contact: { phone: '', email: '', website: '', officeAddress: '' },
  // 3 对接人
  liaison: { name: '', title: '', phone: '' },
  // 4–7
  noCert: false,
  certFile: null as FileV, // 资质证书（合并为一个文件）或无资质情况说明
  copyrightFile: null as FileV,
  patentFile: null as FileV,
  otherIpFile: null as FileV,
  // 账号
  openAccount: true,
  account: { username: '', email: '' },
})

// 切换“暂无相关行业资质”时清空已上传文件，避免证书被当作情况说明（载入已有数据时除外）
watch(
  () => f.noCert,
  () => {
    if (!loadingEdit.value) f.certFile = null
  },
)

// ---------- 编辑模式：载入已有厂商信息 ----------
const asFile = (name?: string): FileV => (name ? { name, size: 0 } : null)
onMounted(async () => {
  if (!isEdit.value) return
  loadingEdit.value = true
  try {
    const o = await getOrg(editId.value)
    const p = o.profile
    Object.assign(f, { vendorId: o.id, zh: o.displayName, en: o.enName ?? '', description: o.description, openAccount: false })
    if (p) {
      Object.assign(f.company, { ...p.company, license: asFile(p.company.licenseFile) })
      Object.assign(f.contact, p.contact)
      Object.assign(f.liaison, p.liaison)
      f.noCert = !!p.qualification?.noQualification
      f.certFile = asFile(p.qualification?.file)
      f.copyrightFile = asFile(p.copyrightFile)
      f.patentFile = asFile(p.patentFile)
      f.otherIpFile = asFile(p.otherIpFile)
    }
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '载入失败', 'error')
  } finally {
    // 等 noCert 的 watch 执行完再解除
    setTimeout(() => (loadingEdit.value = false))
  }
})

// ---------- 校验 ----------
const errors = computed(() => {
  const e: Record<string, string> = {}
  if (!/^[A-Za-z][A-Za-z0-9_-]{1,29}$/.test(f.vendorId)) e.vendorId = '字母开头，可含大小写字母、数字、_ 与 -，2–30 位'
  if (!f.zh.trim()) e.zh = '必填'
  if (byteLen(f.zh) > 50) e.zh = '超出 50 字节'
  if (f.company.creditCode && !CREDIT_CODE_RE.test(f.company.creditCode.toUpperCase())) e.creditCode = '应为 18 位统一社会信用代码（数字与大写字母）'
  if (f.contact.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.contact.email)) e.email = '邮箱格式不正确'
  if (f.contact.website && f.contact.website !== '/' && !/^https?:\/\/\S+\.\S+/.test(f.contact.website)) e.website = '请以 http:// 或 https:// 开头；没有官网填 /'
  if (f.liaison.phone && !/^(1\d{10}|0\d{2,3}-?\d{7,8})$/.test(f.liaison.phone)) e.liaisonPhone = '手机号或座机号格式不正确'
  if (f.contact.phone && !/^(0\d{2,3}-?\d{7,8}|400-?\d{3}-?\d{4}|1\d{10})$/.test(f.contact.phone)) e.phone = '电话格式不正确，如 0571-12345678'
  if (f.openAccount && !/^[a-z0-9._-]{3,32}$/.test(f.account.username)) e.username = '3–32 位小写字母、数字或 . _ -'
  return e
})

const status = computed<{ key: string; name: string; necessity: Necessity; ok: boolean; note?: string }[]>(() => [
  { key: 'base', name: '厂商标识（packageinfo）', necessity: 'required', ok: !errors.value.vendorId && !errors.value.zh },
  { key: 'company', name: '企业主体信息', necessity: 'required', ok: !!(f.company.fullName && f.company.creditCode && !errors.value.creditCode && f.company.foundedAt && f.company.capital && f.company.address && f.company.license) },
  { key: 'contact', name: '企业联系方式', necessity: 'required', ok: !!(f.contact.phone && f.contact.email && f.contact.website && f.contact.officeAddress) && !errors.value.email && !errors.value.website && !errors.value.phone },
  { key: 'liaison', name: '对接人信息', necessity: 'required', ok: !!(f.liaison.name && f.liaison.title && f.liaison.phone) && !errors.value.liaisonPhone },
  {
    key: 'cert',
    name: '行业资质证书',
    necessity: 'suggested',
    ok: !!f.certFile,
    note: '无资质须提交情况说明',
  },
  { key: 'copyright', name: '软件著作权证明', necessity: 'suggested', ok: !!f.copyrightFile },
  { key: 'patent', name: '专利证明', necessity: 'optional', ok: !!f.patentFile },
  { key: 'other', name: '其他知识产权证明', necessity: 'optional', ok: !!f.otherIpFile },
])
// 必须项全部完成；资质证书“有则提供，无则须提交情况说明”，因此也作为提交门槛
const blocking = computed(() => status.value.filter((s) => s.necessity === 'required' && !s.ok).concat(status.value.filter((s) => s.key === 'cert' && !s.ok)))
const accountOk = computed(() => !f.openAccount || (!errors.value.username && !!f.account.email))
// 编辑时只要求厂商标识有效（管理员可分步补全申报材料）；新建时必须完成必须项
const canSubmit = computed(() => (isEdit.value ? !errors.value.vendorId && !errors.value.zh : !blocking.value.length && accountOk.value))

function scrollTo(key: string) {
  document.getElementById('sec-' + key)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// ---------- 提交 ----------
const submitting = ref(false)
const done = ref<{ id: string; account?: { username: string; tempPassword: string } } | null>(null)
async function submit() {
  touched.value = true
  if (!canSubmit.value) {
    toast(isEdit.value ? '请检查厂商标识与中文名称' : `还有 ${blocking.value.length + (accountOk.value ? 0 : 1)} 项未完成`, 'error')
    if (isEdit.value) scrollTo('base')
    else if (blocking.value[0]) scrollTo(blocking.value[0].key)
    return
  }
  submitting.value = true
  try {
    const fileName = (x: FileV) => x?.name
    const payload = {
      id: f.vendorId,
      zh_CN: f.zh.trim(),
      en_US: f.en.trim() || undefined,
      description: f.description.trim(),
      profile: {
        company: { ...f.company, creditCode: f.company.creditCode.toUpperCase(), licenseFile: fileName(f.company.license) },
        contact: { ...f.contact },
        liaison: { ...f.liaison },
        qualification: f.certFile ? { file: f.certFile.name, noQualification: f.noCert } : undefined,
        copyrightFile: fileName(f.copyrightFile),
        patentFile: fileName(f.patentFile),
        otherIpFile: fileName(f.otherIpFile),
      },
    }
    if (isEdit.value) {
      const o = await updateVendor(editId.value, payload)
      toast('厂商信息已保存')
      router.push(`/orgs/${o.id}`)
      return
    }
    const r = await createVendor({ ...payload, account: f.openAccount ? { ...f.account } : undefined })
    done.value = { id: r.org.id, account: r.account }
  } catch (e) {
    toast(e instanceof ApiError ? e.message : isEdit.value ? '保存失败' : '创建失败', 'error')
  } finally {
    submitting.value = false
  }
}
const doneName = computed(() => f.zh)
function onDoneOpen(v: boolean) {
  if (!v && done.value) router.push(`/orgs/${done.value.id}`)
}

</script>

<template>
  <div class="container-page max-w-6xl pt-8">
    <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><Building2 class="size-6 text-brand-600" />{{ isEdit ? '编辑厂商' : '新建厂商' }}</h1>
    <p class="mt-1 text-sm text-gray-500">按《智能运维平台算法中心算法标准 1.0》第四部分“算法厂商提供材料清单”完成入库申报。纸质材料需加盖企业公章，电子版为清晰扫描件。</p>

    <StateView v-if="!can.admin" :error="{ status: 403, message: isEdit ? '仅管理员可以修改厂商信息' : '仅管理员可以新建厂商' }" />
    <div v-else class="mt-6 flex flex-col gap-6 lg:flex-row lg:items-start">
      <form class="card min-w-0 flex-1 space-y-6 p-6" novalidate @submit.prevent="submit">
        <!-- 厂商标识 -->
        <FormSection id="sec-base" title="厂商标识" necessity="required" source="A.1 packageinfo.xml · vendor.*" :desc="isEdit ? '写入算法包描述文件。修改厂商标识会同步更新该厂商下所有算法的 ID、评测记录与厂商账号。' : '写入算法包描述文件，算法提交时自动带出。'">
          <div class="grid gap-4 sm:grid-cols-3">
            <TextField v-model.trim="f.vendorId" label="厂商标识" field="vendor.id" required mono hint="字母开头，可含大小写字母、数字、_ 与 -；不区分大小写判重" :touched="touched || !!f.vendorId" :error="errors.vendorId" />
            <TextField v-model="f.zh" label="中文名称" field="vendor.zh_CN" required :max-bytes="50" :touched="touched" :error="errors.zh" />
            <TextField v-model="f.en" label="英文名称" field="vendor.en_US" :max-bytes="150" />
          </div>
          <TextField v-model="f.description" label="厂商简介" />
        </FormSection>

        <!-- 1 企业主体信息 -->
        <FormSection id="sec-company" title="1. 企业主体信息" necessity="required" desc="与工商备案信息完全一致；须为最新有效信息，经营状态为存续 / 正常开业。">
          <div class="grid gap-4 sm:grid-cols-2">
            <TextField v-model="f.company.fullName" label="企业全称" required :touched="touched" />
            <TextField v-model.trim="f.company.creditCode" label="统一社会信用代码" required mono :touched="touched || !!f.company.creditCode" :error="errors.creditCode" />
          </div>
          <div class="grid gap-4 sm:grid-cols-4">
            <div>
              <label class="label" for="c-type">企业类型<span class="ml-0.5 text-rose-500">*</span></label>
              <select id="c-type" v-model="f.company.type" class="input">
                <option v-for="t in COMPANY_TYPES" :key="t">{{ t }}</option>
              </select>
            </div>
            <TextField v-model="f.company.foundedAt" type="date" label="成立日期" required :touched="touched" />
            <TextField v-model="f.company.capital" label="注册资本" required :touched="touched" />
            <div>
              <label class="label" for="c-status">经营状态<span class="ml-0.5 text-rose-500">*</span></label>
              <select id="c-status" v-model="f.company.status" class="input">
                <option v-for="t in COMPANY_STATUS" :key="t">{{ t }}</option>
              </select>
            </div>
          </div>
          <TextField v-model="f.company.address" label="企业注册地址" required :touched="touched" />
          <div>
            <p class="label">营业执照扫描件<span class="ml-0.5 text-rose-500">*</span> <span class="text-xs font-normal text-gray-500">加盖企业公章</span></p>
            <FileSlot v-model="f.company.license" accept=".pdf,.jpg,.jpeg,.png" label="上传扫描件" :invalid="touched && !f.company.license" />
          </div>
        </FormSection>

        <!-- 2 联系方式 -->
        <FormSection id="sec-contact" title="2. 企业联系方式" necessity="required" desc="联系方式须真实可接通、可接收邮件；企业邮箱或个人邮箱均可；变更需及时报备。">
          <div class="grid gap-4 sm:grid-cols-2">
            <TextField v-model.trim="f.contact.phone" label="官方联系电话" required :touched="touched || !!f.contact.phone" :error="errors.phone" />
            <TextField v-model.trim="f.contact.email" type="email" label="联系邮箱" required :touched="touched || !!f.contact.email" :error="errors.email" />
            <TextField v-model.trim="f.contact.website" label="官方网址" required :touched="touched || !!f.contact.website" :error="errors.website" />
            <TextField v-model="f.contact.officeAddress" label="办公地址" required :touched="touched" />
          </div>
        </FormSection>

        <!-- 3 对接人 -->
        <FormSection id="sec-liaison" title="3. 对接人信息" necessity="required" desc="须为在职正式员工，固定对接算法接入全流程。">
          <div class="grid gap-4 sm:grid-cols-3">
            <TextField v-model="f.liaison.name" label="姓名" required :touched="touched" />
            <TextField v-model="f.liaison.title" label="岗位职务" required :touched="touched" />
            <TextField v-model.trim="f.liaison.phone" label="联系电话" required :touched="touched || !!f.liaison.phone" :error="errors.liaisonPhone" />
          </div>
        </FormSection>

        <!-- 4 资质 -->
        <FormSection id="sec-cert" title="4. 行业资质证书" necessity="suggested" desc="如人工智能行业认证、信息系统资质、安防资质、高新技术企业证书等；须在有效期内，提供含编号、发证单位、有效期的完整扫描件。有则提供，无资质须提交情况说明。">
          <label class="flex items-center gap-2 text-sm"><input v-model="f.noCert" type="checkbox" class="size-4 accent-brand-600" />暂无相关行业资质</label>
          <div>
            <p class="label">{{ f.noCert ? '无资质情况说明' : '资质证书文件' }}<span class="ml-0.5 text-rose-500">*</span></p>
            <FileSlot v-model="f.certFile" :accept="f.noCert ? '.pdf,.doc,.docx' : '.pdf,.zip'" :label="f.noCert ? '上传情况说明' : '上传资质证书'" :invalid="touched && !f.certFile" />
            <p class="hint">{{ f.noCert ? '加盖企业公章的情况说明。' : '多个证书请合并为一个 PDF（或打包为 zip）上传。' }}</p>
          </div>
        </FormSection>

        <!-- 5 软著 -->
        <FormSection id="sec-copyright" title="5. 软件著作权证明" necessity="suggested" desc="与本次申报算法、配套系统相关；著作权归属申报企业，可在国家版权中心核验；提供证书正反面扫描件。">
          <div>
            <p class="label">软件著作权证书文件</p>
            <FileSlot v-model="f.copyrightFile" accept=".pdf,.zip" label="上传软著证书" />
            <p class="hint">多个证书请合并为一个 PDF（或打包为 zip）上传。</p>
          </div>
        </FormSection>

        <!-- 6 专利 -->
        <FormSection id="sec-patent" title="6. 专利证明" necessity="optional" desc="与算法核心技术相关的发明 / 实用新型专利，状态为授权有效；无相关专利可不提交。">
          <div>
            <p class="label">专利证明文件</p>
            <FileSlot v-model="f.patentFile" accept=".pdf,.zip" label="上传专利证明" />
            <p class="hint">专利证书全文及摘要，多个专利请合并为一个 PDF（或打包为 zip）上传。</p>
          </div>
        </FormSection>

        <!-- 7 其他 -->
        <FormSection id="sec-other" title="7. 其他知识产权证明" necessity="optional" desc="商标、技术成果登记证书、独家技术授权证明等，自愿提交。">
          <div>
            <p class="label">其他知识产权证明文件</p>
            <FileSlot v-model="f.otherIpFile" accept=".pdf,.zip" label="上传证明材料" />
            <p class="hint">多份材料请合并为一个 PDF（或打包为 zip）上传。</p>
          </div>
        </FormSection>

        <!-- 账号 -->
        <FormSection v-if="!isEdit" id="sec-account" title="开通厂商账号" desc="账号归属该厂商，用于提交算法与查看自己的评测结果。也可稍后在“管理 → 用户与账号”中添加。">
          <label class="flex items-center gap-2 text-sm"><input v-model="f.openAccount" type="checkbox" class="size-4 accent-brand-600" />同时为对接人开通厂商账号</label>
          <div v-if="f.openAccount" class="grid gap-4 sm:grid-cols-2">
            <TextField v-model.trim="f.account.username" label="用户名" required mono :touched="touched || !!f.account.username" :error="errors.username" />
            <TextField v-model.trim="f.account.email" type="email" label="登录邮箱" required :touched="touched" />
          </div>
        </FormSection>
      </form>

      <!-- 完整度 -->
      <aside class="w-full shrink-0 lg:sticky lg:top-20 lg:w-72">
        <div class="card p-4">
          <h2 class="text-sm font-semibold">申报材料完整度</h2>
          <p class="mt-0.5 text-xs text-gray-500">{{ isEdit ? '编辑时可分步补全；厂商标识与中文名称有效即可保存' : '必须项与资质证书（或情况说明）完成后可提交' }}</p>
          <ul class="mt-3 space-y-1">
            <li v-for="s in status" :key="s.key">
              <button type="button" class="flex w-full cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-800" @click="scrollTo(s.key)">
                <CircleCheck v-if="s.ok" class="size-4 shrink-0 text-emerald-500" />
                <CircleAlert v-else-if="s.necessity === 'required' || s.key === 'cert'" class="size-4 shrink-0" :class="touched ? 'text-rose-500' : 'text-gray-300 dark:text-gray-600'" />
                <CircleDashed v-else class="size-4 shrink-0 text-gray-300 dark:text-gray-600" />
                <span class="min-w-0 flex-1 truncate">{{ s.name }}</span>
                <NecessityBadge :n="s.necessity" />
              </button>
            </li>
          </ul>
          <button type="button" class="btn-brand mt-4 w-full" :disabled="submitting" @click="submit">{{ submitting ? (isEdit ? '保存中…' : '提交中…') : isEdit ? '保存修改' : '创建厂商' }}</button>
          <button type="button" class="btn-default mt-2 w-full" @click="router.back()">取消</button>
        </div>
      </aside>
    </div>

    <Modal :open="!!done" title="厂商已创建" @update:open="onDoneOpen">
      <div v-if="done" class="space-y-3 text-sm">
        <p>厂商 <b>{{ doneName }}</b>（<code class="mono">{{ done.id }}</code>）已入库，后续提交的算法包会自动写入该厂商标识。</p>
        <div v-if="done.account" class="rounded-lg bg-amber-50 p-3 dark:bg-amber-900/20">
          <p class="text-xs text-amber-800 dark:text-amber-300">厂商账号 <b class="mono">{{ done.account.username }}</b> 的临时密码（仅显示一次，演示数据）</p>
          <HashText :value="done.account.tempPassword" :short="40" />
        </div>
      </div>
      <template #footer>
        <RouterLink to="/admin/vendors" class="btn-default">返回厂商列表</RouterLink>
        <RouterLink :to="`/orgs/${done?.id}`" class="btn-brand">查看厂商主页</RouterLink>
      </template>
    </Modal>
  </div>
</template>
