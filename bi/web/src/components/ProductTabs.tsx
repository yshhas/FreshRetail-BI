import { NavLink } from 'react-router-dom'

const TABS = [
  { to: '/products', label: '商品总览', end: true },
  { to: '/products/list', label: 'SKU 列表', end: true },
  { to: '/products/risk', label: '商品风险', end: true },
  { to: '/products/categories', label: 'L1 类别结构', end: true }
]

export function ProductTabs() {
  return (
    <nav className="subnav">
      {TABS.map((t) => (
        <NavLink key={t.to} to={t.to} end={t.end}
          className={({ isActive }) => isActive ? 'active' : ''}>
          {t.label}
        </NavLink>
      ))}
    </nav>
  )
}
