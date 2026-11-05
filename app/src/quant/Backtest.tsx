import { useEffect, useRef, useState } from 'react'
import { ColorType, createChart, LineSeries, AreaSeries, type Time } from 'lightweight-charts'
import { ApiError, backtestApi, type BacktestRequest, type BacktestResult, type Metrics, type StrategyInfo } from '../api'
import { Panel } from '../components'
import { CopyCsvButton } from '../CopyCsv'

const pct = (x: number | undefined, d = 1) => (x == null || !Number.isFinite(x) ? '—' : `${(x * 100).toFixed(d)}%`)
const num = (x: number | undefined, d = 2) => (x == null || !Number.isFinite(x) ? '—' : x.toFixed(d))

const PARAM_LABEL: Record<string, string> = { fast: 'Fast MA (days)', slow: 'Slow MA (days)', lookback: 'Lookback (days)', entry_z: 'Entry z-score' }

function EquityChart({ result }: { result: BacktestResult }) {
  const el = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 11 },
      grid: { vertLines: { color: '#1a212b' }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37', minBarSpacing: 0.05 },
    })
    const strat = chart.addSeries(LineSeries, { color: '#3ddc97', lineWidth: 2, title: 'strategy' })
    const bh = chart.addSeries(LineSeries, { color: '#6cb6ff', lineWidth: 1, title: 'buy & hold' })
    const dd = chart.addSeries(AreaSeries, {
      priceScaleId: 'dd', lineColor: '#f2555a', topColor: 'rgba(242,85,90,0.05)', bottomColor: 'rgba(242,85,90,0.35)',
      lineWidth: 1, title: 'drawdown', priceFormat: { type: 'percent' },
    })
    dd.priceScale().applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } })
    strat.priceScale().applyOptions({ scaleMargins: { top: 0.05, bottom: 0.3 } })
    const seen = new Set<string>()
    const rows = result.curve.filter((c) => (seen.has(c.time) ? false : (seen.add(c.time), true)))
    strat.setData(rows.map((c) => ({ time: c.time as Time, value: c.strategy })))
    bh.setData(rows.map((c) => ({ time: c.time as Time, value: c.buy_hold })))
    dd.setData(rows.map((c) => ({ time: c.time as Time, value: c.drawdown * 100 })))
    chart.timeScale().fitContent()
    return () => chart.remove()
  }, [result])
  return <div ref={el} className="chart" />
}

function MetricsTable({ m }: { m: BacktestResult['metrics'] }) {
  const rows: [string, (x: Metrics) => string][] = [
    ['Total return', (x) => pct(x.total_return)],
    ['CAGR', (x) => pct(x.cagr)],
    ['Volatility (ann.)', (x) => pct(x.volatility)],
    ['Sharpe', (x) => num(x.sharpe)],
    ['Sortino', (x) => num(x.sortino)],
    ['Max drawdown', (x) => pct(x.max_drawdown)],
    ['Calmar', (x) => num(x.calmar)],
    ['Position changes', (x) => (x.trades == null ? '—' : String(x.trades))],
    ['Time invested', (x) => pct(x.exposure, 0)],
    ['Turnover / year', (x) => num(x.turnover_per_year, 1)],
  ]
  return (
    <table className="table">
      <thead><tr><th /><th className="num">Strategy</th><th className="num">Before costs</th><th className="num">Buy &amp; hold</th></tr></thead>
      <tbody>
        {rows.map(([label, fn]) => (
          <tr key={label}><td>{label}</td><td className="num">{fn(m.strategy)}</td><td className="num muted">{fn(m.strategy_before_costs)}</td><td className="num">{fn(m.buy_hold)}</td></tr>
        ))}
      </tbody>
    </table>
  )
}

function sharpeColor(v: number) {
  const a = Math.min(1, Math.abs(v) / 1.5) * 0.6
  return v >= 0 ? `rgba(61,220,151,${a})` : `rgba(242,85,90,${a})`
}

/** Sharpe for every parameter combination tried: a robust result sits on a plateau, not a spike. */
function Surface({ result }: { result: BacktestResult }) {
  const wf = result.walk_forward
  if (!wf.available || !wf.surface?.length) return null
  const keys = Object.keys(wf.surface[0].params)
  const chosen = (p: Record<string, number>) => keys.every((k) => p[k] === result.params[k])
  if (keys.length === 1) {
    const k = keys[0]
    return (
      <table className="surface"><tbody>
        <tr><th>{k}</th>{wf.surface.map((c) => <td key={c.params[k]} className="muted">{c.params[k]}</td>)}</tr>
        <tr><th>Sharpe</th>{wf.surface.map((c) => <td key={c.params[k]} className={chosen(c.params) ? 'surface__on' : ''} style={{ background: sharpeColor(c.sharpe) }}>{c.sharpe.toFixed(2)}</td>)}</tr>
      </tbody></table>
    )
  }
  const [rk, ck] = keys
  const rows = [...new Set(wf.surface.map((c) => c.params[rk]))].sort((a, b) => a - b)
  const cols = [...new Set(wf.surface.map((c) => c.params[ck]))].sort((a, b) => a - b)
  const at = (r: number, c: number) => wf.surface.find((x) => x.params[rk] === r && x.params[ck] === c)
  return (
    <table className="surface"><tbody>
      <tr><th>{rk} \ {ck}</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
      {rows.map((r) => (
        <tr key={r}><th>{r}</th>{cols.map((c) => {
          const cell = at(r, c)
          return cell ? <td key={c} className={chosen(cell.params) ? 'surface__on' : ''} style={{ background: sharpeColor(cell.sharpe) }}>{cell.sharpe.toFixed(2)}</td> : <td key={c} className="muted">—</td>
        })}</tr>
      ))}
    </tbody></table>
  )
}

