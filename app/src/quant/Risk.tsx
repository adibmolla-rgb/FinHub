import { useEffect, useState } from 'react'
import { ApiError, riskApi, type RiskRequest, type RiskResult } from '../api'
import { Panel } from '../components'

const pct = (x: number | undefined, d = 2) => (x == null || !Number.isFinite(x) ? '—' : `${(x * 100).toFixed(d)}%`)
const money = (x: number) => x.toLocaleString(undefined, { maximumFractionDigits: 0 })

function corrColor(c: number) {
  // red for +1, blue for -1, near-transparent around 0
  const a = Math.min(1, Math.abs(c)) * 0.55
  return c >= 0 ? `rgba(242,85,90,${a})` : `rgba(108,182,255,${a})`
}

function Histogram({ r }: { r: RiskResult }) {
  const { counts, edges } = r.histogram
  const W = 640, H = 200, pad = 28
  const max = Math.max(...counts, 1)
  const x0 = edges[0], x1 = edges[edges.length - 1]
  const sx = (x: number) => pad + ((x - x0) / (x1 - x0)) * (W - 2 * pad)
  const bw = (W - 2 * pad) / counts.length
  const lines = [
    { v: -r.var.historical.var, label: `VaR ${pct(r.var.historical.var, 1)}`, color: '#f0b429' },
    { v: -r.var.historical.es, label: `ES ${pct(r.var.historical.es, 1)}`, color: '#f2555a' },
  ]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="hist" role="img">
      {counts.map((c, i) => {
        const left = edges[i] < -r.var.historical.var
        return <rect key={i} x={pad + i * bw + 0.5} y={H - pad - (c / max) * (H - 2 * pad)} width={Math.max(0.5, bw - 1)} height={(c / max) * (H - 2 * pad)} fill={left ? '#f2555a' : '#3ddc97'} opacity={left ? 0.8 : 0.45} />
      })}
      {lines.map((l, i) => (
        <g key={i}>
          <line x1={sx(l.v)} x2={sx(l.v)} y1={pad - 10} y2={H - pad} stroke={l.color} strokeDasharray="4 3" />
          <text x={sx(l.v) - 4} y={pad - 12 + i * 12} textAnchor="end" className="xychart__tick" fill={l.color}>{l.label}</text>
        </g>
      ))}
      {[x0, 0, x1].map((t) => <text key={t} x={sx(t)} y={H - 8} textAnchor="middle" className="xychart__tick">{pct(t, 1)}</text>)}
    </svg>
  )
}

function parseHoldings(text: string) {
  const parts = text.trim().split(/[\s,]+/).filter(Boolean)
  const out: { symbol: string; weight: number }[] = []
  for (let i = 0; i < parts.length; i += 2) {
    const symbol = parts[i]?.toUpperCase()
    const weight = parseFloat(parts[i + 1])
    if (symbol && Number.isFinite(weight) && weight > 0) out.push({ symbol, weight })
  }
  return out
}

