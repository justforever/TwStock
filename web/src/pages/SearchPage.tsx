import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { searchStocks, StockSearchResponse, marketLabel } from '../api'

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [response, setResponse] = useState<StockSearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const timeoutRef = useRef<number | null>(null)
  const reqIdRef = useRef(0)

  // 処理搜索
  const performSearch = async (q: string) => {
    if (q.trim() === '') {
      setResponse(null)
      setError(null)
      return
    }

    const myId = ++reqIdRef.current

    setLoading(true)
    setError(null)

    // 取消前一個請求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }

    abortControllerRef.current = new AbortController()

    try {
      const result = await searchStocks(q, abortControllerRef.current.signal)
      if (myId === reqIdRef.current) {
        setResponse(result)
      }
    } catch (err) {
      if (myId === reqIdRef.current) {
        if (err instanceof Error) {
          if (err.name === 'AbortError') {
            // 忽略中止錯誤
            return
          }
          setError(err)
        } else {
          setError(new Error('未知錯誤'))
        }
        setResponse(null)
      }
    } finally {
      if (myId === reqIdRef.current) {
        setLoading(false)
      }
    }
  }

  // 防抖效果
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.currentTarget.value
    setQuery(value)

    // 如果輸入框為空，立即清空結果
    if (value.trim() === '') {
      setResponse(null)
      setError(null)
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
      return
    }

    // 清除前一個超時
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
    }

    // 設置新的超時
    timeoutRef.current = window.setTimeout(() => {
      performSearch(value)
    }, 250)
  }

  // 快捷鍵處理
  const handleKeyDown = (e: KeyboardEvent) => {
    const el = document.activeElement as HTMLElement | null
    const tag = el?.tagName
    const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el?.isContentEditable === true
    if (e.key === '/' && !typing) {
      e.preventDefault()
      inputRef.current?.focus()
    }
  }

  // 清理和快捷鍵掛載
  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [])

  return (
    <div>
      <input
        ref={inputRef}
        type="search"
        value={query}
        onChange={handleInputChange}
        aria-label="搜尋股票代號或名稱"
        placeholder="輸入代號或名稱，例如 2330 或 台積"
        autoFocus
      />

      {loading && <p role="status">搜尋中…</p>}

      {error && (
        <p role="alert">搜尋失敗：{error.message}</p>
      )}

      {response && query.trim() !== '' && response.items.length === 0 && (
        <p>查無符合的股票</p>
      )}

      {response && response.items.length > 0 && (
        <ul aria-label="搜尋結果">
          {response.items.map((item) => (
            <li key={item.stock_id}>
              <Link to={`/stock/${item.stock_id}`}>
                {`${item.stock_id} ${item.name}`}
              </Link>
              <span>{marketLabel(item.market)}</span>
              {item.is_etf && <span>ETF</span>}
              {item.industry && <span>{item.industry}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
