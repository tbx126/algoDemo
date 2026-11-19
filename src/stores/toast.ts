import { reactive } from 'vue'

export interface Toast {
  id: number
  kind: 'success' | 'error' | 'info'
  text: string
}

export const toasts = reactive<Toast[]>([])
let id = 0

export function toast(text: string, kind: Toast['kind'] = 'success') {
  const t = { id: ++id, kind, text }
  toasts.push(t)
  setTimeout(() => {
    const i = toasts.findIndex((x) => x.id === t.id)
    if (i >= 0) toasts.splice(i, 1)
  }, 3200)
}
