import { Link, useLocation, useNavigate } from 'react-router-dom'
import { returnLabel } from '../lib/navigation'

/**
 * 返回链接：有 returnTo 且存在应用内历史时优先浏览器后退，
 * 以保留多级返回链路（例如 城市 → 门店 → SKU）。刷新/直接打开时回退到 returnTo。
 */
export function BackLink({ returnTo, fallback }: { returnTo: string | null; fallback: string }) {
  const nav = useNavigate()
  const location = useLocation()
  const useHistory = Boolean(returnTo) && location.key !== 'default'

  return (
    <Link
      to={returnTo ?? fallback}
      className="back-link"
      onClick={(event) => {
        if (!useHistory) return
        event.preventDefault()
        nav(-1)
      }}
    >
      {returnLabel(returnTo)}
    </Link>
  )
}
