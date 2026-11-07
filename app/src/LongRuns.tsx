// AGENTS (TradingAgents) and QLIB (Microsoft Qlib): analyses that take minutes, run in the background and are saved.

import { useCallback, useEffect, useRef, useState } from 'react'
import { jobsApi, type AgentsResult, type JobKind, type JobRun, type QlibResult, type Receipt } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { Markdown } from './learn/markdown'
import { DataError, Val } from './Ticker'

const POLL_MS = 3000

function useJob<T>(kind: JobKind) {
  const [runs, setRuns] = useState<JobRun<T>[]>([])
  const [run, setRun] = useState<JobRun<T> | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const starting = useRef(false)

  const refresh = useCallback(() => jobsApi.list<T>(kind).then(setRuns, setError), [kind])

  const follow = useCallback((id: string) => {
    jobsApi.get<T>(id).then(setRun, setError)
  }, [])

  const running = run?.status === 'running' ? run.id : null

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Picks up a run already going, for instance after moving to another screen and back.
  useEffect(() => {
    const going = runs.find((r) => r.status === 'running')
    if (going && !run) follow(going.id)
  }, [runs, run, follow])

  useEffect(() => {
    if (!running) return
    const timer = setInterval(() => {
      jobsApi.get<T>(running).then((next) => {
        setRun(next)
        if (next.status !== 'running') void refresh()
      }, setError)
    }, POLL_MS)
    return () => clearInterval(timer)
  }, [running, refresh])

  const start = async (begin: () => Promise<JobRun<T>>) => {
    if (starting.current) return // a second click must never start, and pay for, a second run
    starting.current = true
    setError(null)
    try {
      setRun(await begin())
      void refresh()
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      starting.current = false
    }
  }

  return { runs, run, error, start, follow, busy: Boolean(running) }
}

function elapsed(run: JobRun<unknown>): string {
  if (!run.finished_at) return ''
  const seconds = (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000
  return seconds < 90 ? `${Math.round(seconds)} seconds` : `${Math.round(seconds / 60)} minutes`
}

function History<T>({ runs, current, onPick, describe }: { runs: JobRun<T>[]; current: JobRun<T> | null; onPick: (id: string) => void; describe: (r: JobRun<T>) => string }) {
  if (!runs.length) return null
  return (
    <>
      <h3 className="subhead">Saved runs</h3>
      <div className="ticket">
        {runs.map((r) => <button key={r.id} className={`chip ${current?.id === r.id ? 'chip--on' : ''}`} onClick={() => onPick(r.id)}>{r.started_at.slice(0, 16).replace('T', ' ')} · {describe(r)}{r.status === 'error' ? ' · failed' : r.status === 'running' ? ' · running' : ''}</button>)}
      </div>
    </>
  )
}

export function AgentsWorkspace({ symbol: firstSymbol }: { symbol?: string }) {
  const [symbol, setSymbol] = useState(firstSymbol ?? '')
  const { runs, run, error, start, follow, busy } = useJob<AgentsResult>('agents')
  const result = run?.status === 'done' ? run.result : null

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="AGENTS" title="A trading firm of AI agents" className="research-wide">
        <div className="stack">
          <p className="muted small">TradingAgents gives one stock to market, news and fundamentals analysts, then has bull and bear researchers argue, a trader decide and a risk team challenge it. It writes a report and can’t place orders.</p>
          <p className="warn small">It makes many calls to the AI provider set with the AI command, so it uses far more than ASK and can take a long time, especially on a small local model. The text is written by AI: its figures have no receipts and can be wrong.</p>
          <form className="ticket searchbar" onSubmit={(e) => { e.preventDefault(); if (symbol.trim()) void start(() => jobsApi.agents(symbol.trim().toUpperCase())) }}>
            <input className="cell" style={{ width: 110 }} value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="TSLA" maxLength={15} spellCheck={false} aria-label="Ticker" />
            <button className="chip chip--on" disabled={busy || !symbol.trim()}>{busy ? 'Running…' : 'Start'}</button>
          </form>
          {error && <DataError error={error} what="this run" />}
          {busy && <p className="muted">Running on {String(run?.request.symbol ?? "")}. You can leave this screen; closing FinHub stops it.</p>}
          {run?.status === 'error' && <p className="bad">This run failed: {run.error}</p>}
          {result && (
            <>
              <p>{result.symbol} as of {result.date}: <strong>{result.rating ?? 'no rating given'}</strong> <span className="muted small">({result.provider}, {result.model}, took {elapsed(run!)})</span></p>
              {result.sections.map((s) => (
                <details key={s.key} open={s.key === 'final_trade_decision'}>
                  <summary>{s.title}</summary>
                  <Markdown src={s.text} />
                </details>
              ))}
            </>
          )}
          <History runs={runs} current={run} onPick={follow} describe={(r) => String(r.request.symbol ?? '')} />
        </div>
      </Panel>
    </main>
  )
}

