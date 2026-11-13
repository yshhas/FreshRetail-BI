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

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
page.on('pageerror', (e) => { throw new Error(`pageerror: ${e.message}`) })

// 1. at_least row filters stores
await page.goto(`${BASE}/risk`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: '经营风险' }).waitFor()
await page.getByRole('button', { name: '至少同时命中', exact: true }).click()
const comboCard = cardByTitle(page, '风险组合')
await comboCard.getByRole('cell', { name: '缺货+高零销', exact: true }).click()
await page.waitForURL('**domains=**')
const domains = search(page.url()).get('domains')
await need(domains === 'stockout_domain,R4', 'domains URL', domains ?? '')
await page.getByText('当前至少组合：').waitFor()
const riskStores = cardByTitle(page, '风险门店')
await riskStores.locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 56 家'), 'at_least count 56')
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('至少组合：缺货 + 高零销'), 'at_least label')
await page.screenshot({ path: `${SHOTS}/c3-at-least.png`, fullPage: true })
ok('C3 at_least filter', '缺货+高零销 -> 56 stores')

// 2. return state from store detail
await riskStores.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
await need(((await page.locator('a.back-link').textContent()) ?? '').includes('返回风险页'), 'back label')
await page.locator('a.back-link').click()
await page.waitForURL('**domains=**')
await riskStores.locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 56 家'), 'returned count')
ok('C3 at_least return', '56 stores restored')

// 3. refresh keeps state
await page.reload({ waitUntil: 'networkidle' })
await page.getByText('当前至少组合：').waitFor()
await riskStores.locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 56 家'), 'refresh count')
ok('C3 at_least refresh', '56 stores after reload')

// 4. cancel
await page.getByRole('button', { name: '取消至少组合' }).click()
await page.waitForFunction(() => !new URLSearchParams(location.search).has('domains'))
await riskStores.locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 888 家'), 'cancel count 888')
ok('C3 cancel at_least', 'back to 888')

// 5. exact vs at_least distinction
await page.getByRole('button', { name: '恰好命中', exact: true }).click()
await comboCard.getByRole('cell', { name: '缺货+高零销', exact: true }).click()
await page.waitForURL('**exact_combo=**')
await riskStores.locator('.subtitle').filter({ hasText: '当前筛选 38 家' }).waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 38 家'), 'exact count 38')
await need(!search(page.url()).has('domains'), 'exact should not carry domains')
await page.getByRole('button', { name: '至少同时命中', exact: true }).click()
await page.waitForFunction(() => !new URLSearchParams(location.search).has('exact_combo'))
await riskStores.locator('.subtitle').filter({ hasText: '当前筛选 888 家' }).waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 888 家'), 'switch clears exact')
ok('C3 exact/at_least distinction', '38 exact vs 56 at_least')

// 6. exact still works after C-3
await page.getByRole('button', { name: '恰好命中', exact: true }).click()
await comboCard.getByRole('cell', { name: '缺货+高零销', exact: true }).click()
await page.waitForURL('**exact_combo=**')
await riskStores.locator('.subtitle').filter({ hasText: '当前筛选 38 家' }).waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 38 家'), 'exact after C3')
ok('C3 exact regression', '38 stores')

await browser.close()
console.log(JSON.stringify({ results }, null, 2))
