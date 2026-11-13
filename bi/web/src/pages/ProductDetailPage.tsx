import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { buildReturnTo, detailHref, safeReturnTo } from '../lib/navigation'
import { fmtIndex, fmtNumber, fmtRate } from '../lib/format'
import { summarizePairs } from '../lib/product'
import { BackLink } from '../components/BackLink'
import { Badge } from '../components/Badge'
import { DataTable, type Column } from '../components/DataTable'
import { FilterSelect } from '../components/FilterSelect'
import { ProductTabs } from '../components/ProductTabs'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'
import type { ProductPairRow, ProductStoreRow } from '../api/types'

const STORE_SORT_OPTIONS = [
  { value: 'total_index|desc', label: '该店指数（降序）' },
  { value: 'zero_days|desc', label: '零销天数（降序）' },
  { value: 'stockout_days|desc', label: '缺货天数（降序）' },
  { value: 'store_id|asc', label: '门店编号（升序）' }
]

const PAIR_DEFINITION =
  '两个均为 P2 flagged SKU，且在观察期内同时进入同一门店的商品集合（观察期内同店共同出现）；' +
  '不代表同日销售、同日缺货、同时缺货、消费者购买搭配关系或商品间因果关系。'

export function ProductDetailPage() {
  const { productId } = useParams()
  const nav = useNavigate()
  const location = useLocation()
  const { get, set } = useUrlFilters()
  const id = Number(productId)
  const safeBack = safeReturnTo(new URLSearchParams(location.search).get('returnTo'))
  const backTo = safeBack ?? '/products/list'
  const page = Math.max(1, Number(get('page', '1')) || 1)
  const city = get('city')
  const quadrant = get('quad')
  const storeSort = get('ssort', 'total_index|desc') || 'total_index|desc'
  const [sortField, sortOrder] = storeSort.split('|')

  const detail = useApi(() => api.getProduct(id), [id])
  const filters = useApi(api.getFilters, [])
  const stores = useApi(() => api.getProductStores(id, {
    city_id: city ? Number(city) : undefined,
    quadrant: quadrant || undefined,
    sort: sortField,
    order: sortOrder === 'asc' ? 'asc' : 'desc',
    page,
    page_size: 50
  }), [id, city, quadrant, sortField, sortOrder, page])
  const pairs = useApi(() => api.getProductPairs(id, 200), [id])

  if (!Number.isFinite(id)) {
    return <div className="page"><ProductTabs /><ErrorBox message="商品不存在" /></div>
  }
  if (detail.loading) return <div className="page"><ProductTabs /><Loading /></div>
  if (detail.error || !detail.data) {
    return (
      <div className="page">
        <ProductTabs />
        <ErrorBox message={detail.error === 'product not found' ? '商品不存在' : (detail.error ?? '商品不存在')} onRetry={detail.reload} />
      </div>
    )
  }

  const d = detail.data.data
  const meta = detail.data.meta
  const flagCount = d.risk_flag_count ?? 0
  const hitFlags = d.risk_flags.filter((f) => f.hit)

  const storeCols: Column<ProductStoreRow>[] = [
    { key: 'store_id', header: '门店', render: (r) => `S${String(r.store_id).padStart(4, '0')}` },
    { key: 'city_id', header: '城市', render: (r) => r.city_id === null || r.city_id === undefined ? '—' : `C${String(r.city_id).padStart(2, '0')}` },
    { key: 'quadrant', header: '四象限', render: (r) => r.quadrant ?? '—' },
    { key: 'cluster', header: '结构群', render: (r) => r.cluster ?? '—' },
    { key: 'total_index', header: '该店指数', render: (r) => fmtIndex(r.total_index) },
    { key: 'zero_days', header: '零销天数', render: (r) => fmtNumber(r.zero_days) },
    { key: 'stockout_days', header: '缺货天数', render: (r) => fmtNumber(r.stockout_days) },
    { key: 'risk_flag_count', header: 'SKU 风险旗标', render: (r) => (r.risk_flag_count ?? 0) > 0 ? <span className="tag bad">{r.risk_flag_count} 项</span> : <span className="muted">无</span> }
  ]

  const pairCols: Column<ProductPairRow>[] = [
    {
      key: 'other_product_id', header: '关联 SKU',
      render: (r) => <button className="link-button" onClick={(e) => { e.stopPropagation(); nav(`/products/${r.other_product_id}`) }}>
        {r.other_product_code ?? `#${r.other_product_id}`}
      </button>
    },
    { key: 'stores_both', header: '同店门店数', render: (r) => fmtNumber(r.stores_both) },
    { key: 'share_stores_both', header: '占全部门店比例', render: (r) => fmtRate(r.share_stores_both) }
  ]

  const storeTotal = stores.data?.meta.n ?? 0
  const suppressed = Boolean(stores.data?.meta.suppressed)
  const pairAll = pairs.data?.data ?? []
  const pairSummary = summarizePairs(pairAll, pairs.data?.meta.n)
  const pairRows = pairSummary.complete
    ? pairAll.filter((p) => p.stores_both >= 20).slice(0, 20)
    : []
  const pairDefinition = pairAll[0]?.definition ?? PAIR_DEFINITION

  return (
    <div className="page">
      <ProductTabs />
      <div className="page-head">
        <div>
          <BackLink returnTo={safeBack} fallback={backTo} />
          <h1>{d.product_code ?? `SKU #${d.product_id}`}</h1>
          <p>L1 类别 {d.category_code ?? '—'} · 观察期 {meta.period} · 覆盖分母 898 家门店</p>
        </div>
        <div className="tag-row">
          {d.head_tail_group && <Badge tone="info">{d.head_tail_group}</Badge>}
          {flagCount >= 2 && <Badge tone="bad">多风险 · {flagCount} 项</Badge>}
          {flagCount === 1 && <Badge tone="warn">风险旗标 · 1 项</Badge>}
          {flagCount === 0 && <Badge tone="good">无风险旗标</Badge>}
        </div>
      </div>

      <Section title="核心指标" subtitle="完整 90 天冻结值；指数为归一化销量指数，不是销售额 / GMV">
        <div className="profile-grid">
          <div><span>累计指数</span><strong>{fmtIndex(d.total_index)}</strong></div>
          <div><span>贡献份额</span><strong>{fmtRate(d.total_share, 2)}</strong></div>
          <div><span>覆盖门店数</span><strong>{fmtNumber(d.store_count)}</strong></div>
          <div><span>覆盖率（/898）</span><strong>{fmtRate(d.store_coverage)}</strong></div>
          <div><span>单店日均指数</span><strong>{fmtNumber(d.per_series_day, 2)}</strong></div>
          <div><span>零销率</span><strong>{fmtRate(d.zero_rate)}</strong></div>
          <div><span>销量 CV（中位）</span><strong>{fmtNumber(d.cv_series_median, 3)}</strong></div>
          <div><span>门店 HHI</span><strong>{fmtNumber(d.hhi, 4)}</strong></div>
          <div><span>有效门店数</span><strong>{fmtNumber(d.effective_stores, 1)}</strong></div>
          <div><span>异常日占比</span><strong>{fmtRate(d.anomaly_rate)}</strong></div>
          <div><span>SKU-日缺货率</span><strong>{fmtRate(d.stockout_day_rate)}</strong></div>
          <div><span>促销行占比</span><strong>{fmtRate(d.promo_rate)}</strong></div>
          <div><span>规模排名</span><strong>{d.rank_scale ?? '—'}</strong></div>
          <div><span>效率排名（全量）</span><strong>{d.rank_eff_all ?? '—'}</strong></div>
        </div>
        <p className="footnote">
          覆盖门店数 = 观察期内出现该 SKU 的门店数，不是每日在售门店数；HHI 仅在覆盖≥5 店时有解释意义；
          效率排名为 P2 冻结全量排名，覆盖 &lt;5 店时另有受限排名，本页不展示派生排名。
        </p>
      </Section>

      <Section title="风险标记" subtitle="四个旗标相互独立；命中数量只作筛查，不是风险等级或综合评分">
        <div className="flag-grid">
          {d.risk_flags.map((f) => (
            <div key={f.code} className={`flag-card ${f.hit ? 'hit' : ''}`}>
              <div className="tag-row">
                <strong>{f.label}</strong>
                <span className={`tag ${f.hit ? 'bad' : ''}`}>{f.hit ? '命中' : '未命中'}</span>
              </div>
              <p>{f.definition}</p>
            </div>
          ))}
        </div>
        {hitFlags.length === 0 && (
          <div className="notice warn" style={{ marginTop: 10 }}>
            未命中 P2 风险旗标，仅表示未触发冻结筛查规则，不代表经营良好或失败；需结合覆盖、规模与同类比较继续复核。
          </div>
        )}
      </Section>

      <Section title="覆盖门店" subtitle={`共 ${fmtNumber(storeTotal)} 家 · 分母 898 家 · 只展示门店明细，不做客户端组统计`}
        right={<div className="pager">
          <button disabled={page <= 1} onClick={() => set('page', page - 1)}>上一页</button>
          <span>第 {page} 页</span>
          <button disabled={page * 50 >= storeTotal} onClick={() => set('page', page + 1)}>下一页</button>
        </div>}>
        <div className="filter-bar">
          <FilterSelect label="城市" value={city} onChange={(v) => set('city', v)}
            options={(filters.data?.cities ?? []).map((c) => ({
              value: String(c.city_id), label: `C${String(c.city_id).padStart(2, '0')} · ${fmtNumber(c.store_count)} 店`
            }))} />
          <FilterSelect label="四象限" value={quadrant} onChange={(v) => set('quad', v)}
            options={(filters.data?.quadrants ?? []).map((q) => ({ value: q, label: q }))} />
          <FilterSelect label="排序" value={storeSort} onChange={(v) => set('ssort', v)} options={STORE_SORT_OPTIONS} />
          <button className="reset" onClick={() => { ['city', 'quad', 'ssort', 'page'].forEach((k) => set(k, '')) }}>重置</button>
        </div>
        {suppressed && (
          <div className="notice warn" style={{ marginTop: 10 }}>
            该 SKU 当前覆盖门店 n={fmtNumber(storeTotal)} &lt; 20，比例类指标不稳定；本接口只返回门店明细，不提供组统计，页面也不做汇总推算。
          </div>
        )}
        {stores.loading ? <Loading /> : stores.error ? <ErrorBox message={stores.error} onRetry={stores.reload} /> :
          <DataTable columns={storeCols} rows={stores.data?.data ?? []}
            onRowClick={(r) => nav(detailHref(`/stores/${r.store_id}`, buildReturnTo(location.pathname, location.search)))} />}
      </Section>

      <Section
        title="同店共同出现（展示前 20）"
        subtitle={`共 ${pairSummary.total ?? '—'} 对 · 达到 20 店门槛 ${pairSummary.eligible ?? '—'} 对 · 本次展示 ${pairRows.length} 对`}
      >
        {pairs.loading ? <Loading /> : pairs.error ? <ErrorBox message={pairs.error} onRetry={pairs.reload} /> : (
          <>
            {(pairs.data?.warnings ?? []).map((w) => <div key={w} className="notice warn">{w}</div>)}
            {pairSummary.total === null && (
              <div className="notice warn">
                共现总数元数据不可用，无法计算门槛数量；未做估算。
              </div>
            )}
            {pairSummary.total !== null && !pairSummary.complete && (
              <div className="notice warn">
                接口未返回完整共现明细（返回 {pairAll.length} 对 / 总数 {pairSummary.total} 对），
                门槛数量不可用；未用不完整数据推算。
              </div>
            )}
            {pairSummary.complete && (
              <DataTable
                columns={pairCols}
                rows={pairRows}
                empty={pairSummary.total === 0
                  ? '该 SKU 在观察期内无同店共现记录'
                  : `共 ${pairSummary.total} 对共现记录，均低于 20 店展示门槛，未在此展示；低于门槛不代表不存在共现。`}
              />
            )}
          </>
        )}
        {pairSummary.complete && pairSummary.total !== null && pairSummary.total > 0 && (
          <p className="footnote">
            共 {pairSummary.total} 对；达到 20 店门槛 {pairSummary.eligible} 对，本次展示 {pairRows.length} 对；
            低于门槛 {pairSummary.low} 对，仅计数、不作比较。
          </p>
        )}
        <p className="footnote">{pairDefinition} 共现总数来自后端 meta.n；门槛数量仅在返回明细完整时计算。</p>
      </Section>
    </div>
  )
}
