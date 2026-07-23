import { Trash2 } from 'lucide-react'
import { useState } from 'react'

import { cn } from '@/lib/cn'

import { DowMiniChart, getLatestValidDowSignalSide } from './DowMiniChart'
import { formatServerTimestamp } from './formatServerTimestamp'
import type {
  DowMonitorOverviewSymbol,
  DowMonitorTimeframeState,
  DowSignalSide,
  DowTimeframe,
} from './types'

const TIMEFRAMES: Array<{ value: DowTimeframe; label: string }> = [
  { value: '5m', label: '5分' },
  { value: '15m', label: '15分' },
  { value: '30m', label: '30分' },
  { value: '60m', label: '60分' },
  { value: 'day', label: '日K' },
]

type VisualState = 'buy' | 'sell' | 'watch' | 'none' | 'blocked'

function visualState(
  state: DowMonitorTimeframeState | undefined,
  forceBlocked: boolean,
): VisualState {
  if (forceBlocked || state?.freshness_state !== 'LIVE') {
    return state || forceBlocked ? 'blocked' : 'none'
  }
  const rawActionCode = state.snapshot?.action_code
  const actionCode = typeof rawActionCode === 'string' ? rawActionCode.toUpperCase() : null
  if (actionCode === 'OPEN_LONG' || actionCode === 'BUY') return 'buy'
  if (
    actionCode === 'CLOSE_LONG'
    || actionCode === 'SELL'
    || actionCode === 'RISK'
    || actionCode === 'REDUCE'
  ) return 'sell'
  if (actionCode === 'WATCH') return 'watch'
  const backendSide = getLatestValidDowSignalSide(state.chart)
  if (backendSide === 'BUY') return 'buy'
  if (backendSide === 'SELL' || backendSide === 'RISK') return 'sell'
  return 'none'
}

function stateClass(state: VisualState) {
  switch (state) {
    case 'buy':
      return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
    case 'sell':
      return 'border-red-500/30 bg-red-500/10 text-red-400'
    case 'watch':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-400'
    case 'blocked':
      return 'border-border bg-elevated/50 text-muted opacity-60'
    default:
      return 'border-border bg-elevated/50 text-muted'
  }
}

function signalClass(side: DowSignalSide) {
  return side === 'BUY' ? 'text-emerald-400' : 'text-red-400'
}

function blockedLabel(
  item: DowMonitorOverviewSymbol,
  state: DowMonitorTimeframeState | undefined,
  forceBlocked: boolean,
  blockedReason?: string,
) {
  if (forceBlocked) return blockedReason ?? '监控状态不可用'
  if (!item.enabled) return '监控已暂停'
  if (state?.freshness_state === 'STALE_DATA') return '数据延迟'
  if (state?.freshness_state === 'ANALYSIS_PAUSED') return '分析暂停'
  return null
}

