export interface MaPoint {
  time: string
  value: number
}

/** 以收盤價算簡單移動平均；資料不足 period 的位置不輸出點。 */
export function simpleMovingAverage(
  bars: { time: string; close: number | null }[],
  period: number
): MaPoint[] {
  if (period <= 0) {
    throw new Error('period 必須大於 0')
  }

  const result: MaPoint[] = []

  for (let i = period - 1; i < bars.length; i++) {
    let sum = 0
    let hasNull = false

    for (let j = i - period + 1; j <= i; j++) {
      const close = bars[j].close
      if (close === null) {
        hasNull = true
        break
      }
      sum += close
    }

    if (!hasNull) {
      const avg = sum / period
      const rounded = Math.round(avg * 10000) / 10000
      result.push({
        time: bars[i].time,
        value: rounded,
      })
    }
  }

  return result
}
