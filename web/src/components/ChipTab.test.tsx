import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChipTab from './ChipTab'
import type { PriceBar, InstitutionalBar, ShareholdingWeek, ForeignHoldingBar } from '../api'

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

const testShareholding: ShareholdingWeek[] = [
  {
    week: '2026-09-18',
    total_holders: 1000000,
    total_shares: 1000000000,
    big_holder_ratio: 80.0,
    retail_ratio: 20.0,
    levels: [
      { level: 1, holders: 600000, shares: 50000000, ratio: 5.0 },
      { level: 2, holders: 350000, shares: 100000000, ratio: 10.0 },
      { level: 3, holders: 40000, shares: 50000000, ratio: 5.0 },
      { level: 12, holders: 5000, shares: 100000000, ratio: 10.0 },
      { level: 13, holders: 2000, shares: 100000000, ratio: 10.0 },
      { level: 14, holders: 1500, shares: 100000000, ratio: 10.0 },
      { level: 15, holders: 1500, shares: 500000000, ratio: 50.0 },
    ],
  },
]

const testForeignHolding: ForeignHoldingBar[] = [
  {
    time: '2026-09-18',
    issued_shares: 25930380458,
    holding_shares: 18151266320,
    available_shares: 7779114138,
    holding_ratio: 70.0,
    available_ratio: 30.0,
    limit_ratio: 100.0,
  },
]

describe('ChipTab', () => {
  it('chip-big-ratio 顯示 80.00%', () => {
    render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const ratios = screen.getAllByTestId('chip-big-ratio')
    expect(ratios[0]).toHaveTextContent('80.00%')
  })

  it('chip-retail-ratio 顯示 20.00%', () => {
    render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const ratios = screen.getAllByTestId('chip-retail-ratio')
    expect(ratios[0]).toHaveTextContent('20.00%')
  })

  it('chip-week 含 2026-09-18', () => {
    render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const weeks = screen.getAllByTestId('chip-week')
    expect(weeks[0]).toHaveTextContent('2026-09-18')
  })

  it('級距表有 7 列', () => {
    const { container } = render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const tables = container.querySelectorAll('.chip-table')
    const levelTable = tables[0] // First chip-table is the shareholding levels
    const rows = levelTable.querySelectorAll('tbody tr')
    // 7 data rows (level 1, 2, 3, 12, 13, 14, 15)
    expect(rows.length).toBe(7)
  })

  it('level 15 那列的人數是 1,500', () => {
    const { container } = render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const tables = container.querySelectorAll('.chip-table')
    const levelTable = tables[0]
    const rows = levelTable.querySelectorAll('tbody tr')
    // Last data row should be level 15
    const lastRow = rows[rows.length - 1]
    expect(lastRow).toHaveTextContent('1,500')
  })

  it('chip-streak-foreign 顯示連買 3 天', () => {
    render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const streaks = screen.getAllByTestId('chip-streak-foreign')
    expect(streaks[0]).toHaveTextContent('連買 3 天')
  })

  it('chip-streak-dealer 顯示連賣 1 天', () => {
    render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const streaks = screen.getAllByTestId('chip-streak-dealer')
    expect(streaks[0]).toHaveTextContent('連賣 1 天')
  })

  it('chip-foreign-ratio 顯示 70.00%', () => {
    render(
      <ChipTab
        bars={testBars}
        institutional={testInstitutional}
        shareholding={testShareholding}
        foreignHolding={testForeignHolding}
      />
    )
    const ratios = screen.getAllByTestId('chip-foreign-ratio')
    expect(ratios[0]).toHaveTextContent('70.00%')
  })

  it('四份資料都是空陣列時顯示對應訊息', () => {
    render(
      <ChipTab
        bars={[]}
        institutional={[]}
        shareholding={[]}
        foreignHolding={[]}
      />
    )
    expect(screen.getByText('尚無集保股權分散資料，請先執行 load-shareholding。')).toBeInTheDocument()
    expect(screen.getByText('尚無外資持股資料（M2 只收上市）。')).toBeInTheDocument()
  })
})
