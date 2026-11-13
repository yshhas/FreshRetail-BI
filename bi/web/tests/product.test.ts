import { describe, expect, it } from 'vitest'
import {
  coverageRangeLabel, flagNames, headTailLabel, isLowCoverage, parseCoverageRange,
  PRODUCT_FLAGS, PRODUCT_RISK_DEFINITIONS, RISK_OPTIONS, summarizePairs
} from '../src/lib/product'

describe('product helpers', () => {
  it('parses valid coverage ranges', () => {
    expect(parseCoverageRange('20|49')).toEqual({ min: 20, max: 49 })
    expect(parseCoverageRange('1|1')).toEqual({ min: 1, max: 1 })
  })

  it('rejects invalid coverage ranges', () => {
    expect(parseCoverageRange('')).toEqual({})
    expect(parseCoverageRange('20')).toEqual({})
    expect(parseCoverageRange('49|20')).toEqual({})
    expect(parseCoverageRange('a|b')).toEqual({})
    expect(parseCoverageRange('-1|10')).toEqual({})
  })

  it('labels coverage ranges', () => {
    expect(coverageRangeLabel('20|49')).toBe('20–49 家')
    expect(coverageRangeLabel('')).toBe('全部覆盖区间')
    expect(coverageRangeLabel('unknown')).toBe('全部覆盖区间')
  })

  it('collects hit flag names', () => {
    expect(flagNames({
      flag_high_cv: true, flag_high_zero: false,
      flag_many_anomaly_days: true, flag_store_concentration: false
    })).toEqual(['高波动', '异常日频繁'])
    expect(flagNames({
      flag_high_cv: false, flag_high_zero: false,
      flag_many_anomaly_days: false, flag_store_concentration: false
    })).toEqual([])
  })

  it('marks only known coverage below 20 as low sample', () => {
    expect(isLowCoverage(1)).toBe(true)
    expect(isLowCoverage(19)).toBe(true)
    expect(isLowCoverage(20)).toBe(false)
    expect(isLowCoverage(null)).toBe(false)
    expect(isLowCoverage(undefined)).toBe(false)
  })

  it('keeps frozen labels and risk options stable', () => {
    expect(PRODUCT_FLAGS.map((x) => x.label)).toEqual(['高波动', '高零销', '异常日频繁', '门店集中'])
    expect(PRODUCT_RISK_DEFINITIONS).toHaveLength(4)
    expect(RISK_OPTIONS.find((x) => x.value === 'high_zero')?.label).toContain('43')
    expect(headTailLabel('头部 Top20%')).toBe('头部 Top20%')
    expect(headTailLabel(undefined)).toBe('—')
  })
})

describe('summarizePairs', () => {
  it('handles a true zero-pair SKU', () => {
    expect(summarizePairs([], 0)).toEqual({ total: 0, eligible: 0, low: 0, complete: true })
  })

  it('counts all pairs below the 20-store threshold', () => {
    const rows = [{ stores_both: 1 }, { stores_both: 3 }, { stores_both: 19 }]
    expect(summarizePairs(rows, 3)).toEqual({ total: 3, eligible: 0, low: 3, complete: true })
  })

  it('counts mixed eligible and low pairs', () => {
    const rows = [{ stores_both: 20 }, { stores_both: 440 }, { stores_both: 13 }, { stores_both: 5 }]
    expect(summarizePairs(rows, 4)).toEqual({ total: 4, eligible: 2, low: 2, complete: true })
  })

  it('counts all pairs above the threshold', () => {
    const rows = [{ stores_both: 20 }, { stores_both: 50 }, { stores_both: 100 }]
    expect(summarizePairs(rows, 3)).toEqual({ total: 3, eligible: 3, low: 0, complete: true })
  })

  it('does not estimate when metadata is missing or rows are incomplete', () => {
    expect(summarizePairs([{ stores_both: 440 }], null)).toEqual({
      total: null, eligible: null, low: null, complete: false
    })
    expect(summarizePairs([{ stores_both: 440 }], 5)).toEqual({
      total: 5, eligible: null, low: null, complete: false
    })
  })
})
