import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { useEffect, useMemo, useRef } from 'react'

import { useChartTheme } from '@/lib/theme'

import type { DowMonitorChart } from './types'

const CANDLE_UP = '#C74040'
const CANDLE_DOWN = '#2D9B65'
const SUPPORT_BLUE = '#3B82F6'
const RESISTANCE_MAGENTA = '#D946EF'
const LONG_TERM_AMBER = '#F59E0B'
const BUY_GREEN = '#22C55E'
const SELL_RED = '#EF4444'

function completeLongTermAnchors(chart: DowMonitorChart) {
  const longTerm = chart.longTerm
  const firstTime = longTerm?.first_anchor_time
  const firstPrice = longTerm?.first_anchor_price
  const secondTime = longTerm?.second_anchor_time
  const secondPrice = longTerm?.second_anchor_price
  if (
    typeof firstTime !== 'string'
    || firstTime.length === 0
    || typeof secondTime !== 'string'
    || secondTime.length === 0
    || typeof firstPrice !== 'number'
    || !Number.isFinite(firstPrice)
    || typeof secondPrice !== 'number'
    || !Number.isFinite(secondPrice)
  ) {
    return null
  }
  return [[firstTime, firstPrice], [secondTime, secondPrice]]
}

export function buildDowMiniChartOption(
  chart: DowMonitorChart,
  colors = {
    border: '#353539',
    grid: 'rgba(255,255,255,0.06)',
  },
): EChartsOption {
  const bars = chart.bars ?? []
  const backendLines = chart.lines ?? []
  const backendSignals = chart.signals ?? []
  const lineSeries = backendLines.map(line => {
    const acceleration = line.role.toUpperCase() === 'ACCELERATION'
    const resistance = line.side.toUpperCase() === 'RESISTANCE'
    return {
      id: line.id,
      name: `${line.side} ${line.role}`,
      type: 'line' as const,
      data: [
        [line.anchorTimes[0], line.anchorPrices[0]],
        [line.anchorTimes[1], line.anchorPrices[1]],
      ],
      showSymbol: false,
      silent: true,
      connectNulls: true,
      lineStyle: {
        color: resistance ? RESISTANCE_MAGENTA : SUPPORT_BLUE,
        type: acceleration ? 'dashed' as const : 'solid' as const,
        width: acceleration ? 1.5 : 2,
      },
      z: acceleration ? 4 : 5,
    }
  })
  const longTermAnchors = completeLongTermAnchors(chart)
  if (longTermAnchors) {
    lineSeries.push({
      id: 'long-term',
      name: '长期趋势',
      type: 'line',
      data: longTermAnchors,
      showSymbol: false,
      silent: true,
      connectNulls: true,
      lineStyle: {
        color: LONG_TERM_AMBER,
        type: 'solid',
        width: 2,
      },
      z: 3,
    })
  }

  return {
    animation: false,
    grid: { top: 4, right: 4, bottom: 4, left: 4, containLabel: false },
    xAxis: {
      type: 'category',
      data: bars.map(bar => bar.timestamp),
      boundaryGap: true,
      axisLine: { show: false, lineStyle: { color: colors.border } },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { show: false },
      splitLine: { show: true, lineStyle: { color: colors.grid } },
    },
    tooltip: { show: false },
    series: [
      {
        id: 'candles',
        type: 'candlestick',
        data: bars.map(bar => [bar.open, bar.close, bar.low, bar.high]),
        itemStyle: {
          color: CANDLE_UP,
          color0: CANDLE_DOWN,
          borderColor: CANDLE_UP,
          borderColor0: CANDLE_DOWN,
        },
        markPoint: {
          symbol: 'circle',
          symbolSize: 7,
          label: { show: false },
          data: backendSignals.map(signal => ({
            name: signal.side,
            coord: [signal.barTime, signal.price],
            itemStyle: {
              color: signal.side.toUpperCase() === 'BUY' ? BUY_GREEN : SELL_RED,
            },
          })),
        },
        z: 2,
      },
      ...lineSeries,
    ],
  }
}

export function DowMiniChart({
  chart,
  testId,
  height = 96,
}: {
  chart: DowMonitorChart
  testId?: string
  height?: number
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartTheme = useChartTheme()
  const option = useMemo(
    () => buildDowMiniChartOption(chart, chartTheme),
    [chart, chartTheme],
  )

  useEffect(() => {
    if (!containerRef.current) return
    const instance = echarts.init(containerRef.current, undefined, { renderer: 'canvas' })
    instance.setOption(option, true)
    const resize = () => instance.resize()
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      instance.dispose()
    }
  }, [option])

  return (
    <div
      ref={containerRef}
      data-testid={testId}
      aria-label="迷你K线"
      className="w-full"
      style={{ height }}
    />
  )
}