export function RiskWorkspace({ initial, onOpen }: { initial?: { symbol: string; weight: number }[]; onOpen?: (command: string) => void }) {
  const [holdingsText, setHoldingsText] = useState(() =>
    (initial?.length ? initial : [{ symbol: 'SPY', weight: 60 }, { symbol: 'TLT', weight: 30 }, { symbol: 'GLD', weight: 10 }])
      .map((h) => `${h.symbol} ${h.weight}`).join('  '),
  )
  const [conf, setConf] = useState(0.99)
  const [range, setRange] = useState<RiskRequest['range']>('5Y')
  const [value, setValue] = useState(10_000)
  const [result, setResult] = useState<RiskResult | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [running, setRunning] = useState(false)

  const run = async () => {
    const holdings = parseHoldings(holdingsText)
    if (!holdings.length) return setError(new Error('Enter holdings as “TICKER weight”, e.g. SPY 60 TLT 40'))
    setRunning(true)
    setError(null)
    try {
      setResult(await riskApi.run({ holdings, range, confidence: conf, value }))
    } catch (e) {
      setError(e as Error)
      setResult(null)
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    if (initial?.length) run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const r = result
  return (
    <main className="grid grid--risk">
      <Panel code="RISK" title="Portfolio" className="grid__riskin">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); run() }}>
          <label className="numfield"><span>Holdings (ticker weight …)</span>
            <input value={holdingsText} onChange={(e) => setHoldingsText(e.target.value)} spellCheck={false} />
          </label>
          <div className="numgrid">
            <label className="numfield"><span>Portfolio value</span>
              <input type="number" value={value} onChange={(e) => setValue(parseFloat(e.target.value))} />
            </label>
            <div className="numfield"><span>Confidence</span>
              <div className="ticket">{[0.95, 0.99].map((c) => <button type="button" key={c} className={`chip ${conf === c ? 'chip--on' : ''}`} onClick={() => setConf(c)}>{c * 100}%</button>)}</div>
            </div>
          </div>
          <div className="ticket">{(['1Y', '5Y', 'MAX'] as const).map((x) => <button type="button" key={x} className={`chip ${range === x ? 'chip--on' : ''}`} onClick={() => setRange(x)}>{x}</button>)}</div>
          <button className="btn btn--buy" type="submit" disabled={running}>{running ? 'Analysing…' : 'Analyse risk'}</button>
          {error && (
            <div className="data-error">
              <p className="bad">{error.message}</p>
              {error instanceof ApiError && error.attempts.length > 0 && <ul className="small muted">{error.attempts.map((a, i) => <li key={i}>✗ {a.provider}: {a.error}</li>)}</ul>}
            </div>
          )}
          {r && r.symbols.length >= 2 && onOpen && <button type="button" className="chip" onClick={() => onOpen(`OPTIM ${r.symbols.map((s, i) => `${s} ${+(r.weights[i] * 100).toFixed(2)}`).join(' ')}`)}>Test these weights out of sample</button>}
          {r && <p className="muted small">{r.period.start} → {r.period.end} · {r.period.days} shared trading days · daily rebalanced · {r.data.map((d) => `${d.symbol}: ${d.provider}`).join(', ')}</p>}
        </form>
      </Panel>

      <Panel code="VAR" title={r ? `1-day loss at ${r.confidence * 100}% confidence` : 'Value at Risk'} className="grid__riskvar">
        {r ? (
          <div className="stack">
            <table className="table">
              <thead><tr><th>Method</th><th className="num">VaR</th><th className="num">VaR ({money(r.value)})</th><th className="num">Expected shortfall</th></tr></thead>
              <tbody>
                {([['Historical', r.var.historical], ['Parametric (normal)', r.var.parametric], ['Monte Carlo (100k)', r.var.monte_carlo]] as const).map(([label, v]) => (
                  <tr key={label}><td>{label}</td><td className="num">{pct(v.var)}</td><td className="num">{money(v.var * r.value)}</td><td className="num">{pct(v.es)} <span className="muted">({money(v.es * r.value)})</span></td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted small">VaR: on {Math.round((1 - r.confidence) * 100)} day(s) in 100 you should expect to lose at least this much. Expected shortfall: the average loss on those days.</p>
            {r.var_backtest.available ? (
              <p className={r.var_backtest.p_value >= 0.05 ? 'ok small' : 'warn small'}>
                {r.var_backtest.p_value >= 0.05 ? '✓' : '⚠'} Backtest of rolling {r.var_backtest.window}-day historical VaR: {r.var_backtest.exceptions} breaches in {r.var_backtest.days} days vs {r.var_backtest.expected.toFixed(1)} expected (Kupiec p = {r.var_backtest.p_value.toFixed(3)}): {r.var_backtest.verdict}.
              </p>
            ) : <p className="muted small">VaR backtest: {r.var_backtest.reason}</p>}
          </div>
        ) : <p className="muted">Historical, parametric and Monte Carlo VaR side by side, with a backtest of whether VaR would have held.</p>}
      </Panel>

      <Panel code="DIST" title="Daily returns distribution" className="grid__riskdist">
        {r ? (
          <div className="stack">
            <Histogram r={r} />
            <div className="kv">
              <span>Volatility</span><span>{pct(r.portfolio.volatility, 1)} a year</span>
              <span>Max drawdown</span><span className="bad">{pct(r.portfolio.max_drawdown, 1)}</span>
              <span>Worst day</span><span>{pct(r.portfolio.worst_day.return, 1)} <span className="muted">{r.portfolio.worst_day.end}</span></span>
              <span>Worst week</span><span>{pct(r.portfolio.worst_week.return, 1)} <span className="muted">{r.portfolio.worst_week.start} → {r.portfolio.worst_week.end}</span></span>
              <span>Worst month</span><span>{pct(r.portfolio.worst_month.return, 1)} <span className="muted">{r.portfolio.worst_month.start} → {r.portfolio.worst_month.end}</span></span>
              <span>Skew / kurtosis</span><span>{r.portfolio.skew.toFixed(2)} / {r.portfolio.kurtosis.toFixed(1)} <span className="muted">(normal: 0 / 3)</span></span>
            </div>
          </div>
        ) : <p className="muted">—</p>}
      </Panel>

      <Panel code="CONTRIB" title="Holdings and risk contribution" className="grid__riskassets">
        {r ? (
          <div className="stack">
            <table className="table">
              <thead><tr><th>Ticker</th><th className="num">Weight</th><th className="num">Volatility</th><th className="num">Return (ann.)</th><th>Share of risk</th></tr></thead>
              <tbody>
                {r.assets.map((a) => (
                  <tr key={a.symbol}>
                    <td>{a.symbol}</td><td className="num">{pct(a.weight, 1)}</td><td className="num">{pct(a.volatility, 1)}</td><td className="num">{pct(a.expected_return, 1)}</td>
                    <td><div className="bar"><span style={{ width: `${Math.max(0, Math.min(100, a.risk_contribution * 100))}%` }} /><em>{pct(a.risk_contribution, 0)}</em></div></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table className="corr">
              <thead><tr><th />{r.symbols.map((s) => <th key={s}>{s}</th>)}</tr></thead>
              <tbody>
                {r.correlation.map((row, i) => (
                  <tr key={i}><th>{r.symbols[i]}</th>{row.map((c, j) => <td key={j} style={{ background: corrColor(c) }}>{c.toFixed(2)}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="muted">—</p>}
      </Panel>

      <Panel code="OPTIM" title="Alternative weights (long-only)" className="grid__riskopt">
        {r ? (
          <div className="stack">
            <table className="table">
              <thead><tr><th>Ticker</th><th className="num">Current</th><th className="num">Min variance</th><th className="num">Max Sharpe</th></tr></thead>
              <tbody>
                {r.symbols.map((s, i) => (
                  <tr key={s}>
                    <td>{s}</td>
                    <td className="num">{pct(r.optimisation.current.weights[i], 0)}</td>
                    <td className="num">{pct(r.optimisation.min_variance.weights[i], 0)} <span className="muted">±{pct(r.optimisation.min_variance.weight_sd?.[i], 0)}</span></td>
                    <td className="num">{pct(r.optimisation.max_sharpe.weights[i], 0)} <span className="muted">±{pct(r.optimisation.max_sharpe.weight_sd?.[i], 0)}</span></td>
                  </tr>
                ))}
                {(['expected_return', 'volatility'] as const).map((k) => (
                  <tr key={k} className="muted"><td>{k === 'expected_return' ? 'Return (hist.)' : 'Volatility'}</td>
                    {(['current', 'min_variance', 'max_sharpe'] as const).map((p) => <td key={p} className="num">{pct(r.optimisation[p][k], 1)}</td>)}
                  </tr>
                ))}
                <tr className="muted"><td>Sharpe (hist.)</td>{(['current', 'min_variance', 'max_sharpe'] as const).map((p) => <td key={p} className="num">{r.optimisation[p].sharpe.toFixed(2)}</td>)}</tr>
              </tbody>
            </table>
            <p className="muted small">± is how much each weight moves when the optimisation is repeated on resampled history (bootstrap). Large ± means the “optimal” weights are mostly noise from estimating returns.</p>
            {r.warnings.map((w, i) => <p key={i} className="warn small">⚠ {w}</p>)}
          </div>
        ) : <p className="muted">—</p>}
      </Panel>
    </main>
  )
}
