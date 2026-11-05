import { useEffect, useRef, useState } from 'react'
import { ColorType, createChart, LineSeries, type ISeriesApi, type Time } from 'lightweight-charts'
import { Panel } from '../components'
import { BOT_INFO, Market, toPrice, YOU, type BotKind, type Scenario } from './market'

const SPEEDS = [5, 10, 25, 50] as const
const QTYS = [50, 100, 250, 500] as const

function fmt(n: number, d = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d })
}

function SimChart({ market, version, reveal }: { market: Market; version: number; reveal: boolean }) {
  const el = useRef<HTMLDivElement>(null)
  const mid = useRef<ISeriesApi<'Line'> | null>(null)
  const value = useRef<ISeriesApi<'Line'> | null>(null)
  const drawn = useRef(0)

  useEffect(() => {
    if (!el.current) return
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#7d8794', fontSize: 11 },
      grid: { vertLines: { color: '#1a212b' }, horzLines: { color: '#1a212b' } },
      rightPriceScale: { borderColor: '#232b37' },
      timeScale: { borderColor: '#232b37', tickMarkFormatter: (t: Time) => `${t}` },
      localization: { timeFormatter: (t: Time) => `step ${t}` },
    })
    mid.current = chart.addSeries(LineSeries, { color: '#3ddc97', lineWidth: 2, title: 'mid' })
    value.current = chart.addSeries(LineSeries, { color: '#f0b429', lineWidth: 1, lineStyle: 2, title: 'true value', visible: false })
    drawn.current = 0
    return () => chart.remove()
  }, [market])

  useEffect(() => {
    value.current?.applyOptions({ visible: reveal })
  }, [reveal])

  useEffect(() => {
    const h = market.history
    for (let i = drawn.current; i < h.length; i++) {
      const s = h[i]
      const t = s.step as Time
      if (s.mid != null) mid.current?.update({ time: t, value: s.mid })
      value.current?.update({ time: t, value: s.value })
    }
    drawn.current = h.length
  }, [market, version])

  return <div ref={el} className="chart" />
}

