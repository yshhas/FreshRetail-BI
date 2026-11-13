import { chromium } from 'playwright-core'
import { writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { executablePath } from './browser.mjs'
const BASE = 'http://127.0.0.1:4173'
const pages = [
  ['overview', '/overview', '898'],
  ['cities-stores', '/cities-stores', '城市经营对比'],
  ['risk', '/risk', '经营风险'],
  ['store-detail', '/stores/35', '门店 S0035'],
]

function median(xs) {
  const a = [...xs].sort((x, y) => x - y)
  return a[Math.floor(a.length / 2)]
}

const browser = await chromium.launch({ executablePath, headless: true })
const out = { base: BASE, runs: 3, pages: {} }
for (const [name, path, waitText] of pages) {
  const values = []
  for (let i = 0; i < 3; i++) {
    const context = await browser.newContext({ viewport: { width: 1600, height: 1200 } })
    const page = await context.newPage()
    const t0 = Date.now()
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' })
    await page.getByText(waitText).first().waitFor()
    const wall = Date.now() - t0
    const nav = await page.evaluate(() => {
      const n = performance.getEntriesByType('navigation')[0]
      const resources = performance.getEntriesByType('resource')
        .filter((r) => r.name.includes('/api/v1/'))
        .map((r) => r.duration)
      return {
        domContentLoaded: n?.domContentLoadedEventEnd ?? null,
        loadEvent: n?.loadEventEnd ?? null,
        apiMax: resources.length ? Math.max(...resources) : null,
        apiCount: resources.length,
      }
    })
    values.push({ wall, ...nav })
    await context.close()
  }
  out.pages[name] = {
    wall_ms_median: median(values.map((x) => x.wall)),
    load_ms_median: median(values.map((x) => x.loadEvent ?? 0)),
    api_max_ms_median: median(values.map((x) => x.apiMax ?? 0)),
    api_count: values[0].apiCount,
  }
}
const target = resolve('../benchmarks/frontend_perf.json')
writeFileSync(target, JSON.stringify(out, null, 2), 'utf8')
console.log(JSON.stringify(out, null, 2))
await browser.close()
