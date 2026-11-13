import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { EChartsOption } from 'echarts'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { buildReturnTo, detailHref } from '../lib/navigation'
import { fmtCompact, fmtNumber } from '../lib/format'
import { Chart } from '../components/Chart'
import { DataTable, type Column } from '../components/DataTable'
import { FilterSelect } from '../components/FilterSelect'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'
import type { RiskComboRow, StoreRow } from '../api/types'

const DOMAIN_LABELS: Record<string, string> = {
  stockout_domain: '缺货域（R1 或 R2）',
  R3: '持续低销域（R3）',
  R4: '高零销域（R4）',
  R5: '高波动域（R5）',
  R6: '高异常日域（R6）'
}

const DOMAIN_CODES: Record<string, string> = {
  缺货: 'stockout_domain',
  持续低销: 'R3',
  高零销: 'R4',
  高波动: 'R5',
  高异常日: 'R6'
}

const DOMAIN_SHORT_LABELS: Record<string, string> = {
  stockout_domain: '缺货',
  R3: '持续低销',
  R4: '高零销',
  R5: '高波动',
  R6: '高异常日'
}

function domainPairLabel(value: string): string {
  const labels = value.split(',').map((code) => DOMAIN_SHORT_LABELS[code] ?? code)
  return labels.join(' + ')
}

