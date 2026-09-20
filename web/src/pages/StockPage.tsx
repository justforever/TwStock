import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import ChartStack from '../components/ChartStack'
import ChipTab from '../components/ChipTab'
import {
  fetchStock,
  fetchPrices,
  fetchInstitutional,
  fetchMargin,
  fetchShareholding,
  fetchForeignHolding,
  marketLabel,
  type StockDetail,
  type PriceBar,
  type InstitutionalBar,
  type MarginBar,
  type ShareholdingWeek,
  type ForeignHoldingBar,
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
  const [institutional, setInstitutional] = useState<InstitutionalBar[]>([])
  const [margin, setMargin] = useState<MarginBar[]>([])
  const [shareholding, setShareholding] = useState<ShareholdingWeek[]>([])
  const [foreignHolding, setForeignHolding] = useState<ForeignHoldingBar[]>([])
  const [range, setRange] = useState<DateRange>(() => {
    const saved = localStorage.getItem('twstock.stockPage.range')
    return (saved as DateRange) || '1Y'
  })
  const [adjusted, setAdjusted] = useState(() => {
    const saved = localStorage.getItem('twstock.stockPage.adjusted')
    return saved ? saved === 'true' : true
  })
  const [tab, setTab] = useState<'chart' | 'chip'>(() => {
    const saved = localStorage.getItem('twstock.stockPage.tab')
    return (saved as 'chart' | 'chip') || 'chart'
  })
  const [showInstitutional, setShowInstitutional] = useState(() => {
    const saved = localStorage.getItem('twstock.stockPage.showInstitutional')
    return saved ? saved === 'true' : true
  })
  const [showMargin, setShowMargin] = useState(() => {
    const saved = localStorage.getItem('twstock.stockPage.showMargin')
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
    localStorage.setItem('twstock.stockPage.tab', tab)
  }, [tab])

  useEffect(() => {
    localStorage.setItem('twstock.stockPage.showInstitutional', String(showInstitutional))
  }, [showInstitutional])

  useEffect(() => {
    localStorage.setItem('twstock.stockPage.showMargin', String(showMargin))
  }, [showMargin])

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

        const results = await Promise.allSettled([
          fetchStock(stockId, abortController.signal),
          fetchPrices(
            stockId,
            { from: fromStr, adj: adjusted },
            abortController.signal
          ),
          fetchInstitutional(stockId, { from: fromStr }, abortController.signal),
          fetchMargin(stockId, { from: fromStr }, abortController.signal),
          fetchShareholding(stockId, { limit: 104 }, abortController.signal),
          fetchForeignHolding(stockId, { from: fromStr }, abortController.signal),
        ])

        if (myId !== reqIdRef.current) return

        const [stockResult, pricesResult, instResult, marginResult, shareholdingResult, foreignResult] = results

        // 處理主要資料（失敗則顯示錯誤）
        if (stockResult.status === 'rejected' || pricesResult.status === 'rejected') {
          if (stockResult.status === 'rejected') {
            setError(stockResult.reason as Error)
          } else if (pricesResult.status === 'rejected') {
            setError(pricesResult.reason as Error)
          }
          return
        }

        setStock(stockResult.value)
        setPrices(pricesResult.value.items)

        // 處理籌碼資料（失敗則用空陣列）
        if (instResult.status === 'fulfilled') {
          setInstitutional(instResult.value.items)
        } else if (instResult.status === 'rejected') {
          console.warn('Failed to fetch institutional data:', instResult.reason)
          setInstitutional([])
        }

        if (marginResult.status === 'fulfilled') {
          setMargin(marginResult.value.items)
        } else if (marginResult.status === 'rejected') {
          console.warn('Failed to fetch margin data:', marginResult.reason)
          setMargin([])
        }

        if (shareholdingResult.status === 'fulfilled') {
          setShareholding(shareholdingResult.value.items)
        } else if (shareholdingResult.status === 'rejected') {
          console.warn('Failed to fetch shareholding data:', shareholdingResult.reason)
          setShareholding([])
        }

        if (foreignResult.status === 'fulfilled') {
          setForeignHolding(foreignResult.value.items)
        } else if (foreignResult.status === 'rejected') {
          console.warn('Failed to fetch foreign holding data:', foreignResult.reason)
          setForeignHolding([])
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
          {stock.market === 'TPEx' && (
            <span className="hint">（上櫃除權息尚未收錄，還原價等同原始價）</span>
          )}
        </label>
      </div>

      {prices && prices.length > 0 ? (
        <>
          <div role="tablist" className="tab-buttons">
            <button
              role="tab"
              aria-selected={tab === 'chart'}
              onClick={() => setTab('chart')}
            >
              K 線
            </button>
            <button
              role="tab"
              aria-selected={tab === 'chip'}
              onClick={() => setTab('chip')}
            >
              籌碼
            </button>
          </div>

          {tab === 'chart' && (
            <>
              <div className="chart-controls">
                <label>
                  <input
                    type="checkbox"
                    checked={showInstitutional}
                    onChange={(e) => setShowInstitutional(e.target.checked)}
                  />
                  法人買賣超
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={showMargin}
                    onChange={(e) => setShowMargin(e.target.checked)}
                  />
                  融資融券
                </label>
              </div>
              <ChartStack
                bars={prices}
                institutional={institutional}
                margin={margin}
                showInstitutional={showInstitutional}
                showMargin={showMargin}
              />
            </>
          )}

          {tab === 'chip' && (
            <ChipTab
              bars={prices}
              institutional={institutional}
              shareholding={shareholding}
              foreignHolding={foreignHolding}
            />
          )}
        </>
      ) : (
        <p>這檔目前沒有日 K 資料，請先執行回補。</p>
      )}
    </div>
  )
}
