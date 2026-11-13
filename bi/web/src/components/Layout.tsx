import { NavLink, Outlet } from 'react-router-dom'

const links = [
  { to: '/overview', label: '经营总览' },
  { to: '/cities-stores', label: '城市与门店' },
  { to: '/products', label: '商品 BI' },
  { to: '/risk', label: '经营风险' }
]

export function Layout() {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">BI</span>
          <div>
            <strong>零售经营 BI</strong>
            <span>P1–P4 冻结指标 · 只读</span>
          </div>
        </div>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} className={({ isActive }) => isActive ? 'active' : ''}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="top-note">KPI 固定 90 天 · 归一化销量指数</div>
      </header>
      <div className="scope-banner">
        当前 KPI 为完整 90 天观察期（2024-03-28 至 2024-06-25）统计值；日期筛选仅影响趋势图的显示窗口，
        不会重算 KPI。销量为归一化销量指数，不是销售额或 GMV。
      </div>
      <main><Outlet /></main>
      <footer>
        数据版本 p1-p4-freeze-2026-11-08 · 只读展示 · 小样本 n&lt;20 已抑制
      </footer>
    </div>
  )
}
