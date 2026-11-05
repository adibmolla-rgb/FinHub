import { useCallback, useEffect, useRef, useState } from 'react'
import { ColorType, createChart, LineSeries, type ISeriesApi, type Time } from 'lightweight-charts'
import { BACKEND_URL } from '../api'
import { Panel } from '../components'

type Level = { price: number; qty: number; orders: number }
type ArenaState = {
  step: number
  seed: number
  best_bid: number | null
  best_ask: number | null
  mid: number | null
  depth: { bids: Level[]; asks: Level[] }
  recent_trades: { price: number; qty: number; buyer: string; seller: string; aggressor: string; step: number }[]
  leaderboard: { name: string; kind: 'bot' | 'participant'; about?: string; pnl: number; position: number }[]
  events: { step: number; text: string }[]
  history: { step: number; mid: number | null; value?: number }[]
}

const ME = 'you'
const f2 = (n: number | null | undefined) => (n == null ? '—' : n.toFixed(2))

async function post(path: string, body: unknown) {
  const res = await fetch(`${BACKEND_URL}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`)
  return data
}

/** The shared simulated market in the backend: AI agents trade here through MCP; you can watch and join. */
export function ArenaWorkspace() {
  const [st, setSt] = useState<ArenaState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [speed, setSpeed] = useState(5)
  const [reveal, setReveal] = useState(false)
  const [qty, setQty] = useState(100)
  const chartEl = useRef<HTMLDivElement>(null)
  const midSeries = useRef<ISeriesApi<'Line'> | null>(null)
  const valueSeries = useRef<ISeriesApi<'Line'> | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/sim/state?history=1500&reveal=${reveal}`)
      setSt(await res.json())
      setError(null)
    } catch (e) {
      setError(String(e))
    }
  }, [reveal])

  // Poll so trades made by AI agents show up even while the clock is paused.
  useEffect(() => {
    load()
    const t = setInterval(load, 1000)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    if (!running) return
    const t = setInterval(() => { post('/sim/advance', { steps: 1 }).then(load, (e) => setError(String(e))) }, 1000 / speed)
    return () => clearInterval(t)
  }, [running, speed, load])

  useEffect(() => {
    if (!chartEl.current) return
    const chart = createChart(chartEl.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 11 },
      grid: { vertLines: { color: '#1a212b' }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37', tickMarkFormatter: (t: Time) => `${t}`, minBarSpacing: 0.05 },
      localization: { timeFormatter: (t: Time) => `step ${t}` },
    })
    midSeries.current = chart.addSeries(LineSeries, { color: '#3ddc97', lineWidth: 2, title: 'mid' })
    valueSeries.current = chart.addSeries(LineSeries, { color: '#f0b429', lineWidth: 1, lineStyle: 2, title: 'true value' })
    return () => chart.remove()
  }, [])

  useEffect(() => {
    if (!st) return
    midSeries.current?.setData(st.history.filter((h) => h.mid != null).map((h) => ({ time: h.step as Time, value: h.mid! })))
    valueSeries.current?.setData(reveal ? st.history.filter((h) => h.value != null).map((h) => ({ time: h.step as Time, value: h.value! })) : [])
  }, [st, reveal])

  const act = (fn: () => Promise<unknown>) => fn().then(load, (e) => setError(String(e)))
  const maxQty = st ? Math.max(1, ...st.depth.bids.map((l) => l.qty), ...st.depth.asks.map((l) => l.qty)) : 1
  const agents = st?.leaderboard.filter((r) => r.kind === 'participant' && r.name !== ME) ?? []
  const me = st?.leaderboard.find((r) => r.name === ME)

  return (
    <main className="grid grid--sim">
      <section className="sim-head">
        <span className="panel__code">ARENA</span>
        <strong>Agent arena</strong>
        <span className="muted">shared simulated market · step {st?.step ?? '—'} · mid {f2(st?.mid)} · {agents.length} AI agent{agents.length === 1 ? '' : 's'} trading</span>
        <button className="chip" onClick={() => setRunning((r) => !r)}>{running ? 'Pause clock' : 'Run clock'}</button>
        {[2, 5, 10, 20].map((s) => <button key={s} className={`chip ${s === speed ? 'chip--on' : ''}`} onClick={() => setSpeed(s)}>{s}/s</button>)}
        <button className="chip" onClick={() => act(() => post('/sim/scenario', { scenario: 'news-up' }))}>Good news</button>
        <button className="chip" onClick={() => act(() => post('/sim/scenario', { scenario: 'news-down' }))}>Bad news</button>
        <button className="chip" onClick={() => act(() => post('/sim/scenario', { scenario: 'crash' }))}>Flash crash</button>
        <button className="chip" onClick={() => act(() => post('/sim/scenario', { scenario: 'drain' }))}>Liquidity drain</button>
        <button className={`chip ${reveal ? 'chip--on' : ''}`} onClick={() => setReveal((r) => !r)}>Reveal true value</button>
        <button className="chip" onClick={() => act(() => post('/sim/reset', { seed: Math.floor(Math.random() * 1e6) }))}>Reset market</button>
      </section>

      <Panel code="DEPTH" title="Order book" className="grid__depth">
        {st && (
          <table className="depth">
            <tbody>
              {[...st.depth.asks].reverse().map((l) => (
                <tr key={`a${l.price}`} className="depth__ask"><td className="depth__bar"><span style={{ width: `${(l.qty / maxQty) * 100}%` }} /></td><td className="bad">{f2(l.price)}</td><td>{l.qty}</td></tr>
              ))}
              <tr className="depth__mid"><td /><td colSpan={2} className="muted">spread {st.best_ask != null && st.best_bid != null ? f2(st.best_ask - st.best_bid) : '—'}</td></tr>
              {st.depth.bids.map((l) => (
                <tr key={`b${l.price}`} className="depth__bid"><td className="depth__bar"><span style={{ width: `${(l.qty / maxQty) * 100}%` }} /></td><td className="ok">{f2(l.price)}</td><td>{l.qty}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel code="GP" title={reveal ? 'Mid price vs true value (dashed)' : 'Mid price'} className="grid__simchart">
        <div className="chart-wrap"><div ref={chartEl} className="chart" /></div>
      </Panel>

      <Panel code="YOU" title="Trade in the arena" className="grid__you">
        <div className="stack">
          {error && <p className="bad small">{error}</p>}
          <div className="ticket">
            <span className="muted">size</span>
            {[50, 100, 250, 500].map((q) => <button key={q} className={`chip ${q === qty ? 'chip--on' : ''}`} onClick={() => setQty(q)}>{q}</button>)}
          </div>
          <div className="ticket">
            <button className="btn btn--buy" onClick={() => act(() => post('/sim/order', { name: ME, side: 'buy', qty }))}>Buy {qty}</button>
            <button className="btn btn--sell" onClick={() => act(() => post('/sim/order', { name: ME, side: 'sell', qty }))}>Sell {qty}</button>
          </div>
          <div className="ticket">
            <button className="chip" onClick={() => act(() => post('/sim/cancel', { name: ME }))}>Cancel my orders</button>
            <button className="chip" onClick={() => {
              const pos = me?.position ?? 0
              if (pos) act(() => post('/sim/order', { name: ME, side: pos > 0 ? 'sell' : 'buy', qty: Math.abs(pos) }))
            }}>Flatten</button>
          </div>
          <div className="kv">
            <span>Position</span><span>{me?.position ?? 0}</span>
            <span>P&amp;L</span><span className={(me?.pnl ?? 0) >= 0 ? 'ok' : 'bad'}>{f2(me?.pnl ?? 0)}</span>
          </div>
          <p className="muted small">
            AI assistants connected through MCP (type MCP for setup) trade here with the finhub_arena_* tools, under their own names.
            Ask one, for example: “Use FinHub’s arena: watch the book, then try to beat the market maker over 200 steps.”
          </p>
        </div>
      </Panel>

      <Panel code="LB" title="Leaderboard (marked to mid)" className="grid__board">
        <table className="table">
          <tbody>
            {st?.leaderboard.map((r) => (
              <tr key={r.name} className={r.kind === 'participant' ? 'board__you' : ''}>
                <td title={r.about ?? 'participant'}>{r.kind === 'participant' ? (r.name === ME ? 'You' : `🤖 ${r.name}`) : r.name}</td>
                <td className={r.pnl >= 0 ? 'ok' : 'bad'}>{f2(r.pnl)}</td>
                <td className="muted">{r.position > 0 ? '+' : ''}{r.position}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel code="TAPE" title="Trades" className="grid__tape">
        <ol className="tape">
          {st?.recent_trades.slice(0, 14).map((t, i) => (
            <li key={i} className={[t.buyer, t.seller].some((n) => !['maker', 'noise', 'momentum', 'meanrev', 'informed'].includes(n)) ? 'tape__you' : ''}>
              <span className={t.aggressor === 'buy' ? 'ok' : 'bad'}>{f2(t.price)}</span><span>{t.qty}</span><span className="muted">{t.buyer} ← {t.seller}</span>
            </li>
          ))}
        </ol>
        {!!st?.events.length && (
          <div className="sim-events">{[...st.events].reverse().slice(0, 3).map((e, i) => <p key={i} className="warn small">step {e.step}: {e.text}</p>)}</div>
        )}
      </Panel>
    </main>
  )
}
