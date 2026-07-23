import { useMemo, useState } from 'react'

import { MarketFilterTabs } from '@/components/MarketFilterTabs'
import { PageHeader } from '@/components/PageHeader'
import { DowMonitorCard } from '@/components/dow-monitor/DowMonitorCard'
import { DowMonitorSignalRail } from '@/components/dow-monitor/DowMonitorSignalRail'
import type {
  DowMonitorMarket,
  DowMonitorNotification,
  DowMonitorOverviewSymbol,
  DowTimeframe,
} from '@/components/dow-monitor/types'
import {
  useAddDowMonitorSymbol,
  useDowMonitorOverview,
  useDowNotifications,
  useRemoveDowMonitorSymbol,
  useSetDowMonitorEnabled,
} from '@/components/dow-monitor/useDowMonitor'
import { cn } from '@/lib/cn'

type SignalFilter = 'all' | 'active' | 'buy' | 'sell'

const SIGNAL_FILTERS: Array<{ value: SignalFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'active', label: '有信号' },
  { value: 'buy', label: '仅买点' },
  { value: 'sell', label: '仅卖点' },
]

function sameMarket(market: DowMonitorMarket, itemMarket: string) {
  return market === 'all' || market === itemMarket
}

function matchesSide(filter: SignalFilter, side: string | null | undefined) {
  if (filter === 'all') return true
  if (filter === 'active') return side != null
  if (filter === 'buy') return side === 'BUY'
  return side === 'SELL' || side === 'RISK'
}

function filterSymbols(
  symbols: DowMonitorOverviewSymbol[],
  market: DowMonitorMarket,
  signal: SignalFilter,
) {
  return symbols.filter(item => (
    sameMarket(market, item.market)
    && matchesSide(signal, item.latest_notification?.side)
  ))
}

function filterNotifications(
  notifications: DowMonitorNotification[],
  market: DowMonitorMarket,
  signal: SignalFilter,
) {
  return notifications.filter(notification => (
    sameMarket(market, notification.market)
    && matchesSide(signal, notification.side)
  ))
}

export function DowMonitor({
  onOpen = () => undefined,
}: {
  onOpen?: (symbol: string, timeframe: DowTimeframe) => void
}) {
  const [market, setMarket] = useState<DowMonitorMarket>('all')
  const [signal, setSignal] = useState<SignalFilter>('all')
  const [symbolInput, setSymbolInput] = useState('')
  const overview = useDowMonitorOverview(market)
  const notificationQuery = useDowNotifications(market)
  const addSymbol = useAddDowMonitorSymbol()
  const removeSymbol = useRemoveDowMonitorSymbol()
  const setEnabled = useSetDowMonitorEnabled()

  const symbols = overview.data?.symbols ?? []
  const notifications = notificationQuery.data?.notifications ?? []
  const filteredSymbols = useMemo(
    () => filterSymbols(symbols, market, signal),
    [market, signal, symbols],
  )
  const filteredNotifications = useMemo(
    () => filterNotifications(notifications, market, signal),
    [market, notifications, signal],
  )

  const submitSymbol = () => {
    const symbol = symbolInput.trim().toUpperCase()
    if (!symbol) return
    addSymbol.mutate({ symbol, enabled: true })
    setSymbolInput('')
  }

  return (
    <div className="min-h-full bg-base">
      <PageHeader
        title="趋势监控"
        subtitle={`${symbols.length} 只 · 后台持续运行`}
        right={(
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              submitSymbol()
            }}
          >
            <input
              value={symbolInput}
              onChange={event => setSymbolInput(event.target.value)}
              aria-label="股票代码"
              placeholder="股票代码"
              className="h-8 w-36 rounded-btn border border-border bg-elevated px-2.5 font-mono text-xs uppercase outline-none transition-colors placeholder:font-sans placeholder:normal-case focus:border-accent/50"
            />
            <button
              type="submit"
              disabled={addSymbol.isPending}
              className="h-8 rounded-btn bg-accent px-3 text-xs font-medium text-white transition-opacity disabled:opacity-50"
            >
              添加
            </button>
          </form>
        )}
      />

      <DowMonitorSignalRail notifications={filteredNotifications} />

      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3 py-2 sm:px-5">
        <MarketFilterTabs value={market} onChange={setMarket} />
        <div className="flex h-8 items-center overflow-hidden rounded-btn border border-border bg-surface">
          {SIGNAL_FILTERS.map(option => (
            <button
              key={option.value}
              type="button"
              aria-pressed={signal === option.value}
              onClick={() => setSignal(option.value)}
              className={cn(
                'h-full px-2.5 text-xs font-medium transition-colors',
                signal === option.value
                  ? 'bg-accent/15 text-accent'
                  : 'text-muted hover:bg-elevated hover:text-secondary',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <span className="ml-auto text-[10px] text-muted">
          数据源 {overview.data?.source ?? 'webstock'}
        </span>
      </div>

      <main className="p-3 sm:px-5">
        {overview.isLoading ? (
          <div className="py-10 text-center text-sm text-muted">加载监控状态…</div>
        ) : filteredSymbols.length === 0 ? (
          <div className="rounded-card border border-dashed border-border py-10 text-center text-sm text-muted">
            当前筛选暂无监控股票
          </div>
        ) : (
          <div
            data-testid="dow-monitor-grid"
            className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4"
          >
            {filteredSymbols.map(item => (
              <DowMonitorCard
                key={item.symbol}
                item={item}
                onOpen={onOpen}
                onToggle={(symbol, enabled) => setEnabled.mutate({ symbol, enabled })}
                onRemove={symbol => removeSymbol.mutate(symbol)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
