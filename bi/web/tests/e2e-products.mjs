import { chromium } from 'playwright-core'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { executablePath } from './browser.mjs'
const BASE = 'http://127.0.0.1:5173'
const SHOTS = resolve('../screenshots')
mkdirSync(SHOTS, { recursive: true })

const results = []
function ok(name, detail = '') {
  results.push({ name, status: 'PASS', detail })
  console.log(`PASS ${name} ${detail}`)
}
async function needText(locator, text, label) {
  await locator.waitFor()
  const content = (await locator.textContent()) ?? ''
  if (!content.includes(text)) throw new Error(`${label}: expected "${text}", got "${content.slice(0, 160)}"`)
}
async function needRows(page, count, label) {
  const rows = await page.locator('.table-wrap tbody tr').count()
  if (rows !== count) throw new Error(`${label}: expected ${count} rows, got ${rows}`)
}

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
page.on('pageerror', (e) => { throw new Error(`pageerror: ${e.message}`) })

// 1. Product overview
await page.goto(`${BASE}/products`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: '商品总览' }).waitFor()
await needText(page.locator('.kpi-card').filter({ hasText: 'SKU 总数' }), '865', 'overview SKU total')
await needText(page.locator('.kpi-card').filter({ hasText: /^风险 SKU/ }), '117', 'overview risk sku')
await needText(page.locator('.kpi-card').filter({ hasText: '多风险 SKU' }), '35', 'overview multi risk')
await needText(page.locator('.kpi-card').filter({ hasText: 'L1 类别' }), '32', 'overview categories')
await needText(page.getByText('高零销旗标为 43 个'), '43', 'overview high_zero note')
if (await page.locator('canvas').count() < 4) throw new Error('product overview charts missing')
await page.waitForTimeout(600)
await page.screenshot({ path: `${SHOTS}/bi2-product-overview.png`, fullPage: true })
ok('product overview', '865 / 117 / 35 / 32 / 4 charts')

// 2. Product list: 865 + pagination
await page.getByRole('link', { name: 'SKU 列表' }).click()
await page.waitForURL('**/products/list')
await page.getByRole('heading', { name: 'SKU 列表' }).waitFor()
await needText(page.getByText('共 865 个 SKU'), '865', 'list total')
await needText(page.getByText('scope=all · 全部商品'), 'scope=all', 'list scope')
await needRows(page, 50, 'list page 1')
await page.waitForTimeout(400)
await page.screenshot({ path: `${SHOTS}/bi2-product-list.png`, fullPage: true })
ok('product list', '865 SKU, 50 rows per page, scope=all')

// 3. Search -> 1 row, then open detail
await page.getByPlaceholder('如 P0005').fill('P0005')
await page.getByRole('button', { name: '查询' }).click()
await page.waitForURL('**q=P0005**')
await page.locator('.table-wrap tbody tr').filter({ hasText: 'P0005' }).first().waitFor()
await needRows(page, 1, 'search P0005')
await needText(page.locator('.table-wrap tbody tr').first(), 'P0005', 'search result')
await page.locator('.table-wrap tbody tr').first().click()
await page.waitForURL('**/products/4**')
ok('product search + drill', 'P0005 -> /products/4')

// 3b. Sort by cumulative index desc -> P0268 first
await page.goto(`${BASE}/products/list?sort=total_index&order=desc`, { waitUntil: 'networkidle' })
await page.locator('.table-wrap tbody tr').first().waitFor()
await needText(page.locator('.table-wrap tbody tr').first(), 'P0268', 'sort top row')
ok('product sort', 'total_index desc -> P0268')

// 4. Detail: flagged SKU
await page.goto(`${BASE}/products/4`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: 'P0005' }).waitFor()
await needText(page.locator('.profile-grid > div').filter({ hasText: '覆盖门店数' }), '783', 'detail coverage')
await needText(page.getByRole('heading', { name: '同店共同出现（展示前 20）' }), '同店共同出现', 'detail pairs heading')
await needText(page.locator('.table-wrap').last(), 'P0601', 'detail pair top')
await page.waitForTimeout(500)
await page.screenshot({ path: `${SHOTS}/bi2-product-detail.png`, fullPage: true })
ok('product detail (flagged)', 'P0005 coverage=783, pair P0601')

const flaggedPairSection = page.locator('.card').filter({ hasText: '同店共同出现（展示前 20）' })
await needText(flaggedPairSection, '共 110 对', 'pair total')
await needText(flaggedPairSection, '达到 20 店门槛 24 对', 'pair eligible')
await needText(flaggedPairSection, '低于门槛 86 对', 'pair below threshold')
ok('pair threshold summary', '110 total / 24 eligible / 86 below / 20 shown')

// 5. Detail: non-flagged SKU
await page.goto(`${BASE}/products/0`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: 'P0001' }).waitFor()
await needText(page.locator('.badge').filter({ hasText: '无风险旗标' }), '无风险旗标', 'non flagged badge')
await needText(page.getByText('未命中 P2 风险旗标').first(), '未命中', 'non flagged notice')
await needText(page.locator('.card').filter({ hasText: '同店共同出现（展示前 20）' }), '无同店共现记录', 'zero pair empty')
await page.screenshot({ path: `${SHOTS}/bi2-product-detail-nonflagged.png`, fullPage: true })
ok('product detail (non-flagged)', 'P0001 no flags, zero pairs')

