import { ref, watch, type Ref, type WatchSource } from 'vue'
import { ApiError } from '@/api'

/** 简单的数据加载组合式函数：自动处理 loading / error，依赖变化时重新加载 */
export function useAsync<T>(fn: () => Promise<T>, deps: WatchSource[] = []) {
  const data = ref<T>() as Ref<T | undefined>
  const loading = ref(true)
  const error = ref<{ status: number; message: string } | null>(null)
  let seq = 0
  async function run() {
    const my = ++seq
    loading.value = true
    error.value = null
    try {
      const r = await fn()
      if (my === seq) data.value = r
    } catch (e) {
      if (my === seq) error.value = e instanceof ApiError ? { status: e.status, message: e.message } : { status: 500, message: String(e) }
    } finally {
      if (my === seq) loading.value = false
    }
  }
  watch(deps, run, { immediate: true, deep: true })
  return { data, loading, error, reload: run }
}
