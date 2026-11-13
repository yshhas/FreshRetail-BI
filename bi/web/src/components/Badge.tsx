import type { ReactNode } from 'react'

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'info' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function StatusBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="muted">—</span>
  const tone = value.includes('不适用') ? 'warn' : 'neutral'
  return <Badge tone={tone}>{value}</Badge>
}