export function SimWorkspace() {
  const [seed, setSeed] = useState(() => Math.floor(Math.random() * 1e6))
  const market = useRef<Market>(new Market(seed))
  const [version, setVersion] = useState(0)
  const [running, setRunning] = useState(true)
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(10)
  const [qty, setQty] = useState<(typeof QTYS)[number]>(100)
  const [reveal, setReveal] = useState(false)

  useEffect(() => {
    market.current = new Market(seed)
    setVersion((v) => v + 1)
  }, [seed])

  useEffect(() => {
    if (!running) return
    const t = setInterval(() => {
      market.current.tick()
      setVersion((v) => v + 1)
    }, 1000 / speed)
    return () => clearInterval(t)
  }, [running, speed, seed])

  const m = market.current
  const act = (fn: () => void) => {
    fn()
    setVersion((v) => v + 1)
  }
  const flatten = () => {
    const pos = m.book.account(YOU).position
    m.book.cancelAll(YOU)
    if (pos > 0) m.you('sell', pos)
    if (pos < 0) m.you('buy', -pos)
  }
  const join = (side: 'buy' | 'sell') => {
    const px = side === 'buy' ? m.book.bestBid() : m.book.bestAsk()
    if (px != null) m.you(side, qty, toPrice(px))
  }

  // Keyboard trading when the command bar is not focused: B buy, S sell, F flatten, Space pause.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA' || e.metaKey || e.ctrlKey) return
      const k = e.key.toLowerCase()
      if (k === 'b') act(() => market.current.you('buy', qty))
      else if (k === 's') act(() => market.current.you('sell', qty))
      else if (k === 'f') act(flatten)
      else if (k === ' ') {
        e.preventDefault()
        setRunning((r) => !r)
      } else return
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qty])

  const depth = m.book.depth(10)
  const maxQty = Math.max(1, ...depth.bids.map((l) => l.qty), ...depth.asks.map((l) => l.qty))
  const you = m.yourBreakdown()
  const mine = m.book.ordersOf(YOU)
  const bots = (Object.keys(BOT_INFO) as BotKind[]).map((k) => ({ k, pnl: m.pnl(k), pos: m.book.account(k).position }))
  const board = [...bots.map((b) => ({ ...b, label: BOT_INFO[b.k].label })), { k: YOU, label: 'You', pnl: you.total, pos: you.position }].sort((a, b) => b.pnl - a.pnl)
  const tape = m.book.trades.slice(-14).reverse()
  const mid = m.book.mid()

  const scenario = (s: Scenario) => act(() => m.trigger(s))

  return (
    <main className="grid grid--sim">
      <section className="sim-head">
        <span className="panel__code">SIM</span>
        <strong>Market simulator</strong>
        <span className="muted">step {m.book.step} · mid {mid != null ? fmt(toPrice(mid)) : '—'}</span>
        <button className="chip" onClick={() => setRunning((r) => !r)}>{running ? 'Pause (Space)' : 'Run (Space)'}</button>
        <span className="muted">speed</span>
        {SPEEDS.map((s) => (
          <button key={s} className={`chip ${s === speed ? 'chip--on' : ''}`} onClick={() => setSpeed(s)}>{s}/s</button>
        ))}
        <span className="muted">events</span>
        <button className="chip" onClick={() => scenario('news-up')}>Good news</button>
        <button className="chip" onClick={() => scenario('news-down')}>Bad news</button>
        <button className="chip" onClick={() => scenario('crash')}>Flash crash</button>
        <button className="chip" onClick={() => scenario('drain')}>Liquidity drain</button>
        <button className={`chip ${reveal ? 'chip--on' : ''}`} onClick={() => setReveal((r) => !r)}>Reveal true value</button>
        <button className="chip" onClick={() => setSeed(Math.floor(Math.random() * 1e6))}>New session</button>
      </section>

      <Panel code="DEPTH" title="Order book" className="grid__depth">
        <table className="depth">
          <tbody>
            {[...depth.asks].reverse().map((l) => (
              <tr key={`a${l.price}`} className="depth__ask">
                <td className="depth__bar"><span style={{ width: `${(l.qty / maxQty) * 100}%` }} /></td>
                <td className="bad">{fmt(toPrice(l.price))}</td>
                <td>{l.qty}</td>
              </tr>
            ))}
            <tr className="depth__mid"><td /><td colSpan={2} className="muted">spread {m.book.bestAsk() != null && m.book.bestBid() != null ? fmt(toPrice(m.book.bestAsk()! - m.book.bestBid()!)) : '—'}</td></tr>
            {depth.bids.map((l) => (
              <tr key={`b${l.price}`} className="depth__bid">
                <td className="depth__bar"><span style={{ width: `${(l.qty / maxQty) * 100}%` }} /></td>
                <td className="ok">{fmt(toPrice(l.price))}</td>
                <td>{l.qty}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel code="GP" title={reveal ? 'Mid price vs true value (dashed)' : 'Mid price'} className="grid__simchart">
        <div className="chart-wrap"><SimChart market={m} version={version} reveal={reveal} /></div>
      </Panel>

      <Panel code="YOU" title="Your trading" className="grid__you">
        <div className="stack">
          <div className="ticket">
            <span className="muted">size</span>
            {QTYS.map((q) => (
              <button key={q} className={`chip ${q === qty ? 'chip--on' : ''}`} onClick={() => setQty(q)}>{q}</button>
            ))}
          </div>
          <div className="ticket">
            <button className="btn btn--buy" onClick={() => act(() => m.you('buy', qty))}>Buy {qty} at market (B)</button>
            <button className="btn btn--sell" onClick={() => act(() => m.you('sell', qty))}>Sell {qty} at market (S)</button>
          </div>
          <div className="ticket">
            <button className="chip" onClick={() => act(() => join('buy'))}>Join best bid</button>
            <button className="chip" onClick={() => act(() => join('sell'))}>Join best offer</button>
            <button className="chip" onClick={() => act(() => m.book.cancelAll(YOU))}>Cancel my orders ({mine.length})</button>
            <button className="chip" onClick={() => act(flatten)}>Flatten (F)</button>
          </div>
          <div className="kv">
            <span>Position</span><span>{you.position} shares</span>
            <span>P&amp;L</span><span className={you.total >= 0 ? 'ok' : 'bad'}>{fmt(you.total)}</span>
            <span>Spread</span><span className={you.spread >= 0 ? 'ok' : 'bad'}>{fmt(you.spread)} <span className="muted">earned by trading better than mid</span></span>
            <span>After trade</span><span className={you.afterTrade >= 0 ? 'ok' : 'bad'}>{fmt(you.afterTrade)} <span className="muted">price moves after you traded (negative = adverse selection)</span></span>
            <span>Fills</span><span>{you.fills}</span>
          </div>
        </div>
      </Panel>

      <Panel code="LB" title="Leaderboard (marked to mid)" className="grid__board">
        <table className="table">
          <tbody>
            {board.map((r) => (
              <tr key={r.k} className={r.k === YOU ? 'board__you' : ''}>
                <td title={r.k === YOU ? '' : BOT_INFO[r.k as BotKind].about}>{r.label}</td>
                <td className={r.pnl >= 0 ? 'ok' : 'bad'}>{fmt(r.pnl)}</td>
                <td className="muted">{r.pos > 0 ? '+' : ''}{r.pos}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Hover a name for its strategy. The informed trader sees the true value; the market maker profits from noise but pays the informed trader.</p>
      </Panel>

      <Panel code="TAPE" title="Trades" className="grid__tape">
        <ol className="tape">
          {tape.map((t) => (
            <li key={t.id} className={t.buyer === YOU || t.seller === YOU ? 'tape__you' : ''}>
              <span className={t.aggressor === 'buy' ? 'ok' : 'bad'}>{fmt(toPrice(t.price))}</span>
              <span>{t.qty}</span>
              <span className="muted">{t.buyer} ← {t.seller}</span>
            </li>
          ))}
        </ol>
        {m.events.length > 0 && (
          <div className="sim-events">
            {m.events.slice(-3).reverse().map((e, i) => <p key={i} className="warn small">step {e.step}: {e.text}</p>)}
          </div>
        )}
      </Panel>
    </main>
  )
}
