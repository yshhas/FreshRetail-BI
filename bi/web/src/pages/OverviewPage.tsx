import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { fmtCompact, fmtIndex, fmtNumber, fmtRate, weekday } from '../lib/format'
import { Chart } from '../components/Chart'
import { DataTable, type Column } from '../components/DataTable'
import { KpiCard } from '../components/KpiCard'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'
import type { CityRow } from '../api/types'

export function OverviewPage() {
  const nav = useNavigate()
  const { get, set } = useUrlFilters()
  const start = get('start')
  const end = get('end')
  const kpis = useApi(api.getKpis, [])
  const profile = useApi(api.getTimeProfile, [])
  const trend = useApi(() => api.getTrend(start || undefined, end || undefined), [start, end])
  const cities = useApi(api.getCities, [])

  const trendOption = useMemo<EChartsOption>(() => ({
    grid: { left: 58, right: 24, top: 24, bottom: 42 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: (trend.data?.data ?? []).map((x) => x.dt.slice(5)) },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => fmtCompact(v) } },
    series: [{
      name: '归一化销量指数',
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: (trend.data?.data ?? []).map((x) => x.sales_index_total),
      areaStyle: { opacity: 0.10 },
      lineStyle: { width: 2, color: '#2563eb' },
      itemStyle: { color: '#2563eb' }
    }]
  }), [trend.data])

  const weekdayOption = useMemo<EChartsOption>(() => ({
    grid: { left: 58, right: 20, top: 24, bottom: 42 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => fmtIndex(Number(v)) },
    xAxis: { type: 'category', data: (profile.data?.data.weekday ?? []).map((x) => weekday(x.weekday)) },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => fmtCompact(v) } },
    series: [{ type: 'bar', data: (profile.data?.data.weekday ?? []).map((x) => x.sales_index), itemStyle: { color: '#7c3aed' }, barMaxWidth: 28 }]
  }), [profile.data])

  const hourOption = useMemo<EChartsOption>(() => ({
    grid: { left: 58, right: 20, top: 24, bottom: 42 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => fmtIndex(Number(v)) },
    xAxis: { type: 'category', data: (profile.data?.data.hours ?? []).map((x) => `${x.hour}:00`) },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => fmtCompact(v) } },
    series: [{ type: 'bar', data: (profile.data?.data.hours ?? []).map((x) => x.sales_index), itemStyle: { color: '#0891b2' }, barMaxWidth: 16 }]
  }), [profile.data])

  const heatmapOption = useMemo<EChartsOption>(() => ({
    grid: { left: 54, right: 24, top: 20, bottom: 54 },
    tooltip: { formatter: (p: unknown) => {
      const d = (p as { data: [number, number, number] }).data
      return `${weekday(d[1])} ${d[0]}:00<br/>指数 ${fmtIndex(d[2])}`
    } },
    xAxis: { type: 'category', data: Array.from({ length: 24 }, (_, i) => `${i}`), name: '小时' },
    yAxis: { type: 'category', data: Array.from({ length: 7 }, (_, i) => weekday(i)), name: '星期' },
    visualMap: { show: false, min: 0, max: Math.max(...(profile.data?.data.heatmap ?? []).map((x) => x.sales_index), 1) },
    series: [{ type: 'heatmap', data: (profile.data?.data.heatmap ?? []).map((x) => [x.hour, x.weekday, x.sales_index]), emphasis: { itemStyle: { borderColor: '#111', borderWidth: 1 } } }]
  }), [profile.data])

  const cityCols: Column<CityRow>[] = [
    { key: 'city_id', header: '城市', render: (r) => `C${String(r.city_id).padStart(2, '0')}` },
    { key: 'store_count', header: '门店数', render: (r) => fmtNumber(r.store_count) },
    { key: 'city_store_day_avg', header: '单店日均', render: (r) => fmtIndex(r.city_store_day_avg) },
    { key: 'city_stockout_sku_day_pooled', header: '城市池化缺货率', render: (r) => fmtRate(r.city_stockout_sku_day_pooled) },
    { key: 'city_stockout_store_mean', header: '门店率简单平均', render: (r) => fmtRate(r.city_stockout_store_mean) },
    { key: 'multi_risk_rate_risk', header: '多风险率（主样本）', render: (r) => fmtRate(r.multi_risk_rate_risk) },
    { key: 'small_city', header: '样本提示', render: (r) => r.small_city ? <span className="tag warn">小城市</span> : <span className="muted">—</span> }
  ]

  if (kpis.loading || profile.loading) return <Loading />
  if (kpis.error) return <ErrorBox message={kpis.error} onRetry={kpis.reload} />

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>经营总览</h1>
          <p>90 天冻结 KPI、销量指数趋势、星期/小时分布与城市概览。</p>
        </div>
        <div className="date-window">
          <label>趋势起点<input type="date" value={start} onChange={(e) => set('start', e.target.value)} /></label>
          <label>趋势终点<input type="date" value={end} onChange={(e) => set('end', e.target.value)} /></label>
          <button onClick={() => { set('start', ''); set('end', '') }}>重置</button>
        </div>
      </div>

      <div className="kpi-grid">
        {(kpis.data?.data ?? []).map((k) => (
          <KpiCard key={k.key} label={k.label} metric={k.metric_id} note={k.note}
            value={k.unit === '比例' ? fmtRate(k.value) : k.unit === '指数' || k.unit === '指数/日' ? fmtIndex(k.value) : fmtNumber(k.value)}
            unit={k.unit === '比例' ? '' : k.unit} />
        ))}
      </div>

      <Section title="90 天销量指数趋势" subtitle={trend.data?.meta.display_window ? `显示窗口：${trend.data.meta.display_window}` : '完整观察期'}>
        {trend.loading ? <Loading /> : trend.error ? <ErrorBox message={trend.error} onRetry={trend.reload} /> : <Chart option={trendOption} height={300} />}
        <p className="footnote">日期筛选仅改变此图显示窗口；上方 KPI 不随日期重算。</p>
      </Section>

      <div className="grid-2">
        <Section title="星期分布" subtitle="90 天汇总，归一化销量指数">
          {profile.data ? <Chart option={weekdayOption} height={280} /> : <Loading />}
        </Section>
        <Section title="小时分布" subtitle="0–23 时，90 天汇总">
          {profile.data ? <Chart option={hourOption} height={280} /> : <Loading />}
        </Section>
      </div>

      <Section title="星期 × 小时热力图" subtitle="颜色越深表示归一化销量指数越高">
        {profile.data ? <Chart option={heatmapOption} height={300} /> : <Loading />}
      </Section>

      <Section title="城市经营概览" subtitle="城市池化率、门店率简单平均、门店中位数需分别解读">
        {cities.loading ? <Loading /> : cities.error ? <ErrorBox message={cities.error} onRetry={cities.reload} /> :
          <DataTable columns={cityCols} rows={cities.data?.data ?? []} onRowClick={(r) => nav(`/cities-stores?city=${r.city_id}`)} />}
      </Section>
    </div>
  )
}
