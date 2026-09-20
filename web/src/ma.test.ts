import { describe, it, expect } from 'vitest'
import { simpleMovingAverage } from './ma'

describe('simpleMovingAverage', () => {
  it('計算 5 根 close 1..5 的簡單移動平均', () => {
    const bars = [
      { time: '2026-09-14', close: 1 },
      { time: '2026-09-15', close: 2 },
      { time: '2026-09-16', close: 3 },
      { time: '2026-09-17', close: 4 },
      { time: '2026-09-18', close: 5 },
    ]
    const result = simpleMovingAverage(bars, 5)
    expect(result).toHaveLength(1)
    expect(result[0].value).toBe(3)
    expect(result[0].time).toBe('2026-09-18')
  })

  it('資料不足時回傳空陣列', () => {
    const bars = [
      { time: '2026-09-16', close: 1 },
      { time: '2026-09-17', close: 2 },
    ]
    const result = simpleMovingAverage(bars, 5)
    expect(result).toHaveLength(0)
  })

  it('period = 0 時拋錯誤', () => {
    const bars = [{ time: '2026-09-16', close: 1 }]
    expect(() => simpleMovingAverage(bars, 0)).toThrow('period 必須大於 0')
  })

  it('視窗內有 null 時不輸出該點', () => {
    const bars = [
      { time: '2026-09-14', close: 1 },
      { time: '2026-09-15', close: null },
      { time: '2026-09-16', close: 3 },
      { time: '2026-09-17', close: 4 },
      { time: '2026-09-18', close: 5 },
    ]
    const result = simpleMovingAverage(bars, 3)
    expect(result).toHaveLength(1)
    expect(result[0].time).toBe('2026-09-18')
    expect(result[0].value).toBe(4)
  })

  it('值四捨五入到小數 4 位', () => {
    const bars = [
      { time: '2026-09-14', close: 1.11111 },
      { time: '2026-09-15', close: 2.22222 },
      { time: '2026-09-16', close: 3.33333 },
    ]
    const result = simpleMovingAverage(bars, 3)
    expect(result).toHaveLength(1)
    expect(result[0].value).toBe(2.2222)
  })
})
