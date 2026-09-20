/** 連續買超（正）／賣超（負）天數：從最後一天往回數，方向改變或遇到 0 就停。 */
export function consecutiveDays(nets: number[]): { days: number; direction: 'buy' | 'sell' | 'none' } {
  if (nets.length === 0) {
    return { days: 0, direction: 'none' }
  }

  const lastValue = nets[nets.length - 1]
  if (lastValue === 0) {
    return { days: 0, direction: 'none' }
  }

  const direction = lastValue > 0 ? 'buy' : 'sell'
  let days = 0

  for (let i = nets.length - 1; i >= 0; i--) {
    const val = nets[i]
    if (val === 0) break
    if ((val > 0 && direction === 'buy') || (val < 0 && direction === 'sell')) {
      days++
    } else {
      break
    }
  }

  return { days, direction }
}

/** 股 → 張的顯示字串（整數、千分位）；例 20_200_000 → "20,200"。 */
export function toLots(shares: number | null | undefined): string {
  if (shares === null || shares === undefined) {
    return '—'
  }
  return Math.round(shares / 1000).toLocaleString('en-US')
}

/** 百分比顯示；null → "—"；例 70 → "70.00%"。 */
export function toPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return value.toFixed(2) + '%'
}
