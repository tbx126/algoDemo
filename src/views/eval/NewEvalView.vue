<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CircleAlert, CircleCheck, FlaskConical, Lock } from 'lucide-vue-next'
import { ApiError, createEval, getQueueStatus, listAlgorithms, listBenchmarks } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { toast } from '@/stores/toast'
import { TASKS } from '@/utils/meta'
import { algoFullLabel } from '@/utils/display'
import StateView from '@/components/ui/StateView.vue'
import TaskBadge from '@/components/ui/TaskBadge.vue'

const route = useRoute()
const router = useRouter()
const { can } = useSession()

const { data: algos } = useAsync(() => listAlgorithms({ pageSize: 999 }))
const { data: benches } = useAsync(() => listBenchmarks())
const { data: q } = useAsync(() => getQueueStatus())

const form = reactive({
  algo: (route.query.algo as string) || '',
  version: (route.query.v as string) || '',
  bench: (route.query.bench as string) || '',
  batch: 16,
  fp16: true,
  seed: 42,
})
const submitting = ref(false)

const isUniversal = (id?: string) => id === 'Admin/random'
const algo = computed(() => algos.value?.items.find((a) => a.id === form.algo))
const bench = computed(() => benches.value?.find((b) => b.id === form.bench))
const versions = computed(() => algo.value?.versions ?? [])
const ver = computed(() => versions.value.find((v) => v.version === form.version))
const benchOptions = computed(() => (benches.value ?? []).filter((b) => !algo.value || isUniversal(algo.value.id) || b.task === algo.value.task))
const algoOptions = computed(() => (algos.value?.items ?? []).filter((a) => !bench.value || isUniversal(a.id) || a.task === bench.value.task))

watch(
  () => form.algo,
  () => {
    if (!versions.value.some((v) => v.version === form.version)) form.version = versions.value.find((v) => v.status === 'ready')?.version ?? ''
    if (bench.value && algo.value && !isUniversal(algo.value.id) && bench.value.task !== algo.value.task) form.bench = ''
  },
)
watch(algos, () => {
  if (form.algo && !form.version) form.version = versions.value.find((v) => v.status === 'ready')?.version ?? ''
})

const checks = computed(() => {
  const out: { ok: boolean; text: string }[] = []
  if (ver.value) out.push({ ok: ver.value.status === 'ready', text: ver.value.status === 'ready' ? `版本 ${ver.value.version} 已构建，镜像可用` : `版本 ${ver.value.version} 不可用（${ver.value.status}）` })
  if (algo.value && bench.value) {
    const ok = isUniversal(algo.value.id) || algo.value.task === bench.value.task
    out.push({ ok, text: isUniversal(algo.value.id) ? '通用随机基线，兼容任意任务类型的评测基准' : ok ? '任务类型匹配' : '任务类型不匹配' })
  }
  if (ver.value && q.value) out.push({ ok: ver.value.gpuMem <= q.value.gpuMemTotal, text: `声明显存 ${ver.value.gpuMem} GB ≤ GPU 总显存 ${q.value.gpuMemTotal} GB` })
  return out
})
const ready = computed(() => form.algo && form.version && form.bench && checks.value.every((c) => c.ok))

