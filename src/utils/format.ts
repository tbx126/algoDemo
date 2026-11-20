export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  const u = ['KB', 'MB', 'GB', 'TB']
  let i = -1
  do {
    n /= 1024
    i++
  } while (n >= 1024 && i < u.length - 1)
  return `${n.toFixed(n < 10 ? 1 : 0)} ${u[i]}`
}

export function fmtNum(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)} 万`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n)
}

// 相对时间以当前时间为基准

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} 天前`
  if (s < 86400 * 365) return `${Math.floor(s / 86400 / 30)} 个月前`
  return `${Math.floor(s / 86400 / 365)} 年前`
}

export function fmtDate(iso: string): string {
  const d = new Date(iso)
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function fmtDuration(sec?: number): string {
  if (sec == null) return '—'
  if (sec < 60) return `${Math.round(sec)} 秒`
  const m = Math.floor(sec / 60)
  if (m < 60) return `${m} 分 ${Math.round(sec % 60)} 秒`
  return `${Math.floor(m / 60)} 时 ${m % 60} 分`
}

export function fmtMetric(v: number | undefined, unit?: string): string {
  if (v == null || Number.isNaN(v)) return '—'
  if (unit === '%') return `${v.toFixed(1)}`
  if (unit === 'ms') return v.toFixed(1)
  if (unit === 'GB') return v.toFixed(2)
  return v < 1 ? v.toFixed(3) : v.toFixed(2)
}

/** 可复现的伪随机数 (mulberry32) */
export function rng(seed: number) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function hashStr(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export function fakeSha(seed: string, len = 64): string {
  const r = rng(hashStr(seed))
  let s = ''
  for (let i = 0; i < len; i++) s += Math.floor(r() * 16).toString(16)
  return s
}
