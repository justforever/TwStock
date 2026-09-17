import { Routes, Route, Link } from 'react-router-dom'
import SearchPage from './pages/SearchPage'
import StockPage from './pages/StockPage'

export default function App() {
  return (
    <>
      <header>
        <Link to="/">TwStock</Link>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<SearchPage />} />
          <Route path="/stock/:stockId" element={<StockPage />} />
          <Route path="*" element={<p>找不到頁面</p>} />
        </Routes>
      </main>
    </>
  )
}
