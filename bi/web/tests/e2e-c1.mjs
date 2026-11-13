import { chromium } from 'playwright-core'
import { resolve } from 'node:path'

import { executablePath } from './browser.mjs'
const BASE = 'http://127.0.0.1:5173'
const SHOTS = resolve('../screenshots')

const results = []
function ok(name, detail = '') {
  results.push({ name, status: 'PASS', detail })
  console.log(`PASS ${name} ${detail}`)
}
function cardByTitle(page, title) {
  return page.locator('.card').filter({ has: page.getByRole('heading', { name: title, exact: true }) })
}
function params(url) {
  return new URL(url).searchParams
}
async function need(cond, label, extra = '') {
  if (!cond) throw new Error(`${label} ${extra}`)
}

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
page.on('pageerror', (e) => { throw new Error(`pageerror: ${e.message}`) })

// 1. Overview city table -> city filtered store list -> store detail -> back
await page.goto(`${BASE}/overview`, { waitUntil: 'networkidle' })
await page.locator('tbody tr').filter({ hasText: 'C03' }).first().click()
await page.waitForURL('**/cities-stores?city=3**')
await page.getByRole('heading', { name: '城市与门店' }).waitFor()
const citySelect = page.locator('.filter-field').filter({ hasText: '城市' }).locator('select')
await page.waitForFunction(() => {
  const field = Array.from(document.querySelectorAll('.filter-field')).find((el) => el.textContent?.includes('城市'))
  return field?.querySelector('select')?.value === '3'
})
await need(await citySelect.inputValue() === '3', 'city select not 3')

const cityStoreList = cardByTitle(page, '门店列表')
await cityStoreList.locator('tbody tr').first().waitFor()
await cityStoreList.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
let backHref = await page.locator('a.back-link').getAttribute('href')
await need(decodeURIComponent(backHref ?? '') === '/cities-stores?city=3', 'city returnTo mismatch', backHref ?? '')
await page.locator('a.back-link').click()
await page.waitForURL('**/cities-stores?city=3**')
await page.waitForFunction(() => {
  const field = Array.from(document.querySelectorAll('.filter-field')).find((el) => el.textContent?.includes('城市'))
  return field?.querySelector('select')?.value === '3'
})
await need(await citySelect.inputValue() === '3', 'city not restored')
await page.screenshot({ path: `${SHOTS}/c1-city-return.png`, fullPage: true })
ok('C1 city -> stores -> detail -> back', 'city=3 restored')

// 2. Browser back / forward restore filtered list
await cityStoreList.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
await page.goBack()
await page.waitForURL('**/cities-stores?city=3**')
await page.goForward()
await page.waitForURL('**/stores/**?returnTo=**')
await page.goBack()
await page.waitForURL('**/cities-stores?city=3**')
ok('C1 browser back/forward', 'history restores city=3')

// 2b. City list with risk filter + page 2 restores all filters
await page.goto(`${BASE}/cities-stores?city=3&risk=stockout_domain&page=2&scope=risk`, { waitUntil: 'networkidle' })
const filteredCityList = cardByTitle(page, '门店列表')
await filteredCityList.locator('tbody tr').first().waitFor()
await filteredCityList.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
await page.locator('a.back-link').click()
await page.waitForURL('**/cities-stores?city=3&risk=stockout_domain&page=2&scope=risk')
const riskSelect = page.locator('.filter-field').filter({ hasText: '风险域' }).locator('select')
await need(await riskSelect.inputValue() === 'stockout_domain', 'city risk filter not restored')
await need((await filteredCityList.getByText('第 2 页').count()) > 0, 'city page not restored')
ok('C1 city risk/page restore', 'risk + page=2 restored')

