import { useMemo } from 'react'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { fmtCompact, fmtIndex, fmtNumber, fmtRate } from '../lib/format'
import { Chart } from '../components/Chart'
import { KpiCard } from '../components/KpiCard'
import { ProductTabs } from '../components/ProductTabs'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'

export function ProductOverviewPage() {
  const overview = useApi(api.getProductOverview, [])
  const flags = useApi(api.getProductRiskCounts, [])

  const d = overview.data?.data
  const f = flags.data

  const coverageOption = useMemo<EChartsOption>(() => ({
    grid: { left: 52, right: 24, top: 28, bottom: 38 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => `${fmtNumber(Number(v))} 个 SKU` },
    xAxis: { type: 'category', name: '覆盖门店数区间', data: (d?.coverage_distribution ?? []).map((x) => x.bucket) },
    yAxis: { type: 'value', name: 'SKU 数', axisLabel: { formatter: (v: number) => fmtCompact(v) } },
    series: [{
      type: 'bar', barMaxWidth: 42,
      data: (d?.coverage_distribution ?? []).map((x) => x.skus),
      itemStyle: { color: '#2563eb' },
      label: { show: true, position: 'top', fontSize: 10 }
    }]
  }), [d])

  const headTailOption = useMemo<EChartsOption>(() => ({
    grid: { left: 96, right: 34, top: 16, bottom: 30 },
    tooltip: {
      formatter: (p: unknown) => {
        const item = p as { dataIndex: number }
        const row = (d?.head_tail ?? [])[item.dataIndex]
        return row ? `${row.group}<br/>${fmtNumber(row.skus)} 个 SKU<br/>占全部 ${fmtRate(row.share)}` : ''
      }
    },
    xAxis: { type: 'value', name: 'SKU 数', axisLabel: { formatter: (v: number) => fmtCompact(v) } },
    yAxis: { type: 'category', data: (d?.head_tail ?? []).map((x) => x.group), axisLabel: { fontSize: 11 } },
    series: [{
      type: 'bar', barMaxWidth: 30,
      data: (d?.head_tail ?? []).map((x) => x.skus),
      itemStyle: { color: '#7c3aed' },
      label: { show: true, position: 'right', fontSize: 10 }
    }]
  }), [d])

  const categoryOption = useMemo<EChartsOption>(() => {
    const rows = (d?.categories ?? []).slice(0, 10)
    return {
      grid: { left: 58, right: 46, top: 16, bottom: 30 },
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

  const riskOption = useMemo<EChartsOption>(() => {
    const rows = [
      { label: '风险 SKU', value: d?.flagged_skus ?? 0 },
      { label: '多风险 SKU', value: d?.multi_flag_skus ?? 0 },
      { label: '高波动', value: f?.high_cv ?? 0 },
      { label: '高零销', value: f?.high_zero ?? 0 },
      { label: '异常日频繁', value: f?.many_anomaly_days ?? 0 },
      { label: '门店集中', value: f?.store_concentration ?? 0 }
    ]
    return {
      grid: { left: 66, right: 30, top: 16, bottom: 30 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'value', name: 'SKU 数' },
      yAxis: { type: 'category', inverse: true, data: rows.map((x) => x.label), axisLabel: { fontSize: 11 } },
      series: [{
        type: 'bar', barMaxWidth: 22,
        data: rows.map((x) => x.value),
        itemStyle: { color: '#be123c' },
        label: { show: true, position: 'right', fontSize: 10 }
      }]
    }
  }, [d, f])

  if (overview.loading || flags.loading) {
    return <div className="page"><ProductTabs /><Loading /></div>
  }
  if (overview.error || !d) {
    return <div className="page"><ProductTabs /><ErrorBox message={overview.error ?? '商品总览数据为空'} onRetry={overview.reload} /></div>
  }

  return (
    <div className="page">
      <ProductTabs />
      <div className="page-head">
        <div>
          <h1>商品总览</h1>
          <p>865 个 SKU 的规模、覆盖、贡献结构、风险旗标与 L1 类别概览；全部为 90 天冻结值。</p>
        </div>
        <span className="tag">观察期 {overview.data?.meta.period}</span>
      </div>

      <div className="kpi-grid four">
        <KpiCard label="SKU 总数" value={fmtNumber(d.sku_count)} unit="个" metric="P2-SKU" note="链级去重" />
        <KpiCard label="累计归一化销量指数" value={fmtIndex(d.total_index)} unit="指数" metric="P1-TOTAL" note="不是销售额 / GMV" />
        <KpiCard label="覆盖门店数（中位）" value={fmtNumber(d.store_count_median)} unit="家" note={`P90 ${fmtNumber(d.store_count_p90, 1)} · 最大 ${fmtNumber(d.store_count_max)}；分母 898`} />
        <KpiCard label="头部 SKU" value={fmtNumber(d.head_tail.find((x) => x.group.includes('头部'))?.skus)} unit="个" note="Top20%" />
        <KpiCard label="长尾 SKU" value={fmtNumber(d.head_tail.find((x) => x.group.includes('长尾'))?.skus)} unit="个" note="Bottom50%" />
        <KpiCard label="风险 SKU" value={fmtNumber(d.flagged_skus)} unit="个" metric="P2-RISK" note="risk_flag_count > 0" />
        <KpiCard label="多风险 SKU" value={fmtNumber(d.multi_flag_skus)} unit="个" note="≥2 个风险旗标" />
        <KpiCard label="L1 类别" value={fmtNumber(d.categories.length)} unit="个" note="商品一级类别" />
      </div>

      <div className="grid-2">
        <Section title="商品覆盖门店数分布" subtitle="覆盖 = 观察期内出现该 SKU 的门店数；分母 898 家；不是每日在售门店数">
          <Chart option={coverageOption} height={280} />
        </Section>
        <Section title="头部与长尾结构" subtitle="按 P2 t8 冻结分组；占比以 865 个 SKU 为分母">
          <Chart option={headTailOption} height={220} />
          <p className="footnote">头部 = 规模前 20%，长尾 = 规模后 50%；不得把长尾低销量直接解释为商品质量差，覆盖门店数同样影响规模。</p>
        </Section>
      </div>

      <div className="grid-2">
        <Section title="L1 类别贡献（前 10）" subtitle="按冻结累计指数降序展示前 10 类；完整 32 类见「L1 类别结构」">
          <Chart option={categoryOption} height={300} />
        </Section>
        <Section title="商品风险旗标概览" subtitle="四个旗标可同时命中；多风险 = 命中 ≥2 项；旗标是筛查提示，不是经营评分">
          <Chart option={riskOption} height={300} />
          <p className="footnote">高零销旗标为 43 个（zero_rate &gt; P95 24.44%）；描述性口径 zero_rate &gt; 20% 为 65 个，两者不可混用。</p>
        </Section>
      </div>

      <p className="footnote">全部指标为归一化销量指数口径，不代表销售额、GMV、利润或真实件数；商品覆盖为观察期内同店口径。</p>
    </div>
  )
}
