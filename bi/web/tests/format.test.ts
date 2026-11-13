import { describe, expect, it } from 'vitest'
import { fmtCompact, fmtIndex, fmtNumber, fmtRate, weekday } from '../src/lib/format'

describe('format helpers', () => {
  it('formats rates', () => {
    expect(fmtRate(0.442668)).toBe('44.3%')
    expect(fmtRate(null)).toBe('—')
  })
  it('formats indices and counts', () => {
    expect(fmtIndex(4493660.787)).toBe('4,493,660.8')
    expect(fmtNumber(898)).toBe('898')
    expect(fmtNumber(null)).toBe('—')
  })
  it('formats compact axis labels', () => {
    expect(fmtCompact(80000)).toBe('8万')
    expect(fmtCompact(1200000)).toBe('120万')
  })
  it('maps weekdays', () => {
    expect(weekday(0)).toBe('周一')
    expect(weekday(6)).toBe('周日')
  })
})
