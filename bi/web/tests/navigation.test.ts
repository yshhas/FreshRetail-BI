import { describe, expect, it } from 'vitest'
import { buildReturnTo, detailHref, returnLabel, safeReturnTo } from '../src/lib/navigation'

describe('safeReturnTo', () => {
  it('accepts allowed internal paths', () => {
    expect(safeReturnTo('/cities-stores?city=3')).toBe('/cities-stores?city=3')
    expect(safeReturnTo('/risk?domain=R4&page=2')).toBe('/risk?domain=R4&page=2')
    expect(safeReturnTo('/products/4?city=8')).toBe('/products/4?city=8')
    expect(safeReturnTo('/stores/35')).toBe('/stores/35')
  })

  it('rejects external, protocol-relative and malformed values', () => {
    expect(safeReturnTo('https://evil.example/x')).toBeNull()
    expect(safeReturnTo('//evil.example/x')).toBeNull()
    expect(safeReturnTo('javascript:alert(1)')).toBeNull()
    expect(safeReturnTo('/../etc/passwd')).toBeNull()
    expect(safeReturnTo('products/4')).toBeNull()
    expect(safeReturnTo('/unknown?x=1')).toBeNull()
    expect(safeReturnTo('/cities-stores\\evil')).toBeNull()
    expect(safeReturnTo('')).toBeNull()
    expect(safeReturnTo(null)).toBeNull()
    expect(safeReturnTo(`/risk?x=${'a'.repeat(600)}`)).toBeNull()
  })

  it('strips nested returnTo to avoid loops', () => {
    expect(safeReturnTo('/products/4?city=8&returnTo=%2Frisk%3Fdomain%3DR4'))
      .toBe('/products/4?city=8')
  })

  it('rejects traversal segments and encoded traversal variants', () => {
    expect(safeReturnTo('/cities-stores/../risk')).toBeNull()
    expect(safeReturnTo('/cities-stores/%2e%2e/risk')).toBeNull()
    expect(safeReturnTo('/cities-stores/%2E%2E/risk')).toBeNull()
    expect(safeReturnTo('/cities-stores/%2e./risk')).toBeNull()
    expect(safeReturnTo('/cities-stores/.%2e/risk')).toBeNull()
    expect(safeReturnTo('/cities-stores/%252e%252e/risk')).toBeNull()
    expect(safeReturnTo('/cities-stores/%25252525252e%25252525252e/risk')).toBeNull()
    expect(safeReturnTo('/cities-stores%2f..%2frisk')).toBeNull()
    expect(safeReturnTo('/cities-stores%5c..%5crisk')).toBeNull()
    expect(safeReturnTo('/%2e%2e/risk')).toBeNull()
  })

  it('does not reject dots inside query parameters', () => {
    expect(safeReturnTo('/products/list?q=..')).toBe('/products/list?q=..')
    expect(safeReturnTo('/products/list?q=a..b&page=2')).toBe('/products/list?q=a..b&page=2')
  })
})

describe('buildReturnTo', () => {
  it('keeps filters while removing its own returnTo', () => {
    expect(buildReturnTo('/cities-stores', '?city=3&returnTo=%2Frisk'))
      .toBe('/cities-stores?city=3')
    expect(buildReturnTo('/products/4', '?city=8&page=2'))
      .toBe('/products/4?city=8&page=2')
    expect(buildReturnTo('/risk', '')).toBe('/risk')
  })
})

describe('detailHref', () => {
  it('encodes returnTo and omits empty values', () => {
    expect(detailHref('/stores/35', '/cities-stores?city=3'))
      .toBe('/stores/35?returnTo=%2Fcities-stores%3Fcity%3D3')
    expect(detailHref('/products/4', null)).toBe('/products/4')
  })
})

describe('returnLabel', () => {
  it('labels known sources and defaults to store list', () => {
    expect(returnLabel('/risk?domain=R4')).toBe('← 返回风险页')
    expect(returnLabel('/products/4')).toBe('← 返回 SKU 页面')
    expect(returnLabel('/stores/35')).toBe('← 返回门店详情')
    expect(returnLabel('/cities-stores?city=3')).toBe('← 返回门店列表')
    expect(returnLabel(null)).toBe('← 返回门店列表')
  })
})
