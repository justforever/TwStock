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
