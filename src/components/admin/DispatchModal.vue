<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, MapPin, Send } from 'lucide-vue-next'
import { ApiError, getDispatchedRegions, getPendingTrialRegionsForAlgo, setAlgorithmDispatches } from '@/api'
import type { RegionName } from '@/types'
import { REGIONS } from '@/utils/meta'
import { algoFullLabel } from '@/utils/display'
import { toast } from '@/stores/toast'
import Modal from '@/components/ui/Modal.vue'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ algorithmId: string }>()
const emit = defineEmits<{ saved: [regions: RegionName[]] }>()

const selected = ref<RegionName[]>([])
const saving = ref(false)
const pendingRegions = computed(() => new Set(getPendingTrialRegionsForAlgo(props.algorithmId)))

watch(
  () => [open.value, props.algorithmId] as const,
  ([isOpen, id]) => {
    if (isOpen && id) {
      selected.value = [...getDispatchedRegions(id)]
    }
  },
  { immediate: true },
)

function toggle(rg: RegionName) {
  if (selected.value.includes(rg)) {
    selected.value = selected.value.filter((x) => x !== rg)
  } else {
    selected.value = [...selected.value, rg]
  }
}

function selectAll() {
  selected.value = [...REGIONS]
}

function clearAll() {
  selected.value = []
}

async function save() {
  if (saving.value || !props.algorithmId) return
  saving.value = true
  try {
    const res = await setAlgorithmDispatches(props.algorithmId, selected.value)
    toast(res.length ? `已将算法下发至 ${res.length} 个区域（${res.slice(0, 4).join('、')}${res.length > 4 ? ' 等' : ''}）` : '已取消该算法的全部区域下发')
    emit('saved', res)
    open.value = false
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '下发保存失败', 'error')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Modal
    v-model:open="open"
    :title="`下发算法至区域侧 · ${algoFullLabel(algorithmId)}`"
    description="勾选目标区域即可将算法下发授权给对应区域侧使用；勾选存在待审批试用申请的区域将自动审批通过。"
    width="max-w-xl"
  >
    <div class="space-y-4">
      <div class="flex items-center justify-between text-xs">
        <span class="text-gray-500">
          已选择 <strong class="mono text-gray-900 dark:text-white">{{ selected.length }}</strong> / {{ REGIONS.length }} 个区域
        </span>
        <div class="flex items-center gap-2">
          <button type="button" class="text-brand-600 hover:underline dark:text-brand-400" @click="selectAll">全选 ({{ REGIONS.length }})</button>
          <span class="text-gray-300 dark:text-gray-700">|</span>
          <button type="button" class="text-gray-500 hover:text-gray-900 dark:hover:text-white" @click="clearAll">清空</button>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-2 sm:grid-cols-4">
        <button
          v-for="rg in REGIONS"
          :key="rg"
          type="button"
          class="relative flex cursor-pointer items-center justify-between gap-1.5 rounded-lg border px-2.5 py-2 text-left text-xs font-medium transition"
          :class="
            selected.includes(rg)
              ? 'border-brand-500 bg-brand-50/80 text-brand-700 ring-1 ring-brand-500/20 dark:border-brand-500 dark:bg-brand-950/50 dark:text-brand-300'
              : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300 dark:hover:bg-gray-800'
          "
          @click="toggle(rg)"
        >
          <span class="flex items-center gap-1.5 truncate">
            <MapPin class="size-3.5 shrink-0 opacity-60" />
            <span>{{ rg }}</span>
          </span>
          <span
            class="flex size-4 shrink-0 items-center justify-center rounded border transition"
            :class="selected.includes(rg) ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-300 dark:border-gray-600'"
          >
            <Check v-if="selected.includes(rg)" class="size-3" />
          </span>
          <span
            v-if="pendingRegions.has(rg)"
            class="absolute -top-1.5 -right-1 rounded-full bg-amber-500 px-1.5 py-0.2 text-[9px] font-semibold text-white shadow-xs"
            title="该区域有待审批的试用申请"
          >
            待审
          </span>
        </button>
      </div>
    </div>

    <template #footer>
      <button type="button" class="btn-default" @click="open = false">取消</button>
      <button type="button" class="btn-brand" :disabled="saving" @click="save">
        <Send class="size-3.5" />{{ saving ? '保存中…' : '确认下发' }}
      </button>
    </template>
  </Modal>
</template>
