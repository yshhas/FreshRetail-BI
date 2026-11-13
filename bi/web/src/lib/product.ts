import type { ProductRow } from '../api/types'

/** 商品覆盖口径的分母：全部 898 家门店（P4-C 口径，不是 888 风险样本）。 */
export const STORE_DENOMINATOR = 898

export const PRODUCT_FLAGS = [
  { key: 'flag_high_cv', label: '高波动' },
  { key: 'flag_high_zero', label: '高零销' },
  { key: 'flag_many_anomaly_days', label: '异常日频繁' },
  { key: 'flag_store_concentration', label: '门店集中' }
] as const

export const PRODUCT_RISK_DEFINITIONS = [
  { code: 'high_cv', label: '高波动', definition: '序列 CV 中位数 > 全部 865 个 SKU 的 P95 = 1.060' },
  { code: 'high_zero', label: '高零销', definition: 'SKU 零销率 > 全部 865 个 SKU 的 P95 = 24.44%' },
  { code: 'many_anomaly_days', label: '异常日频繁', definition: '异常日占比 > 5%（序列内稳健 z 绝对值 > 3.5 记为异常日）' },
  { code: 'store_concentration', label: '门店集中', definition: '覆盖≥5 店且门店销量 HHI > 多店 SKU 的 P95 = 0.184' }
]

export const RISK_OPTIONS = [
  { value: '', label: '全部商品' },
  { value: 'flagged', label: '仅风险 SKU（117）' },
  { value: 'multi', label: '多风险 SKU（35）' },
  { value: 'high_cv', label: '高波动旗标' },
  { value: 'high_zero', label: '高零销旗标（43）' },
  { value: 'many_anomaly_days', label: '异常日频繁旗标' },
  { value: 'store_concentration', label: '门店集中旗标' }
]

export const HEAD_TAIL_OPTIONS = [
  { value: '', label: '全部结构' },
  { value: 'head', label: '头部 Top20%（173）' },
  { value: 'tail', label: '长尾 Bottom50%（432）' }
]

export const COVERAGE_RANGES = [
  { value: '', label: '全部覆盖区间' },
  { value: '1|1', label: '1 家门店' },
  { value: '2|4', label: '2–4 家' },
  { value: '5|9', label: '5–9 家' },
  { value: '10|19', label: '10–19 家' },
  { value: '20|49', label: '20–49 家' },
  { value: '50|99', label: '50–99 家' },
  { value: '100|100000', label: '100 家以上' }
]

export const SORT_OPTIONS = [
  { value: 'rank_scale', label: '规模排名' },
  { value: 'total_index', label: '累计指数' },
  { value: 'store_count', label: '覆盖门店数' },
  { value: 'per_series_day', label: '单店日均指数' },
  { value: 'zero_rate', label: '零销率' },
  { value: 'cv_series_median', label: '销量 CV' },
  { value: 'hhi', label: '门店集中度 HHI' },
  { value: 'risk_flag_count', label: '风险旗标数' },
  { value: 'product_id', label: 'SKU ID' }
]

export interface CoverageRange {
  min?: number
  max?: number
}

/** 解析 "20|49" 形式的覆盖区间；非法输入返回空区间。 */
export function parseCoverageRange(value: string | null | undefined): CoverageRange {
  if (!value) return {}
  const parts = value.split('|')
  if (parts.length !== 2) return {}
  const min = Number(parts[0])
  const max = Number(parts[1])
  if (!Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max < min) return {}
  return { min, max }
}

export function coverageRangeLabel(value: string | null | undefined): string {
  return COVERAGE_RANGES.find((r) => r.value === (value ?? ''))?.label ?? '全部覆盖区间'
}

/** 返回命中的商品风险旗标名称。 */
export function flagNames(row: Pick<ProductRow, 'flag_high_cv' | 'flag_high_zero' | 'flag_many_anomaly_days' | 'flag_store_concentration'>): string[] {
  return PRODUCT_FLAGS.filter((f) => Boolean(row[f.key])).map((f) => f.label)
}

/** n<20 视为小样本；未知覆盖数不标记为小样本。 */
export function isLowCoverage(storeCount: number | null | undefined): boolean {
  return typeof storeCount === 'number' && Number.isFinite(storeCount) && storeCount < 20
}

export function headTailLabel(value: string | null | undefined): string {
  if (!value) return '—'
  return value
}

export interface PairSummary {
  total: number | null
  eligible: number | null
  low: number | null
  complete: boolean
}

/**
 * 汇总共现门槛数量。
 * - total 来自后端 meta.n；
 * - 只有返回行数与 total 完全一致时才计算门槛数量，避免用不完整分页推算；
 * - 元数据缺失/不完整时返回 null，不估算。
 */
export function summarizePairs(
  rows: Array<{ stores_both: number }>,
  total: number | null | undefined
): PairSummary {
  if (typeof total !== 'number' || !Number.isFinite(total) || total < 0) {
    return { total: null, eligible: null, low: null, complete: false }
  }
  if (rows.length !== total) {
    return { total, eligible: null, low: null, complete: false }
  }
  const eligible = rows.filter((r) => r.stores_both >= 20).length
  return { total, eligible, low: total - eligible, complete: true }
}

