import { useEffect, useRef, useState } from 'react'
import { ColorType, createChart, LineSeries, type Time } from 'lightweight-charts'
import { ApiError, formatValue, macroApi, type MacroDashboard, type MacroSeries, type Receipt } from './api'
import { Panel } from './components'

const ORDER = ['cpi', 'unemployment', 'rate_short', 'rate_long', 'gdp_real']

export function Spark({ s, format }: { s: Pick<MacroSeries, 'unit_kind' | 'points'>; format?: (v: number) => string }) {
  const el = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 10 },
      grid: { vertLines: { visible: false }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37', minBarSpacing: 0.05 },
      handleScroll: false,
      handleScale: false,
    })
    const pct = s.unit_kind === 'fraction'
    const line = chart.addSeries(LineSeries, {
      color: '#6cb6ff', lineWidth: 2, priceLineVisible: false,
      priceFormat: format ? { type: 'custom', formatter: format } : pct ? { type: 'custom', formatter: (v: number) => `${(v * 100).toFixed(1)}%` } : { type: 'price', precision: 2, minMove: 0.01 },
    })
    const seen = new Set<string>()
    line.setData(s.points.filter((p) => (seen.has(p.date) ? false : (seen.add(p.date), true))).map((p) => ({ time: p.date as Time, value: p.value })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [s, format])
  return <div ref={el} className="spark" />
}

export function MacroWorkspace({ country, onReceipt }: { country: string; onReceipt: (r: Receipt) => void }) {
  const [data, setData] = useState<MacroDashboard | null>(null)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    macroApi.get(country).then(setData, setError)
  }, [country])

  return (
    <main className="grid grid--macro">
      {!data && !error && <p className="muted">Loading OECD series for {country}…</p>}
      {error && (
        <div className="data-error">
          <p><span className="bad">Couldn’t load macro data.</span> <span className="muted">{error.message}</span></p>
          {error instanceof ApiError && error.attempts.length > 0 && <ul className="small muted">{error.attempts.map((a, i) => <li key={i}>✗ {a.provider}: {a.error}</li>)}</ul>}
        </div>
      )}
      {data && ORDER.filter((k) => data.series[k] || data.errors[k]).map((k) => {
        const s = data.series[k]
        return (
          <Panel key={k} code={k.toUpperCase().slice(0, 6)} title={s ? s.label : k} className="macro-card">
            {s ? (
              <div className="stack">
                <div className="macro-head">
                  <button className="val macro-val" onClick={() => onReceipt(s.latest)}>{formatValue(s.latest)}</button>
                  {s.change_1y && (
                    <button className={`val ${s.change_1y.value >= 0 ? 'warn' : 'ok'}`} onClick={() => onReceipt(s.change_1y!)}>
                      {s.change_1y.value >= 0 ? '+' : ''}{s.unit_kind === 'fraction' ? `${(s.change_1y.value * 100).toFixed(2)} pp` : formatValue(s.change_1y)} over a year
                    </button>
                  )}
                </div>
                <span className="muted small">{s.latest.label.match(/\(([^()]*)\)$/)?.[1]} · unit: {s.unit}</span>
                <Spark s={s} />
              </div>
            ) : <p className="bad small">{data.errors[k]}</p>}
          </Panel>
        )
      })}
      {data && <p className="muted small macro-note">{data.country.replace(/_/g, ' ')} · source: OECD via OpenBB. Percentages come only from series the provider marks as percent; others are shown exactly as reported, with the provider’s unit text. pp = percentage points.</p>}
    </main>
  )
}