// 6. Detail: n<20 suppression
await page.goto(`${BASE}/products/186`, { waitUntil: 'networkidle' })
await page.getByText('当前覆盖门店 n=1 < 20').waitFor()
await page.screenshot({ path: `${SHOTS}/bi2-product-detail-suppressed.png`, fullPage: true })
ok('product detail suppression', 'single-store SKU shows n<20 notice')

// 6b. Detail: filter narrows coverage below 20
await page.goto(`${BASE}/products/4?city=8`, { waitUntil: 'networkidle' })
await page.getByText('当前覆盖门店 n=3 < 20').waitFor()
ok('product filtered suppression', 'city filter n=3 shows notice')

// 6c. Detail: all co-occurrence pairs below the 20-store display threshold
await page.goto(`${BASE}/products/51`, { waitUntil: 'networkidle' })
const lowPairSection = page.locator('.card').filter({ hasText: '同店共同出现（展示前 20）' })
await needText(lowPairSection, '共 5 对共现记录，均低于 20 店展示门槛', 'all-low pair empty')
await needText(lowPairSection, '低于门槛 5 对', 'all-low pair count')
ok('pair all below threshold', '5 pairs below threshold, none hidden as absent')

// 6d. Detail: missing pair metadata must not be estimated
await page.route('**/api/v1/products/4/pairs**', async (route) => {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      data: [],
      meta: {
        period: '2024-03-28/2024-06-25',
        data_version: 'p1-p4-freeze-2026-11-08',
        sample_scope: 'all',
        suppressed: false,
        definitions: ['P4C-PAIRS']
      },
      warnings: []
    })
  })
})
await page.goto(`${BASE}/products/4`, { waitUntil: 'networkidle' })
await page.getByText('共现总数元数据不可用').waitFor()
await page.unroute('**/api/v1/products/4/pairs**')
ok('pair metadata missing', 'shows unavailable, no estimation')

// 7. Product risk page
await page.goto(`${BASE}/products/risk`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: '商品风险' }).waitFor()
await needText(page.locator('.kpi-card').filter({ hasText: /^风险 SKU/ }), '117', 'risk total')
await needText(page.locator('.kpi-card').filter({ hasText: '多风险 SKU' }), '35', 'risk multi')
await needText(page.locator('.kpi-card').filter({ hasText: '高零销' }), '43', 'risk high_zero')
await needText(page.getByText('描述性统计'), '65', 'risk 65 note')
await needRows(page, 50, 'risk page 1')
await page.waitForTimeout(500)
await page.screenshot({ path: `${SHOTS}/bi2-product-risk.png`, fullPage: true })
ok('product risk page', '117 / 35 / high_zero 43 / 65 note')

// 8. Category page
await page.goto(`${BASE}/products/categories`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: 'L1 类别结构' }).waitFor()
await needRows(page, 32, 'category table')
await needText(page.locator('.kpi-card').filter({ hasText: 'L1 类别数' }), '32', 'category count')
await page.waitForTimeout(400)
await page.screenshot({ path: `${SHOTS}/bi2-product-categories.png`, fullPage: true })
ok('product categories', '32 rows')

// 9. Filter change resets page
await page.goto(`${BASE}/products/list?risk=multi&page=2`, { waitUntil: 'networkidle' })
await page.getByText('第 2 页').waitFor()
await page.locator('.filter-field').filter({ hasText: '风险筛选' }).locator('select').selectOption('high_cv')
await page.waitForURL((u) => !u.search.includes('page='))
await page.locator('.pager').getByText('第 1 页').waitFor()
ok('product filter resets page', 'page param removed')

// 10. Empty search result
await page.goto(`${BASE}/products/list?q=NOT-EXIST`, { waitUntil: 'networkidle' })
await page.getByText('暂无匹配记录').waitFor()
ok('product empty state', 'no matching SKU')

// 11. Invalid SKU -> friendly error
await page.goto(`${BASE}/products/999999`, { waitUntil: 'networkidle' })
await page.getByText('商品不存在').first().waitFor()
await page.screenshot({ path: `${SHOTS}/bi2-product-error.png`, fullPage: true })
ok('product error state', '404 -> 商品不存在')

// 12. Loading state on overview
await page.route('**/api/v1/products/overview', async (route) => {
  await new Promise((r) => setTimeout(r, 1000))
  await route.continue()
})
await page.goto(`${BASE}/products`, { waitUntil: 'domcontentloaded' })
await page.getByText('加载中…').first().waitFor()
await page.screenshot({ path: `${SHOTS}/bi2-product-loading.png`, fullPage: false })
await page.unroute('**/api/v1/products/overview')
ok('product loading state', 'delayed overview response')

await browser.close()
console.log(JSON.stringify({ results }, null, 2))
