import { cn } from '@/lib/cn'

import type { DowMonitorNotification } from './types'

function notificationClass(side: DowMonitorNotification['side']) {
  return side === 'BUY'
    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
    : 'border-red-500/30 bg-red-500/10 text-red-400'
}

export function DowMonitorSignalRail({
  notifications,
}: {
  notifications: DowMonitorNotification[]
}) {
  return (
    <section
      data-testid="dow-monitor-signal-rail"
      aria-label="最新信号"
      className="sticky top-0 z-20 border-y border-border bg-base/95 px-3 py-2 backdrop-blur sm:px-5"
    >
      {notifications.length === 0 ? (
        <div className="flex h-8 items-center justify-center text-xs text-muted">暂无最新信号</div>
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
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
