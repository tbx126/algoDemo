<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ApiError, updateDataset } from '@/api'
import { toast } from '@/stores/toast'
import type { Dataset } from '@/types'
import Modal from '@/components/ui/Modal.vue'
import TagInput from '@/components/form/TagInput.vue'

/** 管理员编辑数据集信息（数据内容通过上传新版本更新） */
const props = defineProps<{ ds: Dataset }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [Dataset] }>()

const f = reactive({ summary: '', tags: [] as string[], classes: [] as string[], readme: '' })
watch(open, (v) => v && Object.assign(f, { summary: props.ds.summary, tags: [...props.ds.tags], classes: [...props.ds.classes], readme: props.ds.readme }), { immediate: true })
// 已在 labels.csv 中出现过的类别不应删除，否则已有标注会失效
const usedClasses = computed(() => new Set([...Object.keys(props.ds.train.classCounts), ...Object.keys(props.ds.test?.classCounts ?? {})]))
const removedUsed = computed(() => [...usedClasses.value].filter((c) => props.ds.classes.includes(c) && !f.classes.includes(c)))

const saving = ref(false)
async function save() {
  saving.value = true
  try {
    const d = await updateDataset(props.ds.id, { summary: f.summary.trim(), tags: [...f.tags], classes: [...f.classes], readme: f.readme })
    toast('数据集信息已保存')
    emit('saved', d)
    open.value = false
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '保存失败', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal v-model:open="open" :title="`编辑数据集 · ${ds.id}`" description="修改简介、标签、类别表与数据集卡片。数据文件与 labels.csv 需通过上传新版本更新。" width="max-w-2xl">
    <form id="edit-ds" class="space-y-4" @submit.prevent="save">
      <div>
        <label class="label" for="ed-sum">简介</label>
        <textarea id="ed-sum" v-model="f.summary" rows="2" class="input" />
      </div>
      <TagInput v-model="f.tags" label="标签" />
      <TagInput v-model="f.classes" label="类别表" hint="训练集与测试集共用；labels.csv 的 label 必须在此表内" />
      <p v-if="removedUsed.length" class="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
        注意：{{ removedUsed.join('、') }} 已在现有 labels.csv 中使用，删除后这些标注将不在类别表内。
      </p>
      <div>
        <label class="label" for="ed-md">数据集卡片（Markdown）</label>
        <textarea id="ed-md" v-model="f.readme" rows="10" class="input mono text-xs" />
      </div>
    </form>
    <template #footer>
      <button type="button" class="btn-default" @click="open = false">取消</button>
      <button type="submit" form="edit-ds" class="btn-brand" :disabled="saving">{{ saving ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>