export function RiskPage() {
  const nav = useNavigate()
  const location = useLocation()
  const { get, set, patch } = useUrlFilters()
  const returnTo = buildReturnTo(location.pathname, location.search)
  const domain = get('domain')
  const exactCombo = get('exact_combo')
  const domainPair = get('domains')
  const quadrant = get('quadrant')
  const cluster = get('cluster')
  const page = Math.max(1, Number(get('page', '1')) || 1)
  const comboParam = (get('combo', 'exact') || 'exact') as 'exact' | 'at_least'
  const comboConflict = Boolean(exactCombo && domainPair)
  const effectiveExactCombo = comboConflict ? '' : exactCombo
  const combo = domainPair ? 'at_least' : effectiveExactCombo ? 'exact' : comboParam
  const summary = useApi(api.getRiskSummary, [])
  const filters = useApi(api.getFilters, [])
  const exact = useApi(() => api.getRiskCombinations('exact'), [])
  const atLeast = useApi(() => api.getRiskCombinations('at_least'), [])
  const stores = useApi(() => api.getStores({
    risk_domain: domain || undefined,
    exact_combo: effectiveExactCombo || undefined,
    domains: domainPair || undefined,
    quadrant: quadrant || undefined,
    cluster: cluster || undefined,
    sample_scope: 'risk',
    page,
    page_size: 20,
    sort: 'store_id'
  }), [domain, effectiveExactCombo, domainPair, quadrant, cluster, page])

  const domains = summary.data?.data.domains ?? []
  const flags = summary.data?.data.flags ?? {}
  const multi = summary.data?.data.multi_risk ?? 0

  const domainOption = useMemo<EChartsOption>(() => ({
    grid: { left: 58, right: 20, top: 24, bottom: 38 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: domains.map((d) => `${d.domain_count} 域`) },
    yAxis: { type: 'value', axisLabel: { formatter: (v: number) => fmtCompact(v) } },
    series: [{ type: 'bar', barMaxWidth: 46, data: domains.map((d) => d.stores), itemStyle: { color: '#be123c' } }]
  }), [domains])

  const cards = [
    { key: 'stockout_domain', label: DOMAIN_LABELS.stockout_domain, n: flags.stockout_domain ?? 0, note: 'R1/R2 合并且' },
    { key: 'R3', label: DOMAIN_LABELS.R3, n: flags.R3 ?? 0, note: 'P1 规则' },
    { key: 'R4', label: DOMAIN_LABELS.R4, n: flags.R4 ?? 0, note: 'P90 阈值' },
    { key: 'R5', label: DOMAIN_LABELS.R5, n: flags.R5 ?? 0, note: 'P90 阈值' },
    { key: 'R6', label: DOMAIN_LABELS.R6, n: flags.R6 ?? 0, note: '>P90' }
  ]

  const comboCols: Column<RiskComboRow>[] = [
    { key: 'rank', header: '#', render: (r) => r.rank ?? '—' },
    { key: 'combination', header: combo === 'exact' ? '恰好命中组合' : '至少同时命中（跨域两两）' },
    { key: 'stores', header: '门店数', render: (r) => fmtNumber(r.stores) }
  ]

  const storeCols: Column<StoreRow>[] = [
    { key: 'store_id', header: '门店', render: (r) => `S${String(r.store_id).padStart(4, '0')}` },
    { key: 'city_id', header: '城市', render: (r) => `C${String(r.city_id).padStart(2, '0')}` },
    { key: 'quadrant', header: '四象限', render: (r) => r.quadrant?.slice(0, 2) ?? '—' },
    { key: 'cluster', header: '结构群', render: (r) => r.cluster ?? '—' },
    { key: 'domain_count', header: '风险域数', render: (r) => `${r.domain_count ?? 0}` },
    { key: 'domain_labels', header: '命中域', render: (r) => r.domain_labels || '—' },
    { key: 'multi_risk', header: '多风险', render: (r) => r.multi_risk ? <span className="tag bad">是</span> : <span className="muted">否</span> }
  ]

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>经营风险</h1>
          <p>五个运营风险域、风险组合、多风险门店与风险详情入口。</p>
        </div>
      </div>

      <div className="domain-grid">
        {cards.map((c) => (
          <button key={c.key} className={`domain-card ${domain === c.key ? 'active' : ''}`}
            onClick={() => patch({ domain: domain === c.key ? '' : c.key, exact_combo: '', domains: '' })}>
            <span>{c.label}</span>
            <strong>{fmtNumber(c.n)}</strong>
            <small>{c.note} · 全样本 888</small>
            <small>点击仅筛选下方门店</small>
          </button>
        ))}
        <div className="domain-card structural">
          <span>结构提示（不计入运营域）</span>
          <strong>R7 {fmtNumber(flags.R7 ?? 0)} · R8 {fmtNumber(flags.R8 ?? 0)}</strong>
          <small>全样本 888 · 覆盖偏窄 / 结构集中</small>
        </div>
      </div>

      <div className="filter-bar">
        <FilterSelect label="风险域" value={domain} onChange={(v) => patch({ domain: v, exact_combo: '', domains: '' })}
          options={[
            ...Object.entries(DOMAIN_LABELS).map(([value, label]) => ({ value, label })),
            { value: 'R7', label: 'R7 覆盖偏窄（结构提示）' },
            { value: 'R8', label: 'R8 结构集中（结构提示）' }
          ]} />
        <FilterSelect label="四象限" value={quadrant} onChange={(v) => set('quadrant', v)}
          options={(filters.data?.quadrants ?? []).map((q) => ({ value: q, label: q }))} />
        <FilterSelect label="结构群" value={cluster} onChange={(v) => set('cluster', v)}
          options={(filters.data?.clusters ?? []).map((c) => ({ value: c, label: c }))} />
        <button className="reset" onClick={() => patch({ domain: '', quadrant: '', cluster: '', exact_combo: '', domains: '' })}>重置筛选</button>
      </div>

      <p className="footnote">
        筛选作用范围：风险域 / 四象限 / 结构群 / 精确组合 / 至少组合 仅作用于下方「风险门店」列表；上方风险域计数、多风险门店与风险组合均为全样本 888，不随筛选变化。
      </p>

      {comboConflict && (
        <div className="notice warn">
          URL 同时包含精确组合与至少组合参数，已优先按“至少组合”展示；请取消其中一个筛选。
        </div>
      )}

      {effectiveExactCombo && (
        <div className="notice info">
          当前精确组合：<strong>{effectiveExactCombo}</strong>（恰好命中，域集合完全相等）。
          <button className="link-button" style={{ marginLeft: 10 }} onClick={() => set('exact_combo', '')}>取消精确组合</button>
        </div>
      )}

      {domainPair && (
        <div className="notice info">
          当前至少组合：<strong>{domainPairLabel(domainPair)}</strong>（至少同时命中这两个域，允许其他域）。
          <button className="link-button" style={{ marginLeft: 10 }} onClick={() => set('domains', '')}>取消至少组合</button>
        </div>
      )}

      <div className="grid-2">
        <Section title="运营风险域数量分布" subtitle="全样本 888；当前筛选仅作用于下方门店表">
          {summary.loading ? <Loading /> : summary.error ? <ErrorBox message={summary.error} onRetry={summary.reload} /> :
            <Chart option={domainOption} height={280} />}
        </Section>
        <Section title="多风险门店" subtitle="全样本；≥2 个运营域，R7/R8 不计入">
          {summary.loading ? <Loading /> : <div className="big-stat"><strong>{fmtNumber(multi)}</strong><span>家 · {((multi / (summary.data?.meta.n || 888)) * 100).toFixed(2)}%</span></div>}
          <p className="footnote">多风险是共现计数，不是经营失败标签或综合评分。</p>
        </Section>
      </div>

      <Section title="风险组合" subtitle="全样本 888，不受筛选 · 恰好命中＝域集合完全相等（P4-B，16 种）；至少同时命中＝跨域两两组合（P3-D，10 对，允许其他域）"
        right={<div className="segmented">
          <button className={combo === 'exact' ? 'active' : ''} onClick={() => patch({ combo: 'exact', domains: '' })}>恰好命中</button>
          <button className={combo === 'at_least' ? 'active' : ''} onClick={() => patch({ combo: 'at_least', exact_combo: '' })}>至少同时命中</button>
        </div>}>
        {combo === 'exact'
          ? exact.loading ? <Loading /> : (
            <DataTable columns={comboCols} rows={exact.data?.data ?? []}
              rowClassName={(r) => effectiveExactCombo === r.combination ? 'active-row' : undefined}
              onRowClick={(r) => patch({
                exact_combo: effectiveExactCombo === r.combination ? '' : r.combination,
                domains: '',
                domain: '',
                combo: 'exact'
              })} />
          )
          : atLeast.loading ? <Loading /> : (
            <DataTable columns={comboCols} rows={atLeast.data?.data ?? []}
              rowClassName={(r) => {
                const codes = r.combination.split('+').map((s) => DOMAIN_CODES[s.trim()])
                return domainPair && codes.every(Boolean) && codes.join(',') === domainPair ? 'active-row' : undefined
              }}
              onRowClick={(r) => {
                const names = r.combination.split('+').map((s) => s.trim())
                const codes = names.map((name) => DOMAIN_CODES[name])
                if (names.length !== 2 || codes.some((code) => !code)) return
                const value = codes.join(',')
                patch({
                  domains: domainPair === value ? '' : value,
                  exact_combo: '',
                  domain: '',
                  combo: 'at_least'
                })
              }} />
          )}
        <p className="footnote">
          {combo === 'exact'
            ? '恰好口径来自 P4-B 冻结的 16 种精确组合（域集合完全相等，含三域、四域、五域组合）；点击组合行可按该精确组合筛选下方门店，再次点击取消。与“至少”口径不可直接比较。各行门店数不可相加（同一门店可出现在多个组合）。'
            : '“至少”表示至少同时命中这两个域（允许还命中其他域）；当前只展示 10 个跨域两两组合（5 个运营域两两组合，C(5,2)=10），不代表已枚举三域、四域或五域同时命中的组合。P3-D d8b 原表共 15 行，另 5 行为同域“命中该域”的单域命中数（缺货 154 / 持续低销 90 / 高零销 89 / 高波动 89 / 高异常日 56），与上方风险域卡片数字一致。各行门店数不可相加。点击组合行可按该至少组合筛选下方门店，再次点击取消。'}
        </p>
      </Section>

      <Section title="风险门店" subtitle={`当前筛选 ${stores.data?.meta.n ?? '—'} 家${effectiveExactCombo ? ` · 精确组合：${effectiveExactCombo}` : ''}${domainPair ? ` · 至少组合：${domainPairLabel(domainPair)}` : ''}；点击查看门店风险详情`}
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
