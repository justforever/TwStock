import { describe, it, expect } from 'vitest'
import { consecutiveDays, lotsValue, toLots, toPercent } from './chipMath'

describe('chipMath', () => {
  it('consecutiveDays 連買 3 天', () => {
    const result = consecutiveDays([5000000, 8000000, 12000000])
    expect(result).toEqual({ days: 3, direction: 'buy' })
  })

  it('consecutiveDays 連買 1 天', () => {
    const result = consecutiveDays([1000000, -2000000, 2000000])
    expect(result).toEqual({ days: 1, direction: 'buy' })
  })

  it('consecutiveDays 連賣 1 天', () => {
    const result = consecutiveDays([-300000, 200000, -500000])
    expect(result).toEqual({ days: 1, direction: 'sell' })
  })

  it('consecutiveDays 空陣列', () => {
    const result = consecutiveDays([])
    expect(result).toEqual({ days: 0, direction: 'none' })
  })

  it('consecutiveDays 最後一個是 0', () => {
    const result = consecutiveDays([1, 0])
    expect(result).toEqual({ days: 0, direction: 'none' })
  })

  it('lotsValue 回傳整數張', () => {
    expect(lotsValue(20200000)).toBe(20200)
    expect(lotsValue(0)).toBe(0)
    expect(lotsValue(-5000000)).toBe(-5000)
    expect(lotsValue(1499)).toBe(1)
  })

  it('toLots', () => {
    expect(toLots(20200000)).toBe('20,200')
    expect(toLots(null)).toBe('—')
    expect(toLots(undefined)).toBe('—')
  })

  it('toPercent', () => {
    expect(toPercent(70)).toBe('70.00%')
    expect(toPercent(null)).toBe('—')
    expect(toPercent(undefined)).toBe('—')
  })
})
