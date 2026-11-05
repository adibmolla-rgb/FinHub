import { useEffect, useRef } from 'react'
import { CandlestickSeries, ColorType, createChart, HistogramSeries, LineSeries, type IChartApi, type Time } from 'lightweight-charts'
import type { Bar } from './api'
import { bollinger, ema, rsi, sma } from './quant/indicators'

const UP = '#3ddc97'
const DOWN = '#f2555a'

export const INDICATORS = ['SMA20', 'SMA50', 'SMA200', 'EMA20', 'BB', 'RSI'] as const
export type Indicator = (typeof INDICATORS)[number]

const COLORS: Record<string, string> = { SMA20: '#f0b429', SMA50: '#6cb6ff', SMA200: '#c084fc', EMA20: '#fb923c', BB: '#94a3b8', RSI: '#e879f9' }

/** Candlestick chart with volume and optional indicators, using TradingView's lightweight-charts (Apache-2.0). */
export function PriceChart({ bars, indicators = [] }: { bars: Bar[]; indicators?: Indicator[] }) {
  const el = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 11, panes: { separatorColor: '#232b37' } },
      grid: { vertLines: { color: '#1a212b' }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37', minBarSpacing: 0.05 },
      crosshair: { mode: 0 },
    })
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN, wickUpColor: UP, wickDownColor: DOWN,
    })
    const volume = chart.addSeries(HistogramSeries, { priceScaleId: '', priceFormat: { type: 'volume' } })
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    candles.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.22 } })

    const times = bars.map((b) => b.time as Time)
    candles.setData(bars.map((b) => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })))
    volume.setData(bars.map((b) => ({ time: b.time as Time, value: b.volume, color: b.close >= b.open ? `${UP}55` : `${DOWN}55` })))

    const closes = bars.map((b) => b.close)
    const line = (values: (number | null)[], color: string, title: string, pane = 0, dashed = false) => {
      const s = chart.addSeries(LineSeries, { color, lineWidth: 1, title, lineStyle: dashed ? 2 : 0, priceLineVisible: false, lastValueVisible: false }, pane)
      s.setData(values.flatMap((v, i) => (v == null ? [] : [{ time: times[i], value: v }])))
      return s
    }
    for (const ind of indicators) {
      if (ind.startsWith('SMA')) line(sma(closes, Number(ind.slice(3))), COLORS[ind], ind)
      else if (ind === 'EMA20') line(ema(closes, 20), COLORS[ind], 'EMA20')
      else if (ind === 'BB') {
        const bb = bollinger(closes, 20, 2)
        line(bb.upper, COLORS.BB, 'BB upper', 0, true)
        line(bb.lower, COLORS.BB, 'BB lower', 0, true)
      } else if (ind === 'RSI') {
        const s = line(rsi(closes, 14), COLORS.RSI, 'RSI 14', 1)
        s.createPriceLine({ price: 70, color: '#f2555a88', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' })
        s.createPriceLine({ price: 30, color: '#3ddc9788', lineWidth: 1, lineStyle: 2, axisLabelVisible: false, title: '' })
        chart.panes()[1]?.setHeight(110)
      }
    }
    chart.timeScale().fitContent()
    chartRef.current = chart
    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [bars, indicators])

  return <div ref={el} className="chart" />
}
