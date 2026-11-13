export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

export function fmtNumber(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits }).format(v)
}

export function fmtRate(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

export function fmtIndex(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 }).format(v)
}

export function fmtCompact(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e8) return `${(v / 1e8).toFixed(1)}亿`
  if (a >= 1e4) return `${(v / 1e4).toFixed(0)}万`
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(v)
}

export function weekday(v: number): string {
  return WEEKDAYS[v] ?? `W${v}`
}

export function shortId(prefix: string, id: number): string {
  return `${prefix}${String(id).padStart(4, '0')}`
}

export function dateLabel(iso: string): string {
  return iso.slice(5)
}