export function QlibWorkspace({ onReceipt, onOpen }: { onReceipt: (r: Receipt) => void; onOpen: (command: string) => void }) {
  const { runs, run, error, start, follow, busy } = useJob<QlibResult>('qlib')
  const result = run?.status === 'done' ? run.result : null
  const test = result?.test

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="QLIB" title="Can a machine learning model rank these stocks?" className="research-wide">
        <div className="stack">
          <p className="muted small">Microsoft’s Qlib workflow on FinHub’s large caps: 158 price and volume features, a LightGBM model, and a final test on the last three years, which it never saw while learning. It predicts the return from the next close to the one after, which leaves a day to act on it. No AI provider is involved.</p>
          <div className="ticket">
            <button className="chip chip--on" disabled={busy} onClick={() => void start(() => jobsApi.qlib())}>{busy ? 'Running…' : 'Start'}</button>
            <span className="muted small">Takes several minutes and is saved when it finishes.</span>
          </div>
          {error && <DataError error={error} what="this run" />}
          {busy && <p className="muted">Fetching prices, building features and training. You can leave this screen; closing FinHub stops it.</p>}
          {run?.status === 'error' && <p className="bad">This run failed: {run.error}</p>}
          {result && test && (
            <>
              <p className="warn small">These are today’s large caps, so every one of them is a survivor. That flatters any test on past years.</p>
              {result.rounds_used < 10 && <p className="warn">The model stopped improving after {result.rounds_used} of {result.rounds_allowed} rounds, so it found very little it could use. Read the numbers below with that in mind.</p>}
              <p className="muted small">Learned on {result.segments.train[0]} to {result.segments.train[1]}, tuned on {result.segments.valid[0]} to {result.segments.valid[1]}, tested on {result.segments.test[0]} to {result.segments.test[1]}. {result.stocks} stocks, price data from {result.price_provider}{result.left_out.length ? `; ${result.left_out.length} left out for short history` : ''}. Took {elapsed(run!)}.</p>
              <table className="table">
                <tbody>
                  <tr><td>Information coefficient</td><td className="num"><Val r={test.ic} onReceipt={onReceipt} /></td><td className="muted small">How well each day’s ranking matched what followed. 0 is nothing; 0.05 would be strong</td></tr>
                  <tr><td>Rank information coefficient</td><td className="num"><Val r={test.rank_ic} onReceipt={onReceipt} /></td><td className="muted small">The same, less affected by one stock’s huge move</td></tr>
                  <tr><td>Steadiness (ICIR)</td><td className="num"><Val r={test.icir ?? undefined} onReceipt={onReceipt} /></td><td className="muted small">The average divided by how much it varied from day to day</td></tr>
                  <tr><td>Days it was right</td><td className="num"><Val r={test.ic_positive} onReceipt={onReceipt} /></td><td className="muted small">Share of {test.days} days with a ranking better than chance</td></tr>
                  <tr><td>Top 5 minus bottom 5, a year</td><td className="num"><Val r={test.long_short_annual} onReceipt={onReceipt} /></td><td className="muted small">Trading every day, before any costs, which would take a large share of this. t = {test.long_short_t?.toFixed(2) ?? '—'}, and about 2 or more is what’s usually wanted</td></tr>
                </tbody>
              </table>
              <h3 className="subhead">What it ranks highest and lowest on {result.latest_day}</h3>
              <p className="muted small">The model’s output, not a recommendation.</p>
              <div className="ticket">
                {result.highest.map((r) => <button key={r.symbol} className="chip" onClick={() => onOpen(r.symbol)}>▲ {r.symbol}</button>)}
                {result.lowest.map((r) => <button key={r.symbol} className="chip" onClick={() => onOpen(r.symbol)}>▼ {r.symbol}</button>)}
              </div>
              {result.distinct_predictions < result.stocks / 2 && <p className="warn small">Many stocks got the same prediction ({result.distinct_predictions} different values across {result.stocks}), so this order means little.</p>}
              <h3 className="subhead">Features it leaned on most</h3>
              <div className="ticket"><CopyCsvButton rows={() => [['feature', 'importance'], ...result.top_features.map((f) => [f.name, f.score])]} /></div>
              <table className="table">
                <thead><tr><th>Feature</th><th className="num">Importance</th></tr></thead>
                <tbody>{result.top_features.map((f) => <tr key={f.name}><td><code>{f.name}</code></td><td className="num">{f.score?.toFixed(0) ?? '—'}</td></tr>)}</tbody>
              </table>
            </>
          )}
          <History runs={runs} current={run} onPick={follow} describe={() => 'large caps'} />
        </div>
      </Panel>
    </main>
  )
}
