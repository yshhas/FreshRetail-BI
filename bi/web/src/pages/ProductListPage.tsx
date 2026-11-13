import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { buildReturnTo, detailHref } from '../lib/navigation'
import { fmtNumber } from '../lib/format'
import {
  COVERAGE_RANGES, HEAD_TAIL_OPTIONS, RISK_OPTIONS, SORT_OPTIONS, parseCoverageRange
} from '../lib/product'
import { FilterSelect } from '../components/FilterSelect'
import { ProductTable } from '../components/ProductTable'
import { ProductTabs } from '../components/ProductTabs'
import { Section } from '../components/Section'
import { ErrorBox, Loading } from '../components/States'

export function ProductListPage() {
  const nav = useNavigate()
  const location = useLocation()
  const { get, set } = useUrlFilters()
  const returnTo = buildReturnTo(location.pathname, location.search)
  const q = get('q')
  const category = get('cat')
  const headTail = get('ht')
  const risk = get('risk')
  const coverage = get('cov')
  const sort = get('sort')
  const order = (get('order', 'desc') || 'desc') as 'asc' | 'desc'
  const page = Math.max(1, Number(get('page', '1')) || 1)
  const [keyword, setKeyword] = useState(q)

  useEffect(() => { setKeyword(q) }, [q])

  const range = parseCoverageRange(coverage)
  const products = useApi(() => api.getProducts({
    scope: 'all',
    q: q || undefined,
    category: category || undefined,
    head_tail: (headTail || undefined) as 'head' | 'tail' | undefined,
    risk: risk || undefined,
    coverage_min: range.min,
    coverage_max: range.max,
    sort: sort || undefined,
    order,
    page,
    page_size: 50
  }), [q, category, headTail, risk, coverage, sort, order, page])

  const filters = useApi(api.getFilters, [])
  const total = products.data?.meta.n ?? 0

  const applySearch = () => set('q', keyword.trim())

  return (
    <div className="page">
      <ProductTabs />
      <div className="page-head">
        <div>
          <h1>SKU 列表</h1>
          <p>固定使用 scope=all，展示全部 865 个 SKU；风险 SKU 是其中子集，请通过筛选查看。</p>
        </div>
        <span className="tag">scope=all · 全部商品</span>
      </div>

      <div className="filter-bar">
        <label className="filter-field">
          <span>SKU 搜索</span>
          <input value={keyword} placeholder="如 P0005" maxLength={40}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') applySearch() }} />
        </label>
        <button className="reset" style={{ marginLeft: 0 }} onClick={applySearch}>查询</button>
        <FilterSelect label="L1 类别" value={category} onChange={(v) => set('cat', v)}
          options={(filters.data?.categories ?? []).map((c) => ({
            value: String(c.category_code ?? c.display_code ?? ''),
            label: `${String(c.category_code ?? c.display_code ?? '')} · ${fmtNumber(Number(c.sku_count ?? 0))} SKU`
          }))} />
        <FilterSelect label="头部 / 长尾" value={headTail} onChange={(v) => set('ht', v)} options={HEAD_TAIL_OPTIONS} />
        <FilterSelect label="风险筛选" value={risk} onChange={(v) => set('risk', v)} options={RISK_OPTIONS} />
        <FilterSelect label="覆盖门店区间" value={coverage} onChange={(v) => set('cov', v)} options={COVERAGE_RANGES} />
        <FilterSelect label="排序" value={sort} onChange={(v) => set('sort', v)}
          options={SORT_OPTIONS} placeholder="默认（规模排名升序）" />
        <FilterSelect label="方向" value={order} onChange={(v) => set('order', v)}
          options={[{ value: 'desc', label: '降序' }, { value: 'asc', label: '升序' }]} placeholder="降序" />
        <button className="reset" onClick={() => {
          ['q', 'cat', 'ht', 'risk', 'cov', 'sort', 'order', 'page'].forEach((k) => set(k, ''))
        }}>重置筛选</button>
      </div>

      <p className="footnote">
        当前筛选：搜索 {q || '全部'} · 类别 {category || '全部'} · 结构 {headTail === 'head' ? '头部' : headTail === 'tail' ? '长尾' : '全部'} ·
        风险 {risk || '全部'} · 覆盖 {coverage || '全部'}。筛选变化会自动回到第 1 页。
      </p>

      <Section title="全部 SKU" subtitle={`共 ${fmtNumber(total)} 个 SKU；每页 50 个；点击行进入 SKU 详情`}>
        {products.loading ? <Loading /> : products.error ? <ErrorBox message={products.error} onRetry={products.reload} /> :
          <ProductTable rows={products.data?.data ?? []} onRowClick={(r) => nav(detailHref(`/products/${r.product_id}`, returnTo))} />}
        <div className="pager" style={{ marginTop: 10 }}>
          <button disabled={page <= 1} onClick={() => set('page', page - 1)}>上一页</button>
          <span>第 {page} 页 · 共 {fmtNumber(total)} 个</span>
          <button disabled={page * 50 >= total} onClick={() => set('page', page + 1)}>下一页</button>
        </div>
      </Section>

      <p className="footnote">
        覆盖门店数为观察期内出现该 SKU 的门店数（分母 898），不是每日在售门店数；累计指数为归一化销量指数，不是销售额或 GMV。
      </p>
    </div>
  )
}
