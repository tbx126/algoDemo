<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Trash2, Trophy } from 'lucide-vue-next'
import { ApiError, createBenchmark, listDatasets } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { BUILTIN_TASKS, TASKS } from '@/utils/meta'
import type { MetricDef } from '@/types'
import StateView from '@/components/ui/StateView.vue'
import FakeUpload from '@/components/ui/FakeUpload.vue'

const route = useRoute()
const router = useRouter()
const { can, user } = useSession()
const { data: dsList } = useAsync(() => listDatasets({ pageSize: 999 }))

const PRESETS: Record<string, MetricDef[]> = {
  'image-classification': [
    { key: 'top1', label: 'Top-1', higherIsBetter: true, unit: '%', primary: true },
    { key: 'top5', label: 'Top-5', higherIsBetter: true, unit: '%' },
    { key: 'macro_f1', label: 'Macro-F1', higherIsBetter: true },
  ],
  'object-detection': [
    { key: 'map', label: 'mAP', higherIsBetter: true, unit: '%', primary: true },
    { key: 'map50', label: 'mAP@50', higherIsBetter: true, unit: '%' },
    { key: 'map_small', label: 'mAP-S', higherIsBetter: true, unit: '%' },
  ],
  'semantic-segmentation': [
    { key: 'miou', label: 'mIoU', higherIsBetter: true, unit: '%', primary: true },
    { key: 'pixel_acc', label: '像素准确率', higherIsBetter: true, unit: '%' },
  ],
}
const PERF: MetricDef[] = [
  { key: 'latency_ms', label: '单图耗时', higherIsBetter: false, unit: 'ms' },
  { key: 'peak_mem_gb', label: '峰值显存', higherIsBetter: false, unit: 'GB' },
]

const f = reactive({
  datasetId: (route.query.dataset as string) || '',
  datasetVersion: '',
  name: '',
  displayName: '',
  description: '',
  evaluatorKind: 'builtin' as 'builtin' | 'custom',
  script: null as { name: string; size: number } | null,
  metrics: [] as MetricDef[],
  perf: true,
})
const ds = computed(() => dsList.value?.items.find((d) => d.id === f.datasetId))
const builtin = computed(() => !!ds.value && BUILTIN_TASKS.includes(ds.value.task))
watch(
  ds,
  (d) => {
    if (!d) return
    f.datasetVersion = d.test?.versions[0].version ?? ""
    f.evaluatorKind = BUILTIN_TASKS.includes(d.task) ? 'builtin' : 'custom'
    f.metrics = JSON.parse(JSON.stringify(PRESETS[d.task] ?? [{ key: 'score', label: '得分', higherIsBetter: true, primary: true }]))
    if (!f.name && d.test) f.name = `${d.name.split('-')[0]}-${d.test.versions[0].version.replace('.0', '')}`
  },
  { immediate: true },
)
const evaluator = computed(() => (f.evaluatorKind === 'builtin' ? { name: `builtin/${ds.value?.task === 'image-classification' ? 'classification' : ds.value?.task === 'object-detection' ? 'coco-detection' : 'semantic-seg'}`, version: '2.0.1' } : { name: `${user.value.orgId}/custom-evaluator`, version: '0.1.0' }))
const primaryKey = computed({
  get: () => f.metrics.find((m) => m.primary)?.key ?? '',
  set: (k) => f.metrics.forEach((m) => (m.primary = m.key === k)),
})
const valid = computed(() => ds.value && !!ds.value.test && /^[a-z0-9][a-z0-9-]{1,48}$/.test(f.name) && f.displayName.trim() && f.metrics.length && primaryKey.value && f.metrics.every((m) => m.key && m.label) && (f.evaluatorKind === 'builtin' || f.script))
const submitting = ref(false)

