import type { PriceBar } from '../api'
import type { InstitutionalBar, ShareholdingWeek, ForeignHoldingBar } from '../api'
import { toLots, toPercent, consecutiveDays } from '../chipMath'

export interface ChipTabProps {
  bars: PriceBar[]
  institutional: InstitutionalBar[]
  shareholding: ShareholdingWeek[]
  foreignHolding: ForeignHoldingBar[]
}

const LEVEL_LABELS: Record<number, string> = {
  1: '1–999',
  2: '1,000–5,000',
  3: '5,001–10,000',
  4: '10,001–15,000',
  5: '15,001–20,000',
  6: '20,001–30,000',
  7: '30,001–40,000',
  8: '40,001–50,000',
  9: '50,001–100,000',
  10: '100,001–200,000',
  11: '200,001–400,000',
  12: '400,001–600,000',
  13: '600,001–800,000',
  14: '800,001–1,000,000',
  15: '1,000,001 以上',
}

function Sparkline(props: { values: number[]; width?: number; height?: number; color?: string }) {
  const { values, width = 100, height = 40, color = '#0066cc' } = props

  if (values.length < 2) return null

  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)
  const range = maxVal - minVal || 1

  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width
      const y = height - ((v - minVal) / range) * height
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg role="img" aria-label="趨勢圖" width={width} height={height} style={{ display: 'inline-block', marginLeft: '0.5rem' }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  )
}

export default function ChipTab(props: ChipTabProps) {
  const { shareholding, foreignHolding, institutional } = props

  const latestShareholding = shareholding.length > 0 ? shareholding[shareholding.length - 1] : null
  const latestForeignHolding = foreignHolding.length > 0 ? foreignHolding[foreignHolding.length - 1] : null

  // 計算連續買賣天數
  const foreignNets = institutional.map((b) => b.foreign_net)
  const trustNets = institutional.map((b) => b.trust_net)
  const dealerNets = institutional.map((b) => b.dealer_net)

  const foreignStreak = consecutiveDays(foreignNets)
  const trustStreak = consecutiveDays(trustNets)
  const dealerStreak = consecutiveDays(dealerNets)

  // 最近 20 日法人買賣超（由新到舊）
  const recentInstitutional = institutional.slice(-20).reverse()

  return (
    <div>
      {/* 集保股權分散 */}
      <div className="chip-section">
        <h2>集保股權分散</h2>
        {!latestShareholding ? (
          <p>尚無集保股權分散資料，請先執行 load-shareholding。</p>
        ) : (
          <>
            <p data-testid="chip-week">資料週 {latestShareholding.week} · 總股東人數 {latestShareholding.total_holders.toLocaleString('en-US')} 人</p>

            <div className="chip-metric">
              <span data-testid="chip-big-ratio">400 張以上大戶比例 {toPercent(latestShareholding.big_holder_ratio)}</span>
              <Sparkline
                values={shareholding.map((s) => s.big_holder_ratio)}
                color="#d32f2f"
              />
            </div>

            <div className="chip-metric">
              <span data-testid="chip-retail-ratio">15 張以下散戶比例 {toPercent(latestShareholding.retail_ratio)}</span>
              <Sparkline
                values={shareholding.map((s) => s.retail_ratio)}
                color="#2e7d32"
              />
            </div>

            <table className="chip-table">
              <thead>
                <tr>
                  <th>級距（股）</th>
                  <th>人數</th>
                  <th>股數（張）</th>
                  <th>比例</th>
                </tr>
              </thead>
              <tbody>
                {latestShareholding.levels.map((level) => (
                  <tr key={level.level}>
                    <td>{LEVEL_LABELS[level.level]}</td>
                    <td>{level.holders.toLocaleString('en-US')}</td>
                    <td>{toLots(level.shares)}</td>
                    <td>{toPercent(level.ratio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      {/* 外資持股比例趨勢 */}
      <div className="chip-section">
        <h2>外資持股比例趨勢</h2>
        {!latestForeignHolding ? (
          <p>尚無外資持股資料（M2 只收上市）。</p>
        ) : (
          <>
            <div className="chip-metric">
              <span data-testid="chip-foreign-ratio">外資持股比例 {toPercent(latestForeignHolding.holding_ratio)}</span>
              <Sparkline
                values={foreignHolding.map((f) => f.holding_ratio || 0)}
                color="#f57c00"
              />
            </div>
            <p>尚可投資比例 {toPercent(latestForeignHolding.available_ratio)}</p>
          </>
        )}
      </div>

      {/* 法人連續買賣天數 */}
      <div className="chip-section">
        <h2>法人連續買賣天數</h2>
        <p data-testid="chip-streak-foreign">
          外資 {foreignStreak.direction === 'none' ? '—' : `連${foreignStreak.direction === 'buy' ? '買' : '賣'} ${foreignStreak.days} 天`}
        </p>
        <p data-testid="chip-streak-trust">
          投信 {trustStreak.direction === 'none' ? '—' : `連${trustStreak.direction === 'buy' ? '買' : '賣'} ${trustStreak.days} 天`}
        </p>
        <p data-testid="chip-streak-dealer">
          自營 {dealerStreak.direction === 'none' ? '—' : `連${dealerStreak.direction === 'buy' ? '買' : '賣'} ${dealerStreak.days} 天`}
        </p>

        {recentInstitutional.length > 0 && (
          <>
            <h3 style={{ marginTop: '1.5rem', marginBottom: '1rem', fontSize: '1rem' }}>最近 20 日法人買賣超（張）</h3>
            <table className="chip-table">
              <thead>
                <tr>
                  <th>日期</th>
                  <th>外資</th>
                  <th>投信</th>
                  <th>自營</th>
                  <th>合計</th>
                </tr>
              </thead>
              <tbody>
                {recentInstitutional.map((bar) => (
                  <tr key={bar.time}>
                    <td>{bar.time}</td>
                    <td>{toLots(bar.foreign_net)}</td>
                    <td>{toLots(bar.trust_net)}</td>
                    <td>{toLots(bar.dealer_net)}</td>
                    <td>{toLots(bar.total_net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  )
}
