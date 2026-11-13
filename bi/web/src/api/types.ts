export interface Meta {
  n: number
  period: string
  data_version: string
  sample_scope: string
  suppressed: boolean
  definitions: string[]
  display_window?: string | null
}

export interface Envelope<T> {
  data: T
  meta: Meta
  warnings: string[]
}

export interface Kpi {
  key: string
  label: string
  value: number | null
  unit: string
  metric_id: string
  sample_n: number
  note: string
}

export interface TrendPoint {
  dt: string
  sales_index_total: number
  per_store_index: number
  zero_sales_rate?: number | null
  stockout_day_rate?: number | null
}

export interface HourPoint { hour: number; sales_index: number; share?: number | null }
export interface WeekdayPoint { weekday: number; sales_index: number; share?: number | null }
export interface WeekdayHourPoint { weekday: number; hour: number; sales_index: number }
export interface TimeProfile { hours: HourPoint[]; weekday: WeekdayPoint[]; heatmap: WeekdayHourPoint[] }

export interface CityRow {
  city_id: number
  store_count: number
  city_total_index: number
  city_store_day_avg: number
  sku_per_store_mean?: number | null
  city_stockout_sku_day_pooled?: number | null
  city_stockout_store_mean?: number | null
  city_stockout_hour_pooled?: number | null
  city_zero_rate?: number | null
  small_city?: boolean | null
  stores_all?: number | null
  stores_risk?: number | null
  stockout_sku_day_median?: number | null
  stockout_hour_median?: number | null
  multi_risk?: number | null
  multi_risk_rate_risk?: number | null
  multi_risk_rate_all?: number | null
}

export interface StoreRow {
  store_id: number
  city_id: number
  profile_status: string
  total_index?: number | null
  per_day_index?: number | null
  sku_count?: number | null
  per_sku_day_index?: number | null
  cv?: number | null
  zero_rate?: number | null
  stockout_sku_day_rate?: number | null
  stockout_hour_rate?: number | null
  eff_resid?: number | null
  quadrant?: string | null
  cluster?: string | null
  sku_hhi?: number | null
  n_cat?: number | null
  R1?: boolean | null
  R2?: boolean | null
  R3?: boolean | null
  R4?: boolean | null
  R5?: boolean | null
  R6?: boolean | null
  R7?: boolean | null
  R8?: boolean | null
  stockout_domain?: boolean | null
  domain_count?: number | null
  multi_risk?: boolean | null
  in_risk_sample?: boolean | null
  diagnosis_status?: string | null
  domain_labels?: string | null
  exact_combo?: string | null
  structural_notes?: string | null
}

export interface StoreScatterRow {
  store_id: number
  city_id: number
  per_day_index?: number | null
  eff_resid?: number | null
  quadrant?: string | null
  cluster?: string | null
  multi_risk?: boolean | null
  domain_count?: number | null
}

export interface StoreGroupRow {
  quadrant: string
  cluster: string
  stores: number
  n_flagged_median?: number | null
  share_flagged_median?: number | null
  multi_risk_rate?: number | null
  sample_insufficient: boolean
  suppressed: boolean
}

export interface RiskDomainRow { domain_count: number; stores: number }
export interface RiskSummary {
  domains: RiskDomainRow[]
  multi_risk: number
  flags: Record<string, number>
}
export interface RiskComboRow {
  combination: string
  stores: number
  rank?: number | null
  definition?: string | null
}

export interface Filters {
  cities: Array<{ city_id: number; store_count: number; small_city?: boolean | null }>
  quadrants: string[]
  clusters: string[]
  risk_domains: string[]
  categories: Array<Record<string, unknown>>
  sample_scopes: string[]
  period: string
}

export interface StoreFilters {
  city_id?: number
  quadrant?: string
  cluster?: string
  risk_domain?: string
  exact_combo?: string
  domains?: string
  sample_scope?: 'all' | 'risk'
  page?: number
  page_size?: number
  sort?: string
}

export interface StoreSkuRow {
  product_id: number
  product_code?: string | null
  category_code?: string | null
  days_present?: number | null
  observed_rows?: number | null
  total_index?: number | null
  zero_days?: number | null
  stockout_days?: number | null
  zero_rate?: number | null
  risk_flag_count?: number | null
  flag_high_cv?: boolean | null
  flag_high_zero?: boolean | null
  flag_many_anomaly_days?: boolean | null
  flag_store_concentration?: boolean | null
  is_flagged?: boolean | null
  is_multi_flag?: boolean | null
}

export interface ProductRow {
  product_id: number
  product_code?: string | null
  category_code?: string | null
  store_count?: number | null
  store_coverage?: number | null
  total_index?: number | null
  total_share?: number | null
  cum_share?: number | null
  per_series_day?: number | null
  zero_rate?: number | null
  cv_series_median?: number | null
  hhi?: number | null
  risk_flag_count?: number | null
  flag_high_cv?: boolean | null
  flag_high_zero?: boolean | null
  flag_many_anomaly_days?: boolean | null
  flag_store_concentration?: boolean | null
  rank_scale?: number | null
  rank_eff_all?: number | null
  rank_eff_cov5?: number | null
  head_tail_group?: string | null
  is_flagged?: boolean | null
}

export interface ProductRiskFlag {
  code: string
  label: string
  definition: string
  hit: boolean
}

export interface ProductDetail extends ProductRow {
  series_days?: number | null
  active_day_rate?: number | null
  stockout_day_rate?: number | null
  promo_rate?: number | null
  anomaly_rate?: number | null
  effective_stores?: number | null
  rank_diff?: number | null
  stability_tier?: string | null
  risk_flags: ProductRiskFlag[]
}

export interface ProductStoreRow {
  store_id: number
  city_id?: number | null
  quadrant?: string | null
  cluster?: string | null
  days_present?: number | null
  observed_rows?: number | null
  total_index?: number | null
  zero_days?: number | null
  stockout_days?: number | null
  risk_flag_count?: number | null
  is_flagged?: boolean | null
  is_multi_flag?: boolean | null
}

export interface ProductPairRow {
  other_product_id: number
  other_product_code?: string | null
  stores_both: number
  share_stores_both: number
  definition: string
}

export interface CoverageBucket {
  bucket: string
  min_store_count: number
  max_store_count: number
  skus: number
}

export interface HeadTailRow {
  group: string
  skus: number
  share: number
}

export interface ProductCategoryRow {
  category_code: string
  sku_count: number
  store_count: number
  total_index: number
  share_pct: number
  n_flagged_skus: number
  n_multi_flag_skus: number
  flagged_sku_share?: number | null
  flagged_total_index_share?: number | null
  coverage?: number | null
  rare?: boolean | null
}

export interface ProductOverview {
  sku_count: number
  total_index: number
  store_count_median: number
  store_count_p90: number
  store_count_max: number
  coverage_distribution: CoverageBucket[]
  head_tail: HeadTailRow[]
  flagged_skus: number
  multi_flag_skus: number
  categories: ProductCategoryRow[]
}

export interface ProductFilters {
  scope?: 'all' | 'flagged'
  q?: string
  category?: string
  head_tail?: 'head' | 'tail'
  risk?: string
  coverage_min?: number
  coverage_max?: number
  sort?: string
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface ProductStoreFilters {
  city_id?: number
  quadrant?: string
  cluster?: string
  flagged_only?: boolean
  sort?: string
  order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export interface ProductRiskCounts {
  high_cv: number
  high_zero: number
  many_anomaly_days: number
  store_concentration: number
}

