import { fmtIndex, fmtNumber, fmtRate } from '../lib/format'
import { PRODUCT_FLAGS } from '../lib/product'
import type { ProductRow } from '../api/types'
import { DataTable, type Column } from './DataTable'

export function ProductFlags({ row }: { row: ProductRow }) {
  const count = row.risk_flag_count ?? 0
  if (!count) return <span className="muted">无</span>
  const names = PRODUCT_FLAGS.filter((f) => Boolean(row[f.key])).map((f) => f.label)
  return (
    <span className="tag bad" title={names.join(' + ')}>
      {count} 项{count >= 2 ? ' · 多风险' : ''}
    </span>
  )
}

export function ProductTable({ rows, onRowClick }: {
  rows: ProductRow[]
  onRowClick?: (row: ProductRow) => void
}) {
  const columns: Column<ProductRow>[] = [
    { key: 'product_code', header: 'SKU', render: (r) => r.product_code ?? `#${r.product_id}` },
    { key: 'category_code', header: 'L1 类别', render: (r) => r.category_code ?? '—' },
    { key: 'store_count', header: '覆盖门店', render: (r) => fmtNumber(r.store_count) },
    { key: 'store_coverage', header: '覆盖率', render: (r) => fmtRate(r.store_coverage) },
    { key: 'total_index', header: '累计指数', render: (r) => fmtIndex(r.total_index) },
    { key: 'total_share', header: '贡献份额', render: (r) => fmtRate(r.total_share, 2) },
    { key: 'per_series_day', header: '单店日均', render: (r) => fmtNumber(r.per_series_day, 2) },
    { key: 'zero_rate', header: '零销率', render: (r) => fmtRate(r.zero_rate) },
    { key: 'cv_series_median', header: '销量 CV', render: (r) => fmtNumber(r.cv_series_median, 3) },
    { key: 'hhi', header: '门店 HHI', render: (r) => fmtNumber(r.hhi, 4) },
    { key: 'risk_flag_count', header: '风险旗标', render: (r) => <ProductFlags row={r} /> },
    { key: 'rank_scale', header: '规模排名', render: (r) => r.rank_scale ?? '—' },
    { key: 'head_tail_group', header: '结构', render: (r) => r.head_tail_group ? <span className="tag">{r.head_tail_group}</span> : '—' }
  ]
  return <DataTable columns={columns} rows={rows} onRowClick={onRowClick} />
}
