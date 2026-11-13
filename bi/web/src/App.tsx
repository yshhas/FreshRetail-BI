import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { OverviewPage } from './pages/OverviewPage'
import { CityStorePage } from './pages/CityStorePage'
import { RiskPage } from './pages/RiskPage'
import { StoreDetailPage } from './pages/StoreDetailPage'
import { ProductOverviewPage } from './pages/ProductOverviewPage'
import { ProductListPage } from './pages/ProductListPage'
import { ProductRiskPage } from './pages/ProductRiskPage'
import { ProductCategoryPage } from './pages/ProductCategoryPage'
import { ProductDetailPage } from './pages/ProductDetailPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Navigate to="/overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="cities-stores" element={<CityStorePage />} />
          <Route path="products" element={<ProductOverviewPage />} />
          <Route path="products/list" element={<ProductListPage />} />
          <Route path="products/risk" element={<ProductRiskPage />} />
          <Route path="products/categories" element={<ProductCategoryPage />} />
          <Route path="products/:productId" element={<ProductDetailPage />} />
          <Route path="risk" element={<RiskPage />} />
          <Route path="stores/:storeId" element={<StoreDetailPage />} />
          <Route path="*" element={<div className="page"><div className="empty-state">页面不存在</div></div>} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
