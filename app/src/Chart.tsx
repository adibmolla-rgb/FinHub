import { useEffect, useRef } from 'react'
import { CandlestickSeries, ColorType, createChart, HistogramSeries, type IChartApi, type Time } from 'lightweight-charts'
import type { Bar } from './api'

const UP = '#3ddc97'
const DOWN = '#f2555a'

/** Candlestick chart with volume, using TradingView's lightweight-charts (Apache-2.0). */
export function PriceChart({ bars }: { bars: Bar[] }) {
  const el = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 11 },
      grid: { vertLines: { color: '#1a212b' }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37' },
      crosshair: { mode: 0 },
    })
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderUpColor: UP, borderDownColor: DOWN, wickUpColor: UP, wickDownColor: DOWN,
    })
    const volume = chart.addSeries(HistogramSeries, { priceScaleId: '', priceFormat: { type: 'volume' } })
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    candles.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.22 } })

    candles.setData(bars.map((b) => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })))
    volume.setData(bars.map((b) => ({ time: b.time as Time, value: b.volume, color: b.close >= b.open ? `${UP}55` : `${DOWN}55` })))
    chart.timeScale().fitContent()
    chartRef.current = chart
    return () => {
      chart.remove()
      chartRef.current = null
    }
  }, [bars])

  return <div ref={el} className="chart" />
}
