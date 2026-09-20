export type Market = 'TWSE' | 'TPEx' | 'ESB'

export interface StockItem {
  stock_id: string
  name: string
  market: Market
  industry: string | null
  listed_date: string | null
  is_etf: boolean
}

export interface StockSearchResponse {
  query: string
  count: number
  items: StockItem[]
}

/** 市場代碼轉中文：TWSE→上市、TPEx→上櫃、ESB→興櫃 */
export function marketLabel(market: Market): string {
  switch (market) {
    case 'TWSE':
      return '上市'
    case 'TPEx':
      return '上櫃'
    case 'ESB':
      return '興櫃'
    default:
      const _exhaustive: never = market
      return _exhaustive
  }
}

export interface PriceBar {
  time: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  change: number | null
  volume: number
  turnover: number
  transactions: number
}

export interface PriceResponse {
  stock_id: string
  name: string
  market: Market
  adjusted: boolean
  from: string
  to: string
  count: number
  items: PriceBar[]
}

export interface StockDetail {
  stock_id: string
  name: string
  market: Market
  industry: string | null
  listed_date: string | null
  is_etf: boolean
  is_active: boolean
  latest: PriceBar | null
}

export interface EtlJobSummaryItem {
  job_name: string
  last_status: 'running' | 'success' | 'failed' | 'skipped'
  last_target_date: string | null
  last_target_key: string | null
  last_rows: number
  last_started_at: string
  last_finished_at: string | null
  failed_last_7_days: number
  total_runs: number
}

export interface EtlJobRun {
  job_id: number
  job_name: string
  target_date: string | null
  target_key: string | null
  status: 'running' | 'success' | 'failed' | 'skipped'
  rows: number
  error: string | null
  started_at: string
  finished_at: string | null
  duration_seconds: number | null
}

/** 呼叫 GET /api/stocks；非 2xx 丟 Error(`HTTP ${status}`) */
export async function searchStocks(
  q: string,
  signal?: AbortSignal
): Promise<StockSearchResponse> {
  const url = `/api/stocks?q=${encodeURIComponent(q)}&limit=20`
  const response = await fetch(url, { signal })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export async function fetchStock(
  stockId: string,
  signal?: AbortSignal
): Promise<StockDetail> {
  const response = await fetch(`/api/stocks/${stockId}`, { signal })
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('查無此個股')
    }
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export async function fetchPrices(
  stockId: string,
  params: { from?: string; to?: string; adj?: boolean; limit?: number },
  signal?: AbortSignal
): Promise<PriceResponse> {
  const url = new URL(`/api/stocks/${stockId}/prices`, window.location.origin)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) {
      url.searchParams.set(key, String(value))
    }
  })
  const response = await fetch(url.toString(), { signal })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export async function fetchEtlSummary(
  signal?: AbortSignal
): Promise<{ count: number; items: EtlJobSummaryItem[] }> {
  const response = await fetch('/api/etl/summary', { signal })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}

export async function fetchEtlJobs(
  limit: number,
  signal?: AbortSignal
): Promise<{ count: number; items: EtlJobRun[] }> {
  const url = `/api/etl/jobs?limit=${Math.min(limit, 500)}`
  const response = await fetch(url, { signal })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }
  return response.json()
}
