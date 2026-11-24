<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ApiError, listTags, updateAlgorithm } from '@/api'
import { toast } from '@/stores/toast'
import { BUSINESS_CATEGORIES, TASKS } from '@/utils/meta'
import type { Algorithm, BusinessCategory, Framework, TaskType } from '@/types'
import Modal from '@/components/ui/Modal.vue'
import TagInput from '@/components/form/TagInput.vue'

/** 管理员编辑算法基本信息（版本、镜像、权重等构建产物不在此修改） */
const props = defineProps<{ algo: Algorithm }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Algorithm] }>()

const f = reactive({
  summary: '',
  tags: [] as string[],
  task: 'object-detection' as TaskType,
  business: 'inspection' as BusinessCategory,
  framework: 'PyTorch' as Framework,
  selfDeveloped: false,
  readme: '',
})
const tagSuggestions = ref<string[]>([])
watch(
  open,
  async (v) => {
    if (!v) return
    Object.assign(f, {
      summary: props.algo.summary,
      tags: [...props.algo.tags],
      task: props.algo.task,
      business: props.algo.business ?? 'inspection',
      framework: props.algo.framework,
      selfDeveloped: !!props.algo.selfDeveloped,
      readme: props.algo.readme,
    })
    tagSuggestions.value = (await listTags()).map((t) => t.name)
  },
  { immediate: true },
)

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
  <Modal v-model:open="open" :title="`编辑算法 · ${algo.id}`" description="修改基本信息、分类、标签与算法卡片，将同步更新 algo.yaml（不产生新版本）。" width="max-w-2xl">
    <form id="edit-algo" class="space-y-4" @submit.prevent="save">
      <div class="grid gap-3 sm:grid-cols-3">
        <div>
          <label class="label" for="ea-task">任务分类</label>
          <select id="ea-task" v-model="f.task" class="input">
            <option v-for="(v, k) in TASKS" :key="k" :value="k">{{ v.label }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="ea-biz">业务分类</label>
          <select id="ea-biz" v-model="f.business" class="input">
            <option v-for="(v, k) in BUSINESS_CATEGORIES" :key="k" :value="k">{{ v.label }}</option>
          </select>
        </div>
        <div>
          <label class="label" for="ea-fw">推理框架</label>
          <select id="ea-fw" v-model="f.framework" class="input">
            <option v-for="x in ['PyTorch', 'ONNX', 'TensorRT', 'OpenCV', 'NumPy', 'Paddle']" :key="x">{{ x }}</option>
          </select>
        </div>
      </div>
      <label class="flex cursor-pointer items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input v-model="f.selfDeveloped" type="checkbox" class="size-4 accent-brand-600" />
        <span>标记为<strong>平台自研</strong>算法</span>
      </label>
      <div>
        <label class="label" for="ea-sum">简介</label>
        <textarea id="ea-sum" v-model="f.summary" rows="2" class="input" />
      </div>
      <TagInput v-model="f.tags" label="标签" :suggestions="tagSuggestions" placeholder="输入标签后回车添加，或点选下方已有标签" />
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
