import { computed, reactive, watch } from 'vue'
import type { RegionName, Role } from '@/types'
import { demoIdentity, users } from '@/mock/orgs'
import { REGIONS } from '@/utils/meta'

const ROLE_KEYS: Role[] = ['admin', 'regional', 'demo', 'vendor']

function loadRole(): Role {
  try {
    const v = JSON.parse(localStorage.getItem('algohub-role') ?? 'null')
    return ROLE_KEYS.includes(v) ? v : 'admin'
  } catch {
    return 'admin'
  }
}

function loadRegion(): RegionName {
  try {
    const v = JSON.parse(localStorage.getItem('algohub-region') ?? 'null')
    return REGIONS.includes(v) ? v : '华中'
  } catch {
    return '华中'
  }
}

const state = reactive({
  role: loadRole(),
  region: loadRegion(),
  dark: document.documentElement.classList.contains('dark'),
})

watch(
  () => state.role,
  (r) => {
    try {
      localStorage.setItem('algohub-role', JSON.stringify(r))
    } catch {
      /* ignore */
    }
  },
)
watch(
  () => state.region,
  (rg) => {
    try {
      localStorage.setItem('algohub-region', JSON.stringify(rg))
    } catch {
      /* ignore */
    }
  },
)
watch(
  () => state.dark,
  (d) => {
    document.documentElement.classList.toggle('dark', d)
    try {
      localStorage.setItem('algohub-theme', d ? 'dark' : 'light')
    } catch {
      /* ignore */
    }
  },
)

const user = computed(() => {
  const base = users.find((u) => u.id === demoIdentity[state.role])!
  if (state.role === 'regional') {
    return { ...base, displayName: `${state.region}区域账号`, region: state.region }
  }
  return base
})

const currentRegion = computed<RegionName | null>(() => (state.role === 'regional' ? state.region : null))

/**
 * 算法可见性：
 * - 管理员、演示账号：可见全部；
 * - 区域侧：可见所有已审核算法（至少有一个 ready/building 版本）；
 * - 厂商：可见自己组织的算法及 Admin 平台基线算法。
 * 数据集对所有人可见（训练集可下载，测试集内容仅管理员可见）。
 */
function canSeeAlgo(a: { org: string; versions?: { status: string }[] }): boolean {
  if (state.role === 'vendor') return a.org === user.value.orgId || a.org === 'Admin'
  if (state.role === 'regional') return !a.versions || a.versions.some((v) => v.status === 'ready' || v.status === 'building')
  return true
}

const can = computed(() => {
  const r = state.role
  return {
    createAlgorithm: r === 'admin' || r === 'vendor',
    createDataset: r === 'admin',
    createBenchmark: r === 'admin',
    runEval: r === 'admin' || r === 'vendor', // 厂商只能评测自己的算法（列表本身已按可见性过滤）
    infer: true,
    downloadTrain: true, // 训练集所有人可下载
    testAccess: r === 'admin', // 测试集查看、下载、编辑
    seeOthersOnBoard: r !== 'vendor', // 厂商在排行榜上只看到自己
    admin: r === 'admin',
    review: r === 'admin',
    dispatch: r === 'admin',
    applyTrial: r === 'regional',
    needsReview: r === 'vendor',
  }
})

export function useSession() {
  return { state, user, currentRegion, can, canSeeAlgo }
}
