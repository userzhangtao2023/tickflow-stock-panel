import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { buildDowMiniChartOption } from '@/components/dow-monitor/DowMiniChart'
import type {
  DowMonitorChart,
  DowMonitorNotification,
  DowMonitorOverviewResponse,
  DowMonitorOverviewSymbol,
  DowMonitorTimeframeState,
  DowTimeframe,
} from '@/components/dow-monitor/types'

import { DowMonitor } from './DowMonitor'

const hooks = vi.hoisted(() => ({
  add: vi.fn(),
  remove: vi.fn(),
  setEnabled: vi.fn(),
}))

vi.mock('@/components/dow-monitor/useDowMonitor', () => ({
  useDowMonitorOverview: () => ({ data: overview, isLoading: false }),
  useDowNotifications: () => ({ data: { notifications }, isLoading: false }),
  useAddDowMonitorSymbol: () => ({ mutate: hooks.add, isPending: false }),
  useRemoveDowMonitorSymbol: () => ({ mutate: hooks.remove, isPending: false }),
  useSetDowMonitorEnabled: () => ({ mutate: hooks.setEnabled, isPending: false }),
}))

vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  })),
}))

const TIMEFRAMES: DowTimeframe[] = ['5m', '15m', '30m', '60m', 'day']

const bars = [
  {
    index: 0,
    timestamp: '2026-07-23T01:00:00Z',
    open: 10,
    high: 10.6,
    low: 9.8,
    close: 10.4,
    volume: 100,
  },
  {
    index: 1,
    timestamp: '2026-07-23T01:05:00Z',
    open: 10.4,
    high: 11.2,
    low: 10.2,
    close: 11,
    volume: 120,
  },
]

const authoritativeChart: DowMonitorChart = {
  bars,
  lines: [
    {
      id: 'main-support',
      side: 'SUPPORT',
      role: 'MAIN',
      generation: 1,
      anchorIndexes: [0, 1],
      anchorTimes: [bars[0].timestamp, bars[1].timestamp],
      anchorPrices: [9.8, 10.2],
      createdIndex: 1,
      invalidatedIndex: null,
      controlsSignals: true,
    },
    {
      id: 'acceleration-resistance',
      side: 'RESISTANCE',
      role: 'ACCELERATION',
      generation: 1,
      anchorIndexes: [0, 1],
      anchorTimes: [bars[0].timestamp, bars[1].timestamp],
      anchorPrices: [10.6, 11.2],
      createdIndex: 1,
      invalidatedIndex: null,
      controlsSignals: false,
    },
  ],
  signals: [
    {
      side: 'BUY',
      barIndex: 0,
      barTime: bars[0].timestamp,
      price: 10.4,
      reason: 'backend buy',
      confidence: 'HIGH',
      lineId: 'main-support',
      firstCrossIndex: null,
      firstCrossTime: null,
      volumeRatio: null,
      pattern: '突破',
      evidence: [],
    },
    {
      side: 'RISK',
      barIndex: 1,
      barTime: bars[1].timestamp,
      price: 11,
      reason: 'backend risk',
      confidence: 'HIGH',
      lineId: 'acceleration-resistance',
      firstCrossIndex: null,
      firstCrossTime: null,
      volumeRatio: null,
      pattern: '风险退出',
      evidence: [],
    },
  ],
  longTerm: {
    first_anchor_time: bars[0].timestamp,
    first_anchor_price: 9.6,
    second_anchor_time: bars[1].timestamp,
    second_anchor_price: 10,
  },
}

function state(
  symbol: string,
  market: 'cn' | 'hk' | 'us',
  timeframe: DowTimeframe,
  actionCode?: string,
  freshness: DowMonitorTimeframeState['freshness_state'] = 'LIVE',
  chart: DowMonitorChart = { bars, lines: [], signals: [] },
): DowMonitorTimeframeState {
  return {
    symbol,
    market,
    timeframe,
    freshness_state: freshness,
    source_timestamp: '2026-07-23T01:05:00Z',
    snapshot: actionCode ? { action_code: actionCode } : {},
    chart,
    updated_at: '2026-07-23T01:05:01Z',
  }
}

function notification(
  symbol: string,
  market: 'cn' | 'hk' | 'us',
  side: 'BUY' | 'SELL' | 'RISK',
  action: string,
): DowMonitorNotification {
  return {
    notification_id: `${symbol}-${side}`,
    event_key: `${symbol}-${side}-1`,
    symbol,
    market,
    timeframe: '5m',
    side,
    action_name: action,
    shape_name: side === 'BUY' ? '向上突破' : '加速线失守',
    triggered_at: '2026-07-23T01:05:00Z',
    trigger_price: 11,
    snapshot_payload: {},
    read_at: null,
  }
}

const hkNotification = notification('01347.HK', 'hk', 'BUY', '买入')
const usNotification = notification('INTC.US', 'us', 'SELL', '卖出')

