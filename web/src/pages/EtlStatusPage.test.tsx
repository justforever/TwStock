import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import EtlStatusPage from './EtlStatusPage'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('EtlStatusPage', () => {
  it('mock fetch 回兩個端點的假資料 → 表格出現 daily_price_twse、成功、失敗', async () => {
    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/etl/summary')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              count: 2,
              items: [
                {
                  job_name: 'daily_price_twse',
                  last_status: 'success',
                  last_target_date: '2026-09-18',
                  last_target_key: null,
                  last_rows: 1043,
                  last_started_at: '2026-09-18T15:31:02+08:00',
                  last_finished_at: '2026-09-18T15:31:09+08:00',
                  failed_last_7_days: 0,
                  total_runs: 128,
                },
                {
                  job_name: 'daily_price_tpex',
                  last_status: 'failed',
                  last_target_date: '2026-09-18',
                  last_target_key: null,
                  last_rows: 0,
                  last_started_at: '2026-09-18T16:31:02+08:00',
                  last_finished_at: '2026-09-18T16:31:09+08:00',
                  failed_last_7_days: 2,
                  total_runs: 50,
                },
              ],
            }),
        })
      }
      if (url.includes('/api/etl/jobs')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              count: 1,
              items: [
                {
                  job_id: 128,
                  job_name: 'daily_price_twse',
                  target_date: '2026-09-18',
                  target_key: null,
                  status: 'success',
                  rows: 1043,
                  error: null,
                  started_at: '2026-09-18T15:31:02+08:00',
                  finished_at: '2026-09-18T15:31:09+08:00',
                  duration_seconds: 7.0,
                },
              ],
            }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(<EtlStatusPage />)

    const elements = await screen.findAllByText('daily_price_twse')
    expect(elements.length).toBeGreaterThan(0)
    const successElements = await screen.findAllByText('成功')
    const failElements = await screen.findAllByText('失敗')
    expect(successElements.length).toBeGreaterThan(0)
    expect(failElements.length).toBeGreaterThan(0)
  })

  it('錯誤訊息被截斷並加 title 屬性', async () => {
    const longError =
      'This is a very long error message that should be truncated because it exceeds eighty characters in length'

    ;(globalThis.fetch as any).mockImplementation((url: string) => {
      if (url.includes('/api/etl/summary')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              count: 0,
              items: [],
            }),
        })
      }
      if (url.includes('/api/etl/jobs')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              count: 1,
              items: [
                {
                  job_id: 1,
                  job_name: 'test_job',
                  target_date: null,
                  target_key: null,
                  status: 'failed',
                  rows: 0,
                  error: longError,
                  started_at: '2026-09-18T15:31:02+08:00',
                  finished_at: '2026-09-18T15:31:09+08:00',
                  duration_seconds: 7.0,
                },
              ],
            }),
        })
      }
      return Promise.reject(new Error('Unexpected URL'))
    })

    render(<EtlStatusPage />)

    const errorSpan = await screen.findByTitle(longError)
    expect(errorSpan.textContent).toHaveLength(81) // 80 chars + "…"
  })
})
