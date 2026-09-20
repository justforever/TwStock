import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { act } from 'react'
import ChartStack from './ChartStack'
import type { PriceBar, InstitutionalBar, MarginBar } from '../api'

const { charts } = vi.hoisted(() => ({ charts: [] as any[] }))

vi.mock('lightweight-charts', () => {
  const makeSeries = () => ({
    setData: vi.fn(),
    applyOptions: vi.fn(),
    priceScale: () => ({ applyOptions: vi.fn() }),
  })
  return {
    createChart: vi.fn(() => {
      const timeScale = {
        fitContent: vi.fn(),
        applyOptions: vi.fn(),
        subscribeVisibleLogicalRangeChange: vi.fn(),
        unsubscribeVisibleLogicalRangeChange: vi.fn(),
        setVisibleLogicalRange: vi.fn(),
        getVisibleLogicalRange: vi.fn(() => null),
      }
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
})

const testBars: PriceBar[] = [
  {
    time: '2026-09-16',
    open: 995.0,
    high: 1005.0,
    low: 990.0,
    close: 1000.0,
    change: 10.0,
    volume: 25000000,
    turnover: 25000000000,
    transactions: 30000,
  },
  {
    time: '2026-09-17',
    open: 1000.0,
    high: 1008.0,
    low: 995.0,
    close: 1005.0,
    change: 5.0,
    volume: 28000000,
    turnover: 28000000000,
    transactions: 32000,
  },
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
]

const testInstitutional: InstitutionalBar[] = [
  {
    time: '2026-09-16',
    foreign_buy: 20000000,
    foreign_sell: 15000000,
    foreign_net: 5000000,
    trust_buy: 2000000,
    trust_sell: 1500000,
    trust_net: 500000,
    dealer_buy: 1500000,
    dealer_sell: 1000000,
    dealer_net: 500000,
    total_net: 6000000,
  },
  {
    time: '2026-09-17',
    foreign_buy: 25000000,
    foreign_sell: 17000000,
    foreign_net: 8000000,
    trust_buy: 2500000,
    trust_sell: 1800000,
    trust_net: 700000,
    dealer_buy: 1800000,
    dealer_sell: 900000,
    dealer_net: 900000,
    total_net: 9600000,
  },
  {
    time: '2026-09-18',
    foreign_buy: 30000000,
    foreign_sell: 18000000,
    foreign_net: 12000000,
    trust_buy: 3000000,
    trust_sell: 1000000,
    trust_net: 2000000,
    dealer_buy: 2000000,
    dealer_sell: 2500000,
    dealer_net: -500000,
    total_net: 13500000,
  },
]

const testMargin: MarginBar[] = [
  {
    time: '2026-09-16',
    margin_buy: 1000000,
    margin_sell: 800000,
    margin_redeem: 50000,
    margin_prev_balance: 19000000,
    margin_balance: 19500000,
    margin_limit: 100000000,
    short_buy: 40000,
    short_sell: 120000,
    short_redeem: 5000,
    short_prev_balance: 800000,
    short_balance: 900000,
    short_limit: 100000000,
    offset_amount: 10000,
    sbl_sell: 200000,
    sbl_balance: 4200000,
    margin_ratio: 4.615,
  },
  {
    time: '2026-09-17',
    margin_buy: 1100000,
    margin_sell: 850000,
    margin_redeem: 80000,
    margin_prev_balance: 19500000,
    margin_balance: 20000000,
    margin_limit: 100000000,
    short_buy: 45000,
    short_sell: 130000,
    short_redeem: 10000,
    short_prev_balance: 900000,
    short_balance: 1000000,
    short_limit: 100000000,
    offset_amount: 15000,
    sbl_sell: 250000,
    sbl_balance: 4350000,
    margin_ratio: 5.0,
  },
  {
    time: '2026-09-18',
    margin_buy: 1200000,
    margin_sell: 900000,
    margin_redeem: 100000,
    margin_prev_balance: 20000000,
    margin_balance: 20200000,
    margin_limit: 100000000,
    short_buy: 50000,
    short_sell: 150000,
    short_redeem: 10000,
    short_prev_balance: 1000000,
    short_balance: 1090000,
    short_limit: 100000000,
    offset_amount: 20000,
    sbl_sell: 300000,
    sbl_balance: 4500000,
    margin_ratio: 5.396,
  },
]

describe('ChartStack', () => {
  it('四個開關全開時建立四張圖', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )
    expect(charts.length).toBe(4)
  })

  it('每張圖都訂閱十字線', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )
    for (const chart of charts) {
      expect(chart.subscribeCrosshairMove).toHaveBeenCalled()
      expect(chart.__crosshair).toBeTruthy()
    }
  })

  it('主圖十字線會同步到其他三個 pane', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    act(() => {
      charts[0].__crosshair({ time: '2026-09-18', point: { x: 10, y: 20 }, seriesData: new Map() })
    })

    expect(charts[1].setCrosshairPosition).toHaveBeenCalled()
    expect(charts[2].setCrosshairPosition).toHaveBeenCalled()
    expect(charts[3].setCrosshairPosition).toHaveBeenCalled()
    expect(charts[0].setCrosshairPosition).not.toHaveBeenCalled()
  })

  it('副圖十字線也會同步回主圖', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    act(() => {
      charts[2].__crosshair({ time: '2026-09-17' })
    })

    expect(charts[0].setCrosshairPosition).toHaveBeenCalled()
  })

  it('滑鼠移出時清掉十字線', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    act(() => {
      charts[0].__crosshair({})
    })

    expect(charts[1].clearCrosshairPosition).toHaveBeenCalled()
    expect(charts[2].clearCrosshairPosition).toHaveBeenCalled()
    expect(charts[3].clearCrosshairPosition).toHaveBeenCalled()
  })

  it('讀數面板跟著十字線換日期', () => {
    const { container } = render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    const readout = container.querySelector('[data-testid="chart-readout"]') as HTMLElement
    let dateSpan = readout.querySelector('[data-testid="readout-date"]') as HTMLElement
    expect(dateSpan).toHaveTextContent('2026-09-18')

    act(() => {
      charts[0].__crosshair({ time: '2026-09-16' })
    })

    dateSpan = readout.querySelector('[data-testid="readout-date"]') as HTMLElement
    const foreignSpan = readout.querySelector('[data-testid="readout-foreign"]') as HTMLElement
    const marginSpan = readout.querySelector('[data-testid="readout-margin"]') as HTMLElement
    expect(dateSpan).toHaveTextContent('2026-09-16')
    expect(foreignSpan).toHaveTextContent('5,000')
    expect(marginSpan).toHaveTextContent('19,500')
  })

  it('關掉兩個副圖只建兩張圖', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={false}
        showMargin={false}
      />
    )
    expect(charts.length).toBe(2)
  })

  it('bars 為空時不建圖', () => {
    render(
      <ChartStack
        bars={[]}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )
    expect(charts.length).toBe(0)
  })

  it('連續十字線移動不會重建圖表', () => {
    render(
      <ChartStack
        bars={testBars}
        institutional={testInstitutional}
        margin={testMargin}
        showInstitutional={true}
        showMargin={true}
      />
    )

    const initialChartsCount = charts.length
    expect(initialChartsCount).toBe(4)

    // 第一次十字線移動
    act(() => {
      charts[0].__crosshair({ time: '2026-09-17' })
    })
    expect(charts.length).toBe(initialChartsCount)

    // 第二次十字線移動
    act(() => {
      charts[0].__crosshair({ time: '2026-09-16' })
    })
    expect(charts.length).toBe(initialChartsCount)

    // 第三次十字線移動
    act(() => {
      charts[0].__crosshair({ time: '2026-09-18' })
    })
    expect(charts.length).toBe(initialChartsCount)
  })
})