function symbolFixture(
  symbol: string,
  market: 'cn' | 'hk' | 'us',
  enabled: boolean,
  latest: DowMonitorNotification | null,
  states: DowMonitorOverviewSymbol['states'],
): DowMonitorOverviewSymbol {
  return {
    symbol,
    market,
    enabled,
    created_at: '2026-07-23T00:00:00Z',
    updated_at: '2026-07-23T01:05:01Z',
    states,
    latest_notification: latest,
    last_success_at: '2026-07-23T01:05:01Z',
    last_error: null,
  }
}

const overview: DowMonitorOverviewResponse = {
  symbols: [
    symbolFixture('01347.HK', 'hk', true, hkNotification, {
      '5m': state('01347.HK', 'hk', '5m', 'OPEN_LONG', 'LIVE', authoritativeChart),
      '15m': state('01347.HK', 'hk', '15m', 'CLOSE_LONG'),
      '30m': state('01347.HK', 'hk', '30m', 'WATCH'),
      '60m': state('01347.HK', 'hk', '60m', 'OPEN_LONG', 'STALE_DATA'),
      day: state('01347.HK', 'hk', 'day'),
    }),
    symbolFixture('INTC.US', 'us', true, usNotification, Object.fromEntries(
      TIMEFRAMES.map(timeframe => [
        timeframe,
        state('INTC.US', 'us', timeframe, 'CLOSE_LONG'),
      ]),
    )),
    symbolFixture('600000.SH', 'cn', true, null, {
      '5m': state('600000.SH', 'cn', '5m', 'OPEN_LONG', 'ANALYSIS_PAUSED'),
    }),
    symbolFixture('600519.SH', 'cn', true, null, {
      '5m': state('600519.SH', 'cn', '5m'),
    }),
  ],
  source: 'webstock',
  source_timestamp: '2026-07-23T01:05:00Z',
}

const notifications = [hkNotification, usNotification]

beforeEach(() => {
  hooks.add.mockReset()
  hooks.remove.mockReset()
  hooks.setEnabled.mockReset()
})

describe('Dow monitor page', () => {
  it('shows a wide four-column grid and filters cards plus signals by the same market', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    expect(screen.getByTestId('dow-monitor-grid')).toHaveClass('2xl:grid-cols-4')
    await user.click(screen.getByRole('button', { name: '港股' }))

    expect(screen.getByTestId('card-01347.HK')).toBeInTheDocument()
    expect(screen.queryByTestId('card-INTC.US')).not.toBeInTheDocument()
    expect(screen.getByTestId('signal-01347.HK')).toBeInTheDocument()
    expect(screen.queryByTestId('signal-INTC.US')).not.toBeInTheDocument()
  })

  it('filters both cards and notifications by active, buy, and sell signal states', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    await user.click(screen.getByRole('button', { name: '有信号' }))
    expect(screen.queryByTestId('card-600000.SH')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '仅买点' }))
    expect(screen.getByTestId('card-01347.HK')).toBeInTheDocument()
    expect(screen.queryByTestId('card-INTC.US')).not.toBeInTheDocument()
    expect(screen.getByTestId('signal-01347.HK')).toBeInTheDocument()
    expect(screen.queryByTestId('signal-INTC.US')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '仅卖点' }))
    expect(screen.queryByTestId('card-01347.HK')).not.toBeInTheDocument()
    expect(screen.getByTestId('card-INTC.US')).toBeInTheDocument()
    expect(screen.queryByTestId('signal-01347.HK')).not.toBeInTheDocument()
    expect(screen.getByTestId('signal-INTC.US')).toBeInTheDocument()
  })

  it('never mutates monitoring when switching market tabs', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    await user.click(screen.getByRole('button', { name: '美股' }))

    expect(hooks.setEnabled).not.toHaveBeenCalled()
  })

  it('keeps switches independent and routes add/remove through Task 8 mutations', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    await user.click(screen.getByRole('switch', { name: '01347.HK 监控开关' }))
    expect(hooks.setEnabled).toHaveBeenCalledWith({ symbol: '01347.HK', enabled: false })
    expect(hooks.setEnabled).not.toHaveBeenCalledWith(
      expect.objectContaining({ symbol: 'INTC.US' }),
    )

    await user.type(screen.getByRole('textbox', { name: '股票代码' }), '  aapl.us ')
    await user.click(screen.getByRole('button', { name: '添加' }))
    expect(hooks.add).toHaveBeenCalledWith({ symbol: 'AAPL.US', enabled: true })

    await user.click(screen.getByRole('button', { name: '移除 INTC.US' }))
    expect(hooks.remove).toHaveBeenCalledWith('INTC.US')
  })

  it('shows all five timeframe badges and changes only the selected card mini chart', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    render(<DowMonitor onOpen={onOpen} />)

    const hongKongCard = screen.getByTestId('card-01347.HK')
    const unitedStatesCard = screen.getByTestId('card-INTC.US')
    for (const label of ['5分', '15分', '30分', '60分', '日K']) {
      expect(within(hongKongCard).getByRole('button', { name: label })).toBeInTheDocument()
    }

    expect(within(hongKongCard).getByTestId('mini-chart-01347.HK-5m')).toBeInTheDocument()
    expect(within(unitedStatesCard).getByTestId('mini-chart-INTC.US-5m')).toBeInTheDocument()
    await user.click(within(hongKongCard).getByRole('button', { name: '15分' }))
    expect(within(hongKongCard).getByTestId('mini-chart-01347.HK-15m')).toBeInTheDocument()
    expect(within(unitedStatesCard).getByTestId('mini-chart-INTC.US-5m')).toBeInTheDocument()

    await user.click(hongKongCard)
    expect(onOpen).toHaveBeenCalledWith('01347.HK', '15m')
  })

  it('uses green buy, red sell/risk, yellow watch, gray none, and blocked stale states', () => {
    render(<DowMonitor />)
    const card = screen.getByTestId('card-01347.HK')

    expect(within(card).getByRole('button', { name: '5分' })).toHaveClass('text-emerald-400')
    expect(within(card).getByRole('button', { name: '15分' })).toHaveClass('text-red-400')
    expect(within(card).getByRole('button', { name: '30分' })).toHaveClass('text-amber-400')
    expect(within(card).getByRole('button', { name: '日K' })).toHaveClass('text-muted')
    expect(within(card).getByRole('button', { name: '60分' })).toHaveAttribute(
      'data-tradable',
      'false',
    )
    expect(within(card).getByText('买入')).toHaveClass('text-emerald-400')

    expect(screen.getByTestId('signal-INTC.US')).toHaveClass('border-red-500/30')
    expect(screen.getByTestId('card-600000.SH')).toHaveAttribute('data-tradable', 'false')
    expect(within(screen.getByTestId('card-600000.SH')).getByText('分析暂停')).toBeInTheDocument()
  })

  it('shows the compact no-signal state without inventing a notification', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    await user.click(screen.getByRole('button', { name: 'A股' }))

    expect(screen.getByText('暂无可交易信号')).toBeInTheDocument()
    expect(screen.getByTestId('dow-monitor-signal-rail')).toHaveTextContent('暂无最新信号')
  })
})

