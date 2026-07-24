import { useCallback, useEffect, useState } from 'react'
import { Activity, Play } from 'lucide-react'

type Fetcher = (input: string, init?: RequestInit) => Promise<{ ok: boolean; json: () => Promise<any> }>
type Stock = {
  symbol: string
  name: string
  market?: string
  totalScore?: number
  strategyScore?: number
  lastDone?: number | null
  triggerTimeframes?: string[]
  localTriggerTimeframes?: string[]
  longTermTriggerTimeframes?: string[]
  formalTimeframes?: string[]
  provisionalTimeframes?: string[]
  signalTime?: string
  calculatedAt?: string
  dataFreshness?: string
}
type ScanJob = {
  runId: string
  status: 'queued' | 'running' | 'complete' | 'failed'
  completed?: number
  total?: number
  selected?: number
  failed?: number
  currentSymbol?: string
  error?: string
}

export type DowScreenerRow = {
  symbol: string
  name: string
  market?: string
  score: number | null
  close: number | null
  strategy_summary: string
  trigger_timeframes: string[]
  local_trigger_timeframes: string[]
  long_term_trigger_timeframes: string[]
  formal_timeframes: string[]
  provisional_timeframes: string[]
  signal_time: string
  calculated_at: string
  data_freshness: string
}

export type DowScreenerResult = {
  rows: DowScreenerRow[]
  total: number
  asOf: string
}

export const DOW_TREND_STRATEGY_ID = 'dow_trend'
const marketNames: Record<string, string> = { cn: 'A股', hk: '港股', us: '美股', all: '全部市场' }
const periodLabel = (period: string) => period === 'day' ? '日线' : period
const ignoreResults = () => undefined

async function ensureServiceConnection(fetcher: Fetcher) {
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      if ((await fetcher('/health')).ok) return
    } catch {
      // A safe GET may be retried after a deployment switches connections.
    }
  }
  throw new Error('服务连接中断，请稍后重新执行')
}

function triggerSummary(stock: Stock): string {
  const local = stock.localTriggerTimeframes ?? stock.triggerTimeframes ?? []
  const longTerm = stock.longTermTriggerTimeframes ?? []
  return [
    local.length ? `局部 ${local.map(periodLabel).join(' + ')}` : '',
    longTerm.length ? `长期 ${longTerm.map(periodLabel).join(' + ')}` : '',
  ].filter(Boolean).join(' · ')
}

export function toDowScreenerRows(stocks: Stock[]): DowScreenerRow[] {
  return stocks.map(stock => ({
    symbol: stock.symbol,
    name: stock.name,
    market: stock.market,
    score: stock.strategyScore ?? stock.totalScore ?? null,
    close: stock.lastDone ?? null,
    strategy_summary: triggerSummary(stock),
    trigger_timeframes: stock.triggerTimeframes ?? [],
    local_trigger_timeframes: stock.localTriggerTimeframes ?? [],
    long_term_trigger_timeframes: stock.longTermTriggerTimeframes ?? [],
    formal_timeframes: stock.formalTimeframes ?? [],
    provisional_timeframes: stock.provisionalTimeframes ?? [],
    signal_time: stock.signalTime ?? '',
    calculated_at: stock.calculatedAt ?? '',
    data_freshness: stock.dataFreshness ?? '',
  }))
}

function resultDate(payload: any, rows: DowScreenerRow[]): string {
  const candidate = payload?.metrics?.scoreDate ?? rows[0]?.signal_time ?? ''
  return String(candidate).slice(0, 10)
}

export function DowStrategyCard({
  market,
  fetcher = fetch,
  onResults = ignoreResults,
}: {
  market: string
  fetcher?: Fetcher
  onResults?: (result: DowScreenerResult | null) => void
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [matchedCount, setMatchedCount] = useState(0)
  const [job, setJob] = useState<ScanJob | null>(null)

  const loadPool = useCallback(async () => {
    const response = await fetcher(`/api/dow-strategy/pool?market=${market}&limit=80`)
    if (!response.ok) throw new Error('道氏策略服务暂不可用')
    const payload = await response.json()
    const rows = toDowScreenerRows(payload.stocks ?? [])
    setMatchedCount(rows.length)
    setLoaded(true)
    onResults({ rows, total: rows.length, asOf: resultDate(payload, rows) })
  }, [fetcher, market, onResults])

  const run = useCallback(async () => {
    setLoading(true)
    setError('')
    setLoaded(false)
    setMatchedCount(0)
    onResults(null)
    try {
      await ensureServiceConnection(fetcher)
      const response = await fetcher('/api/dow-strategy/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ market }),
      })
      if (!response.ok) throw new Error('无法启动道氏策略选股')
      let current = await response.json() as ScanJob
      if (!current.runId) throw new Error('选股任务未返回任务编号')
      setJob(current)
      while (current.status === 'queued' || current.status === 'running') {
        await new Promise(resolve => setTimeout(resolve, 250))
        const statusResponse = await fetcher(`/api/dow-strategy/runs/${encodeURIComponent(current.runId)}`)
        if (!statusResponse.ok) throw new Error('无法读取选股进度')
        current = await statusResponse.json() as ScanJob
        setJob(current)
      }
      if (current.status === 'failed') throw new Error(current.error || '道氏策略选股失败')
      await loadPool()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '选股失败')
    } finally {
      setLoading(false)
    }
  }, [fetcher, loadPool, market, onResults])

  useEffect(() => {
    setError('')
    setLoaded(false)
    setMatchedCount(0)
    setJob(null)
    onResults(null)
  }, [market, onResults])

  const status = error
    ? error
    : loading && job
      ? `正在扫描${marketNames[market] ?? market}：${job.completed ?? 0}/${job.total ?? 0}${job.currentSymbol ? ` · ${job.currentSymbol}` : ''}`
      : loaded
        ? matchedCount > 0
          ? `${marketNames[market] ?? market}选股完成，共 ${matchedCount} 只；结果已载入下方列表`
          : `${marketNames[market] ?? market}选股完成，当前暂无符合条件的股票`
        : '点击“执行选股”开始扫描'

  return (
    <section className="flex flex-wrap items-center justify-between gap-3 border-y border-border py-2">
      <div className="flex min-w-0 items-center gap-2">
        <Activity className="h-4 w-4 shrink-0 text-cyan-400" />
        <span className="min-w-0">
          <b className="block text-sm text-foreground">道氏趋势 · 多周期</b>
          <small className={error ? 'text-danger' : loading || loaded ? 'text-cyan-300' : 'text-muted'}>
            {status}
          </small>
        </span>
      </div>
      <button
        type="button"
        onClick={() => void run()}
        disabled={loading}
        className="inline-flex items-center gap-1.5 rounded-btn border border-cyan-400/30 bg-cyan-500/15 px-3 py-2 text-xs text-cyan-300 disabled:cursor-wait disabled:opacity-60"
      >
        <Play className="h-3.5 w-3.5" />
        {loading ? '执行中…' : '执行选股'}
      </button>
    </section>
  )
}
