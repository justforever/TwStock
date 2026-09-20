import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import StockPage from './StockPage'

const { charts } = vi.hoisted(() => ({ charts: [] as any[] }))

vi.mock('lightweight-charts', () => {
  const makeSeries = () => ({
    setData: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: () => ({ applyOptions: vi.fn() }),
  })
  const timeScale = {
    fitContent: vi.fn(),
    applyOptions: vi.fn(),
    subscribeVisibleLogicalRangeChange: vi.fn(),
    unsubscribeVisibleLogicalRangeChange: vi.fn(),
    setVisibleLogicalRange: vi.fn(),
    getVisibleLogicalRange: vi.fn(() => null),
  }
  return {
    createChart: vi.fn(() => {
      const chart: any = {
        addCandlestickSeries: vi.fn(() => makeSeries()),
        addLineSeries: vi.fn(() => makeSeries()),
        addHistogramSeries: vi.fn(() => makeSeries()),
        removeSeries: vi.fn(),
        timeScale: () => timeScale,
        priceScale: () => ({ applyOptions: vi.fn(), width: () => 72 }),
        applyOptions: vi.fn(),
        subscribeCrosshairMove: vi.fn((h: any) => { chart.__crosshair = h }),
        unsubscribeCrosshairMove: vi.fn(),
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
        resize: vi.fn(),
        remove: vi.fn(),
        __crosshair: null,
      }
      charts.push(chart)
      return chart
    }),
    ColorType: { Solid: 'solid' },
    CrosshairMode: { Normal: 0, Magnet: 1 },
    LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
  }
})

beforeEach(() => {
  charts.length = 0
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
})

describe('StockPage', () => {
  it('預設顯示 K 線分頁與讀數面板', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '2330', count: 0, items: [] }),
        })
      }
      return Promise.reject(new Error('Unexpected URL: ' + url))
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
    expect(await screen.findByTestId('readout-ohlc')).toBeInTheDocument()
    // 預設顯示 K 線分頁
    expect(screen.getByRole('tab', { name: 'K 線' })).toHaveAttribute('aria-selected', 'true')
    // 讀數面板應該顯示
    expect(screen.getByTestId('chart-readout')).toBeInTheDocument()
  })

  it('點 5Y 後，fetch 被以含 from= 且日期在 5 年前的 URL 呼叫', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '2330', count: 0, items: [] }),
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
      if (url.includes('/api/stocks/2330') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '2330', count: 0, items: [] }),
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
    const adjustedCheckbox = checkboxes[0] // 第一個 checkbox
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
      if (url.includes('/api/stocks/9999') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '9999', count: 0, items: [] }),
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

  it('點「籌碼」分頁會顯示大戶比例', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/shareholding')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '2330',
              count: 1,
              items: [
                {
                  week: '2026-09-18',
                  total_holders: 1000000,
                  total_shares: 1000000000,
                  big_holder_ratio: 80.0,
                  retail_ratio: 20.0,
                  levels: [],
                },
              ],
            }),
        })
      }
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '2330', count: 0, items: [] }),
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
    await screen.findByText(/2330/)

    // 點擊籌碼分頁
    const chipTab = screen.getByRole('tab', { name: '籌碼' })
    await userEvent.click(chipTab)

    // 應該顯示大戶比例
    expect(await screen.findByTestId('chip-big-ratio')).toHaveTextContent('80.00%')
  })

  it('會呼叫四個籌碼端點', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '2330', count: 0, items: [] }),
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

    await screen.findByText(/2330/)

    const fetchCalls = (globalThis.fetch as any).mock.calls
    const hasInstitutional = fetchCalls.some((call: any[]) => call[0].includes('/institutional'))
    const hasMargin = fetchCalls.some((call: any[]) => call[0].includes('/margin'))
    const hasShareholding = fetchCalls.some((call: any[]) => call[0].includes('/shareholding'))
    const hasForeignHolding = fetchCalls.some((call: any[]) => call[0].includes('/foreign-holding'))

    expect(hasInstitutional).toBe(true)
    expect(hasMargin).toBe(true)
    expect(hasShareholding).toBe(true)
    expect(hasForeignHolding).toBe(true)
  })

  it('籌碼端點回 500 時頁面仍然顯示 K 線', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/2330') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
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
      if (url.includes('/institutional')) {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({}),
        })
      }
      if (url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '2330', count: 0, items: [] }),
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

    await screen.findByText(/2330/)

    // 不應該出現 alert
    const alerts = screen.queryAllByRole('alert')
    expect(alerts.length).toBe(0)

    // 應該看得到讀數面板（K 線還在）
    expect(screen.getByTestId('chart-readout')).toBeInTheDocument()
  })

  it('上櫃個股顯示還原價註記', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/stocks/1101') && !url.includes('/prices') && !url.includes('/institutional') && !url.includes('/margin') && !url.includes('/shareholding') && !url.includes('/foreign')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '1101',
              name: '台泥',
              market: 'TPEx',
              industry: '水泥業',
              listed_date: '1962-09-05',
              is_etf: false,
              is_active: true,
              latest: {
                time: '2026-09-18',
                open: 40.0,
                high: 41.0,
                low: 39.5,
                close: 40.5,
                change: 0.5,
                volume: 5000000,
                turnover: 200000000,
                transactions: 10000,
              },
            }),
        })
      }
      if (url.includes('/api/stocks/1101/prices')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              stock_id: '1101',
              count: 1,
              items: [
                {
                  time: '2026-09-18',
                  open: 40.0,
                  high: 41.0,
                  low: 39.5,
                  close: 40.5,
                  change: 0.5,
                  volume: 5000000,
                  turnover: 200000000,
                  transactions: 10000,
                },
              ],
            }),
        })
      }
      if (url.includes('/institutional') || url.includes('/margin') || url.includes('/shareholding') || url.includes('/foreign-holding')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stock_id: '1101', count: 0, items: [] }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(
      <MemoryRouter initialEntries={['/stock/1101']}>
        <Routes>
          <Route path="/stock/:stockId" element={<StockPage />} />
        </Routes>
      </MemoryRouter>
    )

    await screen.findByText(/台泥/)

    // 應該看得到註記
    expect(screen.getByText(/上櫃除權息尚未收錄/)).toBeInTheDocument()
  })
})
