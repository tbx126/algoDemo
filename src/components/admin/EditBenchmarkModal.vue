<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ApiError, getDataset, updateBenchmark } from '@/api'
import { toast } from '@/stores/toast'
import type { Benchmark, MetricDef } from '@/types'
import Modal from '@/components/ui/Modal.vue'

/** 管理员编辑评测基准：名称、说明、绑定的测试集版本与指标配置 */
const props = defineProps<{ b: Benchmark }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Benchmark] }>()

const f = reactive({ displayName: '', description: '', datasetVersion: '', metrics: [] as MetricDef[] })
const testVersions = ref<string[]>([])
watch(
  open,
  async (v) => {
    if (!v) return
    Object.assign(f, { displayName: props.b.displayName, description: props.b.description, datasetVersion: props.b.datasetVersion, metrics: JSON.parse(JSON.stringify(props.b.metrics)) })
    try {
      testVersions.value = (await getDataset(props.b.datasetId)).test?.versions.map((x) => x.version) ?? [props.b.datasetVersion]
    } catch {
      testVersions.value = [props.b.datasetVersion]
    }
  },
  { immediate: true },
)
function setPrimary(key: string) {
  f.metrics.forEach((m) => (m.primary = m.key === key))
}

const saving = ref(false)
async function save() {
  if (!f.displayName.trim()) return toast('显示名称不能为空', 'error')
  saving.value = true
  try {
    const b = await updateBenchmark(props.b.id, { displayName: f.displayName.trim(), description: f.description.trim(), datasetVersion: f.datasetVersion, metrics: f.metrics })
    toast('评测基准已保存')
    emit('saved', b)
    open.value = false
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal v-model:open="open" :title="`编辑评测基准 · ${b.name}`" width="max-w-2xl">
    <form id="edit-bench" class="space-y-4" @submit.prevent="save">
      <div class="grid gap-3 sm:grid-cols-[1fr_160px]">
        <div>
          <label class="label" for="eb-name">显示名称</label>
          <input id="eb-name" v-model="f.displayName" class="input" required />
        </div>
        <div>
          <label class="label" for="eb-ver">测试集版本</label>
          <select id="eb-ver" v-model="f.datasetVersion" class="input">
            <option v-for="v in testVersions" :key="v" :value="v">{{ v }}</option>
          </select>
        </div>
      </div>
      <div>
        <label class="label" for="eb-desc">说明</label>
        <textarea id="eb-desc" v-model="f.description" rows="2" class="input" />
      </div>
      <div>
        <p class="label">指标</p>
        <div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table class="table-base">
            <thead><tr><th>主指标</th><th>键</th><th>名称</th><th>单位</th><th>方向</th></tr></thead>
            <tbody>
              <tr v-for="m in f.metrics" :key="m.key">
                <td><input type="radio" name="eb-primary" :checked="m.primary" class="accent-amber-500" :aria-label="`设 ${m.label} 为主指标`" @change="setPrimary(m.key)" /></td>
                <td class="mono text-xs">{{ m.key }}</td>
                <td><input v-model="m.label" class="input py-1" aria-label="指标名称" /></td>
                <td><input v-model="m.unit" class="input w-16 py-1" aria-label="单位" /></td>
                <td>
                  <select v-model="m.higherIsBetter" class="input py-1" aria-label="方向">
                    <option :value="true">越高越好</option>
                    <option :value="false">越低越好</option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <p class="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
        更换测试集版本或主指标会改变排行榜的比较口径；已有评测记录仍基于原测试集版本，建议重新评测后再对比。
      </p>
    </form>
    <template #footer>
      <button type="button" class="btn-default" @click="open = false">取消</button>
      <button type="submit" form="edit-bench" class="btn-brand" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>