async function submit() {
  if (!valid.value || !ds.value) return
  submitting.value = true
  try {
    const b = await createBenchmark({
      name: f.name,
      displayName: f.displayName,
      description: f.description || `${f.datasetId} ${f.datasetVersion} 测试集`,
      task: ds.value.task,
      datasetId: f.datasetId,
      datasetVersion: f.datasetVersion,
      evaluator: evaluator.value.name,
      evaluatorVersion: evaluator.value.version,
      metrics: [...f.metrics, ...(f.perf ? PERF : [])],
      org: ds.value.org,
    })
    toast('评测基准已创建')
    router.push(`/benchmarks/${b.id}`)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '创建失败', 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="container-page max-w-3xl pt-8">
    <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><Trophy class="size-6 text-amber-500" />新建评测基准</h1>
    <p class="mt-1 text-sm text-gray-500">绑定一个数据集测试集的具体版本 + 评测器版本 + 指标配置。创建后规则不可修改，如需变更请新建基准。</p>

    <StateView v-if="!can.createBenchmark" :error="{ status: 403, message: '仅管理员可以创建评测基准' }" />
    <StateView v-else :loading="!dsList">
      <form class="card mt-6 space-y-5 p-6" @submit.prevent="submit">
        <div class="grid gap-4 sm:grid-cols-[1fr_140px]">
          <div>
            <label class="label" for="b-ds">数据集</label>
            <select id="b-ds" v-model="f.datasetId" class="input" required>
              <option value="" disabled>选择数据集…</option>
              <option v-for="d in dsList?.items" :key="d.id" :value="d.id" :disabled="!d.test">{{ d.id }}（{{ TASKS[d.task].label }}）{{ d.test ? '' : ' · 未上传测试集' }}</option>
            </select>
          </div>
          <div>
            <label class="label" for="b-dv">测试集版本</label>
            <select id="b-dv" v-model="f.datasetVersion" class="input" :disabled="!ds">
              <option v-for="v in ds?.test?.versions" :key="v.version">{{ v.version }}</option>
            </select>
          </div>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="label" for="b-name">基准 ID</label>
            <input id="b-name" v-model.trim="f.name" class="input mono" />
          </div>
          <div>
            <label class="label" for="b-dn">显示名称</label>
            <input id="b-dn" v-model="f.displayName" class="input" />
          </div>
        </div>
        <div>
          <label class="label" for="b-desc">说明</label>
          <textarea id="b-desc" v-model="f.description" rows="2" class="input" />
        </div>

        <div v-if="ds">
          <span class="label">评测器</span>
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="flex cursor-pointer gap-2 rounded-lg border p-3 text-sm" :class="[f.evaluatorKind === 'builtin' ? 'border-brand-500 ring-2 ring-brand-500/20' : 'border-gray-200 dark:border-gray-700', !builtin ? 'cursor-not-allowed opacity-50' : '']">
              <input v-model="f.evaluatorKind" type="radio" value="builtin" :disabled="!builtin" class="mt-0.5 accent-brand-600" />
              <span><span class="block font-medium">内置评测器</span><span class="text-xs text-gray-500">{{ builtin ? '分类 / 检测 / 分割，统一输出格式' : '该任务类型暂无内置评测器' }}</span></span>
            </label>
            <label class="flex cursor-pointer gap-2 rounded-lg border p-3 text-sm" :class="f.evaluatorKind === 'custom' ? 'border-brand-500 ring-2 ring-brand-500/20' : 'border-gray-200 dark:border-gray-700'">
              <input v-model="f.evaluatorKind" type="radio" value="custom" class="mt-0.5 accent-brand-600" />
              <span><span class="block font-medium">自定义评测器</span><span class="text-xs text-gray-500">上传评测脚本，在隔离容器中运行</span></span>
            </label>
          </div>
          <div v-if="f.evaluatorKind === 'custom'" class="mt-3">
            <FakeUpload v-model="f.script" accept=".zip,.py" label="上传评测器代码包" hint="实现 evaluate(predictions, ground_truth) -> dict" />
          </div>
          <p class="hint">将使用 <code class="mono">{{ evaluator.name }}@{{ evaluator.version }}</code></p>
        </div>

        <div v-if="ds">
          <div class="mb-2 flex items-center justify-between">
            <span class="label mb-0">指标配置</span>
            <button type="button" class="btn-ghost text-xs" @click="f.metrics.push({ key: '', label: '', higherIsBetter: true })"><Plus class="size-3.5" />添加指标</button>
          </div>
          <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table class="table-base">
              <thead><tr><th>主指标</th><th>键</th><th>名称</th><th>单位</th><th>方向</th><th></th></tr></thead>
              <tbody>
                <tr v-for="(m, i) in f.metrics" :key="i">
                  <td><input v-model="primaryKey" type="radio" :value="m.key" class="accent-amber-500" :aria-label="`设 ${m.label} 为主指标`" /></td>
                  <td><input v-model.trim="m.key" class="input mono py-1" aria-label="指标键" /></td>
                  <td><input v-model="m.label" class="input py-1" aria-label="指标名称" /></td>
                  <td><input v-model="m.unit" class="input w-16 py-1" aria-label="单位" /></td>
                  <td>
                    <select v-model="m.higherIsBetter" class="input py-1" aria-label="方向">
                      <option :value="true">越高越好</option>
                      <option :value="false">越低越好</option>
                    </select>
                  </td>
                  <td><button type="button" class="btn-ghost px-1.5" aria-label="删除指标" @click="f.metrics.splice(i, 1)"><Trash2 class="size-3.5" /></button></td>
                </tr>
              </tbody>
            </table>
          </div>
          <label class="mt-3 flex items-center gap-2 text-sm"><input v-model="f.perf" type="checkbox" class="size-4 accent-brand-600" />同时记录单图耗时与峰值显存</label>
        </div>

        <div class="flex justify-end gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
          <button type="button" class="btn-default" @click="router.back()">取消</button>
          <button type="submit" class="btn-brand" :disabled="!valid || submitting">{{ submitting ? '创建中…' : '创建评测基准' }}</button>
        </div>
      </form>
    </StateView>
  </div>
</template>