export function DowMonitorCard({
  item,
  onOpen,
  onToggle,
  onRemove,
  forceBlocked = false,
  blockedReason,
  quoteReady = true,
  togglePending = false,
  removePending = false,
}: {
  item: DowMonitorOverviewSymbol
  onOpen: (symbol: string, timeframe: DowTimeframe) => void
  onToggle: (symbol: string, enabled: boolean) => void
  onRemove: (symbol: string) => void
  forceBlocked?: boolean
  blockedReason?: string
  quoteReady?: boolean
  togglePending?: boolean
  removePending?: boolean
}) {
  const [timeframe, setTimeframe] = useState<DowTimeframe>('5m')
  const selectedState = item.states[timeframe]
  const blocked = blockedLabel(item, selectedState, forceBlocked, blockedReason)
  const price = quoteReady
    && typeof item.last_price === 'number'
    && Number.isFinite(item.last_price)
    ? item.last_price
    : null
  const change = quoteReady
    && typeof item.change_pct === 'number'
    && Number.isFinite(item.change_pct)
    ? item.change_pct * 100
    : null
  const name = typeof item.name === 'string' && item.name.trim() && item.name.trim() !== item.symbol
    ? item.name.trim()
    : null
  const quoteTime = quoteReady ? formatServerTimestamp(item.quote_timestamp) : null
  const successTime = quoteReady ? formatServerTimestamp(item.last_success_at) : null

  return (
    <article
      data-testid={`card-${item.symbol}`}
      data-tradable={blocked ? 'false' : 'true'}
      className={cn(
        'group relative min-w-0 overflow-hidden rounded-card border bg-surface transition-colors hover:border-accent/40',
        blocked ? 'border-border/70 opacity-75' : 'border-border',
      )}
    >
      <div className="flex items-start gap-2 px-2.5 pb-1.5 pt-2">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0 font-mono text-sm font-semibold tracking-wide">
              {item.symbol}
            </span>
            {name && <span className="truncate text-xs text-secondary">{name}</span>}
          </div>
          <div className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-lg tabular-nums">
              {price == null ? '—' : price.toFixed(2)}
            </span>
            {change != null && (
              <span className={cn(
                'font-mono text-[10px] tabular-nums',
                change > 0 ? 'text-bull' : change < 0 ? 'text-bear' : 'text-muted',
              )}>
                {change > 0 ? '+' : ''}{change.toFixed(2)}%
              </span>
            )}
          </div>
          {(quoteTime || successTime) && (
            <div className="mt-0.5 flex gap-2 font-mono text-[9px] text-muted">
              {quoteTime && <span>行情 {quoteTime}</span>}
              {successTime && <span>成功 {successTime}</span>}
            </div>
          )}
        </div>

        <button
          type="button"
          role="switch"
          aria-label={`${item.symbol} 监控开关`}
          aria-checked={item.enabled}
          disabled={togglePending}
          onClick={() => onToggle(item.symbol, !item.enabled)}
          className={cn(
            'relative mt-0.5 h-[18px] w-8 shrink-0 rounded-full transition-colors disabled:cursor-wait disabled:opacity-50',
            item.enabled ? 'bg-accent/70' : 'bg-border',
          )}
        >
          <span
            className={cn(
              'absolute top-0.5 h-3.5 w-3.5 rounded-full bg-white transition-transform',
              item.enabled ? 'translate-x-0' : '-translate-x-4',
            )}
            style={{ right: 2 }}
          />
        </button>

        <button
          type="button"
          aria-label={`移除 ${item.symbol}`}
          disabled={removePending}
          onClick={() => onRemove(item.symbol)}
          className="rounded p-0.5 text-muted transition-colors hover:bg-danger/10 hover:text-danger disabled:cursor-wait disabled:opacity-50"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-5 gap-1 px-2.5 pb-1.5">
        {TIMEFRAMES.map(option => {
          const state = item.states[option.value]
          const currentVisualState = visualState(state, forceBlocked || !item.enabled)
          return (
            <button
              key={option.value}
              type="button"
              aria-label={option.label}
              aria-pressed={timeframe === option.value}
              data-tradable={currentVisualState === 'blocked' ? 'false' : 'true'}
              onClick={() => setTimeframe(option.value)}
              className={cn(
                'h-6 rounded border text-[10px] font-medium transition-colors',
                stateClass(currentVisualState),
                timeframe === option.value && 'ring-1 ring-accent/70',
              )}
            >
              {option.label}
            </button>
          )
        })}
      </div>

      <button
        type="button"
        aria-label={`打开 ${item.symbol} 完整K线`}
        onClick={() => onOpen(item.symbol, timeframe)}
        className="block w-full border-y border-border/50 px-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
      >
        <DowMiniChart
          chart={selectedState?.chart ?? {}}
          testId={`mini-chart-${item.symbol}-${timeframe}`}
        />
      </button>

      <div className="flex h-8 min-w-0 items-center gap-1.5 px-2.5 text-xs">
        {blocked ? (
          <span className="font-medium text-muted">{blocked}</span>
        ) : item.latest_notification ? (
          <>
            <span className={cn('shrink-0 font-medium', signalClass(item.latest_notification.side))}>
              {item.latest_notification.action_name}
            </span>
            <span className="truncate text-secondary">{item.latest_notification.shape_name}</span>
          </>
        ) : (
          <span className="text-muted">暂无可交易信号</span>
        )}
      </div>
    </article>
  )
}
