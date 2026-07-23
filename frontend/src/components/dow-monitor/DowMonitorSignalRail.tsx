import { cn } from '@/lib/cn'

import type { DowMonitorNotification } from './types'

function notificationClass(side: DowMonitorNotification['side']) {
  return side === 'BUY'
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
    : 'border-red-500/30 bg-red-500/10 text-red-400'
}

export function DowMonitorSignalRail({
  notifications,
  loading = false,
  error = false,
  onRead,
  readPendingIds,
}: {
  notifications: DowMonitorNotification[]
  loading?: boolean
  error?: boolean
  onRead?: (notificationId: string) => void
  readPendingIds?: ReadonlySet<string>
}) {
  return (
    <section
      data-testid="dow-monitor-signal-rail"
      aria-label="最新信号"
      className="sticky top-0 z-20 border-y border-border bg-base/95 px-3 py-2 backdrop-blur sm:px-5"
    >
      {notifications.length === 0 ? (
        <div className="flex h-8 items-center justify-center text-xs text-muted">
          {loading ? '正在加载通知' : error ? '通知加载失败' : '暂无最新信号'}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 xl:grid-cols-4">
          {notifications.slice(0, 8).map(notification => (
            <div
              key={notification.notification_id}
              data-testid={`signal-${notification.symbol}`}
              className={cn(
                'flex min-w-0 items-center gap-2 rounded-btn border px-2 py-1.5 text-xs',
                notificationClass(notification.side),
              )}
            >
              <span className="shrink-0 font-mono font-semibold">{notification.symbol}</span>
              <span className="shrink-0 rounded bg-base/30 px-1 font-mono text-[10px]">
                {notification.timeframe}
              </span>
              <span className="shrink-0 font-medium">{notification.action_name}</span>
              <span className="truncate text-secondary">{notification.shape_name}</span>
              {notification.read_at == null && onRead && (
                <button
                  type="button"
                  aria-label={`标记 ${notification.symbol} 已读`}
                  disabled={readPendingIds?.has(notification.notification_id)}
                  onClick={() => onRead(notification.notification_id)}
                  className="ml-auto shrink-0 rounded border border-current/30 px-1 py-0.5 text-[10px] disabled:cursor-wait disabled:opacity-50"
                >
                  已读
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
