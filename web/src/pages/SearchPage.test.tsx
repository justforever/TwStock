import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import SearchPage from './SearchPage'

describe('SearchPage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    cleanup()
  })

  const renderComponent = () => {
    render(
      <MemoryRouter>
        <SearchPage />
      </MemoryRouter>
    )
  }

  it('should search and display results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ query: '2330', count: 1, items: [
            {
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              industry: '半導體業',
              listed_date: '1994-09-05',
              is_etf: false
            }
          ] }),
          { status: 200 }
        )
      )
    )

    const user = userEvent.setup()
    renderComponent()

    const input = screen.getByLabelText('搜尋股票代號或名稱')
    await user.type(input, '2330')

    const result = await screen.findByText('2330 台積電')
    expect(result).toBeInTheDocument()
    expect(screen.getByText('上市')).toBeInTheDocument()

    const link = screen.getByRole('link', { name: /2330 台積電/ })
    expect(link).toHaveAttribute('href', '/stock/2330')
  })

  it('should show no results message when API returns empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ query: 'xyz', count: 0, items: [] }),
          { status: 200 }
        )
      )
    )

    const user = userEvent.setup()
    renderComponent()

    const input = screen.getByLabelText('搜尋股票代號或名稱')
    await user.type(input, 'xyz')

    await screen.findByText('查無符合的股票')
  })

  it('should show error message on API error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('', { status: 500 })
      )
    )

    const user = userEvent.setup()
    renderComponent()

    const input = screen.getByLabelText('搜尋股票代號或名稱')
    await user.type(input, 'test')

    await screen.findByRole('alert')
    expect(screen.getByRole('alert')).toHaveTextContent('搜尋失敗')
  })

  it('should display ETF badge for ETF stocks', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ query: '0050', count: 1, items: [
            {
              stock_id: '0050',
              name: '元大台灣50',
              market: 'TWSE',
              industry: null,
              listed_date: '2003-06-30',
              is_etf: true
            }
          ] }),
          { status: 200 }
        )
      )
    )

    const user = userEvent.setup()
    renderComponent()

    const input = screen.getByLabelText('搜尋股票代號或名稱')
    await user.type(input, '0050')

    await screen.findByText(/0050 元大台灣50/)
    expect(screen.getByText('ETF')).toBeInTheDocument()
  })

  it('should focus input with / shortcut key', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ query: '', count: 0, items: [] }),
          { status: 200 }
        )
      )
    )

    const user = userEvent.setup()
    renderComponent()

    const input = screen.getByLabelText('搜尋股票代號或名稱') as HTMLInputElement
    input.blur()

    await user.keyboard('/')

    expect(input).toHaveFocus()
  })

  it('should clear results when input is cleared', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ query: '2330', count: 1, items: [
            {
              stock_id: '2330',
              name: '台積電',
              market: 'TWSE',
              industry: '半導體業',
              listed_date: '1994-09-05',
              is_etf: false
            }
          ] }),
          { status: 200 }
        )
      )
    )

    const user = userEvent.setup()
    renderComponent()

    const input = screen.getByLabelText('搜尋股票代號或名稱')
    await user.type(input, '2330')

    await screen.findByText('2330 台積電')

    await user.clear(input)

    expect(screen.queryByText('2330 台積電')).not.toBeInTheDocument()
    expect(screen.queryByText('查無符合的股票')).not.toBeInTheDocument()
  })
})
