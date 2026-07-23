import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildDowMiniChartOption,
  DowMiniChart,
} from '@/components/dow-monitor/DowMiniChart'
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
  markRead: vi.fn(),
  remove: vi.fn(),
  setEnabled: vi.fn(),
  overview: {} as Record<string, unknown>,
  notifications: {} as Record<string, unknown>,
  status: {} as Record<string, unknown>,
  addState: {} as Record<string, unknown>,
  readState: {} as Record<string, unknown>,
  removeState: {} as Record<string, unknown>,
  toggleState: {} as Record<string, unknown>,
}))

const chartMocks = vi.hoisted(() => ({
  disconnect: vi.fn(),
  dispose: vi.fn(),
  init: vi.fn(),
  observe: vi.fn(),
  resize: vi.fn(),
  setOption: vi.fn(),
  resizeCallback: undefined as ResizeObserverCallback | undefined,
}))

vi.mock('@/components/dow-monitor/useDowMonitor', () => ({
  useDowMonitorOverview: () => hooks.overview,
  useDowMonitorStatus: () => hooks.status,
  useDowNotifications: () => hooks.notifications,
  useAddDowMonitorSymbol: () => ({ mutate: hooks.add, ...hooks.addState }),
  useMarkDowNotificationRead: () => ({ mutate: hooks.markRead, ...hooks.readState }),
  useRemoveDowMonitorSymbol: () => ({ mutate: hooks.remove, ...hooks.removeState }),
  useSetDowMonitorEnabled: () => ({ mutate: hooks.setEnabled, ...hooks.toggleState }),
}))

vi.mock('echarts', () => ({
  init: chartMocks.init,
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
    name: symbol === '01347.HK' ? '华丰科技' : null,
    last_price: symbol === '01347.HK' ? 13.47 : 21.5,
    change_pct: symbol === '01347.HK' ? 0.0125 : -0.02,
    quote_timestamp: 1_774_752_700_000,
    market,
    enabled,
    created_at: '2026-07-23T00:00:00Z',
    updated_at: '2026-07-23T01:05:01Z',
    states,
    latest_notification: latest,
    last_success_at: '2026-07-23T01:05:01Z',
    last_error: null,
  } as DowMonitorOverviewSymbol
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
    symbolFixture('600519.SH', 'cn', false, null, {
      '5m': state('600519.SH', 'cn', '5m', 'OPEN_LONG', 'LIVE', authoritativeChart),
    }),
    symbolFixture('000001.SZ', 'cn', true, null, {
      '5m': state('000001.SZ', 'cn', '5m'),
    }),
  ],
  source: 'webstock',
  source_timestamp: '2026-07-23T01:05:00Z',
}

const notifications = [hkNotification, usNotification]

