// PORT: your own buys and sells, valued at live prices. FinHub only records what you enter here;
// it has no broker connection and can't place orders.

import { useCallback, useEffect, useState } from 'react'
import { portfolioApi, type Portfolio, type PortfolioSide, type PortfolioTotal, type Receipt } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { DataError, Val } from './Ticker'

const tone = (r: Receipt | undefined) => (!r ? '' : r.value >= 0 ? 'ok' : 'bad')
// Today on this computer's calendar. toISOString alone is UTC, which is a different day for part of the day.
const today = () => {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

function Totals({ total, onReceipt }: { total: PortfolioTotal; onReceipt: (r: Receipt) => void }) {
  return (
    <div className="stack">
      <div className="figs">
        <div className="fig"><span className="muted small">Market value</span><Val r={total.value} onReceipt={onReceipt} className="fig__val" /></div>
        <div className="fig"><span className="muted small">Cost basis</span><Val r={total.cost_basis} onReceipt={onReceipt} className="fig__val" /></div>
        <div className="fig"><span className="muted small">Unrealised profit</span><Val r={total.unrealized} onReceipt={onReceipt} className={`fig__val ${tone(total.unrealized)}`} /></div>
        <div className="fig"><span className="muted small">Unrealised return</span><Val r={total.unrealized_pct} onReceipt={onReceipt} className={`fig__val ${tone(total.unrealized_pct)}`} /></div>
        <div className="fig"><span className="muted small">Change today</span><Val r={total.day_change} onReceipt={onReceipt} className={`fig__val ${tone(total.day_change)}`} /></div>
        <div className="fig"><span className="muted small">Realised profit</span><Val r={total.realized} onReceipt={onReceipt} className={`fig__val ${tone(total.realized)}`} /></div>
      </div>
      {!total.complete && <p className="warn small">No totals: {total.missing.join(', ')} has no live price, and leaving it out would understate them.</p>}
    </div>
  )
}

function EntryForm({ onSaved }: { onSaved: () => void }) {
  const [side, setSide] = useState<PortfolioSide>('buy')
  const [symbol, setSymbol] = useState('')
  const [quantity, setQuantity] = useState('')
  const [price, setPrice] = useState('')
  const [fees, setFees] = useState('')
  const [day, setDay] = useState(today)
  const [error, setError] = useState<string | null>(null)
  const split = side === 'split'

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    portfolioApi.add({ symbol, side, quantity: Number(quantity), price: split ? undefined : Number(price), fees: fees ? Number(fees) : 0, date: day }).then(
      () => { setSymbol(''); setQuantity(''); setPrice(''); setFees(''); onSaved() },
      (err) => setError(err.message),
    )
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="ticket">
        {(['buy', 'sell', 'split'] as const).map((s) => <button type="button" key={s} className={`chip ${side === s ? 'chip--on' : ''}`} onClick={() => setSide(s)}>{s[0].toUpperCase() + s.slice(1)}</button>)}
        <input className="research-input port-input" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="Ticker" aria-label="Ticker" spellCheck={false} required />
        <input className="research-input port-input" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder={split ? 'New shares per old' : 'Shares'} aria-label={split ? 'New shares for each old share' : 'Shares'} inputMode="decimal" required />
        {!split && <input className="research-input port-input" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="Price per share" aria-label="Price per share" inputMode="decimal" required />}
        {!split && <input className="research-input port-input" value={fees} onChange={(e) => setFees(e.target.value)} placeholder="Fees (optional)" aria-label="Fees" inputMode="decimal" />}
        <input className="research-select" type="date" value={day} max={today()} onChange={(e) => setDay(e.target.value)} aria-label="Trade date" required />
        <button className="chip chip--on" type="submit">Add</button>
      </div>
      {error && <p className="bad small">{error}</p>}
    </form>
  )
}

function DeleteButton({ onDelete }: { onDelete: () => void }) {
  const [asking, setAsking] = useState(false)
  if (!asking) return <button className="chip" onClick={() => setAsking(true)}>Delete</button>
  return (
    <span className="ticket">
      <button className="chip" onClick={onDelete}>Confirm</button>
      <button className="chip" onClick={() => setAsking(false)}>Keep</button>
    </span>
  )
}