async function submit() {
  if (!ready.value) return
  submitting.value = true
  try {
    const r = await createEval({ algorithmId: form.algo, algoVersion: form.version, benchmarkId: form.bench, params: { batch_size: form.batch, fp16: form.fp16, seed: form.seed } })
    toast(`评测任务 ${r.id} 已提交，进入队列`)
    router.push(`/evals/${r.id}`)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '提交失败', 'error')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="container-page max-w-3xl pt-8">
    <h1 class="flex items-center gap-2 text-2xl font-semibold text-gray-900 dark:text-white"><FlaskConical class="size-6 text-brand-600" />发起评测</h1>
    <p class="mt-1 text-sm text-gray-500">选择“算法版本 × 评测基准”，任务进入调度队列，完成后结果自动归档并更新排行榜。</p>

    <StateView v-if="!can.runEval" :error="{ status: 403, message: '演示账号不能发起评测' }" />
    <StateView v-else :loading="!algos || !benches">
      <form class="card mt-6 space-y-5 p-6" @submit.prevent="submit">
        <div class="grid gap-4 sm:grid-cols-[1fr_160px]">
          <div>
            <label class="label" for="f-algo">算法</label>
            <select id="f-algo" v-model="form.algo" class="input" required>
              <option value="" disabled>选择算法…</option>
              <option v-for="a in algoOptions" :key="a.id" :value="a.id">{{ algoFullLabel(a) }}（{{ TASKS[a.task].label }}）</option>
            </select>
          </div>
          <div>
            <label class="label" for="f-ver">版本</label>
            <select id="f-ver" v-model="form.version" class="input" :disabled="!algo" required>
              <option v-for="v in versions" :key="v.version" :value="v.version" :disabled="v.status !== 'ready'">{{ v.version }}{{ v.status !== 'ready' ? '（不可用）' : '' }}</option>
            </select>
          </div>
        </div>
        <div>
          <label class="label" for="f-bench">评测基准</label>
          <select id="f-bench" v-model="form.bench" class="input" required>
            <option value="" disabled>选择评测基准…</option>
            <option v-for="b in benchOptions" :key="b.id" :value="b.id">{{ b.displayName }}</option>
          </select>
          <p v-if="algo" class="hint">已按算法任务类型「{{ TASKS[algo.task].label }}」筛选</p>
          <div v-if="bench" class="mt-2 flex flex-wrap items-center gap-1.5 rounded-lg bg-gray-50 p-2.5 text-xs dark:bg-gray-800/60">
            <TaskBadge :task="bench.task" />
            <span class="chip mono">{{ bench.datasetId }} · test@{{ bench.datasetVersion }}</span>
            <span class="chip mono">{{ bench.evaluator }}@{{ bench.evaluatorVersion }}</span>
            <span class="chip"><Lock class="size-3" />GT 不进入容器</span>
          </div>
        </div>

        <fieldset class="grid gap-4 sm:grid-cols-3">
          <legend class="label mb-2">运行参数</legend>
          <div>
            <label class="hint mt-0 mb-1 block" for="f-batch">batch_size</label>
            <input id="f-batch" v-model.number="form.batch" type="number" min="1" max="256" class="input" />
          </div>
          <div>
            <label class="hint mt-0 mb-1 block" for="f-seed">seed</label>
            <input id="f-seed" v-model.number="form.seed" type="number" class="input" />
          </div>
          <label class="flex items-center gap-2 self-end pb-2 text-sm"><input v-model="form.fp16" type="checkbox" class="size-4 accent-brand-600" />FP16 推理</label>
        </fieldset>

        <div v-if="checks.length" class="space-y-1.5 rounded-lg border border-gray-100 p-3 dark:border-gray-800">
          <p class="text-xs font-medium text-gray-500">提交前检查</p>
          <p v-for="c in checks" :key="c.text" class="flex items-center gap-1.5 text-sm" :class="c.ok ? 'text-gray-700 dark:text-gray-300' : 'text-rose-600'">
            <CircleCheck v-if="c.ok" class="size-4 text-emerald-500" />
            <CircleAlert v-else class="size-4" />{{ c.text }}
          </p>
          <p v-if="q" class="text-xs text-gray-500">当前队列：{{ q.running }} 个运行中，{{ q.queued }} 个排队。</p>
        </div>

        <div class="flex justify-end gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
          <button type="button" class="btn-default" @click="router.back()">取消</button>
          <button type="submit" class="btn-brand" :disabled="!ready || submitting">{{ submitting ? '提交中…' : '提交评测' }}</button>
        </div>
      </form>
    </StateView>
  </div>
</template>
