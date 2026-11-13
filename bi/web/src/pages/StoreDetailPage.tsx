import { useMemo } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApi } from '../lib/useApi'
import { useUrlFilters } from '../lib/useUrlFilters'
import { buildReturnTo, detailHref, safeReturnTo } from '../lib/navigation'
import { fmtIndex, fmtNumber, fmtRate } from '../lib/format'
import { BackLink } from '../components/BackLink'
import { Badge } from '../components/Badge'
import { DataTable, type Column } from '../components/DataTable'
import { FilterSelect } from '../components/FilterSelect'
import { Section } from '../components/Section'
import { ErrorBox, Loading, Suppressed } from '../components/States'
import type { StoreSkuRow } from '../api/types'

const RISK_LABELS: Array<{ key: 'R1' | 'R2' | 'R3' | 'R4' | 'R5' | 'R6' | 'R7' | 'R8'; label: string; structural?: boolean }> = [
  { key: 'R1', label: 'R1 缺货广度' },
  { key: 'R2', label: 'R2 缺货强度' },
  { key: 'R3', label: 'R3 持续低销' },
  { key: 'R4', label: 'R4 高零销' },
  { key: 'R5', label: 'R5 高波动' },
  { key: 'R6', label: 'R6 高异常日' },
  { key: 'R7', label: 'R7 覆盖偏窄', structural: true },
  { key: 'R8', label: 'R8 结构集中', structural: true }
]

