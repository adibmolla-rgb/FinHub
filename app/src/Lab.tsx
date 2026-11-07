// OPTIM and REPORT: skfolio and QuantStats, running in the agent engine's environment. No AI model is involved.

import { useEffect, useState } from 'react'
import { labApi, type LabReport, type OptimResult, type Receipt } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { DataError, Val } from './Ticker'

type Common = { onReceipt: (r: Receipt) => void }
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)

export function OptimWorkspace({ holdings, range: initialRange, onReceipt, onOpen }: { holdings: { symbol: string; weight: number }[]; range: string; onOpen: (c: string) => void } & Common) {
  const [range, setRange] = useState(initialRange)
  const [data, setData] = useState<OptimResult | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let live = true
    setData(null)
    setError(null)
    if (holdings.length >= 2) labApi.optimise(holdings, range).then((d) => { if (live) setData(d) }, (e) => { if (live) setError(e) })
    return () => { live = false }
  }, [holdings, range])

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="OPTIM" title="Do these weights hold up?" className="research-wide">
        <div className="stack">
          {holdings.length < 2 && <p className="muted">Give it at least two holdings: <code>OPTIM SPY 60 TLT 30 GLD 10</code>.</p>}
          {holdings.length >= 2 && (
            <>
              <p className="muted small">Each method chooses weights using the past year, then holds them for the next quarter, over and over. Only the held quarters count, so no method sees the data it’s judged on.</p>
              <div className="ticket">
                {['5Y', 'MAX'].map((r) => <button key={r} className={`chip ${range === r ? 'chip--on' : ''}`} onClick={() => setRange(r)}>{r}</button>)}
                <button className="chip" onClick={() => onOpen(`RISK ${holdings.map((h) => `${h.symbol} ${h.weight}`).join(' ')}`)}>Open in RISK</button>
              </div>
            </>
          )}
          {error && <DataError error={error} what="this test" />}
          {holdings.length >= 2 && !data && !error && <p className="muted">Testing… (usually under a minute)</p>}
          {data && (
            <>
              <p className="muted small">{data.start} to {data.end} · {data.held_days} days held across {data.windows} quarters.</p>
              {data.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
              <div className="ticket">
                <CopyCsvButton rows={() => [['method', 'return_a_year', 'volatility', 'sharpe', 'max_drawdown', ...data.symbols], ...data.rows.map((r) => [r.name, r.annual_return?.value, r.annual_volatility?.value, r.sharpe?.value, r.max_drawdown?.value, ...data.symbols.map((s) => r.weights[s])])]} />
              </div>
              <table className="table">
                <thead><tr><th>Method</th><th className="num">Return a year</th><th className="num">Volatility</th><th className="num">Sharpe</th><th className="num">Worst fall</th>{data.symbols.map((s) => <th key={s} className="num">{s}</th>)}</tr></thead>
                <tbody>
                  {data.rows.map((r) => (
                    <tr key={r.name} className={r.yours ? 'row--mine' : ''}>
                      <td>{r.yours ? <strong>{r.name}</strong> : r.name}</td>
                      <td className="num"><Val r={r.annual_return ?? undefined} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={r.annual_volatility ?? undefined} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={r.sharpe ?? undefined} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={r.max_drawdown ?? undefined} onReceipt={onReceipt} /></td>
                      {data.symbols.map((s) => <td key={s} className="num muted">{pct(r.weights[s], 0)}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.problems.map((p) => <p key={p.name} className="warn small">{p.name} couldn’t be tested: {p.error}</p>)}
              <p className="muted small">The weights shown for each method are what it would choose today, using the past year. Results are before trading costs, and rankings shift with the period, so a small lead means little. Tickers are limited to what they all traded through. Prices are dividend-adjusted.</p>
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}

function ReportBody({ data, onReceipt }: { data: LabReport } & Common) {
  const hasBenchmark = !!data.benchmark_label
  return (
    <div className="stack">
      <p className="muted small">{data.start} to {data.end} · {data.days} trading days{hasBenchmark ? ` · against ${data.benchmark_label}` : ''}.</p>
      {data.warnings?.map((w) => <p key={w} className="warn small">{w}</p>)}
      <div className="ticket">
        <CopyCsvButton rows={() => [['metric', data.label, ...(hasBenchmark ? [data.benchmark_label ?? ''] : [])], ...data.metrics.map((m) => [m.label, m.value, ...(hasBenchmark ? [m.benchmark?.value] : [])])]} />
      </div>
      <table className="table">
        <thead><tr><th>Measure</th><th className="num">{data.label}</th>{hasBenchmark && <th className="num">{data.benchmark_label}</th>}</tr></thead>
        <tbody>
          {data.metrics.map((m) => (
            <tr key={m.key}>
              <td>{m.label}</td>
              <td className="num"><Val r={m.receipt} onReceipt={onReceipt} /></td>
              {hasBenchmark && <td className="num"><Val r={m.benchmark ?? undefined} onReceipt={onReceipt} /></td>}
            </tr>
          ))}
          {data.relative.map((m) => (
            <tr key={m.key}>
              <td>{m.label}</td>
              <td className="num"><Val r={m.receipt} onReceipt={onReceipt} /></td>
              <td />
            </tr>
          ))}
        </tbody>
      </table>
      {data.drawdowns.length > 0 && (
        <>
          <h3 className="small">Worst falls</h3>
          <table className="table">
            <thead><tr><th>Started</th><th>Lowest</th><th>Recovered</th><th className="num">Days</th><th className="num">Depth</th></tr></thead>
            <tbody>
              {data.drawdowns.map((d) => (
                <tr key={d.start}><td className="cell-date">{d.start}</td><td className="cell-date">{d.low}</td><td className="cell-date">{d.end}</td><td className="num">{d.days}</td><td className="num bad">{pct(d.depth)}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {data.monthly.length > 0 && (
        <>
          <h3 className="small">Returns by month</h3>
          <div className="table-scroll">
            <table className="table">
              <thead><tr><th>Year</th>{MONTHS.map((m) => <th key={m} className="num">{m[0] + m.slice(1).toLowerCase()}</th>)}<th className="num">Year</th></tr></thead>
              <tbody>
                {data.monthly.map((row) => (
                  <tr key={row.year}>
                    <td>{row.year}</td>
                    {MONTHS.map((m) => {
                      const v = row[m]
                      return <td key={m} className={`num ${v == null || v === 0 ? 'muted' : v < 0 ? 'bad' : 'ok'}`}>{v == null || v === 0 ? '—' : pct(v)}</td>
                    })}
                    <td className={`num ${(row.EOY ?? 0) < 0 ? 'bad' : 'ok'}`}>{pct(row.EOY)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="muted small">Sharpe and Sortino use a risk-free rate of 0. A few good years can hide a poor recent one, so read the months too.</p>
    </div>
  )
}

/** A report for a series FinHub already has, such as a backtest or a paper account. */
export function SeriesReport({ title, load, onReceipt }: { title: string; load: () => Promise<LabReport> } & Common) {
  const [open, setOpen] = useState(false)
  const [data, setData] = useState<LabReport | null>(null)
  const [error, setError] = useState<Error | null>(null)
  function show() {
    setOpen(true)
    if (data) return
    setError(null)
    load().then(setData, setError)
  }
  if (!open) return <button className="chip" onClick={show}>{title}</button>
  return (
    <div className="stack">
      <div className="ticket"><button className="chip" onClick={() => setOpen(false)}>Hide report</button></div>
      {error && <DataError error={error} what="this report" />}
      {!data && !error && <p className="muted">Working it out…</p>}
      {data && <ReportBody data={data} onReceipt={onReceipt} />}
    </div>
  )
}

export function ReportWorkspace({ symbol, benchmark, range: initialRange, onReceipt }: { symbol: string; benchmark?: string; range: string } & Common) {
  const [range, setRange] = useState(initialRange)
  const [data, setData] = useState<LabReport | null>(null)
  const [error, setError] = useState<Error | null>(null)
  useEffect(() => {
    let live = true
    setData(null)
    setError(null)
    labApi.report(symbol, benchmark, range).then((d) => { if (live) setData(d) }, (e) => { if (live) setError(e) })
    return () => { live = false }
  }, [symbol, benchmark, range])
  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="REPORT" title={`Performance report · ${symbol}`} className="research-wide">
        <div className="stack">
          <div className="ticket">{['1Y', '5Y', 'MAX'].map((r) => <button key={r} className={`chip ${range === r ? 'chip--on' : ''}`} onClick={() => setRange(r)}>{r}</button>)}</div>
          {error && <DataError error={error} what="this report" />}
          {!data && !error && <p className="muted">Working it out… (the first one after launch can take a minute)</p>}
          {data && <ReportBody data={data} onReceipt={onReceipt} />}
        </div>
      </Panel>
    </main>
  )
}
