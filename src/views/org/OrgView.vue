<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Box, Database, FileBadge, Users } from 'lucide-vue-next'
import { getOrg, listAlgorithms, listDatasets, listUsers } from '@/api'
import { useAsync } from '@/utils/useAsync'
import { useSession } from '@/stores/session'
import { ROLES } from '@/utils/meta'
import StateView from '@/components/ui/StateView.vue'
import OrgAvatar from '@/components/ui/OrgAvatar.vue'
import AlgoCard from '@/components/algo/AlgoCard.vue'
import DatasetCard from '@/components/dataset/DatasetCard.vue'

const route = useRoute()
const { user, can } = useSession()
const id = computed(() => route.params.id as string)
const { data: org, loading, error } = useAsync(() => getOrg(id.value))
const { data: algos } = useAsync(() => listAlgorithms({ org: id.value, pageSize: 999, sort: 'updated' }))
const { data: dss } = useAsync(() => listDatasets({ org: id.value, pageSize: 999, sort: 'updated' }))
const { data: members } = useAsync(() => listUsers())
const orgMembers = computed(() => (members.value ?? []).filter((u) => u.orgId === id.value && u.active))
const showMembers = computed(() => can.value.admin || user.value.orgId === id.value)
const tab = ref<'algos' | 'datasets'>('algos')
</script>

<template>
  <StateView :loading="loading" :error="error">
    <div v-if="org" class="container-page pt-8">
      <div class="flex flex-wrap items-center gap-4">
        <OrgAvatar :org="org.id" :size="64" />
        <div>
          <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">{{ org.displayName }}<span class="chip ml-2 align-middle text-xs">{{ org.kind === 'vendor' ? '厂商' : org.id === 'Admin' ? '命名空间' : '内部团队' }}</span></h1>
          <p class="mono text-sm text-gray-500">{{ org.name }}</p>
          <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">{{ org.description }}</p>
        </div>
      </div>

      <div class="mt-8 flex flex-col gap-8 lg:flex-row">
        <div class="min-w-0 flex-1">
          <div class="mb-4 flex gap-1 border-b border-gray-100 dark:border-gray-800">
            <button class="tab" :class="{ 'tab-active': tab === 'algos' }" @click="tab = 'algos'"><Box class="size-4" />算法 <span class="text-gray-400">{{ algos?.total ?? 0 }}</span></button>
            <button class="tab" :class="{ 'tab-active': tab === 'datasets' }" @click="tab = 'datasets'"><Database class="size-4" />数据集 <span class="text-gray-400">{{ dss?.total ?? 0 }}</span></button>
          </div>
          <StateView v-if="tab === 'algos'" :loading="!algos" :empty="algos && !algos.items.length" empty-text="该组织暂无你可见的算法">
            <div class="grid gap-3 xl:grid-cols-2"><AlgoCard v-for="a in algos!.items" :key="a.id" :a="a" /></div>
          </StateView>
          <StateView v-else :loading="!dss" :empty="dss && !dss.items.length" empty-text="该组织暂无你可见的数据集">
            <div class="grid gap-3 xl:grid-cols-2"><DatasetCard v-for="d in dss!.items" :key="d.id" :d="d" /></div>
          </StateView>
        </div>
        <aside class="w-full shrink-0 lg:w-72">
          <div v-if="org.kind === 'team'" class="card p-4 text-sm text-gray-600 dark:text-gray-400">
            {{ org.id === 'Admin' ? '管理员上传的数据集统一放在此命名空间。' : '平台内部命名空间，存放基线算法，由管理员统一维护。' }}
          </div>
          <div v-else class="card p-4">
            <h3 class="mb-3 flex items-center gap-1.5 text-sm font-semibold"><Users class="size-4" />厂商账号 <span class="font-normal text-gray-400">{{ orgMembers.length }}</span></h3>
            <template v-if="showMembers">
              <div v-for="u in orgMembers" :key="u.id" class="flex items-center justify-between py-1 text-sm">
                <span>{{ u.displayName }}</span><span class="text-xs text-gray-500">{{ ROLES[u.role].label }}</span>
              </div>
            </template>
            <p v-else class="text-sm text-gray-500">仅本厂商与管理员可查看</p>
          </div>
          <div v-if="can.admin && org.profile" class="card mt-4 space-y-3 p-4 text-sm">
            <h3 class="flex items-center gap-1.5 font-semibold"><FileBadge class="size-4" />入库申报信息</h3>
            <div><p class="text-xs text-gray-500">企业全称</p><p>{{ org.profile.company.fullName }}</p></div>
            <div><p class="text-xs text-gray-500">统一社会信用代码</p><p class="mono">{{ org.profile.company.creditCode }}</p></div>
            <div><p class="text-xs text-gray-500">类型 / 状态</p><p>{{ org.profile.company.type }} · {{ org.profile.company.status }} · {{ org.profile.company.capital }}</p></div>
            <div><p class="text-xs text-gray-500">联系方式</p><p>{{ org.profile.contact.phone }} · {{ org.profile.contact.email }}</p></div>
            <div><p class="text-xs text-gray-500">对接人</p><p>{{ org.profile.liaison.name }}（{{ org.profile.liaison.title }}）{{ org.profile.liaison.phone }}</p></div>
            <div><p class="text-xs text-gray-500">资质 / 软著 / 专利</p><p>{{ org.profile.certificates.length || (org.profile.noCertificateNote ? '无资质（已提交说明）' : 0) }} / {{ org.profile.copyrights.length }} / {{ org.profile.patents.length }}</p></div>
          </div>
        </aside>
      </div>
    </div>
  </StateView>
</template>
