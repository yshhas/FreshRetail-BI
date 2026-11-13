﻿﻿﻿﻿﻿﻿﻿import { chromium } from 'playwright-core'
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

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
page.on('pageerror', (e) => { throw new Error(`pageerror: ${e.message}`) })

// 1. Overview
await page.goto(`${BASE}/overview`, { waitUntil: 'networkidle' })
await page.getByText('898').first().waitFor()
await assertNoError()
if (await page.locator('canvas').count() < 3) throw new Error('overview charts missing')
await page.screenshot({ path: `${SHOTS}/e2e-overview.png`, fullPage: true })
ok('overview', 'KPI=898, charts rendered')

// 2. City table click -> city filter in URL
await page.getByRole('link', { name: '城市与门店' }).click()
await page.waitForURL('**/cities-stores')
await page.locator('tbody tr').filter({ hasText: 'C03' }).first().click()
await page.waitForURL('**/cities-stores?city=3**')
await page.getByRole('heading', { name: '门店列表' }).waitFor()
await page.getByText('全样本 18 城').first().waitFor()
await page.getByText('筛选结果').first().waitFor()
await page.locator('.footnote').filter({ hasText: '主样本 888' }).first().waitFor()
await page.waitForTimeout(800)
await page.screenshot({ path: `${SHOTS}/e2e-city-filter.png`, fullPage: true })
ok('city drill filter', 'URL city=3')

// 3. Store detail via direct route
await page.goto(`${BASE}/stores/35`, { waitUntil: 'networkidle' })
await page.getByText('门店 S0035').waitFor()
await page.getByRole('heading', { name: '风险标记' }).waitFor()
await assertNoError()
ok('store detail', 'S0035 rendered')

// 4. Risk domain click + combination toggle
await page.goto(`${BASE}/risk`, { waitUntil: 'networkidle' })
await page.locator('.domain-card').filter({ hasText: '缺货域（R1 或 R2）' }).click()
await page.waitForURL('**domain=stockout_domain**')
await page.getByRole('button', { name: '至少同时命中' }).click()
await page.waitForURL('**combo=at_least**')
await page.getByText('至少同时命中', { exact: true }).first().waitFor()
await page.getByText('全样本 888，不受筛选').waitFor()
await page.getByText('C(5,2)=10').waitFor()
await page.waitForTimeout(800)
await page.screenshot({ path: `${SHOTS}/e2e-risk-filter.png`, fullPage: true })
ok('risk filter', 'domain + at_least')

// 5. Low-SKU store guard
await page.goto(`${BASE}/stores/842`, { waitUntil: 'networkidle' })
await page.getByText('SKU<10', { exact: false }).first().waitFor()
await page.getByText('不参与风险诊断', { exact: false }).first().waitFor()
await page.screenshot({ path: `${SHOTS}/e2e-low-sku.png`, fullPage: true })
ok('low-SKU guard', 'S0842 no diagnosis')

// 6. Empty state: R7 structure flag in Q2 has zero stores
const q2 = encodeURIComponent('Q2 高规模·相对低效率')
await page.goto(`${BASE}/risk?domain=R7&quadrant=${q2}`, { waitUntil: 'networkidle' })
await page.getByText('当前筛选 0 家').waitFor()
await page.getByText('暂无匹配记录').first().waitFor()
await page.screenshot({ path: `${SHOTS}/e2e-empty.png`, fullPage: true })
ok('empty state', 'R7 + Q2 = 0 stores')

// 7. Error state: non-existent store
await page.goto(`${BASE}/stores/999999`, { waitUntil: 'networkidle' })
await page.getByText('数据加载失败').waitFor()
await page.screenshot({ path: `${SHOTS}/e2e-error.png`, fullPage: true })
ok('error state', '404 store')

// 8. Filter change resets pagination
await page.goto(`${BASE}/cities-stores?city=3&page=2`, { waitUntil: 'networkidle' })
await page.getByText('第 2 页').waitFor()
await page.locator('.filter-field').filter({ hasText: '风险域' }).locator('select').selectOption('R3')
await page.waitForURL((u) => !u.search.includes('page='))
await page.getByText('第 1 页').waitFor()
ok('filter resets page', 'page param removed on filter change')

// 9. Loading state: delay KPI response and capture skeleton
await page.route('**/api/v1/overview/kpis', async (route) => {
  await new Promise((r) => setTimeout(r, 1200))
  await route.continue()
})
await page.goto(`${BASE}/overview`, { waitUntil: 'domcontentloaded' })
await page.getByText('加载中…').first().waitFor()
await page.screenshot({ path: `${SHOTS}/e2e-loading.png`, fullPage: false })
await page.unroute('**/api/v1/overview/kpis')
ok('loading state', 'delayed KPI response')

async function assertNoError() {
  if (await page.getByText('数据加载失败').count()) throw new Error('visible data error')
}

await browser.close()
console.log(JSON.stringify({ results }, null, 2))
