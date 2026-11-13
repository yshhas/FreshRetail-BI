import { existsSync } from 'node:fs'

// 优先使用 CHROME_PATH；否则按常见安装位置查找。
const candidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
  '/usr/bin/google-chrome-stable',
  '/usr/bin/chromium',
  '/usr/bin/chromium-browser',
].filter(Boolean)

export const executablePath = candidates.find((candidate) => existsSync(candidate))

if (!executablePath) {
  throw new Error(
    '未找到 Chrome/Chromium。请安装 Chrome，或设置 CHROME_PATH 指向浏览器可执行文件。'
  )
}