export type BacktestPreset = { symbol?: string; strategy?: string; params?: number[] }

export function BacktestWorkspace({ preset }: { preset: BacktestPreset }) {
  const [strategies, setStrategies] = useState<StrategyInfo[] | null>(null)
  const [req, setReq] = useState<BacktestRequest>({
    symbol: preset.symbol ?? 'SPY', strategy: preset.strategy ?? 'sma', params: {}, range: '5Y',
    cost_bps: 5, slippage_bps: 5, allow_short: false,
  })
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [running, setRunning] = useState(false)

  const run = async (r: BacktestRequest) => {
    setRunning(true)
    setError(null)
    try {
      setResult(await backtestApi.run(r))
    } catch (e) {
      setError(e as Error)
      setResult(null)
    } finally {
      setRunning(false)
    }
  }

  useEffect(() => {
    backtestApi.strategies().then((list) => {
      setStrategies(list)
      const spec = list.find((s) => s.name === req.strategy) ?? list[0]
      const params = { ...spec.defaults }
      spec.params.forEach((k, i) => {
        const v = preset.params?.[i]
        if (v != null && Number.isFinite(v)) params[k] = v
      })
      const initial = { ...req, strategy: spec.name, params }
      setReq(initial)
      if (preset.symbol) run(initial)
    }, (e) => setError(e))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const spec = strategies?.find((s) => s.name === req.strategy)
  const wf = result?.walk_forward
  const dsr = result?.deflated_sharpe

  return (
    <main className="grid grid--bt">
      <Panel code="BACKTEST" title="Strategy" className="grid__btform">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); run(req) }}>
          <div className="numgrid">
            <label className="numfield"><span>Ticker</span>
              <input value={req.symbol} onChange={(e) => setReq({ ...req, symbol: e.target.value.toUpperCase() })} spellCheck={false} />
            </label>
            <label className="numfield"><span>Strategy</span>
              <select className="select" value={req.strategy} onChange={(e) => {
                const s = strategies?.find((x) => x.name === e.target.value)
                if (s) setReq({ ...req, strategy: s.name, params: { ...s.defaults } })
              }}>
                {strategies?.map((s) => <option key={s.name} value={s.name}>{s.label}</option>)}
              </select>
            </label>
            {spec?.params.map((k) => (
              <label key={k} className="numfield"><span>{PARAM_LABEL[k] ?? k}</span>
                <input type="number" step={k === 'entry_z' ? 0.25 : 1} value={req.params[k] ?? ''} onChange={(e) => setReq({ ...req, params: { ...req.params, [k]: parseFloat(e.target.value) } })} />
              </label>
            ))}
            <label className="numfield"><span>Commission (bps per trade)</span>
              <input type="number" step={1} value={req.cost_bps} onChange={(e) => setReq({ ...req, cost_bps: parseFloat(e.target.value) })} />
            </label>
            <label className="numfield"><span>Slippage (bps per trade)</span>
              <input type="number" step={1} value={req.slippage_bps} onChange={(e) => setReq({ ...req, slippage_bps: parseFloat(e.target.value) })} />
            </label>
          </div>
          <div className="ticket">
            {(['1Y', '5Y', 'MAX'] as const).map((r) => (
              <button type="button" key={r} className={`chip ${req.range === r ? 'chip--on' : ''}`} onClick={() => setReq({ ...req, range: r })}>{r}</button>
            ))}
            <label className="inline small"><input type="checkbox" checked={req.allow_short} onChange={(e) => setReq({ ...req, allow_short: e.target.checked })} /> allow shorting</label>
          </div>
          <button className="btn btn--buy" type="submit" disabled={running}>{running ? 'Running… (first run waits for the data engine)' : 'Run backtest'}</button>
          <p className="muted small">1 bp = 0.01%. A round trip pays commission + slippage twice. Walk-forward needs about 6+ years (use MAX).</p>
        </form>
      </Panel>

      <Panel code="EQ" title={result ? `${result.symbol} · ${result.label} ${Object.values(result.params).join('/')} · growth of 1` : 'Equity curve'} className="grid__bteq">
        <div className="chart-wrap">
          {error && (
            <div className="data-error">
              <p><span className="bad">Backtest failed.</span> <span className="muted">{error.message}</span></p>
              {error instanceof ApiError && error.attempts.length > 0 && (
                <ul className="small muted">{error.attempts.map((a, i) => <li key={i}>✗ {a.provider}: {a.error}</li>)}</ul>
              )}
            </div>
          )}
          {!result && !error && <p className="muted">Pick a ticker and strategy, then run. Green: strategy · blue: buy &amp; hold · red: drawdown.</p>}
          {result && <EquityChart result={result} />}
        </div>
      </Panel>

      <Panel code="VAL" title="Can you trust this result?" className="grid__btval">
        {result ? (
          <ul className="checks">
            <li className={result.causality_check ? 'ok' : 'bad'}>{result.causality_check ? '✓' : '✗'} No look-ahead: signals on truncated history match the full run</li>
            <li className="ok">✓ Next-bar fills: {result.fills.toLowerCase()}</li>
            <li className="ok">✓ Costs: {result.costs.commission_bps} bps commission + {result.costs.slippage_bps} bps slippage per trade</li>
            <li className={result.data.adjusted ? 'ok' : 'warn'}>{result.data.adjusted ? '✓' : '⚠'} Prices {result.data.adjusted ? 'adjusted for splits and dividends' : 'NOT adjusted'} · {result.data.bars} bars from {result.data.provider}</li>
            {wf?.available ? (
              <li className={wf.out_of_sample.sharpe > 0.5 * result.metrics.strategy.sharpe ? 'ok' : 'warn'}>
                {wf.out_of_sample.sharpe > 0.5 * result.metrics.strategy.sharpe ? '✓' : '⚠'} Walk-forward (parameters chosen on the past only): Sharpe {num(wf.out_of_sample.sharpe)} out of sample since {wf.oos_start}, vs {num(result.metrics.strategy.sharpe)} full sample
              </li>
            ) : (
              <li className="muted">– Walk-forward: {wf && !wf.available ? wf.reason : '—'}</li>
            )}
            {dsr && Number.isFinite(dsr.dsr) && (
              <li className={dsr.dsr >= 0.95 ? 'ok' : 'warn'}>
                {dsr.dsr >= 0.95 ? '✓' : '⚠'} Deflated Sharpe: {pct(dsr.dsr, 0)} probability the edge is real after {dsr.trials} parameter combinations (luck alone would give a Sharpe of ~{num(dsr.sr0_annual)})
              </li>
            )}
            {result.warnings.filter((w) => !w.startsWith('Deflated Sharpe probability')).map((w, i) => <li key={i} className="warn">⚠ {w}</li>)}
          </ul>
        ) : (
          <p className="muted">Each run is checked for look-ahead bias, costs, overfitting (walk-forward) and luck (deflated Sharpe).</p>
        )}
      </Panel>

      <Panel code="STATS" title="Performance" className="grid__btstats">
        {result ? (
          <div className="stack">
            <MetricsTable m={result.metrics} />
            <p className="muted small">{result.period.start} → {result.period.end}. Sharpe uses a zero risk-free rate.</p>
            <div className="ticket">
              <CopyCsvButton label="Copy metrics" rows={() => [
                ['metric', 'strategy', 'before_costs', 'buy_and_hold'],
                ...(['total_return', 'cagr', 'volatility', 'sharpe', 'sortino', 'max_drawdown', 'calmar', 'trades', 'exposure', 'turnover_per_year'] as const).map((k) => [
                  k, result.metrics.strategy[k] ?? null, result.metrics.strategy_before_costs[k] ?? null, result.metrics.buy_hold[k] ?? null,
                ]),
              ]} />
              <CopyCsvButton label="Copy equity curve" rows={() => [['date', 'strategy', 'buy_and_hold', 'drawdown'], ...result.curve.map((c) => [c.time, c.strategy, c.buy_hold, c.drawdown])]} />
            </div>
          </div>
        ) : <p className="muted">—</p>}
      </Panel>

      <Panel code="WF" title="Walk-forward folds and parameter sensitivity" className="grid__btwf">
        {wf?.available ? (
          <div className="wfgrid">
          <table className="table">
            <thead><tr><th>Fold</th><th>Chosen on past data</th><th className="num">In-sample Sharpe</th><th className="num">Next-period Sharpe</th></tr></thead>
            <tbody>
              {wf.folds.map((f) => (
                <tr key={f.fold}>
                  <td>{f.fold}</td>
                  <td><code>{Object.entries(f.params).map(([k, v]) => `${k}=${v}`).join(' ')}</code></td>
                  <td className="num">{num(f.in_sample_sharpe)}</td>
                  <td className={`num ${f.out_of_sample_sharpe >= 0 ? 'ok' : 'bad'}`}>{num(f.out_of_sample_sharpe)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="stack">
            <span className="muted small">Full-sample Sharpe for all {wf.trials} combinations tried (yours outlined). A broad green area suggests a robust effect; one bright cell among red suggests luck.</span>
            <Surface result={result!} />
          </div>
          </div>
        ) : <p className="muted">{wf && !wf.available ? wf.reason : 'Shown after a run.'}</p>}
      </Panel>
    </main>
  )
}
