import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DowMonitorMarket } from './types'
import {
  useAddDowMonitorSymbol,
  useDowMonitorDetail,
  useDowMonitorOverview,
  useDowNotifications,
  useMarkDowNotificationRead,
  useRemoveDowMonitorSymbol,
  useSetDowMonitorEnabled,
} from './useDowMonitor'

const fetchMock = vi.fn()

function response(body: unknown) {
  return {
    ok: true,
    json: () => Promise.resolve(body),
  } as Response
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return {
    queryClient,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  }
}

beforeEach(() => {
  fetchMock.mockResolvedValue(response({ symbols: [], source: 'webstock', source_timestamp: null }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

describe('Dow monitor queries', () => {
  it('keeps market filtering as a query parameter and never toggles hidden symbols', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => useDowMonitorOverview('hk'), { wrapper })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/dow-monitor/overview?market=hk', expect.anything())
    })
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/symbols/INTC.US'),
      expect.anything(),
    )
  })

  it('uses market and timeframe only as query parameters', async () => {
    const { wrapper } = createWrapper()

    renderHook(() => {
      useDowNotifications('us')
      useDowMonitorDetail('INTC.US', '15m')
    }, { wrapper })

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/dow-monitor/notifications?market=us', expect.anything())
      expect(fetchMock).toHaveBeenCalledWith('/api/dow-monitor/INTC.US?timeframe=15m', expect.anything())
    })
  })

  it('polls each read model every 15 seconds and retains successful data during a refresh', async () => {
    const { queryClient, wrapper } = createWrapper()
    const hongKong = { symbols: [{ symbol: '01347.HK' }], source: 'webstock', source_timestamp: null }
    const unitedStates = { symbols: [{ symbol: 'INTC.US' }], source: 'webstock', source_timestamp: null }
    let resolveRefresh: (value: Response) => void
    fetchMock.mockResolvedValueOnce(response(hongKong))
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveRefresh = resolve }))

    const { result, rerender } = renderHook(
      ({ market }) => useDowMonitorOverview(market),
      { initialProps: { market: 'hk' as DowMonitorMarket }, wrapper },
    )

    await waitFor(() => expect(result.current.data).toEqual(hongKong))
    rerender({ market: 'us' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(result.current.data).toEqual(hongKong)
    expect(result.current.isPlaceholderData).toBe(true)

    await act(async () => resolveRefresh!(response(unitedStates)))
    await waitFor(() => expect(result.current.data).toEqual(unitedStates))

    renderHook(() => {
      useDowNotifications('us')
      useDowMonitorDetail('INTC.US', '15m')
    }, { wrapper })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4))

    for (const queryKey of [
      ['dow-monitor', 'overview', 'us'],
      ['dow-monitor', 'notifications', 'us'],
      ['dow-monitor', 'detail', 'INTC.US', '15m'],
    ]) {
      const query = queryClient.getQueryCache().find({ queryKey, exact: true })
      const options = query?.options as
        | { refetchInterval?: number; placeholderData?: unknown }
        | undefined
      expect(options?.refetchInterval).toBe(15_000)
      expect(options?.placeholderData).toBeDefined()
    }
  })

  it('invalidates only affected Dow monitor query families after mutations', async () => {
    const { queryClient, wrapper } = createWrapper()
    const invalidateQueries = vi.spyOn(queryClient, 'invalidateQueries')
    const removeQueries = vi.spyOn(queryClient, 'removeQueries')
    const { result } = renderHook(
      () => ({
        add: useAddDowMonitorSymbol(),
        remove: useRemoveDowMonitorSymbol(),
        setEnabled: useSetDowMonitorEnabled(),
        markRead: useMarkDowNotificationRead(),
      }),
      { wrapper },
    )

    await act(async () => {
      await result.current.add.mutateAsync({ symbol: '01347.HK' })
      await result.current.remove.mutateAsync('01347.HK')
      await result.current.setEnabled.mutateAsync({ symbol: '01347.HK', enabled: false })
      await result.current.markRead.mutateAsync('notification-1')
    })

    expect(removeQueries).toHaveBeenCalledWith({ queryKey: ['dow-monitor', 'detail', '01347.HK'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['dow-monitor', 'overview'] })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: ['dow-monitor', 'notifications'] })
    for (const [argument] of invalidateQueries.mock.calls) {
      const filter = argument as { queryKey?: readonly unknown[] } | undefined
      expect(filter?.queryKey?.[0]).toBe('dow-monitor')
    }
  })
})
