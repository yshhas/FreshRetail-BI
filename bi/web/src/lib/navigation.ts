const ALLOWED_PREFIXES = ['/cities-stores', '/risk', '/products', '/stores']
const MAX_RETURN_TO_LENGTH = 500

/** 反复解码路径（最多 5 次），用于识别 %2e%2e / %252e%252e 等多层编码穿越变体。 */
function decodedPathForTraversal(rawPath: string): string {
  let decoded = rawPath
  for (let i = 0; i < 5; i += 1) {
    try {
      const next = decodeURIComponent(decoded)
      if (next === decoded) break
      decoded = next
    } catch {
      break
    }
  }
  return decoded
}

/** 只检查路径部分；查询参数中的 ".." 不应误伤。 */
function hasPathTraversal(value: string): boolean {
  const rawPath = value.split(/[?#]/)[0]
  if (/(^|\/)\.\.(\/|$)/.test(rawPath)) return true
  const decoded = decodedPathForTraversal(rawPath)
  // 多层编码在 5 次解码后仍残留编码点/斜杠/反斜杠时，直接拒绝，避免无限编码绕过。
  if (/%2e|%2f|%5c/i.test(decoded)) return true
  const normalized = decoded.replace(/\\/g, '/')
  return normalized.split('/').some((segment) => segment === '..')
}

/**
 * 校验并规范化站内 returnTo。
 * - 只允许白名单站内路径；
 * - 拒绝外链、协议相对地址、路径穿越与反斜杠；
 * - 自动移除嵌套的 returnTo，避免循环；
 * - 非法/缺失返回 null，由调用方回退到默认页面。
 */
export function safeReturnTo(value: string | null | undefined): string | null {
  if (!value) return null
  if (value.length > MAX_RETURN_TO_LENGTH) return null
  if (!value.startsWith('/') || value.startsWith('//')) return null
  if (value.includes('\\')) return null
  if (hasPathTraversal(value)) return null

  let url: URL
  try {
    url = new URL(value, 'http://internal.local')
  } catch {
    return null
  }
  if (url.origin !== 'http://internal.local') return null
  if (url.username || url.password) return null
  if (url.pathname.includes('..')) return null

  const allowed = ALLOWED_PREFIXES.some(
    (prefix) => url.pathname === prefix || url.pathname.startsWith(`${prefix}/`)
  )
  if (!allowed) return null

  url.searchParams.delete('returnTo')
  const query = url.searchParams.toString()
  return query ? `${url.pathname}?${query}` : url.pathname
}

/** 用当前页面的 pathname + search 生成来源地址，并移除自身 returnTo。 */
export function buildReturnTo(pathname: string, search: string): string {
  const params = new URLSearchParams(search)
  params.delete('returnTo')
  const query = params.toString()
  return query ? `${pathname}?${query}` : pathname
}

/** 生成带 returnTo 的详情链接；returnTo 不存在时不加多余参数。 */
export function detailHref(path: string, returnTo: string | null | undefined): string {
  if (!returnTo) return path
  const params = new URLSearchParams()
  params.set('returnTo', returnTo)
  return `${path}?${params.toString()}`
}

export function returnLabel(value: string | null | undefined): string {
  if (value?.startsWith('/risk')) return '← 返回风险页'
  if (value?.startsWith('/products')) return '← 返回 SKU 页面'
  if (value?.startsWith('/stores')) return '← 返回门店详情'
  return '← 返回门店列表'
}