export function StoreDetailPage() {
  const { storeId } = useParams()
  const location = useLocation()
  const nav = useNavigate()
  const { get, set, patch } = useUrlFilters()
  const safeBack = safeReturnTo(new URLSearchParams(location.search).get('returnTo'))
  const backTo = safeBack ?? '/cities-stores'
  const id = Number(storeId)
  const skScope = get('skscope', 'all') || 'all'
  const skSort = get('sksort', 'total_index|desc') || 'total_index|desc'
  const skPage = Math.max(1, Number(get('page', '1')) || 1)
  const [skSortField, skSortOrder] = skSort.split('|')
  const store = useApi(() => api.getStore(id), [id])
  const groups = useApi(api.getGroups, [])
  const storeSkus = useApi(() => api.getStoreSkus(id, {
    flagged_only: skScope === 'flagged',
    sort: skSortField,
    order: skSortOrder === 'asc' ? 'asc' : 'desc',
    page: skPage,
    page_size: 50
  }), [id, skScope, skSort, skPage])

  const s = store.data?.data
  const lowSku = s ? !s.in_risk_sample : false
  const peer = useMemo(() => (groups.data?.data ?? []).find(
    (g) => g.quadrant === s?.quadrant && g.cluster === s?.cluster
  ), [groups.data, s])

  if (store.loading) return <div className="page"><Loading /></div>
  if (store.error) return <div className="page"><ErrorBox message={store.error === 'store not found' ? '门店不存在' : store.error} onRetry={store.reload} /></div>
  if (!s) return <div className="page"><ErrorBox message="门店不存在" /></div>

  const review: Array<{ evidence: string; action: string }> = []
  if (lowSku) review.push({ evidence: 'SKU 覆盖数 <10（基础档案）', action: '保留基础画像；不参与风险诊断、四象限或同类比较。' })
  if (s.stockout_domain) review.push({ evidence: 'R1 或 R2 命中（缺货域）', action: '复核缺货发生时段、SKU-日记录与排面/补货记录；不推断缺货原因。' })
  if (s.R3) review.push({ evidence: 'R3：P1 连续低销 ≥7 天', action: '复核低销起止时间、涉及 SKU 与结构变化；不推断因果。' })
  if (s.R4) review.push({ evidence: 'R4：零销率高于全样本 P90', action: '复核零销 SKU 是否长期无销售、下架或缺货标记。' })
  if (s.R5) review.push({ evidence: 'R5：销量 CV 高于全样本 P90', action: '复核波动集中的日期与同期异常/促销记录。' })
  if (s.R6) review.push({ evidence: 'R6：异常日占比 >P90', action: '复核异常日清单与对应商品/时段。' })
  if (s.R7) review.push({ evidence: 'R7：SKU 覆盖处于 P10 以下（结构提示）', action: '复核覆盖过窄是否由业态/门店规模造成；不作经营能力判断。' })
  if (s.R8) review.push({ evidence: 'R8：SKU HHI 处于同覆盖分位 P90 以上（结构提示）', action: '复核头部 SKU 依赖与结构集中；不推断经营好坏。' })
  if (!review.length) review.push({ evidence: '当前无冻结风险标记', action: '保持观察；可结合趋势与同类门店继续复核。' })

  const skuCols: Column<StoreSkuRow>[] = [
    { key: 'product_code', header: 'SKU', render: (r) => r.product_code ?? `#${r.product_id}` },
    { key: 'category_code', header: 'L1 类别', render: (r) => r.category_code ?? '—' },
    { key: 'total_index', header: '该店指数', render: (r) => fmtIndex(r.total_index) },
    { key: 'days_present', header: '覆盖天数', render: (r) => fmtNumber(r.days_present) },
    { key: 'zero_rate', header: '零销率', render: (r) => fmtRate(r.zero_rate) },
    { key: 'stockout_days', header: '缺货天数', render: (r) => fmtNumber(r.stockout_days) },
    {
      key: 'risk_flag_count', header: '风险旗标',
      render: (r) => (r.risk_flag_count ?? 0) > 0
        ? <span className="tag bad">{r.risk_flag_count} 项{r.is_multi_flag ? ' · 多风险' : ''}</span>
        : <span className="muted">无</span>
    }
  ]

  const skuTotal = storeSkus.data?.meta.n ?? 0

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <BackLink returnTo={safeBack} fallback={backTo} />
          <h1>门店 S{String(s.store_id).padStart(4, '0')}</h1>
          <p>城市 C{String(s.city_id).padStart(2, '0')} · {s.profile_status} · {s.diagnosis_status ?? '—'}</p>
        </div>
        <div className="tag-row">
          {s.quadrant && <Badge tone="info">{s.quadrant}</Badge>}
          {s.cluster && <Badge>{s.cluster}</Badge>}
          {s.multi_risk && <Badge tone="bad">多风险 {s.domain_count ?? ''} 域</Badge>}
        </div>
      </div>

      {lowSku && (
        <div className="notice warn">
          该门店 SKU&lt;10，仅保留基础档案；不参与风险诊断、四象限/同类比较。风险字段显示为 —。
        </div>
      )}

      <Section title="门店画像" subtitle="所有指标为完整 90 天观察期冻结值">
        <div className="profile-grid">
          <div><span>单店日均指数</span><strong>{fmtIndex(s.per_day_index)}</strong></div>
          <div><span>90 天指数合计</span><strong>{fmtIndex(s.total_index)}</strong></div>
          <div><span>SKU 覆盖数</span><strong>{fmtNumber(s.sku_count)}</strong></div>
          <div><span>单 SKU 日均</span><strong>{fmtNumber(s.per_sku_day_index, 3)}</strong></div>
          <div><span>销量 CV</span><strong>{fmtNumber(s.cv, 3)}</strong></div>
          <div><span>零销率</span><strong>{fmtRate(s.zero_rate)}</strong></div>
          <div><span>SKU-日缺货率</span><strong>{fmtRate(s.stockout_sku_day_rate)}</strong></div>
          <div><span>小时槽位缺货率</span><strong>{fmtRate(s.stockout_hour_rate)}</strong></div>
          <div><span>相对效率残差</span><strong>{fmtNumber(s.eff_resid, 4)}</strong></div>
          <div><span>SKU HHI</span><strong>{fmtNumber(s.sku_hhi, 4)}</strong></div>
          <div><span>一级类别数</span><strong>{fmtNumber(s.n_cat)}</strong></div>
          <div><span>运营风险域</span><strong>{s.in_risk_sample ? `${s.domain_count ?? 0} 个` : '不诊断'}</strong></div>
        </div>
      </Section>

      <Section title="风险标记" subtitle="R1–R6 为五个运营风险域来源；R7/R8 仅结构提示，不计入域数量">
        <div className="risk-tags">
          {RISK_LABELS.map((r) => {
            const active = Boolean(s[r.key])
            return (
              <div key={r.key} className={`risk-tag ${active ? 'active' : ''} ${r.structural ? 'structural' : ''}`}>
                <span>{r.label}</span>
                <strong>{lowSku ? '—' : active ? '命中' : '未命中'}</strong>
              </div>
            )
          })}
        </div>
        <div className="detail-notes">
          <div><span>命中域</span><strong>{s.domain_labels || '—'}</strong></div>
          <div><span>精确组合</span><strong>{s.exact_combo || '—'}</strong></div>
          <div><span>结构提示</span><strong>{s.structural_notes || '—'}</strong></div>
          <div><span>诊断状态</span><strong>{s.diagnosis_status || '—'}</strong></div>
        </div>
      </Section>

      <Section title="该店 SKU（观察期内）" subtitle={`共 ${fmtNumber(skuTotal)} 个 · 观察期内出现的 SKU；点击进入 SKU 详情`}>
        <div className="filter-bar">
          <FilterSelect label="SKU 范围" value={skScope === 'flagged' ? 'flagged' : 'all'}
            onChange={(v) => set('skscope', v === 'all' ? '' : v)}
            options={[{ value: 'all', label: '全部 SKU' }, { value: 'flagged', label: '仅风险 SKU' }]} />
          <FilterSelect label="排序" value={skSort} onChange={(v) => set('sksort', v)}
            options={[
              { value: 'total_index|desc', label: '该店指数（降序）' },
              { value: 'zero_days|desc', label: '零销天数（降序）' },
              { value: 'stockout_days|desc', label: '缺货天数（降序）' },
              { value: 'product_id|asc', label: 'SKU 编号（升序）' }
            ]} />
          <button className="reset" onClick={() => patch({ skscope: '', sksort: '', page: '' })}>重置</button>
        </div>
        {storeSkus.loading ? <Loading /> : storeSkus.error ? (
          <ErrorBox message={storeSkus.error} onRetry={storeSkus.reload} />
        ) : (
          <DataTable columns={skuCols} rows={storeSkus.data?.data ?? []}
            onRowClick={(r) => nav(detailHref(`/products/${r.product_id}`, buildReturnTo(location.pathname, location.search)))} />
        )}
        <div className="pager" style={{ marginTop: 10 }}>
          <button disabled={skPage <= 1} onClick={() => set('page', skPage - 1)}>上一页</button>
          <span>第 {skPage} 页 · 共 {fmtNumber(skuTotal)} 个</span>
          <button disabled={skPage * 50 >= skuTotal} onClick={() => set('page', skPage + 1)}>下一页</button>
        </div>
        <p className="footnote">
          零销率 = 零销天数 / 观察行数；覆盖天数 = 观察期内出现天数；风险旗标为 P2 冻结标记。
          该列表为门店明细，不做组统计或客户端聚合。
        </p>
      </Section>

      <Section title="同类门店比较" subtitle="P3-B 四象限 × P3-C G1–G4；n<20 不比较">
        {!s.in_risk_sample || !s.quadrant || s.quadrant === '不适用' || !s.cluster || s.cluster === '不适用' ? <div className="empty-state">该门店不参与结构分组</div> :
          peer ? (
            <div className="profile-grid compact">
              <div><span>同类组</span><strong>{peer.quadrant} / {peer.cluster}</strong></div>
              <div><span>同类门店数</span><strong>{peer.stores}</strong></div>
              <div><span>风险 SKU 中位</span><strong>{peer.suppressed ? <Suppressed n={peer.stores} /> : fmtNumber(peer.n_flagged_median, 1)}</strong></div>
              <div><span>风险 SKU 占比中位</span><strong>{peer.suppressed ? <Suppressed n={peer.stores} /> : fmtRate(peer.share_flagged_median)}</strong></div>
              <div><span>多风险率</span><strong>{peer.suppressed ? <Suppressed n={peer.stores} /> : fmtRate(peer.multi_risk_rate)}</strong></div>
              <div><span>样本状态</span><strong>{peer.sample_insufficient ? '样本不足（n<20）' : '可比较'}</strong></div>
            </div>
          ) : <div className="empty-state">未找到同类组</div>}
      </Section>

      <Section title="复核清单（非措施承诺）" subtitle="按“数据证据 → 建议复核事项”组织；不做因果判断">
        <div className="review-list">
          {review.map((r, i) => (
            <div key={i} className="review-item">
              <span className="review-index">{i + 1}</span>
              <div>
                <strong>{r.evidence}</strong>
                <p>{r.action}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  )
}