export function PortfolioWorkspace({ version, onReceipt, onOpen }: { version: number; onReceipt: (r: Receipt) => void; onOpen: (command: string) => void }) {
  const [data, setData] = useState<Portfolio | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [saved, setSaved] = useState(0)

  const reload = useCallback(() => { setActionError(null); setSaved((n) => n + 1) }, [])
  useEffect(() => {
    let live = true
    portfolioApi.get().then(
      (d) => { if (live) { setData(d); setError(null) } },
      (e) => { if (live) setError(e) },
    )
    return () => { live = false }
  }, [version, saved])

  function remove(id: string) {
    setActionError(null)
    portfolioApi.remove(id).then(reload, (e) => setActionError(e.message))
  }

  const empty = data && data.transactions.length === 0
  return (
    <main className="grid grid--research">
      <Panel code="PORT" title="Portfolio" className="research-wide">
        <div className="stack">
          {error && <DataError error={error} what="your portfolio" />}
          {!data && !error && <p className="muted">Loading your portfolio…</p>}
          {empty && <p className="muted">Nothing here yet. Add a trade below, or type <code>PORT BUY AAPL 10 150</code>. This is your own record: FinHub can’t place real orders.</p>}
          {data?.totals.map((t) => (
            <div key={t.currency ?? 'unknown'} className="stack">
              {data.totals.length > 1 && <span className="muted small">{t.currency ?? 'Currency not stated'}</span>}
              <Totals total={t} onReceipt={onReceipt} />
            </div>
          ))}
          {data?.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
          {data && data.positions.length > 0 && (
            <>
              <div className="ticket">
                {data.risk_holdings && data.risk_holdings.length > 0 && (
                  <button className="chip" onClick={() => onOpen(`RISK ${data.risk_holdings!.map((h) => `${h.symbol} ${h.weight}`).join(' ')}`)}>Measure risk</button>
                )}
                <CopyCsvButton rows={() => [
                  ['symbol', 'currency', 'shares', 'average_cost', 'cost_basis', 'price', 'value', 'unrealized', 'unrealized_pct', 'day_change', 'weight'],
                  ...data.positions.map((p) => [p.symbol, p.currency, p.shares.value, p.average_cost.value, p.cost_basis.value, p.price?.value, p.value?.value, p.unrealized?.value, p.unrealized_pct?.value, p.day_change?.value, p.weight?.value]),
                ]} />
              </div>
              <table className="table">
                <thead><tr><th>Ticker</th><th className="num">Shares</th><th className="num">Avg cost</th><th className="num">Price</th><th className="num">Value</th><th className="num">Profit</th><th className="num">Return</th><th className="num">Today</th><th className="num">Weight</th></tr></thead>
                <tbody>
                  {data.positions.map((p) => (
                    <tr key={p.symbol}>
                      <td><button className="link" onClick={() => onOpen(`EQ ${p.symbol}`)}>{p.symbol}</button></td>
                      <td className="num"><Val r={p.shares} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={p.average_cost} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={p.price} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={p.value} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={p.unrealized} onReceipt={onReceipt} className={tone(p.unrealized)} /></td>
                      <td className="num"><Val r={p.unrealized_pct} onReceipt={onReceipt} className={tone(p.unrealized_pct)} /></td>
                      <td className="num"><Val r={p.day_change} onReceipt={onReceipt} className={tone(p.day_change)} /></td>
                      <td className="num"><Val r={p.weight} onReceipt={onReceipt} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {data && data.closed.length > 0 && (
            <p className="muted small">
              Closed: {data.closed.map((c, i) => (
                <span key={c.symbol}>{i > 0 && ' · '}{c.symbol} <Val r={c.realized ?? undefined} onReceipt={onReceipt} className={tone(c.realized ?? undefined)} /></span>
              ))}
            </p>
          )}
          {data && !empty && <p className="muted small">Cost basis is first-in, first-out, with fees included. Dividends aren’t recorded, so these are price returns. Enter splits yourself: FinHub doesn’t detect them. Enter prices in the currency the ticker is quoted in (London tickers are often in pence). Prices can be delayed.</p>}
        </div>
      </Panel>
      <Panel code="TRADE" title="Your trades" className="research-wide">
        <div className="stack">
          <EntryForm onSaved={reload} />
          {actionError && <p className="bad small">{actionError}</p>}
          {data && data.transactions.length > 0 && (
            <>
              <div className="ticket">
                <CopyCsvButton rows={() => [['date', 'side', 'symbol', 'quantity', 'price', 'fees'], ...data.transactions.map((t) => [t.date, t.side, t.symbol, t.quantity, t.side === 'split' ? '' : t.price, t.side === 'split' ? '' : t.fees])]} />
              </div>
              <table className="table">
                <thead><tr><th>Date</th><th>Trade</th><th>Ticker</th><th className="num">Shares</th><th className="num">Price</th><th className="num">Fees</th><th /></tr></thead>
                <tbody>
                  {data.transactions.map((t) => (
                    <tr key={t.id}>
                      <td className="cell-date">{t.date}</td>
                      <td>{t.side === 'split' ? `Split ${t.quantity}-for-1` : t.side === 'buy' ? 'Buy' : 'Sell'}</td>
                      <td>{t.symbol}</td>
                      <td className="num">{t.side === 'split' ? '—' : t.quantity.toLocaleString()}</td>
                      <td className="num">{t.side === 'split' ? '—' : t.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}</td>
                      <td className="num">{t.side === 'split' || !t.fees ? '—' : t.fees.toLocaleString(undefined, { minimumFractionDigits: 2 })}</td>
                      <td className="num"><DeleteButton onDelete={() => remove(t.id)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}
