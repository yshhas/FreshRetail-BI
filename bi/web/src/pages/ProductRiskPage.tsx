import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { buildReturnTo, detailHref } from '../lib/navigation'
import { fmtNumber } from '../lib/format'
import { PRODUCT_RISK_DEFINITIONS } from '../lib/product'
import { Chart } from '../components/Chart'
import { KpiCard } from '../components/KpiCard'
import { ProductTable } from '../components/ProductTable'
import { ProductTabs } from '../components/ProductTabs'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'

const RISK_TABS = [
  { value: 'flagged', label: '全部风险 SKU' },
  { value: 'multi', label: '多风险 SKU' },
  { value: 'high_cv', label: '高波动' },
  { value: 'high_zero', label: '高零销' },
  { value: 'many_anomaly_days', label: '异常日频繁' },
  { value: 'store_concentration', label: '门店集中' }
]

export function ProductRiskPage() {
  const nav = useNavigate()
  const location = useLocation()
  const { get, set } = useUrlFilters()
  const risk = get('risk', 'flagged') || 'flagged'
  const page = Math.max(1, Number(get('page', '1')) || 1)

  const overview = useApi(api.getProductOverview, [])
  const counts = useApi(api.getProductRiskCounts, [])
  const products = useApi(() => api.getProducts({
    scope: 'all', risk, page, page_size: 50
  }), [risk, page])

  const d = overview.data?.data
  const c = counts.data
  const total = products.data?.meta.n ?? 0

  const chartOption = useMemo<EChartsOption>(() => {
    const rows = [
      { label: '风险 SKU', value: d?.flagged_skus ?? 0 },
      { label: '多风险 SKU', value: d?.multi_flag_skus ?? 0 },
      { label: '高波动', value: c?.high_cv ?? 0 },
      { label: '高零销', value: c?.high_zero ?? 0 },
      { label: '异常日频繁', value: c?.many_anomaly_days ?? 0 },
      { label: '门店集中', value: c?.store_concentration ?? 0 }
    ]
    return {
      grid: { left: 72, right: 34, top: 10, bottom: 28 },
      tooltip: { trigger: 'axis', valueFormatter: (v) => `${fmtNumber(Number(v))} 个 SKU` },
      xAxis: { type: 'value', name: 'SKU 数', axisLabel: { formatter: (v: number) => fmtNumber(v) } },
      yAxis: { type: 'category', inverse: true, data: rows.map((x) => x.label), axisLabel: { fontSize: 11 } },
      series: [{
        type: 'bar', barMaxWidth: 22,
        data: rows.map((x) => x.value),
        itemStyle: { color: '#be123c' },
        label: { show: true, position: 'right', fontSize: 10 }
      }]
    }
  }, [d, c])

  if (overview.loading || counts.loading) {
    return <div className="page"><ProductTabs /><Loading /></div>
  }
  if (overview.error || !d) {
    return <div className="page"><ProductTabs /><ErrorBox message={overview.error ?? '商品风险数据为空'} onRetry={overview.reload} /></div>
  }

  return (
    <div className="page">
      <ProductTabs />
      <div className="page-head">
        <div>
          <h1>商品风险</h1>
          <p>117 个命中 P2 风险旗标的 SKU 与 35 个多风险 SKU；旗标是筛查提示，不是经营评分或因果结论。</p>
        </div>
        <span className="tag">观察期 {overview.data?.meta.period}</span>
      </div>

      <div className="kpi-grid six">
        <KpiCard label="风险 SKU" value={fmtNumber(d.flagged_skus)} unit="个" metric="P2-RISK" note="risk_flag_count > 0" />
        <KpiCard label="多风险 SKU" value={fmtNumber(d.multi_flag_skus)} unit="个" note="≥2 个旗标" />
        <KpiCard label="高波动" value={fmtNumber(c?.high_cv)} unit="个" note="CV 中位 > P95 1.060" />
        <KpiCard label="高零销" value={fmtNumber(c?.high_zero)} unit="个" note="零销率 > P95 24.44%" />
        <KpiCard label="异常日频繁" value={fmtNumber(c?.many_anomaly_days)} unit="个" note="异常日占比 > 5%" />
        <KpiCard label="门店集中" value={fmtNumber(c?.store_concentration)} unit="个" note="覆盖≥5 且 HHI > P95 0.184" />
      </div>

      <div className="notice warn">
        口径区分：high_zero 风险旗标为 <strong>43</strong> 个 SKU（zero_rate &gt; P95 24.44%）；
        描述性统计 zero_rate &gt; 20% 为 <strong>65</strong> 个 SKU。两者不可互相替代，本页计数使用冻结旗标口径。
      </div>

      <div className="grid-2">
        <Section title="风险旗标分布" subtitle="同一 SKU 可命中多个旗标，各行不可相加为 117">
          <Chart option={chartOption} height={260} />
        </Section>
        <Section title="风险标记定义" subtitle="来自 P2 冻结规则；不推导风险等级或综合评分">
          <div className="flag-grid">
            {PRODUCT_RISK_DEFINITIONS.map((f) => (
              <div key={f.code} className="flag-card">
                <strong>{f.label}</strong>
                <p>{f.definition}</p>
              </div>
            ))}
          </div>
        </Section>
      </div>

      <div className="segmented">
        {RISK_TABS.map((t) => (
          <button key={t.value} className={risk === t.value ? 'active' : ''}
            onClick={() => set('risk', t.value)}>{t.label}</button>
        ))}
      </div>

      <Section title="风险 SKU 列表" subtitle={`当前筛选 ${fmtNumber(total)} 个 SKU；每页 50 个；点击行进入详情`}>
        {products.loading ? <Loading /> : products.error ? <ErrorBox message={products.error} onRetry={products.reload} /> :
          <ProductTable rows={products.data?.data ?? []}
            onRowClick={(r) => nav(detailHref(`/products/${r.product_id}`, buildReturnTo(location.pathname, location.search)))} />}
        <div className="pager" style={{ marginTop: 10 }}>
          <button disabled={page <= 1} onClick={() => set('page', page - 1)}>上一页</button>
          <span>第 {page} 页 · 共 {fmtNumber(total)} 个</span>
          <button disabled={page * 50 >= total} onClick={() => set('page', page + 1)}>下一页</button>
        </div>
      </Section>

      <p className="footnote">
        风险旗标只表示该 SKU 在冻结规则下被标记，不能直接解释为经营失败、商品质量差或因果结论；
        高覆盖低单产与低覆盖高单产需要分别复核。
      </p>
    </div>
  )
}
