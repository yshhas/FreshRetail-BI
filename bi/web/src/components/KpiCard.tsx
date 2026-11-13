import type { ReactNode } from 'react'

export function KpiCard({ label, value, unit, note, metric }: {
  label: string; value: ReactNode; unit?: string; note?: string; metric?: string
}) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}<span className="kpi-unit">{unit}</span></div>
      <div className="kpi-meta">
        {metric && <span className="metric-pill">{metric}</span>}
        {note}
      </div>
    </div>
  )
}
