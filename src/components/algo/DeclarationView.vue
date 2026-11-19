<script setup lang="ts">
import { computed, ref } from 'vue'
import { CircleCheck, CircleX, FileText } from 'lucide-vue-next'
import type { AlgoDeclaration } from '@/types'
import { CHECKLIST, CROSS_DIRECTIONS, DELIVERIES, POLYGON_TYPES, managementJson, packageInfoXml, technicalJson } from '@/utils/standard'
import { fmtBytes } from '@/utils/format'
import NecessityBadge from '@/components/form/NecessityBadge.vue'

/** 展示按《算法标准 1.0》提交的申报信息 */
const props = defineProps<{ d: AlgoDeclaration }>()
const file = ref<'pkg' | 'mgmt' | 'tech'>('mgmt')
const text = computed(() => (file.value === 'pkg' ? packageInfoXml(props.d.packageInfo) : file.value === 'mgmt' ? managementJson(props.d.management) : technicalJson(props.d.technical)))
const m = computed(() => props.d.management)
const t = computed(() => props.d.technical)
const p = computed(() => props.d.params)
const supports = computed(() => [
  { k: '通用参数 generalParam', on: p.value.generalParam.enabled },
  { k: '检测区域 detectRegionList', on: p.value.detectRegion },
  { k: '屏蔽区域 maskRegionList', on: p.value.maskRegion },
  { k: '区域规则 ruleRegionList', on: p.value.ruleRegion.enabled },
  { k: '目标数量过滤 numberCondition', on: p.value.numberCondition },
  { k: '目标尺寸过滤 sizeFilter', on: p.value.sizeFilter },
])
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-[1fr_420px]">
    <div class="min-w-0 space-y-6">
      <section class="card p-5">
        <h2 class="section-title mb-3">算法属性</h2>
        <dl class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-xs text-gray-500">名称</dt><dd>{{ m.name.zh_CN }}<span v-if="m.name.en_US" class="text-gray-500"> · {{ m.name.en_US }}</span></dd></div>
          <div><dt class="text-xs text-gray-500">算法标识 / 版本</dt><dd class="mono">{{ m.id }} @ {{ t.version }}</dd></div>
          <div><dt class="text-xs text-gray-500">厂商</dt><dd>{{ d.packageInfo.vendor.zh_CN }} <code class="mono text-xs text-gray-400">{{ d.packageInfo.vendor.id }}</code></dd></div>
          <div><dt class="text-xs text-gray-500">算法分类</dt><dd class="flex flex-wrap gap-1"><code v-for="c in m.classifications" :key="c" class="chip mono">{{ c }}</code></dd></div>
          <div class="sm:col-span-2"><dt class="text-xs text-gray-500">适用场所</dt><dd class="flex flex-wrap gap-1"><span v-for="c in m.places" :key="c" class="chip">{{ c }}</span></dd></div>
          <div class="sm:col-span-2"><dt class="text-xs text-gray-500">使用要求</dt>
            <dd class="mt-1 grid gap-1 sm:grid-cols-2">
              <span v-for="(v, k) in m.conditions.description.zh_CN" v-show="v" :key="k"><code class="mono text-xs text-gray-400">{{ k }}</code> {{ v }}</span>
            </dd>
          </div>
        </dl>
      </section>

      <section class="card p-5">
        <h2 class="section-title mb-3">技术信息</h2>
        <dl class="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
          <div><dt class="text-xs text-gray-500">数据类型</dt><dd class="flex flex-wrap gap-1"><span v-for="(s, i) in t.analysisSources" :key="i" class="chip">{{ s.type }}<template v-if="s.format?.length"> · {{ s.format.join('/') }}</template><template v-if="s.min"> · {{ s.min }}–{{ s.max }}</template></span></dd></div>
          <div><dt class="text-xs text-gray-500">芯片</dt><dd>{{ t.environment.chip }}<span v-if="t.environment.basePackage" class="text-gray-500"> · {{ t.environment.basePackage.id }} {{ t.environment.basePackage.minorVersion }}–{{ t.environment.basePackage.majorVersion }}</span></dd></div>
          <div class="sm:col-span-2"><dt class="text-xs text-gray-500">占用资源</dt><dd>显存 {{ t.requirement.videoMemory }} MB · 内存 {{ t.requirement.memory }} MB · 磁盘 {{ t.requirement.disk }} MB · 智能内存 {{ t.requirement.AImemory }} MB · CPU {{ t.requirement.CPU }} 核</dd></div>
          <div class="sm:col-span-2"><dt class="text-xs text-gray-500">性能规格</dt>
            <dd class="mt-1 flex flex-wrap gap-1"><span v-for="(a, i) in t.abilityInfos" :key="i" class="chip">{{ a.type }} · {{ a.specification }} · 算力 {{ a.ability }}% · {{ a.taskAbility }} 路</span></dd>
          </div>
          <div><dt class="text-xs text-gray-500">事件信息</dt><dd class="mono">{{ t.regulation.eventCode }}</dd></div>
          <div><dt class="text-xs text-gray-500">事件类型</dt><dd class="flex flex-wrap gap-1"><code v-for="e in p.eventTypes" :key="e" class="chip mono">{{ e }}</code></dd></div>
        </dl>
      </section>

      <section class="card p-5">
        <h2 class="section-title mb-3">支持的分析参数</h2>
        <div class="grid gap-1.5 text-sm sm:grid-cols-2">
          <p v-for="s in supports" :key="s.k" class="flex items-center gap-1.5" :class="s.on ? '' : 'text-gray-400'">
            <CircleCheck v-if="s.on" class="size-4 text-emerald-500" /><CircleX v-else class="size-4" />{{ s.k }}
          </p>
        </div>
        <p v-if="p.ruleRegion.enabled" class="mt-2 text-xs text-gray-500">
          跨线方向：{{ p.ruleRegion.crossDirections.map((x) => CROSS_DIRECTIONS.find((d) => d.v === x)?.label).join('、') }} · 区域类型：{{ p.ruleRegion.polygonTypes.map((x) => POLYGON_TYPES.find((d) => d.v === x)?.label).join('、') }}
        </p>
      </section>

      <section class="card p-5">
        <h2 class="section-title mb-3">交付材料</h2>
        <div class="divide-y divide-gray-100 text-sm dark:divide-gray-800">
          <div v-for="x in DELIVERIES" :key="x.key" class="flex items-center gap-2 py-2">
            <FileText class="size-4 shrink-0 text-gray-400" />
            <span class="min-w-0 flex-1 truncate">{{ x.name }}</span>
            <NecessityBadge :n="x.necessity" />
            <template v-if="d.deliveries.find((y) => y.key === x.key)">
              <span class="mono max-w-48 truncate text-xs text-gray-500">{{ d.deliveries.find((y) => y.key === x.key)!.fileName }}</span>
              <span class="text-xs text-gray-400">{{ fmtBytes(d.deliveries.find((y) => y.key === x.key)!.size) }}</span>
            </template>
            <span v-else class="text-xs text-gray-400">未提交</span>
          </div>
        </div>
        <p class="mt-3 text-xs text-gray-500">文档内容自查：已确认 {{ d.checklist.length }} / {{ CHECKLIST.length }} 项</p>
      </section>
    </div>

    <aside class="min-w-0">
      <div class="card p-4 lg:sticky lg:top-20">
        <h2 class="mb-2 text-sm font-semibold">描述文件</h2>
        <div class="no-scrollbar mb-2 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-gray-100 dark:border-gray-800">
          <button type="button" class="tab" :class="{ 'tab-active': file === 'pkg' }" @click="file = 'pkg'">packageinfo.xml</button>
          <button type="button" class="tab" :class="{ 'tab-active': file === 'mgmt' }" @click="file = 'mgmt'">managementinfo.json</button>
          <button type="button" class="tab" :class="{ 'tab-active': file === 'tech' }" @click="file = 'tech'">technicalinfo.json</button>
        </div>
        <pre class="scroll-thin max-h-[560px] overflow-auto rounded-lg bg-gray-900 p-3 text-[11px] leading-relaxed text-gray-100">{{ text }}</pre>
      </div>
    </aside>
  </div>
</template>
