import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { buildReturnTo, detailHref } from '../lib/navigation'
import { fmtCompact, fmtIndex, fmtNumber, fmtRate } from '../lib/format'
import { Chart } from '../components/Chart'
import { DataTable, type Column } from '../components/DataTable'
import { FilterSelect } from '../components/FilterSelect'
import { Section } from '../components/Section'
import { ErrorBox, Loading, Suppressed } from '../components/States'
import type { CityRow, StoreGroupRow, StoreRow } from '../api/types'

const QUADRANT_COLORS: Record<string, string> = {
  'Q1 高规模·相对高效率': '#2563eb',
  'Q2 高规模·相对低效率': '#f59e0b',
  'Q3 低规模·相对高效率': '#10b981',
  'Q4 低规模·相对低效率': '#ef4444'
}

const RISK_LABELS: Record<string, string> = {
  stockout_domain: '缺货域（R1|R2）',
  R3: 'R3 持续低销',
  R4: 'R4 高零销',
  R5: 'R5 高波动',
  R6: 'R6 高异常日',
  multi_risk: '多风险门店'
}

export function CityStorePage() {
  const nav = useNavigate()
  const location = useLocation()
  const { get, set } = useUrlFilters()
  const returnTo = buildReturnTo(location.pathname, location.search)
  const city = get('city')
  const quadrant = get('quadrant')
  const cluster = get('cluster')
  const risk = get('risk')
  const scope = (get('scope', 'risk') || 'risk') as 'all' | 'risk'
  const page = Math.max(1, Number(get('page', '1')) || 1)
  const filters = useApi(api.getFilters, [])
  const cities = useApi(api.getCities, [])
  const scatter = useApi(api.getStoreScatter, [])
  const groups = useApi(api.getGroups, [])
  const stores = useApi(() => api.getStores({
    city_id: city ? Number(city) : undefined,
    quadrant: quadrant || undefined,
    cluster: cluster || undefined,
    risk_domain: risk || undefined,
    sample_scope: scope,
    page,
    page_size: 20,
    sort: 'store_id'
  }), [city, quadrant, cluster, risk, scope, page])

  const scatterRows = useMemo(() => (scatter.data?.data ?? []).filter((r) => {
    if (city && String(r.city_id) !== city) return false
    if (quadrant && r.quadrant !== quadrant) return false
    if (cluster && r.cluster !== cluster) return false
    return true
  }), [scatter.data, city, quadrant, cluster])

  const scatterOption = useMemo<EChartsOption>(() => {
    const byQ = new Map<string, Array<{ value: [number, number, number]; store_id: number }>>()
    for (const r of scatterRows) {
      const q = r.quadrant ?? '未分层'
      if (!byQ.has(q)) byQ.set(q, [])
      byQ.get(q)!.push({ value: [Number(r.per_day_index ?? 0), Number(r.eff_resid ?? 0), r.store_id], store_id: r.store_id })
    }
    return {
      grid: { left: 60, right: 28, top: 20, bottom: 52 },
      tooltip: {
        formatter: (p: unknown) => {
          const d = (p as { data: { value: [number, number, number] } }).data
          return `S${String(d.value[2]).padStart(4, '0')}<br/>单店日均 ${fmtIndex(d.value[0])}<br/>相对效率残差 ${d.value[1].toFixed(4)}`
        }
      },
      legend: { top: 0, type: 'scroll' },
      xAxis: { type: 'log', axisLabel: { formatter: (v: number) => fmtCompact(v) }, minorTick: { show: false } },
      yAxis: { type: 'value', name: '相对效率残差', nameLocation: 'middle', nameGap: 42, nameTextStyle: { fontSize: 10 } },
      series: [...byQ.entries()].map(([q, data]) => ({
        name: q,
        type: 'scatter',
        symbolSize: 6,
        data,
        itemStyle: { color: QUADRANT_COLORS[q] ?? '#64748b', opacity: 0.65 }
      }))
    }
  }, [scatterRows])

  const cityCols: Column<CityRow>[] = [
    { key: 'city_id', header: '城市', render: (r) => `C${String(r.city_id).padStart(2, '0')}` },
    { key: 'store_count', header: '门店数（全部 898）', render: (r) => fmtNumber(r.store_count) },
    { key: 'city_store_day_avg', header: '单店日均', render: (r) => fmtIndex(r.city_store_day_avg) },
    { key: 'city_stockout_sku_day_pooled', header: '城市池化缺货率', render: (r) => fmtRate(r.city_stockout_sku_day_pooled) },
    { key: 'city_stockout_store_mean', header: '门店率简单平均', render: (r) => fmtRate(r.city_stockout_store_mean) },
    { key: 'stockout_sku_day_median', header: '门店中位数', render: (r) => fmtRate(r.stockout_sku_day_median) },
    { key: 'multi_risk_rate_risk', header: '多风险率', render: (r) => fmtRate(r.multi_risk_rate_risk) }
  ]

  const groupCols: Column<StoreGroupRow>[] = [
    { key: 'quadrant', header: '四象限' },
    { key: 'cluster', header: '结构群' },
    { key: 'stores', header: '门店数', render: (r) => fmtNumber(r.stores) },
    { key: 'n_flagged_median', header: '风险 SKU 中位', render: (r) => r.suppressed ? <Suppressed n={r.stores} /> : fmtNumber(r.n_flagged_median, 1) },
    { key: 'share_flagged_median', header: '风险 SKU 占比中位', render: (r) => r.suppressed ? <Suppressed n={r.stores} /> : fmtRate(r.share_flagged_median) },
    { key: 'multi_risk_rate', header: '多风险率', render: (r) => r.suppressed ? <Suppressed n={r.stores} /> : fmtRate(r.multi_risk_rate) },
    { key: 'sample_insufficient', header: '样本', render: (r) => r.sample_insufficient ? <span className="tag warn">n&lt;20 样本不足</span> : <span className="tag">可比较</span> }
  ]

  const storeCols: Column<StoreRow>[] = [
    { key: 'store_id', header: '门店', render: (r) => `S${String(r.store_id).padStart(4, '0')}` },
    { key: 'city_id', header: '城市', render: (r) => `C${String(r.city_id).padStart(2, '0')}` },
    { key: 'per_day_index', header: '单店日均', render: (r) => fmtIndex(r.per_day_index) },
    { key: 'sku_count', header: 'SKU 数', render: (r) => fmtNumber(r.sku_count) },
    { key: 'zero_rate', header: '零销率', render: (r) => fmtRate(r.zero_rate) },
    { key: 'stockout_sku_day_rate', header: 'SKU-日缺货率', render: (r) => fmtRate(r.stockout_sku_day_rate) },
    { key: 'cv', header: '销量 CV', render: (r) => fmtNumber(r.cv, 3) },
    { key: 'quadrant', header: '四象限', render: (r) => r.quadrant ? <span className="tag">{r.quadrant.slice(0, 2)}</span> : '—' },
    { key: 'cluster', header: '结构', render: (r) => r.cluster ?? '—' },
    { key: 'domain_count', header: '风险域', render: (r) => r.in_risk_sample ? `${r.domain_count ?? 0} 个` : <span className="tag warn">不诊断</span> },
    { key: 'multi_risk', header: '多风险', render: (r) => r.multi_risk ? <span className="tag bad">是</span> : <span className="muted">否</span> }
  ]

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>城市与门店</h1>
          <p>城市对比、门店筛选、四象限分布、画像详情与同类门店比较。</p>
        </div>
      </div>

      <div className="filter-bar">
        <FilterSelect label="城市" value={city} onChange={(v) => set('city', v)}
          options={(filters.data?.cities ?? []).map((c) => ({ value: String(c.city_id), label: `C${String(c.city_id).padStart(2, '0')} · ${c.store_count} 店` }))} />
        <FilterSelect label="四象限" value={quadrant} onChange={(v) => set('quadrant', v)}
          options={(filters.data?.quadrants ?? []).map((q) => ({ value: q, label: q }))} />
        <FilterSelect label="结构群" value={cluster} onChange={(v) => set('cluster', v)}
          options={(filters.data?.clusters ?? []).map((c) => ({ value: c, label: c }))} />
        <FilterSelect label="风险域" value={risk} onChange={(v) => set('risk', v)}
          options={[
            { value: 'stockout_domain', label: '缺货域（R1|R2）' },
            { value: 'R3', label: 'R3 持续低销' },
            { value: 'R4', label: 'R4 高零销' },
            { value: 'R5', label: 'R5 高波动' },
            { value: 'R6', label: 'R6 高异常日' },
            { value: 'multi_risk', label: '多风险门店' }
          ]} />
        <FilterSelect label="样本" value={scope} onChange={(v) => set('scope', v)} placeholder="主样本 888"
          options={[{ value: 'risk', label: '主样本 888' }, { value: 'all', label: '全部 898' }]} />
        <button className="reset" onClick={() => { ['city', 'quadrant', 'cluster', 'risk', 'page'].forEach((k) => set(k, '')) }}>重置筛选</button>
      </div>

      <p className="footnote">
        当前筛选：城市 {city ? `C${String(city).padStart(2, '0')}` : '全部'} · 四象限 {quadrant || '全部'} · 结构群 {cluster || '全部'} · 风险域 {risk ? (RISK_LABELS[risk] ?? risk) : '全部'} · 样本 {scope === 'risk' ? '主样本 888' : '全部 898'}。
        作用范围：城市 / 四象限 / 结构群 → 门店四象限与门店列表；风险域 / 样本 → 仅门店列表；「城市经营对比」（全样本 18 城）与「同类门店比较」（全样本 16 组）不受筛选影响。
      </p>

      <Section title="城市经营对比" subtitle="全样本 18 城横向参照，不随下方筛选变化 · 城市池化率 ≠ 城市门店率简单平均 ≠ 门店中位数">
        {cities.loading ? <Loading /> : cities.error ? <ErrorBox message={cities.error} onRetry={cities.reload} /> :
          <DataTable columns={cityCols} rows={cities.data?.data ?? []} onRowClick={(r) => set('city', r.city_id)} />}
        <p className="footnote">
          城市表为全部门店口径（898 家）；下方门店列表默认仅显示风险分析主样本（888 家，SKU≥10），因此同一城市两处门店数可能相差 SKU&lt;10 门店（如 C03：101 vs 92）。
        </p>
      </Section>

      <Section title="门店四象限" subtitle={`显示 ${scatterRows.length} 家 · 受 城市/四象限/结构群 筛选，不受 风险域/样本 影响；点击点位进入门店详情`}>
        {scatter.loading ? <Loading /> : scatter.error ? <ErrorBox message={scatter.error} onRetry={scatter.reload} /> :
          <Chart option={scatterOption} height={420} onEvents={{
            click: (p) => {
              const d = (p as { data?: { store_id?: number } }).data
              if (d?.store_id) nav(detailHref(`/stores/${d.store_id}`, returnTo))
            }
          }} />}
        <p className="footnote">横轴为单店日均归一化销量指数（对数），纵轴为 P3-B 相对效率残差；象限仅探索性分层。</p>
      </Section>

      <Section title="同类门店比较（四象限 × 结构群）" subtitle="全样本 16 组，不受当前筛选影响；n<20 单元格统计值由后端抑制">
        {groups.loading ? <Loading /> : groups.error ? <ErrorBox message={groups.error} onRetry={groups.reload} /> :
          <DataTable columns={groupCols} rows={groups.data?.data ?? []} />}
      </Section>

      <Section title="门店列表" subtitle={`筛选结果：共 ${stores.data?.meta.n ?? '—'} 家；点击行查看画像`}
        right={<div className="pager">
          <button disabled={page <= 1} onClick={() => set('page', page - 1)}>上一页</button>
          <span>第 {page} 页</span>
          <button disabled={page * 20 >= (stores.data?.meta.n ?? 0)} onClick={() => set('page', page + 1)}>下一页</button>
        </div>}>
        {stores.loading ? <Loading /> : stores.error ? <ErrorBox message={stores.error} onRetry={stores.reload} /> :
          <DataTable columns={storeCols} rows={stores.data?.data ?? []} onRowClick={(r) => nav(detailHref(`/stores/${r.store_id}`, returnTo))} />}
      </Section>
    </div>
  )
}
