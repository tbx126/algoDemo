<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ApiError, updateAlgorithm } from '@/api'
import { toast } from '@/stores/toast'
import { TASKS } from '@/utils/meta'
import type { Algorithm, Framework, TaskType } from '@/types'
import Modal from '@/components/ui/Modal.vue'
import TagInput from '@/components/form/TagInput.vue'

/** 管理员编辑算法基本信息（版本、镜像、权重等构建产物不在此修改） */
const props = defineProps<{ algo: Algorithm }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Algorithm] }>()

const f = reactive({ summary: '', tags: [] as string[], task: 'object-detection' as TaskType, framework: 'PyTorch' as Framework, readme: '' })
watch(open, (v) => v && Object.assign(f, { summary: props.algo.summary, tags: [...props.algo.tags], task: props.algo.task, framework: props.algo.framework, readme: props.algo.readme }), { immediate: true })

const saving = ref(false)
async function save() {
  saving.value = true
  try {
    const a = await updateAlgorithm(props.algo.id, { ...f, summary: f.summary.trim(), tags: [...f.tags] })
    toast('算法信息已保存')
    emit('saved', a)
    open.value = false
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal v-model:open="open" :title="`编辑算法 · ${algo.id}`" description="修改基本信息与算法卡片。版本、镜像与权重属于构建产物，需通过提交新版本更新。" width="max-w-2xl">
    <form id="edit-algo" class="space-y-4" @submit.prevent="save">
      <div class="grid gap-3 sm:grid-cols-2">
        <div>
          <label class="label" for="ea-task">平台评测任务类型</label>
          <select id="ea-task" v-model="f.task" class="input">
            <option v-for="(v, k) in TASKS" :key="k" :value="k">{{ v.label }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="ea-fw">推理框架</label>
          <select id="ea-fw" v-model="f.framework" class="input">
            <option v-for="x in ['PyTorch', 'ONNX', 'TensorRT', 'OpenCV', 'NumPy', 'Paddle']" :key="x">{{ x }}</option>
          </select>
        </div>
      </div>
      <div>
        <label class="label" for="ea-sum">简介</label>
        <textarea id="ea-sum" v-model="f.summary" rows="2" class="input" />
      </div>
      <TagInput v-model="f.tags" label="标签" />
      <div>
        <label class="label" for="ea-md">算法卡片（Markdown）</label>
        <textarea id="ea-md" v-model="f.readme" rows="10" class="input mono text-xs" />
      </div>
    </form>
    <template #footer>
      <button type="button" class="btn-default" @click="open = false">取消</button>
      <button type="submit" form="edit-algo" class="btn-brand" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>
