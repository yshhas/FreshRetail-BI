import type {
  CityRow, Envelope, Filters, Kpi, ProductDetail, ProductFilters, ProductOverview,
  ProductPairRow, ProductRiskCounts, ProductRow, ProductStoreFilters, ProductStoreRow,
  RiskComboRow, RiskSummary, StoreFilters, StoreGroupRow, StoreRow, StoreScatterRow,
  StoreSkuRow, TimeProfile, TrendPoint
} from './types'

const BASE = '/api/v1'

function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

async function get<T>(path: string, params: Record<string, string | number | undefined | null> = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}${qs(params)}`, { headers: { Accept: 'application/json' } })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  getKpis: () => get<Envelope<Kpi[]>>('/overview/kpis'),
  getTrend: (start?: string, end?: string) => get<Envelope<TrendPoint[]>>('/overview/trend', { start, end }),
  getTimeProfile: () => get<Envelope<TimeProfile>>('/overview/time-profile'),
  getCities: () => get<Envelope<CityRow[]>>('/cities'),
  getFilters: () => get<Filters>('/meta/filters'),
  getStoreScatter: () => get<Envelope<StoreScatterRow[]>>('/stores/scatter'),
  getStores: (f: StoreFilters) => get<Envelope<StoreRow[]>>('/stores', {
    city_id: f.city_id, quadrant: f.quadrant, cluster: f.cluster, risk_domain: f.risk_domain,
    exact_combo: f.exact_combo, domains: f.domains,
    sample_scope: f.sample_scope, page: f.page, page_size: f.page_size, sort: f.sort
  }),
  getStore: (id: number) => get<Envelope<StoreRow>>(`/stores/${id}`),
  getStoreSkus: (id: number, f: {
    flagged_only?: boolean; sort?: string; order?: 'asc' | 'desc'; page?: number; page_size?: number
  } = {}) => get<Envelope<StoreSkuRow[]>>(`/stores/${id}/skus`, {
    flagged_only: f.flagged_only ? 'true' : undefined,
    sort: f.sort, order: f.order, page: f.page, page_size: f.page_size
  }),
  getGroups: () => get<Envelope<StoreGroupRow[]>>('/stores/groups'),
  getRiskSummary: () => get<Envelope<RiskSummary>>('/risk/summary'),
  getRiskCombinations: (definition: 'exact' | 'at_least') =>
    get<Envelope<RiskComboRow[]>>('/risk/combinations', { definition }),

  getProductOverview: () => get<Envelope<ProductOverview>>('/products/overview'),
  getProducts: (f: ProductFilters) => get<Envelope<ProductRow[]>>('/products', {
    scope: f.scope, q: f.q, category: f.category, head_tail: f.head_tail, risk: f.risk,
    coverage_min: f.coverage_min, coverage_max: f.coverage_max,
    sort: f.sort, order: f.order, page: f.page, page_size: f.page_size
  }),
  getProduct: (id: number) => get<Envelope<ProductDetail>>(`/products/${id}`),
  getProductStores: (id: number, f: ProductStoreFilters) =>
    get<Envelope<ProductStoreRow[]>>(`/products/${id}/stores`, {
      city_id: f.city_id, quadrant: f.quadrant, cluster: f.cluster,
      flagged_only: f.flagged_only ? 'true' : undefined, sort: f.sort, order: f.order,
      page: f.page, page_size: f.page_size
    }),
  getProductPairs: (id: number, limit = 20) =>
    get<Envelope<ProductPairRow[]>>(`/products/${id}/pairs`, { limit }),
  getProductRiskCounts: async (): Promise<ProductRiskCounts> => {
    const keys: Array<keyof ProductRiskCounts> = [
      'high_cv', 'high_zero', 'many_anomaly_days', 'store_concentration'
    ]
    const rows = await Promise.all(keys.map((risk) =>
      get<Envelope<ProductRow[]>>('/products', { scope: 'all', risk, page_size: 1 })
    ))
    return keys.reduce((acc, key, i) => {
      acc[key] = rows[i].meta.n
      return acc
    }, {} as ProductRiskCounts)
  }
}
