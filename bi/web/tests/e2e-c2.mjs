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
async function waitText(page, text) {
  await page.getByText(text, { exact: false }).first().waitFor()
}
async function selectValue(page, label) {
  return page.locator('.filter-field').filter({ hasText: label }).locator('select').inputValue()
}

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1600, height: 1200 } })
page.on('pageerror', (e) => { throw new Error(`pageerror: ${e.message}`) })

// 1. C-2-A: exact combo row -> filtered risk stores
await page.goto(`${BASE}/risk`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: '经营风险' }).waitFor()
const comboCard = cardByTitle(page, '风险组合')
await comboCard.getByRole('cell', { name: '缺货+高零销', exact: true }).click()
await page.waitForURL('**exact_combo=**')
const combo = search(page.url()).get('exact_combo')
await need(combo === '缺货+高零销', 'exact combo URL', combo ?? '')
await page.getByText('当前精确组合：').waitFor()
const riskStores = cardByTitle(page, '风险门店')
await riskStores.locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 38 家'), 'exact combo store count')
await page.screenshot({ path: `${SHOTS}/c2-exact-combo.png`, fullPage: true })
ok('C2-A exact combo', '缺货+高零销 -> 38 stores')

// exact combo + C-1 return state
await riskStores.locator('tbody tr').first().click()
await page.waitForURL('**/stores/**?returnTo=**')
await need(((await page.locator('a.back-link').textContent()) ?? '').includes('返回风险页'), 'exact combo back label')
await page.locator('a.back-link').click()
await page.waitForURL('**exact_combo=**')
await riskStores.locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 38 家'), 'exact combo restored')
ok('C2-A exact combo return', '38 stores restored after detail')

// clear selected combo
await page.getByRole('button', { name: '取消精确组合' }).click()
await page.waitForFunction(() => !new URLSearchParams(location.search).has('exact_combo'))
await page.waitForFunction(() => document.querySelector('.card .subtitle') !== null)
await page.locator('.card').filter({ hasText: '风险门店' }).locator('tbody tr').first().waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 888 家'), 'combo clear store count')
ok('C2-A clear combo', 'back to 888 stores')

// at_least row filters stores (C-3 behavior, C-2 regression)
await page.getByRole('button', { name: '至少同时命中', exact: true }).click()
await comboCard.getByRole('cell', { name: '缺货+高零销', exact: true }).click()
await page.waitForURL('**domains=**')
await page.getByText('当前至少组合：').waitFor()
await riskStores.locator('.subtitle').filter({ hasText: '当前筛选 56 家' }).waitFor()
await need(((await riskStores.locator('.subtitle').textContent()) ?? '').includes('当前筛选 56 家'), 'at_least count 56')
ok('C2-A at_least filter', '56 stores after C-3')

await page.getByRole('button', { name: '取消至少组合' }).click()
await page.waitForFunction(() => !new URLSearchParams(location.search).has('domains'))
await riskStores.locator('.subtitle').filter({ hasText: '当前筛选 888 家' }).waitFor()

// 2. C-2-B: store -> SKU list
await page.goto(`${BASE}/stores/35`, { waitUntil: 'networkidle' })
await page.getByRole('heading', { name: '门店 S0035' }).waitFor()
const skuCard = cardByTitle(page, '该店 SKU（观察期内）')
await skuCard.locator('tbody tr').first().waitFor()
await need(((await skuCard.locator('.subtitle').textContent()) ?? '').includes('共 69 个'), 'SKU total 69')
await need((await skuCard.locator('tbody tr').count()) === 50, 'SKU first page rows')
await page.screenshot({ path: `${SHOTS}/c2-store-skus.png`, fullPage: true })
ok('C2-B store SKUs', '69 SKUs, 50 rows')

// flagged filter
await skuCard.locator('.filter-field').filter({ hasText: 'SKU 范围' }).locator('select').selectOption('flagged')
await page.waitForURL('**skscope=flagged**')
await page.waitForFunction(() => {
  const card = Array.from(document.querySelectorAll('.card')).find((el) => el.textContent?.includes('该店 SKU（观察期内）'))
  return (card?.querySelector('.subtitle')?.textContent ?? '').includes('共 6 个')
})
await need((await skuCard.locator('tbody tr').count()) === 6, 'flagged SKU rows')
ok('C2-B flagged filter', '6 risk SKUs')

// SKU row -> detail -> back to store
await skuCard.locator('tbody tr').first().click()
await page.waitForURL('**/products/**?returnTo=**')
await need(((await page.locator('a.back-link').textContent()) ?? '').includes('返回门店详情'), 'SKU back label')
await page.locator('a.back-link').click()
await page.waitForURL('**/stores/35?skscope=flagged**')
await need((await selectValue(page, 'SKU 范围')) === 'flagged', 'store SKU filter restored')
ok('C2-B SKU drill + back', 'return to store with skscope=flagged')

// pagination on all SKUs
await page.locator('.filter-field').filter({ hasText: 'SKU 范围' }).locator('select').selectOption({ label: '全部 SKU' })
await page.waitForFunction(() => !new URLSearchParams(location.search).has('skscope'))
const pager = cardByTitle(page, '该店 SKU（观察期内）').locator('.pager')
await pager.getByRole('button', { name: '下一页' }).click()
await page.waitForURL('**page=2**')
const page2Rows = cardByTitle(page, '该店 SKU（观察期内）').locator('tbody tr')
await page.waitForFunction(
  (title) => {
    const card = [...document.querySelectorAll('.card')].find((node) =>
      [...node.querySelectorAll('h1,h2,h3,h4')].some((h) => h.textContent?.trim() === title)
    )
    return Boolean(card) && card.querySelectorAll('tbody tr').length === 19
  },
  '该店 SKU（观察期内）',
  { timeout: 15000 }
)
await need((await page2Rows.count()) === 19, 'SKU page 2 rows')
ok('C2-B SKU pagination', 'page 2 has 19 rows')

// 3. Low-SKU store warning and no false risk flags
await page.goto(`${BASE}/stores/842`, { waitUntil: 'networkidle' })
const lowCard = cardByTitle(page, '该店 SKU（观察期内）')
await lowCard.locator('tbody tr').first().waitFor()
await need((await lowCard.locator('tbody tr').count()) === 9, 'store 842 SKU rows')
await page.getByText('SKU<10').first().waitFor()
ok('C2-B low-SKU store', '9 SKUs + base-profile warning')

await browser.close()
console.log(JSON.stringify({ results }, null, 2))
