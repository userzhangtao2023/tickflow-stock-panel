import { useCallback, useState } from 'react'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { DowStrategyCard, type DowScreenerRow } from './DowStrategyCard'
import { ScreenerTable } from './ScreenerTable'
import type { ColumnConfig } from '@/lib/screener-columns'

const columns: ColumnConfig[] = [
  { id: 'builtin:symbol', source: { type: 'builtin', key: 'symbol' }, label: '标的', visible: true, pinned: true, align: 'left' },
  { id: 'builtin:strategies', source: { type: 'builtin', key: 'strategies' }, label: '策略', visible: true, align: 'left' },
  { id: 'builtin:score', source: { type: 'builtin', key: 'score' }, label: '评分', visible: true, align: 'right' },
]

function DowListHarness({ fetcher }: { fetcher: any }) {
  const [rows, setRows] = useState<DowScreenerRow[]>([])
  const handleResults = useCallback((result: { rows: DowScreenerRow[] } | null) => {
    setRows(result?.rows ?? [])
  }, [])
  return (
    <>
      <DowStrategyCard market="hk" fetcher={fetcher} onResults={handleResults} />
      {rows.length > 0 && (
        <ScreenerTable
          rows={rows}
          columns={columns}
          strategyIdToName={{ dow_trend: '道氏趋势 · 多周期' }}
          symbolStrategyMap={new Map(rows.map(row => [row.symbol, ['dow_trend']]))}
          activeStrategy="dow_trend"
          watchlistSet={new Set()}
          onPreview={() => undefined}
          onToggleWatchlist={() => undefined}
          watchlistPending={false}
        />
      )}
    </>
  )
}

describe('DowStrategyCard', () => {
  it('waits for an explicit click before starting the current-market scan', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dow-strategy/runs') return { ok: true, json: async () => ({ runId: 'scan-hk-1', status: 'running', completed: 0, total: 10 }) }
      if (url.includes('/runs/')) return { ok: true, json: async () => ({ runId: 'scan-hk-1', status: 'complete', completed: 10, total: 10, selected: 0 }) }
      return { ok: true, json: async () => ({ stocks: [] }) }
    })
    render(<DowStrategyCard market="hk" fetcher={fetchMock as any} />)

    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText('点击“执行选股”开始扫描')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '执行选股' }))
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

    await userEvent.click(screen.getByRole('button', { name: '执行选股' }))
    expect(await screen.findByText('港股选股完成，当前暂无符合条件的股票')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '执行选股' }))
    expect(fetchMock).toHaveBeenCalledTimes(6)
  })

  it('publishes local and long-term period matches as shared-list row data', async () => {
    const onResults = vi.fn()
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dow-strategy/runs') return { ok: true, json: async () => ({ runId: 'scan-hk-3', status: 'complete', completed: 10, total: 10 }) }
      return { ok: true, json: async () => ({ metrics: { scoreDate: '2026-07-24' }, stocks: [{ symbol: '700.HK', name: '腾讯控股', strategyScore: 82, triggerTimeframes: ['30m', 'day'], localTriggerTimeframes: ['30m'], longTermTriggerTimeframes: ['day'], formalTimeframes: ['30m'], provisionalTimeframes: ['day'], dataFreshness: 'partial' }] }) }
    })
    render(<DowStrategyCard market="hk" fetcher={fetchMock as any} onResults={onResults} />)
    await userEvent.click(screen.getByRole('button', { name: '执行选股' }))
    expect(await screen.findByText('港股选股完成，共 1 只；结果已载入下方列表')).toBeInTheDocument()
    expect(onResults).toHaveBeenLastCalledWith(expect.objectContaining({
      total: 1,
      asOf: '2026-07-24',
      rows: [expect.objectContaining({
        symbol: '700.HK',
        score: 82,
        strategy_summary: '局部 30m · 长期 日线',
        formal_timeframes: ['30m'],
        provisional_timeframes: ['day'],
      })],
    }))
  })

  it('hands matched stocks to the shared screener table instead of rendering stock cards', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/dow-strategy/runs') {
        return { ok: true, json: async () => ({ runId: 'scan-hk-list', status: 'complete', completed: 10, total: 10 }) }
      }
      return {
        ok: true,
        json: async () => ({
          stocks: [{
            symbol: '700.HK',
            name: '腾讯控股',
            market: 'HK',
            totalScore: 82,
            strategyScore: 82,
            triggerTimeframes: ['30m', 'day'],
            localTriggerTimeframes: ['30m'],
            longTermTriggerTimeframes: ['day'],
            signalTime: '2026-07-24T10:30:00+08:00',
          }],
        }),
      }
    })

    render(<DowListHarness fetcher={fetchMock} />)
    await userEvent.click(screen.getByRole('button', { name: '执行选股' }))

    const table = await screen.findByRole('table')
    expect(table).toBeInTheDocument()
    expect(within(table).getByText('700.HK')).toBeInTheDocument()
    expect(screen.getAllByText('700.HK')).toHaveLength(1)
    expect(within(table).getByText('道氏趋势 · 多周期')).toBeInTheDocument()
    expect(within(table).getByText('82.0')).toBeInTheDocument()
    expect(within(table).getByText('局部 30m · 长期 日线')).toBeInTheDocument()
  })
})
