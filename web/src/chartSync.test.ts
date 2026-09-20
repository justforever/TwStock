import { describe, it, expect, vi } from 'vitest'
import { applyCrosshairToOthers, crosshairTime } from './chartSync'
import type { SyncPane } from './chartSync'

describe('chartSync', () => {
  it('其他 pane 收到 setCrosshairPosition', () => {
    const pane1: SyncPane = {
      id: 'main',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 1008]]),
    }
    const pane2: SyncPane = {
      id: 'volume',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 30000000]]),
    }
    const pane3: SyncPane = {
      id: 'institutional',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 13500000]]),
    }

    applyCrosshairToOthers([pane1, pane2, pane3], 'main', '2026-09-18')

    expect(pane1.chart.setCrosshairPosition).not.toHaveBeenCalled()
    expect(pane2.chart.setCrosshairPosition).toHaveBeenCalledWith(30000000, '2026-09-18', pane2.series)
    expect(pane3.chart.setCrosshairPosition).toHaveBeenCalledWith(13500000, '2026-09-18', pane3.series)
  })

  it('來源 pane 自己不會被設定', () => {
    const pane1: SyncPane = {
      id: 'main',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 1008]]),
    }
    const pane2: SyncPane = {
      id: 'volume',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 30000000]]),
    }

    applyCrosshairToOthers([pane1, pane2], 'main', '2026-09-18')

    expect(pane1.chart.setCrosshairPosition).not.toHaveBeenCalled()
  })

  it('time 為 null 時全部 clear', () => {
    const pane1: SyncPane = {
      id: 'main',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 1008]]),
    }
    const pane2: SyncPane = {
      id: 'volume',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 30000000]]),
    }

    applyCrosshairToOthers([pane1, pane2], 'main', null)

    expect(pane1.chart.clearCrosshairPosition).not.toHaveBeenCalled()
    expect(pane2.chart.clearCrosshairPosition).toHaveBeenCalledTimes(1)
  })

  it('某個 pane 沒有那天的資料時只 clear 它', () => {
    const pane1: SyncPane = {
      id: 'main',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-18', 1008]]),
    }
    const pane2: SyncPane = {
      id: 'volume',
      chart: {
        setCrosshairPosition: vi.fn(),
        clearCrosshairPosition: vi.fn(),
      },
      series: {} as any,
      valueByTime: new Map([['2026-09-17', 25000000]]),
    }

    applyCrosshairToOthers([pane1, pane2], 'main', '2026-09-18')

    expect(pane2.chart.clearCrosshairPosition).toHaveBeenCalledTimes(1)
    expect(pane2.chart.setCrosshairPosition).not.toHaveBeenCalled()
  })

  it('crosshairTime', () => {
    expect(crosshairTime({ time: '2026-09-18' })).toBe('2026-09-18')
    expect(crosshairTime({})).toBeNull()
    expect(crosshairTime({ time: 1758153600 })).toBeNull()
  })
})