beforeEach(() => {
  hooks.add.mockReset()
  hooks.markRead.mockReset()
  hooks.remove.mockReset()
  hooks.setEnabled.mockReset()
  hooks.add.mockImplementation((_variables, options) => options?.onSuccess?.())
  chartMocks.disconnect.mockReset()
  chartMocks.dispose.mockReset()
  chartMocks.init.mockReset()
  chartMocks.observe.mockReset()
  chartMocks.resize.mockReset()
  chartMocks.setOption.mockReset()
  chartMocks.resizeCallback = undefined
  chartMocks.init.mockReturnValue({
    dispose: chartMocks.dispose,
    resize: chartMocks.resize,
    setOption: chartMocks.setOption,
  })
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: ResizeObserverCallback) {
      chartMocks.resizeCallback = callback
    }
    observe = chartMocks.observe
    disconnect = chartMocks.disconnect
  })
  hooks.overview = {
    data: overview,
    isError: false,
    isLoading: false,
  }
  hooks.notifications = {
    data: { notifications },
    isError: false,
    isLoading: false,
  }
  hooks.status = {
    data: {
      running: true,
      poll_seconds: 15,
      source: 'webstock',
      last_started_at: '2026-07-23T01:05:00Z',
      last_completed_at: '2026-07-23T01:05:00Z',
      last_success_at: '2026-07-23T01:05:00Z',
      last_error: null,
      errors: {},
    },
    isError: false,
    isLoading: false,
  }
  hooks.addState = { isError: false, isPending: false }
  hooks.readState = { isError: false, isPending: false }
  hooks.removeState = { isError: false, isPending: false }
  hooks.toggleState = { isError: false, isPending: false }
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Dow monitor page', () => {
  it('shows a wide four-column grid and filters cards plus signals by the same market', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    expect(screen.getByTestId('dow-monitor-grid')).toHaveClass(
      'grid-cols-1',
      'md:grid-cols-2',
      'xl:grid-cols-3',
      '2xl:grid-cols-4',
    )
    await user.click(screen.getByRole('button', { name: '港股' }))

    expect(screen.getByTestId('card-01347.HK')).toBeInTheDocument()
    expect(screen.queryByTestId('card-INTC.US')).not.toBeInTheDocument()
    expect(screen.getByTestId('signal-01347.HK')).toBeInTheDocument()
    expect(screen.queryByTestId('signal-INTC.US')).not.toBeInTheDocument()
  })

  it('uses authoritative quote header fields and only falls back to the symbol for a missing name', () => {
    render(<DowMonitor />)

    const named = screen.getByTestId('card-01347.HK')
    expect(within(named).getByText('华丰科技')).toBeInTheDocument()
    expect(within(named).getByText('13.47')).toBeInTheDocument()
    expect(within(named).getByText('+1.25%')).toBeInTheDocument()
    expect(within(named).queryByText('+5.77%')).not.toBeInTheDocument()

    const unnamed = screen.getByTestId('card-INTC.US')
    expect(within(unnamed).getAllByText('INTC.US')).toHaveLength(1)
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
    expect(hooks.add).toHaveBeenCalledWith(
      { symbol: 'AAPL.US', enabled: true },
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    )
    expect(screen.getByRole('textbox', { name: '股票代码' })).toHaveValue('')

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

    await user.click(within(hongKongCard).getByRole('button', { name: '打开 01347.HK 详情' }))
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

    const disabled = screen.getByTestId('card-600519.SH')
    expect(disabled).toHaveAttribute('data-tradable', 'false')
    expect(within(disabled).getByText('监控已暂停')).toBeInTheDocument()
    for (const label of ['5分', '15分', '30分', '60分', '日K']) {
      expect(within(disabled).getByRole('button', { name: label })).toHaveClass('text-muted')
      expect(within(disabled).getByRole('button', { name: label })).not.toHaveClass(
        'text-emerald-400',
        'text-red-400',
      )
    }
  })

  it('shows the compact no-signal state without inventing a notification', async () => {
    const user = userEvent.setup()
    render(<DowMonitor />)

    await user.click(screen.getByRole('button', { name: 'A股' }))

    expect(screen.getByText('暂无可交易信号')).toBeInTheDocument()
    expect(screen.getByTestId('dow-monitor-signal-rail')).toHaveTextContent('暂无最新信号')
  })

  it('retains prior layout but blocks every card when queries disconnect', () => {
    hooks.overview = { data: overview, isError: true, isLoading: false }
    hooks.notifications = {
      data: { notifications },
      isError: true,
      isLoading: false,
    }

    render(<DowMonitor />)

    expect(screen.getByRole('alert')).toHaveTextContent('监控状态连接失败')
    expect(screen.getByRole('alert')).toHaveTextContent('通知连接失败')
    expect(screen.getByTestId('card-01347.HK')).toHaveAttribute('data-tradable', 'false')
    for (const label of ['5分', '15分', '30分', '60分', '日K']) {
      expect(
        within(screen.getByTestId('card-01347.HK')).getByRole('button', { name: label }),
      ).toHaveClass('text-muted')
    }
    expect(screen.getByTestId('signal-01347.HK')).toBeInTheDocument()
  })

  it('blocks retained data when backend status is stopped and exposes loading states', () => {
    hooks.status = {
      data: { ...(hooks.status.data as object), running: false },
      isError: false,
      isLoading: false,
    }
    const { rerender } = render(<DowMonitor />)

    expect(screen.getByRole('alert')).toHaveTextContent('后台监控未运行')
    expect(screen.getByTestId('card-01347.HK')).toHaveAttribute('data-tradable', 'false')
    expect(screen.queryByText('后台持续运行')).not.toBeInTheDocument()

    hooks.status = { data: undefined, isError: false, isLoading: true }
    hooks.notifications = { data: undefined, isError: false, isLoading: true }
    rerender(<DowMonitor />)
    expect(screen.getByRole('alert')).toHaveTextContent('正在连接监控服务')
    expect(screen.getByTestId('dow-monitor-signal-rail')).toHaveTextContent('正在加载通知')
    expect(screen.getByText('数据源不可用')).toBeInTheDocument()
  })

  it('keeps failed mutations visible and retryable, clearing add input only on success', async () => {
    const user = userEvent.setup()
    hooks.addState = { isError: true, isPending: false, error: new Error('add failed') }
    hooks.removeState = { isError: true, isPending: false, error: new Error('remove failed') }
    hooks.toggleState = { isError: true, isPending: false, error: new Error('toggle failed') }
    hooks.readState = { isError: true, isPending: false, error: new Error('read failed') }
    hooks.add.mockImplementation(() => undefined)
    const { rerender } = render(<DowMonitor />)

    expect(screen.getByRole('alert')).toHaveTextContent('添加失败，请重试')
    expect(screen.getByRole('alert')).toHaveTextContent('移除失败，请重试')
    expect(screen.getByRole('alert')).toHaveTextContent('监控开关更新失败，请重试')
    expect(screen.getByRole('alert')).toHaveTextContent('标记已读失败，请重试')

    const input = screen.getByRole('textbox', { name: '股票代码' })
    await user.type(input, 'aapl.us')
    await user.click(screen.getByRole('button', { name: '添加' }))
    expect(input).toHaveValue('aapl.us')
    expect(screen.getByRole('button', { name: '添加' })).not.toBeDisabled()
    expect(screen.getByRole('switch', { name: '01347.HK 监控开关' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: '移除 INTC.US' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: '标记 01347.HK 已读' })).not.toBeDisabled()

    hooks.addState = { isError: false, isPending: false }
    hooks.add.mockImplementation((_variables, options) => options?.onSuccess?.())
    rerender(<DowMonitor />)
    await user.click(screen.getByRole('button', { name: '添加' }))
    expect(input).toHaveValue('')
  })

  it('keeps pending mutation controls explicit and scoped', () => {
    hooks.addState = { isError: false, isPending: true }
    hooks.toggleState = {
      isError: false,
      isPending: true,
      variables: { symbol: '01347.HK', enabled: false },
    }
    hooks.removeState = {
      isError: false,
      isPending: true,
      variables: 'INTC.US',
    }
    hooks.readState = {
      isError: false,
      isPending: true,
      variables: hkNotification.notification_id,
    }

    render(<DowMonitor />)

    expect(screen.getByRole('button', { name: '添加中' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: '01347.HK 监控开关' })).toBeDisabled()
    expect(screen.getByRole('switch', { name: 'INTC.US 监控开关' })).not.toBeDisabled()
    expect(screen.getByRole('button', { name: '移除 INTC.US' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '标记 01347.HK 已读' })).toBeDisabled()
  })

  it('uses a dedicated detail control and never opens from nested keyboard actions', async () => {
    const user = userEvent.setup()
    const onOpen = vi.fn()
    render(<DowMonitor onOpen={onOpen} />)
    const card = screen.getByTestId('card-01347.HK')
    expect(card).not.toHaveAttribute('role', 'button')

    for (const control of [
      within(card).getByRole('switch', { name: '01347.HK 监控开关' }),
      within(card).getByRole('button', { name: '移除 01347.HK' }),
      within(card).getByRole('button', { name: '15分' }),
    ]) {
      control.focus()
      await user.keyboard('{Enter}')
      await user.keyboard(' ')
      expect(onOpen).not.toHaveBeenCalled()
    }

    const open = within(card).getByRole('button', { name: '打开 01347.HK 详情' })
    open.focus()
    await user.keyboard('{Enter}')
    expect(onOpen).toHaveBeenCalledWith('01347.HK', '15m')
  })

  it('survives legacy malformed chart payloads without rendering invented semantics', () => {
    const legacy = structuredClone(overview)
    legacy.symbols[0].states['5m']!.chart = {
      bars: [null, { timestamp: 'not-a-time', open: 'bad' }],
      lines: [{ role: 'FUTURE_ROLE', side: 'UNKNOWN' }],
      signals: [{ side: 'HOLD', price: 'bad' }],
      longTerm: { first_anchor_time: 'not-a-time', first_anchor_price: 1 },
    } as unknown as DowMonitorChart
    hooks.overview = { data: legacy, isError: false, isLoading: false }

    expect(() => render(<DowMonitor />)).not.toThrow()
    expect(screen.getByTestId('card-01347.HK')).toBeInTheDocument()
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

  it('omits malformed and unknown legacy bars, lines, signals, and anchors', () => {
    const option = buildDowMiniChartOption({
      bars: [
        bars[0],
        null,
        { ...bars[1], timestamp: 'not-a-time' },
        { ...bars[1], close: Number.NaN },
      ],
      lines: [
        authoritativeChart.lines![0],
        { ...authoritativeChart.lines![1], role: 'FUTURE_ROLE' },
        { ...authoritativeChart.lines![1], side: 'UNKNOWN' },
        { ...authoritativeChart.lines![1], anchorPrices: [10, Number.NaN] },
      ],
      signals: [
        authoritativeChart.signals![0],
        { ...authoritativeChart.signals![1], side: 'HOLD' },
        { ...authoritativeChart.signals![1], price: Number.NaN },
        { ...authoritativeChart.signals![1], barTime: '2020-01-01T00:00:00Z' },
      ],
      longTerm: {
        first_anchor_time: 'not-a-time',
        first_anchor_price: 9.6,
        second_anchor_time: bars[1].timestamp,
        second_anchor_price: 10,
      },
    } as unknown as DowMonitorChart)
    const series = option.series as Array<Record<string, any>>
    const candle = series.find(item => item.id === 'candles')

    expect(candle).toBeDefined()
    expect(candle!.data).toHaveLength(1)
    expect(series.filter(item => item.type === 'line').map(item => item.id)).toEqual([
      'main-support',
    ])
    expect(candle!.markPoint.data).toHaveLength(1)
    expect(candle!.markPoint.data[0].name).toBe('BUY')
    expect(series.some(item => item.id === 'long-term')).toBe(false)
  })

  it('reuses one chart instance, observes resize, and disposes on unmount', () => {
    const { rerender, unmount } = render(
      <DowMiniChart chart={{ bars, lines: [], signals: [] }} />,
    )

    expect(chartMocks.init).toHaveBeenCalledTimes(1)
    expect(chartMocks.observe).toHaveBeenCalledTimes(1)
    expect(chartMocks.setOption).toHaveBeenCalledTimes(1)

    rerender(<DowMiniChart chart={authoritativeChart} />)
    expect(chartMocks.init).toHaveBeenCalledTimes(1)
    expect(chartMocks.setOption).toHaveBeenCalledTimes(2)

    act(() => chartMocks.resizeCallback?.([], {} as ResizeObserver))
    expect(chartMocks.resize).toHaveBeenCalledTimes(1)
    unmount()
    expect(chartMocks.disconnect).toHaveBeenCalledTimes(1)
    expect(chartMocks.dispose).toHaveBeenCalledTimes(1)
  })
})