// 3. Risk page domain + combo mode + page -> detail -> back
await page.goto(`${BASE}/risk?domain=stockout_domain&combo=at_least&page=2`, { waitUntil: 'networkidle' })
await need(await page.getByRole('button', { name: '至少同时命中', exact: true }).evaluate((el) => el.classList.contains('active')), 'combo at_least not active')
const riskStoreList = cardByTitle(page, '风险门店')
await riskStoreList.locator('tbody tr').first().waitFor()
await riskStoreList.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
backHref = await page.locator('a.back-link').getAttribute('href')
const decodedRiskBack = decodeURIComponent(backHref ?? '')
await need(decodedRiskBack.includes('domain=stockout_domain'), 'risk domain returnTo missing', decodedRiskBack)
await need(decodedRiskBack.includes('combo=at_least'), 'risk combo returnTo missing', decodedRiskBack)
await need(decodedRiskBack.includes('page=2'), 'risk page returnTo missing', decodedRiskBack)
await need((await page.locator('a.back-link').textContent())?.includes('返回风险页') ?? false, 'risk back label')
await page.locator('a.back-link').click()
await page.waitForURL('**/risk?domain=stockout_domain&combo=at_least&page=2')
await need(await page.getByRole('button', { name: '至少同时命中', exact: true }).evaluate((el) => el.classList.contains('active')), 'combo not restored')
ok('C1 risk -> stores -> detail -> back', 'domain/combo/page restored')

// 4. SKU detail -> coverage stores -> store detail -> back
await page.goto(`${BASE}/products/4?city=8&ssort=zero_days%7Cdesc&page=1`, { waitUntil: 'networkidle' })
const storeSection = cardByTitle(page, '覆盖门店')
await storeSection.locator('tbody tr').first().waitFor()
await storeSection.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
backHref = await page.locator('a.back-link').getAttribute('href')
await need((await page.locator('a.back-link').textContent())?.includes('返回 SKU 页面') ?? false, 'sku back label')
await page.locator('a.back-link').click()
await page.waitForURL('**/products/4?city=8&ssort=zero_days%7Cdesc&page=1')
await need(params(page.url()).get('city') === '8', 'sku city not restored')
await need(params(page.url()).get('ssort') === 'zero_days|desc', 'sku ssort not restored')
await need(params(page.url()).get('page') === '1', 'sku page not restored')
await page.screenshot({ path: `${SHOTS}/c1-sku-return.png`, fullPage: true })
ok('C1 SKU -> stores -> detail -> back', 'SKU filters restored')

// 5. Direct / invalid / overlong returnTo fallback
for (const [name, url] of [
  ['direct', `${BASE}/stores/35`],
  ['external', `${BASE}/stores/35?returnTo=https%3A%2F%2Fevil.example%2Fx`],
  ['protocol-relative', `${BASE}/stores/35?returnTo=%2F%2Fevil.example%2Fx`],
  ['unknown internal', `${BASE}/stores/35?returnTo=%2Funknown`],
  ['traversal', `${BASE}/stores/35?returnTo=%2Fcities-stores%2F..%2Frisk`],
  ['encoded traversal', `${BASE}/stores/35?returnTo=%2Fcities-stores%2F%252e%252e%2Frisk`],
  ['overlong', `${BASE}/stores/35?returnTo=${encodeURIComponent('/risk?' + 'a'.repeat(600))}`]
]) {
  await page.goto(url, { waitUntil: 'networkidle' })
  const href = await page.locator('a.back-link').getAttribute('href')
  await need(href === '/cities-stores', `${name} returnTo not rejected`, href ?? '')
}
ok('C1 returnTo safety', 'external/unknown/overlong fallback to /cities-stores')

// 6. Refresh keeps valid returnTo
await page.goto(`${BASE}/stores/35?returnTo=%2Frisk%3Fdomain%3DR4`, { waitUntil: 'networkidle' })
await page.reload({ waitUntil: 'networkidle' })
backHref = await page.locator('a.back-link').getAttribute('href')
await need(backHref === '/risk?domain=R4', 'refresh lost returnTo', backHref ?? '')
ok('C1 refresh returnTo', '/risk?domain=R4 preserved')

// 7. Product list -> SKU detail -> back restores list filters
await page.goto(`${BASE}/products/list?risk=multi&page=1`, { waitUntil: 'networkidle' })
const productList = cardByTitle(page, '全部 SKU')
await productList.locator('tbody tr').first().waitFor()
await productList.locator('tbody tr').first().click()
await page.waitForURL('**/products/**?returnTo=**')
await page.locator('a.back-link').click()
await page.waitForURL('**/products/list?risk=multi**')
await need(params(page.url()).get('risk') === 'multi', 'product list risk not restored')
ok('C1 product list return', 'risk=multi restored')

await browser.close()
console.log(JSON.stringify({ results }, null, 2))
