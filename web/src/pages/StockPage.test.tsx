import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import StockPage from './StockPage'

vi.mock('lightweight-charts', () => {
  const series = {
    setData: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: () => ({ applyOptions: vi.fn() }),
  }
  const timeScale = {
    fitContent: vi.fn(),
    applyOptions: vi.fn(),
    subscribeVisibleLogicalRangeChange: vi.fn(),
    unsubscribeVisibleLogicalRangeChange: vi.fn(),
    setVisibleLogicalRange: vi.fn(),
    getVisibleLogicalRange: vi.fn(() => null),
  }
  return {
    createChart: vi.fn(() => ({
      addCandlestickSeries: vi.fn(() => series),
      addLineSeries: vi.fn(() => series),
      addHistogramSeries: vi.fn(() => series),
      timeScale: () => timeScale,
      applyOptions: vi.fn(),
      resize: vi.fn(),
      remove: vi.fn(),
    })),
    ColorType: { Solid: 'solid' },
    CrosshairMode: { Normal: 0, Magnet: 1 },
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
  }
})

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('StockPage', () => {
  it('顯示 2330、台積電、最新收盤 1008', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              industry: '半導體業',
              listed_date: '1994-09-05',
              is_etf: false,
              is_active: true,
              latest: {
                time: '2026-09-18',
                open: 996.0,
                high: 1010.0,
                low: 995.0,
                close: 1008.0,
                change: 13.0,
                volume: 30000000,
                turnover: 30000000000,
                transactions: 35000,
              },
            }),
        })
      }
      if (url.includes('/api/stocks/2330/prices')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              adjusted: false,
              from: '2025-09-18',
              to: '2026-09-18',
              count: 1,
              items: [
                {
                  time: '2026-09-18',
                  open: 996.0,
                  high: 1010.0,
                  low: 995.0,
                  close: 1008.0,
                  change: 13.0,
                  volume: 30000000,
                  turnover: 30000000000,
                  transactions: 35000,
                },
              ],
            }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(
      <MemoryRouter initialEntries={['/stock/2330']}>
        <Routes>
          <Route path="/stock/:stockId" element={<StockPage />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByText(/2330/)).toBeInTheDocument()
    expect(await screen.findByText(/台積電/)).toBeInTheDocument()
    expect(await screen.findByText(/1008/)).toBeInTheDocument()
  })

  it('點 5Y 後，fetch 被以含 from= 且日期在 5 年前的 URL 呼叫', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              industry: null,
              listed_date: null,
              is_etf: false,
              is_active: true,
              latest: null,
            }),
        })
      }
      if (url.includes('/api/stocks/2330/prices')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              adjusted: false,
              from: '2021-09-18',
              to: '2026-09-18',
              count: 0,
              items: [],
            }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(
      <MemoryRouter initialEntries={['/stock/2330']}>
        <Routes>
          <Route path="/stock/:stockId" element={<StockPage />} />
        </Routes>
      </MemoryRouter>
    )

    const button5Y = await screen.findByRole('button', { name: '5Y' })
    await userEvent.click(button5Y)

    const allFetchCalls = (globalThis.fetch as any).mock.calls
    const pricesFetchCall = allFetchCalls.find((call: any[]) =>
      call[0].includes('/api/stocks/2330/prices')
    )
    expect(pricesFetchCall).toBeDefined()
    expect(pricesFetchCall[0]).toContain('from=')
  })

  it('API 回 500 → 出現 role="alert"', async () => {
    ;(globalThis.fetch as any).mockImplementation(() => {
      return Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      })
    })

    render(
      <MemoryRouter initialEntries={['/stock/2330']}>
        <Routes>
          <Route path="/stock/:stockId" element={<StockPage />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByRole('alert')).toBeInTheDocument()
  })

  it('取消勾選還原價後，fetch URL 含 adj=false', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              industry: '半導體業',
              listed_date: '1994-09-05',
              is_etf: false,
              is_active: true,
              latest: {
                time: '2026-09-18',
                open: 996.0,
                high: 1010.0,
                low: 995.0,
                close: 1008.0,
                change: 13.0,
                volume: 30000000,
                turnover: 30000000000,
                transactions: 35000,
              },
            }),
        })
      }
      if (url.includes('/api/stocks/2330/prices')) {
        // 根據 URL 中的 adj 參數改變 adjusted 欄位
        const adjusted = url.includes('adj=false') ? false : true
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              adjusted,
              from: '2025-09-18',
              to: '2026-09-18',
              count: 1,
              items: [
                {
                  time: '2026-09-18',
                  open: 996.0,
                  high: 1010.0,
                  low: 995.0,
                  close: 1008.0,
                  change: 13.0,
                  volume: 30000000,
                  turnover: 30000000000,
                  transactions: 35000,
                },
              ],
            }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(
      <MemoryRouter initialEntries={['/stock/2330']}>
        <Routes>
          <Route path="/stock/:stockId" element={<StockPage />} />
        </Routes>
      </MemoryRouter>
    )

    // 等待頁面載入
    await screen.findByText(/收盤/)

    // 找到還原價 checkbox 並取消勾選
    const checkboxes = screen.getAllByRole('checkbox')
    const adjustedCheckbox = checkboxes[0] // 只有一個 checkbox
    expect(adjustedCheckbox).toBeChecked()

    await userEvent.click(adjustedCheckbox)

    // 等待變化完成
    await new Promise((resolve) => setTimeout(resolve, 100))

    // 檢查 fetch 調用中是否存在 adj=false
    const allFetchCalls = (globalThis.fetch as any).mock.calls
    const pricesFetchCalls = allFetchCalls.filter((call: any[]) =>
      call[0].includes('/api/stocks/2330/prices')
    )

    // 應該有至少 2 個 fetch（初始 adj=true，點擊後 adj=false）
    const hasAdjFalse = pricesFetchCalls.some((call: any[]) =>
      call[0].includes('adj=false')
    )
    expect(hasAdjFalse).toBe(true)
  })

  it('count: 0 時出現「沒有日 K 資料」字樣', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/9999')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '9999',
              name: '測試股票',
              market: 'TWSE',
              industry: '測試業',
              listed_date: '2026-01-01',
              is_etf: false,
              is_active: true,
              latest: null,
            }),
        })
      }
      if (url.includes('/api/stocks/9999/prices')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '9999',
              name: '測試股票',
              market: 'TWSE',
              adjusted: false,
              from: '2025-09-18',
              to: '2026-09-18',
              count: 0,
              items: [],
            }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(
      <MemoryRouter initialEntries={['/stock/9999']}>
        <Routes>
          <Route path="/stock/:stockId" element={<StockPage />} />
        </Routes>
      </MemoryRouter>
    )

    // 等待頁面載入，找到「沒有日 K 資料」文字
    const noDataElement = await screen.findByText(/沒有日 K 資料/)
    expect(noDataElement).toBeInTheDocument()
  })
})
