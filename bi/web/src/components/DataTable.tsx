import type { ReactNode } from 'react'

export interface Column<T> {
  key: string
  header: string
  render?: (row: T) => ReactNode
  className?: string
}

export function DataTable<T extends object>({
  columns, rows, onRowClick, empty = '暂无匹配记录', rowClassName
}: {
  columns: Column<T>[]; rows: T[]; onRowClick?: (row: T) => void; empty?: string
  rowClassName?: (row: T) => string | undefined
}) {
  if (!rows.length) return <div className="empty-state">{empty}</div>
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.className}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const rec = row as Record<string, unknown>
            return (
              <tr
                key={String(rec.store_id ?? rec.city_id ?? rec.product_id ?? rec.combination ?? rec.cluster ?? i)}
                className={[onRowClick ? 'clickable' : '', rowClassName?.(row)].filter(Boolean).join(' ') || undefined}
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((c) => (
                  <td key={c.key} className={c.className}>
                    {c.render ? c.render(row) : String(rec[c.key] ?? '—')}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
