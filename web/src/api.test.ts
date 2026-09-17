import { describe, it, expect, afterEach, vi } from 'vitest'
import { marketLabel, searchStocks } from './api'

describe('api', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  describe('marketLabel', () => {
    it('TWSE → 上市', () => {
      expect(marketLabel('TWSE')).toBe('上市')
    })

    it('TPEx → 上櫃', () => {
      expect(marketLabel('TPEx')).toBe('上櫃')
    })

    it('ESB → 興櫃', () => {
      expect(marketLabel('ESB')).toBe('興櫃')
    })
  })

  describe('searchStocks', () => {
    it('should call fetch with correct URL', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ query: '台積', count: 0, items: [] }),
          { status: 200 }
        )
      )
      vi.stubGlobal('fetch', mockFetch)

      await searchStocks('台積')

      expect(mockFetch).toHaveBeenCalledOnce()
      const [url] = mockFetch.mock.calls[0]
      expect(url).toBe('/api/stocks?q=%E5%8F%B0%E7%A9%8D&limit=20')
    })

    it('should reject on HTTP error', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        new Response('', { status: 500 })
      )
      vi.stubGlobal('fetch', mockFetch)

      await expect(searchStocks('test')).rejects.toThrow('HTTP 500')
    })
  })
})
