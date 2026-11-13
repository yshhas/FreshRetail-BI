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
function search(url) { return new URL(url).searchParams }
async function need(cond, label, extra = '') {
  if (!cond) throw new Error(`${label} ${extra}`)
}
async function selectValue(page, label) {
  return page.locator('.filter-field').filter({ hasText: label }).locator('select').inputValue()
}

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
page.on('pageerror', (e) => { throw new Error(`pageerror: ${e.message}`) })

// 1. multi-level: city -> store -> SKU -> store -> city
await page.goto(`${BASE}/cities-stores?city=3&risk=stockout_domain&page=2&scope=risk`, { waitUntil: 'networkidle' })
const cityList = cardByTitle(page, '门店列表')
await cityList.locator('tbody tr').first().waitFor()
await cityList.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
const storeUrl = page.url()

const skuCard = cardByTitle(page, '该店 SKU（观察期内）')
await skuCard.locator('tbody tr').first().waitFor()
await skuCard.locator('tbody tr').first().click()
await page.waitForURL('**/products/**?returnTo=**')
await page.locator('a.back-link').click()
await page.waitForURL('**/stores/**')
await need(page.url() === storeUrl, 'SKU back should restore store URL', page.url())
await need(search(page.url()).has('returnTo'), 'store URL should keep returnTo')
ok('C4 multi-level SKU back', 'store URL with returnTo restored')

await page.locator('a.back-link').click()
await page.waitForURL('**/cities-stores?city=3**')
await cityList.locator('tbody tr').first().waitFor()
await page.waitForFunction(
  () => {
    const valueOf = (label) => {
      const field = [...document.querySelectorAll('.filter-field')].find((node) =>
        node.textContent?.includes(label)
      )
      return field?.querySelector('select')?.value
    }
    const card = [...document.querySelectorAll('.card')].find((node) =>
      [...node.querySelectorAll('h1,h2,h3,h4')].some(
        (h) => h.textContent?.trim() === '门店列表'
      )
    )
    const pager = card?.querySelector('.pager')?.textContent ?? ''
    return (
      valueOf('城市') === '3' &&
      valueOf('风险域') === 'stockout_domain' &&
      valueOf('样本') === 'risk' &&
      pager.includes('第 2 页')
    )
  },
  { timeout: 15000 }
)
await need((await selectValue(page, '城市')) === '3', 'city restored')
await need((await selectValue(page, '风险域')) === 'stockout_domain', 'risk restored')
await need((await selectValue(page, '样本')) === 'risk', 'scope restored')
await need(((await cityList.locator('.pager').textContent()) ?? '').includes('第 2 页'), 'page restored')
ok('C4 multi-level city back', 'city/risk/scope/page restored')

// 2. product risk -> SKU -> back
await page.goto(`${BASE}/products/risk?risk=multi&page=1`, { waitUntil: 'networkidle' })
const productRisk = cardByTitle(page, '风险 SKU 列表')
await productRisk.locator('tbody tr').first().waitFor()
await productRisk.locator('tbody tr').first().click()
await page.waitForURL('**/products/**?returnTo=**')
await need(((await page.locator('a.back-link').textContent()) ?? '').includes('SKU 页面'), 'product risk back label')
await page.locator('a.back-link').click()
await page.waitForURL('**/products/risk?risk=multi**')
await productRisk.locator('tbody tr').first().waitFor()
await need(((await productRisk.locator('.subtitle').textContent()) ?? '').includes('当前筛选 35 个 SKU'), 'product risk count restored')
ok('C4 product risk returnTo', 'risk=multi / 35 restored')

// 3. manual mode conflict: domains wins, no API error
await page.goto(`${BASE}/risk?exact_combo=%E7%BC%BA%E8%B4%A7%2B%E9%AB%98%E9%9B%B6%E9%94%80&domains=stockout_domain%2CR4`, { waitUntil: 'networkidle' })
await page.getByText('URL 同时包含精确组合与至少组合参数').waitFor()
const riskStores = cardByTitle(page, '风险门店')
await riskStores.locator('.subtitle').filter({ hasText: '当前筛选 56 家' }).waitFor()
await need(!(await page.getByText('数据加载失败').count()), 'conflict should not error')
ok('C4 mode conflict', 'domains priority, 56 stores')

// 4. active row highlight
await page.goto(`${BASE}/risk?domains=stockout_domain%2CR4&combo=at_least`, { waitUntil: 'networkidle' })
const comboCard = cardByTitle(page, '风险组合')
await comboCard.locator('tr.active-row').first().waitFor()
await need((await comboCard.locator('tr.active-row').count()) === 1, 'one active at_least row')
await need((await comboCard.locator('tr.active-row').textContent() ?? '').includes('缺货+高零销'), 'active row is selected pair')
ok('C4 active row', 'at_least selected row highlighted')

await page.goto(`${BASE}/risk?exact_combo=%E7%BC%BA%E8%B4%A7%2B%E9%AB%98%E9%9B%B6%E9%94%80`, { waitUntil: 'networkidle' })
await comboCard.locator('tr.active-row').first().waitFor()
await need((await comboCard.locator('tr.active-row').count()) === 1, 'one active exact row')
ok('C4 active exact row', 'exact selected row highlighted')

// 5. low-SKU notice appears once
await page.goto(`${BASE}/stores/842`, { waitUntil: 'networkidle' })
const lowNotices = page.locator('.notice.warn').filter({ hasText: 'SKU<10' })
await lowNotices.first().waitFor()
await need((await lowNotices.count()) === 1, 'low SKU notice should appear once')
ok('C4 low-SKU notice', 'single notice')

await page.screenshot({ path: `${SHOTS}/c4-risk-mode.png`, fullPage: true })
await browser.close()
console.log(JSON.stringify({ results }, null, 2))
