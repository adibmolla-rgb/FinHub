import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { Panel } from '../components'
import {
  binomial, blackScholes, bounds, breakevens, greeks, impliedVol, legValue, monteCarlo,
  payoffAtExpiry, STRATEGIES, strategyCost, strategyGreeks, validate, type Leg, type OptionInput, type OptionType,
} from './options'
import { XYChart } from './XYChart'

const f = (n: number, d = 4) => (Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }) : '—')

function Num({ label, value, onChange, step = 1, suffix }: { label: string; value: number; onChange: (v: number) => void; step?: number; suffix?: string }) {
  return (
    <label className="numfield">
      <span>{label}</span>
      <input type="number" value={Number.isFinite(value) ? value : ''} step={step} onChange={(e) => onChange(parseFloat(e.target.value))} />
      {suffix && <em>{suffix}</em>}
    </label>
  )
}

export function OptionsWorkspace({ symbol }: { symbol?: string }) {
  // Inputs in the units people type (percent, days); converted to fractions/years once, below.
  const [type, setType] = useState<OptionType>('call')
  const [spot, setSpot] = useState(100)
  const [strike, setStrike] = useState(100)
  const [days, setDays] = useState(90)
  const [volPct, setVolPct] = useState(25)
  const [ratePct, setRatePct] = useState(4)
  const [divPct, setDivPct] = useState(0)
  const [american, setAmerican] = useState(false)
  const [marketPrice, setMarketPrice] = useState<number>(NaN)
  const [spotNote, setSpotNote] = useState<string | null>(null)
  const [preset, setPreset] = useState('bull_call')
  const [legs, setLegs] = useState<Leg[]>(() => STRATEGIES.bull_call.legs(100))

  // OPT AAPL: start from the live price when the data engine can provide it.
  useEffect(() => {
    if (!symbol) return
    let live = true
    setSpotNote(`Loading ${symbol} price…`)
    api.quote(symbol).then(
      (q) => {
        const p = q.values.price
        if (!live || !p) return
        setSpot(Number(p.value.toFixed(2)))
        setStrike(Number(p.value.toFixed(0)))
        setLegs(STRATEGIES[preset].legs(p.value))
        setSpotNote(`Spot from ${symbol} via ${q.provider_name}`)
      },
      (e) => live && setSpotNote(`Couldn’t load ${symbol} (${e.message}); using the spot you enter.`),
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  const o: OptionInput = { type, S: spot, K: strike, T: days / 365, r: ratePct / 100, q: divPct / 100, sigma: volPct / 100 }
  const err = validate(o)

  const prices = useMemo(() => {
    if (err) return null
    const bs = blackScholes(o)
    const tree = binomial(o, 500, false)
    const treeAm = binomial(o, 500, true)
    const mc = monteCarlo(o, 100_000)
    return { bs, tree, treeAm, mc, g: greeks(o), b: bounds(o) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, spot, strike, days, volPct, ratePct, divPct, err])

  const iv = Number.isFinite(marketPrice) && !err ? impliedVol(marketPrice, o) : undefined
  const agree = prices ? Math.abs(prices.tree - prices.bs) < 0.01 && Math.abs(prices.mc.price - prices.bs) < 4 * prices.mc.stderr + 1e-9 : false

  const market = { S: spot, T: days / 365, r: ratePct / 100, q: divPct / 100, sigma: volPct / 100 }
  const strat = useMemo(() => {
    if (err || !legs.length) return null
    const cost = strategyCost(legs, market)
    const lo = spot * 0.5
    const hi = spot * 1.5
    const pts: [number, number][] = []
    const today: [number, number][] = []
    const halfway = { ...market, T: market.T / 2 }
    for (let i = 0; i <= 200; i++) {
      const x = lo + ((hi - lo) * i) / 200
      pts.push([x, payoffAtExpiry(legs, cost, x)])
      today.push([x, strategyCost(legs, { ...halfway, S: x }) - cost])
    }
    const ys = pts.map((p) => p[1])
    const slopeHi = pts[200][1] - pts[199][1]
    const slopeLo = pts[1][1] - pts[0][1]
    const maxProfit = slopeHi > 1e-9 || slopeLo < -1e-9 ? 'unlimited' : f(Math.max(...ys), 2)
    const maxLoss = slopeHi < -1e-9 || slopeLo > 1e-9 ? 'unlimited' : f(Math.min(...ys), 2)
    return { cost, pts, today, maxProfit, maxLoss, be: breakevens(legs, cost, lo, hi), g: strategyGreeks(legs, market) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [legs, spot, days, volPct, ratePct, divPct, err])

  const setLeg = (i: number, patch: Partial<Leg>) => setLegs((ls) => ls.map((l, j) => (i === j ? { ...l, ...patch } : l)))

  return (
    <main className="grid grid--opt">
      <Panel code="OPT" title="Option inputs" className="grid__optin">
        <div className="stack">
          <div className="ticket">
            {(['call', 'put'] as const).map((t) => (
              <button key={t} className={`chip ${type === t ? 'chip--on' : ''}`} onClick={() => setType(t)}>{t}</button>
            ))}
          </div>
          <div className="numgrid">
            <Num label="Spot" value={spot} onChange={setSpot} step={0.5} />
            <Num label="Strike" value={strike} onChange={setStrike} step={0.5} />
            <Num label="Days to expiry" value={days} onChange={setDays} />
            <Num label="Volatility" value={volPct} onChange={setVolPct} step={0.5} suffix="%" />
            <Num label="Risk-free rate" value={ratePct} onChange={setRatePct} step={0.1} suffix="%" />
            <Num label="Dividend yield" value={divPct} onChange={setDivPct} step={0.1} suffix="%" />
          </div>
          {spotNote && <p className="muted small">{spotNote}</p>}
          {err && <p className="bad">{err}</p>}
          <p className="muted small">Percent inputs are converted to fractions once (25% → 0.25) before any formula sees them; days → years as days ÷ 365.</p>
        </div>
      </Panel>

      <Panel code="PX" title="Price — three independent methods" className="grid__optpx">
        {prices && (
          <div className="stack">
            <table className="table">
              <tbody>
                <tr><td>Black–Scholes (closed form)</td><td className="num">{f(prices.bs)}</td></tr>
                <tr><td>Binomial tree, 500 steps</td><td className="num">{f(prices.tree)}</td></tr>
                <tr><td>Monte Carlo, 100k paths</td><td className="num">{f(prices.mc.price)} <span className="muted">± {f(prices.mc.stderr)}</span></td></tr>
                <tr>
                  <td>
                    <label className="inline">
                      <input type="checkbox" checked={american} onChange={(e) => setAmerican(e.target.checked)} /> American (early exercise)
                    </label>
                  </td>
                  <td className="num">{american ? f(prices.treeAm) : <span className="muted">tick to price</span>}</td>
                </tr>
                <tr><td className="muted">No-arbitrage bounds</td><td className="num muted">{f(prices.b.lower)} – {f(prices.b.upper)}</td></tr>
              </tbody>
            </table>
            <p className={agree ? 'ok small' : 'warn small'}>
              {agree ? '✓ The three methods agree (tree within 0.01, Monte Carlo within 4 standard errors).' : '⚠ The methods disagree more than expected; check the inputs.'}
            </p>
            {american && prices.treeAm - prices.tree > 1e-4 && (
              <p className="muted small">Early-exercise premium: {f(prices.treeAm - prices.tree)}</p>
            )}
          </div>
        )}
      </Panel>

      <Panel code="GRK" title="Greeks" className="grid__optgrk">
        {prices && (
          <table className="table">
            <tbody>
              <tr><td>Delta</td><td className="num">{f(prices.g.delta)}</td><td className="muted">price change per 1.00 move in spot</td></tr>
              <tr><td>Gamma</td><td className="num">{f(prices.g.gamma)}</td><td className="muted">delta change per 1.00 move in spot</td></tr>
              <tr><td>Vega</td><td className="num">{f(prices.g.vega)}</td><td className="muted">per 1 volatility point</td></tr>
              <tr><td>Theta</td><td className="num">{f(prices.g.theta)}</td><td className="muted">per calendar day</td></tr>
              <tr><td>Rho</td><td className="num">{f(prices.g.rho)}</td><td className="muted">per 1 rate point</td></tr>
            </tbody>
          </table>
        )}
        <div className="ivbox">
          <Num label="Market price" value={marketPrice} onChange={setMarketPrice} step={0.05} />
          <span>
            Implied vol:{' '}
            {iv === undefined ? <span className="muted">enter a price</span> : iv === null ? <span className="bad">outside no-arbitrage bounds</span> : <strong className="ok">{f(iv * 100, 2)}%</strong>}
          </span>
        </div>
      </Panel>

      <Panel code="STRAT" title="Strategy builder" className="grid__optstrat">
        <div className="stack">
          <div className="ticket">
            {Object.entries(STRATEGIES).map(([k, s]) => (
              <button key={k} className={`chip ${preset === k ? 'chip--on' : ''}`} onClick={() => { setPreset(k); setLegs(s.legs(spot)) }}>{s.label}</button>
            ))}
          </div>
          <div className="strat">
            <div className="stack">
            <table className="table">
              <thead><tr><th>Leg</th><th>Strike</th><th>Qty</th><th>Price now</th><th /></tr></thead>
              <tbody>
                {legs.map((l, i) => (
                  <tr key={i}>
                    <td>
                      <select value={l.kind} onChange={(e) => setLeg(i, { kind: e.target.value as Leg['kind'] })}>
                        <option value="call">call</option><option value="put">put</option><option value="stock">stock</option>
                      </select>
                    </td>
                    <td>{l.kind === 'stock' ? '—' : <input className="cell" type="number" step={0.5} value={l.strike} onChange={(e) => setLeg(i, { strike: parseFloat(e.target.value) })} />}</td>
                    <td><input className="cell" type="number" step={1} value={l.qty} onChange={(e) => setLeg(i, { qty: parseInt(e.target.value, 10) || 0 })} /></td>
                    <td className="num">{err ? '—' : f(legValue(l, market), 2)}</td>
                    <td><button className="chip" onClick={() => setLegs((ls) => ls.filter((_, j) => j !== i))}>✕</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button className="chip strat__add" onClick={() => setLegs((ls) => [...ls, { kind: 'call', strike: Math.round(spot), qty: 1 }])}>+ Add leg</button>
            {strat && (
              <div className="kv">
                <span>{strat.cost >= 0 ? 'Cost' : 'Credit'}</span><span>{f(Math.abs(strat.cost), 2)}</span>
                <span>Max profit</span><span className="ok">{strat.maxProfit}</span>
                <span>Max loss</span><span className="bad">{strat.maxLoss}</span>
                <span>Break-even</span><span>{strat.be.length ? strat.be.map((b) => f(b, 2)).join(', ') : 'none in range'}</span>
                <span>Delta / Vega</span><span>{f(strat.g.delta, 3)} / {f(strat.g.vega, 3)}</span>
                <span>Theta / day</span><span>{f(strat.g.theta, 3)}</span>
              </div>
            )}
            </div>
          {strat && (
            <XYChart
              series={[
                { label: 'Profit at expiry', color: '#3ddc97', points: strat.pts, fill: true },
                { label: 'Profit halfway to expiry (Black–Scholes)', color: '#6cb6ff', points: strat.today, dashed: true },
              ]}
              markers={[{ x: spot, label: `spot ${f(spot, 2)}`, color: '#f0b429' }, ...strat.be.map((b) => ({ x: b, label: `BE ${f(b, 2)}` }))]}
              xLabel={(x) => x.toFixed(0)}
              yLabel={(y) => y.toFixed(1)}
            />
          )}
          </div>
          <p className="muted small">Per one unit of each leg (multiply by your contract size, often 100). Model values assume constant volatility; real option prices include a volatility smile.</p>
        </div>
      </Panel>
    </main>
  )
}
