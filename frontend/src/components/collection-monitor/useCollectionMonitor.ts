import { useQueries, useQuery } from '@tanstack/react-query'
import type {
  CollectionGapPage,
  CollectionMonitorFilters,
  CollectionMonitorOverview,
  DatasetKey,
  CollectionTaskPage,
  MarketCollectionEvidence,
  MarketKey,
} from './types'

const API_ROOT = '/api/collection-monitor'
const REFRESH_INTERVAL_MS = 30_000
const MARKETS: readonly MarketKey[] = ['cn', 'hk', 'us']

export interface CollectionMonitorPagination {
  taskOffset: number
  gapOffset: number
  limit: number
}

export class CollectionMonitorRequestError extends Error {
  constructor(readonly status: number) {
    super(status === 503 ? 'collection_monitoring_evidence_unavailable' : 'collection_monitor_request_failed')
  }
}

function todayInShanghai() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

function routeFromApiUrl(raw: string): {
  pathname: string
  params: URLSearchParams
} {
  const parsed = new URL(raw, 'http://localhost')
  return {
    pathname: parsed.pathname.replace(/\/+$/, ''),
    params: parsed.searchParams,
  }
}

function toInt(value: string | null, fallback: number): number {
  if (!value) return fallback
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? parsed : fallback
}

function fallbackUnavailableOverview(rawUrl: string): CollectionMonitorOverview {
  const { params } = routeFromApiUrl(rawUrl)
  return {
    tradeDate: params.get('date') ?? todayInShanghai(),
    evidenceState: 'unavailable',
    evidenceAt: null,
  }
}

function fallbackUnavailableMarket(rawUrl: string): MarketCollectionEvidence {
  const { pathname, params } = routeFromApiUrl(rawUrl)
  const market = pathname.split('/').at(-1) as MarketKey | undefined

  return {
    market: market ?? 'hk',
    tradeDate: params.get('date') ?? todayInShanghai(),
    evidenceState: 'unavailable',
    evidenceAt: null,
    datasets: [],
  }
}

function fallbackUnavailableTasks(rawUrl: string): CollectionTaskPage {
  const { params } = routeFromApiUrl(rawUrl)

  return {
    tradeDate: params.get('date') ?? todayInShanghai(),
    evidenceState: 'unavailable',
    evidenceAt: null,
    limit: toInt(params.get('limit'), 100),
    offset: toInt(params.get('offset'), 0),
    total: 0,
    tasks: [],
  }
}

function fallbackUnavailableGaps(rawUrl: string): CollectionGapPage {
  const { params } = routeFromApiUrl(rawUrl)
  const datasetKey = (params.get('dataset') as DatasetKey | null) ?? 'capital_distribution'

  return {
    tradeDate: params.get('date') ?? todayInShanghai(),
    market: (params.get('market') ?? 'hk') as MarketKey,
    datasetKey,
    evidenceState: 'unavailable',
    evidenceAt: null,
    limit: toInt(params.get('limit'), 100),
    offset: toInt(params.get('offset'), 0),
    total: 0,
    gaps: [],
  }
}

function fallbackEvidenceEnvelope<T>(rawUrl: string): T {
  const { pathname } = routeFromApiUrl(rawUrl)
  if (pathname === '/api/collection-monitor/overview') {
    return fallbackUnavailableOverview(rawUrl) as T
  }
  if (pathname.startsWith('/api/collection-monitor/markets/')) {
    return fallbackUnavailableMarket(rawUrl) as T
  }
  if (pathname === '/api/collection-monitor/tasks') {
    return fallbackUnavailableTasks(rawUrl) as T
  }
  if (pathname === '/api/collection-monitor/gaps') {
    return fallbackUnavailableGaps(rawUrl) as T
  }

  return {
    evidenceState: 'unavailable',
    evidenceAt: null,
  } as T
}

function isRetryableFailure(status: number): boolean {
  return status >= 500
}

function queryString(values: Record<string, string | number | undefined>) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== '') query.set(key, String(value))
  }
  return query.toString()
}

async function readJson<T>(url: string): Promise<T> {
  try {
    const response = await fetch(url, { headers: { Accept: 'application/json' } })
    if (!response.ok) {
      if (isRetryableFailure(response.status)) return fallbackEvidenceEnvelope<T>(url)
      throw new CollectionMonitorRequestError(response.status)
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof TypeError) {
      return fallbackEvidenceEnvelope<T>(url)
    }
    throw error
  }
}

const queryOptions = {
  refetchInterval: REFRESH_INTERVAL_MS,
  refetchIntervalInBackground: true,
  retry: false,
} as const

export function useCollectionMonitor(
  filters: CollectionMonitorFilters,
  pagination: CollectionMonitorPagination,
) {
  const overview = useQuery({
    queryKey: ['collection-monitor', 'overview', filters.date],
    queryFn: () => readJson<CollectionMonitorOverview>(
      `${API_ROOT}/overview?${queryString({ date: filters.date })}`,
    ),
    ...queryOptions,
  })

  const markets = useQueries({
    queries: MARKETS.map(market => ({
      queryKey: ['collection-monitor', 'market', market, filters.date],
      queryFn: () => readJson<MarketCollectionEvidence>(
        `${API_ROOT}/markets/${market}?${queryString({ date: filters.date })}`,
      ),
      ...queryOptions,
    })),
  })

  const tasks = useQuery({
    queryKey: [
      'collection-monitor',
      'tasks',
      filters.date,
      filters.status,
      filters.technology,
      filters.market,
      filters.dataset,
      filters.mode,
      pagination.limit,
      pagination.taskOffset,
    ],
    queryFn: () => readJson<CollectionTaskPage>(
      `${API_ROOT}/tasks?${queryString({
        date: filters.date,
        status: filters.status,
        technology: filters.technology,
        market: filters.market,
        dataset: filters.dataset,
        mode: filters.mode,
        limit: pagination.limit,
        offset: pagination.taskOffset,
      })}`,
    ),
    ...queryOptions,
  })

  const gaps = useQuery({
    queryKey: [
      'collection-monitor',
      'gaps',
      filters.market,
      filters.dataset,
      filters.date,
      pagination.limit,
      pagination.gapOffset,
    ],
    queryFn: () => readJson<CollectionGapPage>(
      `${API_ROOT}/gaps?${queryString({
        market: filters.market,
        dataset: filters.dataset,
        date: filters.date,
        limit: pagination.limit,
        offset: pagination.gapOffset,
      })}`,
    ),
    ...queryOptions,
  })

  return { overview, markets, tasks, gaps }
}
