import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import CandleChart from '../components/CandleChart'
import {
  fetchStock,
  fetchPrices,
  marketLabel,
  type StockDetail,
  type PriceBar,
} from '../api'

type DateRange = '3M' | '6M' | '1Y' | '3Y' | '5Y'

const RANGE_DAYS: Record<DateRange, number> = {
  '3M': 90,
  '6M': 180,
  '1Y': 365,
  '3Y': 1095,
  '5Y': 1825,
}

export default function StockPage() {
  const { stockId } = useParams<{ stockId: string }>()
  const [stock, setStock] = useState<StockDetail | null>(null)
  const [prices, setPrices] = useState<PriceBar[]>([])
  const [range, setRange] = useState<DateRange>(() => {
    const saved = localStorage.getItem('twstock.stockPage.range')
    return (saved as DateRange) || '1Y'
  })
  const [adjusted, setAdjusted] = useState(() => {
    const saved = localStorage.getItem('twstock.stockPage.adjusted')
    return saved ? saved === 'true' : true
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const reqIdRef = useRef(0)

  useEffect(() => {
    localStorage.setItem('twstock.stockPage.range', range)
  }, [range])

  useEffect(() => {
    localStorage.setItem('twstock.stockPage.adjusted', String(adjusted))
  }, [adjusted])

  useEffect(() => {
    if (!stockId) return

    const myId = ++reqIdRef.current
    const abortController = new AbortController()

    const load = async () => {
      try {
        setLoading(true)
        setError(null)

        const daysBack = RANGE_DAYS[range]
        const today = new Date()
        const fromDate = new Date(today)
        fromDate.setDate(fromDate.getDate() - daysBack)

        const fromStr = fromDate.toISOString().split('T')[0]

        const [stockData, pricesData] = await Promise.all([
          fetchStock(stockId, abortController.signal),
          fetchPrices(
            stockId,
            { from: fromStr, adj: adjusted },
            abortController.signal
          ),
        ])

        if (myId === reqIdRef.current) {
          setStock(stockData)
          setPrices(pricesData.items)
        }
      } catch (err) {
        if (myId === reqIdRef.current) {
          if (err instanceof Error && err.name !== 'AbortError') {
            setError(err)
          }
        }
      } finally {
        if (myId === reqIdRef.current) {
          setLoading(false)
        }
      }
    }

    load()
    return () => abortController.abort()
  }, [stockId, range, adjusted])

  if (!stockId) {
    return <p>股票代號缺失</p>
  }

  if (loading) {
    return <p role="status">載入中…</p>
  }

  if (error) {
    return <p role="alert">載入失敗：{error.message}</p>
  }

  if (!stock) {
    return <p>找不到股票資訊</p>
  }

  const changeClass =
    stock.latest && stock.latest.change !== null && stock.latest.change >= 0
      ? 'up'
      : 'down'
  const volumeDisplay =
    stock.latest && stock.latest.volume > 0
      ? `${(stock.latest.volume / 1000).toLocaleString(undefined, {
          maximumFractionDigits: 0,
        })} 張`
      : '—'

  return (
    <div>
      <div className="stock-header">
        <h1>
          {stock.stock_id} {stock.name}
        </h1>
        <p>
          {marketLabel(stock.market)}
          {stock.is_etf && ' · ETF'}
          {stock.industry && ` · ${stock.industry}`}
        </p>
        {stock.latest && (
          <div className="stock-latest">
            <p className={changeClass}>
              收盤 {stock.latest.close?.toFixed(2)}
              {stock.latest.change !== null &&
                ` ${stock.latest.change >= 0 ? '+' : ''}${stock.latest.change.toFixed(2)}`}
            </p>
            <p>成交量 {volumeDisplay}</p>
          </div>
        )}
      </div>

      <div className="stock-toolbar">
        <div className="range-buttons">
          {(Object.keys(RANGE_DAYS) as DateRange[]).map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              aria-pressed={range === r}
            >
              {r}
            </button>
          ))}
        </div>
        <label>
          <input
            type="checkbox"
            checked={adjusted}
            onChange={(e) => setAdjusted(e.target.checked)}
          />
          還原價
        </label>
      </div>

      {prices && prices.length > 0 ? (
        <CandleChart bars={prices} />
      ) : (
        <p>這檔目前沒有日 K 資料，請先執行回補。</p>
      )}
    </div>
  )
}
