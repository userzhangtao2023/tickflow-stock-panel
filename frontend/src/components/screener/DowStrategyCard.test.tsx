import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DowStrategyCard } from './DowStrategyCard'

describe('DowStrategyCard', () => {
  it('starts a current-market scan and shows progress before loading its pool', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dow-strategy/runs') return { ok: true, json: async () => ({ runId: 'scan-hk-1', status: 'running', completed: 0, total: 10 }) }
      if (url.includes('/runs/')) return { ok: true, json: async () => ({ runId: 'scan-hk-1', status: 'complete', completed: 10, total: 10, selected: 0 }) }
      return { ok: true, json: async () => ({ stocks: [] }) }
    })
    render(<DowStrategyCard market="hk" fetcher={fetchMock as any} />)

    expect(await screen.findByText('港股选股完成，当前暂无符合条件的股票')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('/api/dow-strategy/runs', expect.objectContaining({ method: 'POST' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/dow-strategy/runs/scan-hk-1')
  })

  it('shows a completed empty-state message when the market pool has no matches', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dow-strategy/runs') return { ok: true, json: async () => ({ runId: 'scan-hk-2', status: 'complete', completed: 10, total: 10 }) }
      return { ok: true, json: async () => ({ stocks: [] }) }
    })
    render(<DowStrategyCard market="hk" fetcher={fetchMock as any} />)

    expect(await screen.findByText('港股选股完成，当前暂无符合条件的股票')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '刷新选股结果' }))
    expect(fetchMock).toHaveBeenCalledTimes(4)
  })

  it('runs selection, shows three periods and backtests the selected stock', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('/backtest')) return { ok: true, json: async () => ({ metrics: { tradeCount: 1, cumulativeReturn: .12, maximumDrawdown: -.03, winRate: 1 }, trades: [] }) }
      if (url === '/api/dow-strategy/runs') return { ok: true, json: async () => ({ runId: 'scan-hk-3', status: 'complete', completed: 10, total: 10 }) }
      if (url.includes('/700.HK')) return { ok: true, json: async () => ({ timeframeStates: { '15m': { available: true, action: 'WATCH' }, '30m': { available: true, action: 'OPEN_LONG' }, day: { available: false, reason: '暂不可用' } }, dataFreshness: 'partial' }) }
      return { ok: true, json: async () => ({ stocks: [{ symbol: '700.HK', name: '腾讯控股', strategyScore: 82, triggerTimeframes: ['30m'], dataFreshness: 'partial' }] }) }
    })
    render(<DowStrategyCard market="hk" fetcher={fetchMock as any} />)
    expect(await screen.findByText(/700.HK/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /700.HK/ }))
    expect(await screen.findByText('OPEN_LONG')).toBeInTheDocument()
    expect(screen.getByText('15分钟')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '回测当前股票' }))
    expect(await screen.findByText('12.00%')).toBeInTheDocument()
  })
})
