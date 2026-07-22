import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DowStrategyCard } from './DowStrategyCard'

describe('DowStrategyCard', () => {
  it('runs selection, shows three periods and backtests the selected stock', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.includes('/backtest')) return { ok: true, json: async () => ({ metrics: { tradeCount: 1, cumulativeReturn: .12, maximumDrawdown: -.03, winRate: 1 }, trades: [] }) }
      if (url.includes('/700.HK')) return { ok: true, json: async () => ({ timeframeStates: { '15m': { available: true, action: 'WATCH' }, '30m': { available: true, action: 'OPEN_LONG' }, day: { available: false, reason: '暂不可用' } }, dataFreshness: 'partial' }) }
      return { ok: true, json: async () => ({ stocks: [{ symbol: '700.HK', name: '腾讯控股', strategyScore: 82, triggerTimeframes: ['30m'], dataFreshness: 'partial' }] }) }
    })
    render(<DowStrategyCard market="hk" fetcher={fetchMock as any} />)
    await userEvent.click(screen.getByRole('button', { name: '执行选股' }))
    expect(await screen.findByText(/700.HK/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /700.HK/ }))
    expect(await screen.findByText('OPEN_LONG')).toBeInTheDocument()
    expect(screen.getByText('15分钟')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '回测当前股票' }))
    expect(await screen.findByText('12.00%')).toBeInTheDocument()
  })
})
