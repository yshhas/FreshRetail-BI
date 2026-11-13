import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { fmtIndex, fmtNumber, fmtRate } from '../lib/format'
import { Chart } from '../components/Chart'
import { DataTable, type Column } from '../components/DataTable'
import { KpiCard } from '../components/KpiCard'
import { ProductTabs } from '../components/ProductTabs'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'
import type { ProductCategoryRow } from '../api/types'

export function ProductCategoryPage() {
  const overview = useApi(api.getProductOverview, [])
  const d = overview.data?.data

  const chartOption = useMemo<EChartsOption>(() => {
    const rows = (d?.categories ?? []).slice(0, 10)
    return {
      grid: { left: 58, right: 48, top: 12, bottom: 28 },
      tooltip: {
        formatter: (p: unknown) => {
          const item = p as { dataIndex: number }
          const row = rows[item.dataIndex]
          return row
            ? `${row.category_code}<br/>份额 ${row.share_pct.toFixed(2)}%<br/>${fmtNumber(row.sku_count)} 个 SKU / 覆盖 ${fmtNumber(row.store_count)} 店`
            : ''
        }
      },
      xAxis: { type: 'value', name: '指数份额（%）', axisLabel: { formatter: (v: number) => `${v}%` } },
      yAxis: { type: 'category', inverse: true, data: rows.map((x) => x.category_code), axisLabel: { fontSize: 11 } },
      series: [{
        type: 'bar', barMaxWidth: 18,
        data: rows.map((x) => Number(x.share_pct.toFixed(2))),
        itemStyle: { color: '#0891b2' },
        label: { show: true, position: 'right', formatter: '{c}%', fontSize: 10 }
      }]
    }
  }, [d])

  const columns: Column<ProductCategoryRow>[] = [
    { key: 'category_code', header: 'L1 类别' },
    {
      key: 'sku_count', header: 'SKU 数',
      render: (r) => <>{fmtNumber(r.sku_count)}{r.sku_count < 20 ? <span className="tag warn" style={{ marginLeft: 6 }}>SKU&lt;20</span> : null}</>
    },
    { key: 'store_count', header: '覆盖门店', render: (r) => fmtNumber(r.store_count) },
    { key: 'coverage', header: '覆盖率', render: (r) => fmtRate(r.coverage) },
    { key: 'total_index', header: '累计指数', render: (r) => fmtIndex(r.total_index) },
    { key: 'share_pct', header: '指数份额', render: (r) => `${r.share_pct.toFixed(2)}%` },
    { key: 'n_flagged_skus', header: '风险 SKU', render: (r) => fmtNumber(r.n_flagged_skus) },
    { key: 'n_multi_flag_skus', header: '多风险 SKU', render: (r) => fmtNumber(r.n_multi_flag_skus) },
    { key: 'flagged_sku_share', header: '风险 SKU 占比', render: (r) => fmtRate(r.flagged_sku_share) },
    { key: 'flagged_total_index_share', header: '风险指数占比', render: (r) => fmtRate(r.flagged_total_index_share) },
    { key: 'rare', header: '覆盖类型', render: (r) => r.rare ? <span className="tag warn">少数类别</span> : <span className="muted">普遍</span> }
  ]

  if (overview.loading) return <div className="page"><ProductTabs /><Loading /></div>
  if (overview.error || !d) {
    return <div className="page"><ProductTabs /><ErrorBox message={overview.error ?? '类别数据为空'} onRetry={overview.reload} /></div>
  }

  return (
    <div className="page">
      <ProductTabs />
      <div className="page-head">
        <div>
          <h1>L1 类别结构</h1>
          <p>32 个一级类别的商品规模、覆盖门店、指数份额与风险分布；全部为 90 天冻结值。</p>
        </div>
        <span className="tag">观察期 {overview.data?.meta.period}</span>
      </div>

      <div className="kpi-grid four">
        <KpiCard label="L1 类别数" value={fmtNumber(d.categories.length)} unit="个" note="商品一级类别" />
        <KpiCard label="SKU 总数" value={fmtNumber(d.sku_count)} unit="个" metric="P2-SKU" note="32 类合计" />
        <KpiCard label="风险 SKU" value={fmtNumber(d.flagged_skus)} unit="个" metric="P2-RISK" note="全链口径" />
        <KpiCard label="多风险 SKU" value={fmtNumber(d.multi_flag_skus)} unit="个" note="≥2 个旗标" />
      </div>

      <Section title="类别指数份额（前 10）" subtitle="按冻结累计指数降序展示前 10 类；份额为全链归一化销量指数占比">
        <Chart option={chartOption} height={300} />
      </Section>

      <Section title="32 个 L1 类别" subtitle="覆盖门店为观察期内出现该类别的门店数，不是每日在售门店数">
        <DataTable columns={columns} rows={d.categories} />
        <p className="footnote">
          「SKU&lt;20」表示该类别下 SKU 数不足 20，仅适合浏览，不适合类间平均比较；
          类别结构为描述性统计，不代表经营因果。
        </p>
      </Section>
    </div>
  )
}