describe('Dow mini chart semantics', () => {
  it('uses solid blue/magenta main lines, dashed acceleration, and backend signal colors', () => {
    const option = buildDowMiniChartOption(authoritativeChart)
    const series = option.series as Array<Record<string, any>>
    const main = series.find(item => item.id === 'main-support')
    const acceleration = series.find(item => item.id === 'acceleration-resistance')
    const candle = series.find(item => item.id === 'candles')

    expect(main?.lineStyle).toMatchObject({ color: '#3B82F6', type: 'solid' })
    expect(acceleration?.lineStyle).toMatchObject({ color: '#D946EF', type: 'dashed' })
    expect(candle?.markPoint.data).toEqual(expect.arrayContaining([
      expect.objectContaining({ itemStyle: { color: '#22C55E' } }),
      expect.objectContaining({ itemStyle: { color: '#EF4444' } }),
    ]))
    expect(option.xAxis).toMatchObject({ axisLabel: { show: false } })
    expect(option.yAxis).toMatchObject({ axisLabel: { show: false } })
    expect(option.legend).toBeUndefined()
  })

  it('draws the amber long-term line only when both persisted anchors are complete', () => {
    const complete = buildDowMiniChartOption(authoritativeChart).series as Array<Record<string, any>>
    const incomplete = buildDowMiniChartOption({
      ...authoritativeChart,
      longTerm: {
        first_anchor_time: bars[0].timestamp,
        first_anchor_price: 9.6,
        second_anchor_time: bars[1].timestamp,
      },
    }).series as Array<Record<string, any>>

    expect(complete.find(item => item.id === 'long-term')?.lineStyle).toMatchObject({
      color: '#F59E0B',
    })
    expect(incomplete.some(item => item.id === 'long-term')).toBe(false)
  })

  it('does not infer lines or signals when the backend returns none', () => {
    const option = buildDowMiniChartOption({ bars, lines: [], signals: [] })
    const series = option.series as Array<Record<string, any>>
    const candle = series.find(item => item.id === 'candles')

    expect(series.filter(item => item.type === 'line')).toHaveLength(0)
    expect(candle?.markPoint.data).toEqual([])
  })

  it('resizes the chart from the existing window resize convention', () => {
    render(<DowMonitor />)
    fireEvent(window, new Event('resize'))
    expect(screen.getByTestId('mini-chart-01347.HK-5m')).toBeInTheDocument()
  })
})
