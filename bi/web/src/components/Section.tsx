import type { ReactNode } from 'react'

export function Section({
  title, subtitle, right, children
}: { title: string; subtitle?: string; right?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <div className="card-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p className="subtitle">{subtitle}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  )
}
