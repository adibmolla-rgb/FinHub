import { useEffect, useRef, useState } from 'react'
import { ColorType, createChart, LineSeries, type Time } from 'lightweight-charts'
import { api, ApiError, type History, type Range } from '../api'
import { Panel } from '../components'
import { align, correlation, returns, stats } from './compare'
import { rebase } from './indicators'

const PALETTE = ['#3ddc97', '#6cb6ff', '#f0b429', '#e879f9', '#fb923c', '#94a3b8', '#f2555a', '#22d3ee']
const pct = (x: number) => (Number.isFinite(x) ? `${(x * 100).toFixed(1)}%` : '—')

export function CompareWorkspace({ symbols }: { symbols: string[] }) {
  const [range, setRange] = useState<Range>('1Y')
  const [hist, setHist] = useState<Record<string, History>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    Promise.allSettled(symbols.map((s) => api.history(s, range, true))).then((res) => {
      if (!live) return
      const h: Record<string, History> = {}
      const e: Record<string, string> = {}
      res.forEach((r, i) => {
        if (r.status === 'fulfilled') h[symbols[i]] = r.value
        else e[symbols[i]] = r.reason instanceof ApiError ? r.reason.message : String(r.reason)
      })
      setHist(h)
      setErrors(e)
      setLoading(false)
    })
    return () => { live = false }
  }, [symbols, range])

  const loaded = symbols.filter((s) => hist[s])
  const aligned = align(loaded.map((s) => ({ symbol: s, dates: hist[s].bars.map((b) => String(b.time)), closes: hist[s].bars.map((b) => b.close) })))

  useEffect(() => {
    if (!el.current || aligned.dates.length < 2) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 11 },
      grid: { vertLines: { color: '#1a212b' }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37', minBarSpacing: 0.05 },
    })
    loaded.forEach((s, i) => {
      const line = chart.addSeries(LineSeries, { color: PALETTE[i % PALETTE.length], lineWidth: 2, title: s })
      const r = rebase(aligned.closes[s])
      line.setData(aligned.dates.map((d, k) => ({ time: d as Time, value: r[k] })))
    })
    chart.timeScale().fitContent()
    return () => chart.remove()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hist])

  const rets = Object.fromEntries(loaded.map((s) => [s, returns(aligned.closes[s])]))
  return (
    <main className="grid grid--cmp">
      <Panel code="CMP" title={`${symbols.join(' vs ')} · growth of 1 (adjusted)`} className="grid__cmpchart">
        <div className="chart-wrap">
          <div className="chart-toolbar">
            {(['1M', '3M', '6M', '1Y', '5Y', 'MAX'] as const).map((r) => (
              <button key={r} className={`chip ${r === range ? 'chip--on' : ''}`} onClick={() => setRange(r)}>{r}</button>
            ))}
            {aligned.dates.length > 0 && <span className="badge">{aligned.dates[0]} → {aligned.dates[aligned.dates.length - 1]} · {aligned.dates.length} shared days</span>}
          </div>
          {loading && <p className="muted">Loading {symbols.length} histories…</p>}
          {Object.entries(errors).map(([s, e]) => <p key={s} className="bad small">{s}: {e}</p>)}
          {!loading && aligned.dates.length >= 2 && <div ref={el} className="chart" />}
        </div>
      </Panel>
      <Panel code="STATS" title="Over the shared period" className="grid__cmpstats">
        {loaded.length > 0 && aligned.dates.length >= 2 ? (
          <div className="stack">
            <table className="table">
              <thead><tr><th>Ticker</th><th className="num">Total</th><th className="num">CAGR</th><th className="num">Volatility</th><th className="num">Sharpe</th><th className="num">Max DD</th><th>Source</th></tr></thead>
              <tbody>
                {loaded.map((s, i) => {
                  const st = stats(aligned.closes[s])
                  return (
                    <tr key={s}>
                      <td><i className="swatch" style={{ background: PALETTE[i % PALETTE.length] }} />{s}</td>
                      <td className={`num ${st.total >= 0 ? 'ok' : 'bad'}`}>{pct(st.total)}</td>
                      <td className="num">{pct(st.cagr)}</td>
                      <td className="num">{pct(st.vol)}</td>
                      <td className="num">{st.sharpe.toFixed(2)}</td>
                      <td className="num bad">{pct(st.maxDrawdown)}</td>
                      <td className="muted small">{hist[s].provider_name}{hist[s].adjusted ? '' : ' (unadjusted!)'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {loaded.length > 1 && (
              <table className="corr">
                <thead><tr><th />{loaded.map((s) => <th key={s}>{s}</th>)}</tr></thead>
                <tbody>
                  {loaded.map((a) => (
                    <tr key={a}><th>{a}</th>{loaded.map((b) => {
                      const c = correlation(rets[a], rets[b])
                      return <td key={b} style={{ background: c >= 0 ? `rgba(242,85,90,${Math.abs(c) * 0.55})` : `rgba(108,182,255,${Math.abs(c) * 0.55})` }}>{Number.isFinite(c) ? c.toFixed(2) : '—'}</td>
                    })}</tr>
                  ))}
                </tbody>
              </table>
            )}
            <p className="muted small">Daily-return correlations. Sharpe uses a zero risk-free rate. Prices adjusted for splits and dividends, so total return includes dividends.</p>
          </div>
        ) : <p className="muted">—</p>}
      </Panel>
    </main>
  )
}
