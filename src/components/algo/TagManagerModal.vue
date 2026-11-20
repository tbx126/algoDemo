<script setup lang="ts">
import { ref, watch } from 'vue'
import { Check, Pencil, Plus, Tag, Trash2, X } from 'lucide-vue-next'
import { ApiError, createTag, deleteTag, listTags, renameTag, type TagSummary } from '@/api'
import { toast } from '@/stores/toast'
import Modal from '@/components/ui/Modal.vue'

/** 标签管理弹窗：新增标签、修改标签名称（同步所有算法）、删除标签 */
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ changed: [] }>()

const tags = ref<TagSummary[]>([])
const loading = ref(false)
const newName = ref('')
const busy = ref(false)

const editing = ref<string | null>(null)
const editDraft = ref('')

async function load() {
  loading.value = true
  try {
    tags.value = await listTags()
  } finally {
    loading.value = false
  }
}

watch(open, (v) => {
  if (v) {
    editing.value = null
    newName.value = ''
    load()
  }
})

async function add() {
  const v = newName.value.trim()
  if (!v || busy.value) return
  busy.value = true
  try {
    await createTag(v)
    newName.value = ''
    toast(`已添加标签「${v}」`)
    await load()
    emit('changed')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '添加失败', 'error')
  } finally {
    busy.value = false
  }
}

function startEdit(name: string) {
  editing.value = name
  editDraft.value = name
}

async function saveEdit(oldName: string) {
  const next = editDraft.value.trim()
  if (!next) {
    toast('标签名称不能为空', 'error')
    return
  }
  if (next === oldName) {
    editing.value = null
    return
  }
  busy.value = true
  try {
    await renameTag(oldName, next)
    editing.value = null
    toast(`已将「${oldName}」重命名为「${next}」`)
    await load()
    emit('changed')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '修改失败', 'error')
  } finally {
    busy.value = false
  }
}

async function remove(name: string) {
  if (busy.value) return
  busy.value = true
  try {
    await deleteTag(name)
    toast(`已删除标签「${name}」`, 'info')
    if (editing.value === name) editing.value = null
    await load()
    emit('changed')
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '删除失败', 'error')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <Modal v-model:open="open" title="标签管理" description="新增标签、修改标签名称或移除不再使用的标签；重命名会同步更新已关联该标签的算法。" width="max-w-lg">
    <div class="space-y-4">
      <form class="flex gap-2" @submit.prevent="add">
        <input v-model="newName" class="input flex-1" placeholder="输入新标签名称，回车添加" aria-label="新标签名称" />
        <button type="submit" class="btn-primary shrink-0" :disabled="busy || !newName.trim()">
          <Plus class="size-4" />添加标签
        </button>
      </form>

      <div class="flex items-center justify-between text-xs text-gray-500">
        <span>共 {{ tags.length }} 个标签</span>
        <span>括号内为关联算法数</span>
      </div>

      <div v-if="loading && !tags.length" class="py-8 text-center text-sm text-gray-400">加载中…</div>
      <div v-else-if="!tags.length" class="rounded-lg border border-dashed border-gray-200 py-8 text-center text-sm text-gray-400 dark:border-gray-800">暂无标签</div>
      <ul v-else class="scroll-thin max-h-80 divide-y divide-gray-100 overflow-y-auto rounded-lg border border-gray-200 dark:divide-gray-800 dark:border-gray-800">
        <li v-for="t in tags" :key="t.name" class="flex items-center gap-2 px-3 py-2 text-sm">
          <Tag class="size-3.5 shrink-0 text-gray-400" />
          <template v-if="editing === t.name">
            <input
              v-model="editDraft"
              class="input h-7 flex-1 py-0 text-sm"
              aria-label="修改标签名称"
              autofocus
              @keydown.enter.prevent="saveEdit(t.name)"
              @keydown.esc.prevent="editing = null"
            />
            <button type="button" class="btn-ghost px-1.5 py-1 text-emerald-600" title="保存" :disabled="busy" @click="saveEdit(t.name)">
              <Check class="size-4" />
            </button>
            <button type="button" class="btn-ghost px-1.5 py-1 text-gray-400" title="取消" @click="editing = null">
              <X class="size-4" />
            </button>
          </template>
          <template v-else>
            <span class="min-w-0 flex-1 truncate text-gray-800 dark:text-gray-200">{{ t.name }}</span>
            <span class="chip shrink-0 text-[11px]">{{ t.count }} 个算法</span>
            <button type="button" class="btn-ghost px-1.5 py-1 text-xs text-gray-500" title="修改名称" @click="startEdit(t.name)">
              <Pencil class="size-3.5" />
            </button>
            <button type="button" class="btn-ghost px-1.5 py-1 text-xs text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-950/40" title="删除标签" :disabled="busy" @click="remove(t.name)">
              <Trash2 class="size-3.5" />
            </button>
          </template>
        </li>
      </ul>
    </div>
    <template #footer>
      <button type="button" class="btn-default" @click="open = false">关闭</button>
    </template>
  </Modal>
</template>
