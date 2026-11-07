// PAPER: practice trading with real prices and fake money. It can't reach a broker. Orders fill at the close of the
// first session still ahead when they were placed, so nothing can fill at a price that was already known.

import { useCallback, useEffect, useState } from 'react'
import { labApi, paperApi, timeAgo, type PaperAccount, type PaperAccountSummary, type PaperSide, type Receipt } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { SeriesReport } from './Lab'
import { DataError, Val } from './Ticker'
import { XYChart } from './quant/XYChart'

export type PaperPreset = { side: PaperSide; symbol: string; quantity: number }

const money = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const tone = (v: number | null | undefined) => (v == null ? '' : v < 0 ? 'bad' : 'ok')

function OrderForm({ accountId, preset, nextFill, onPlaced }: { accountId: string; preset?: PaperPreset; nextFill: string; onPlaced: () => void }) {
  const [side, setSide] = useState<PaperSide>(preset?.side ?? 'buy')
  const [symbol, setSymbol] = useState(preset?.symbol ?? '')
  const [quantity, setQuantity] = useState(preset ? String(preset.quantity) : '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    paperApi.place(accountId, symbol, side, Number(quantity)).then(
      () => { setSymbol(''); setQuantity(''); onPlaced() },
      (err) => setError(err.message),
    ).finally(() => setBusy(false))
  }

  return (
    <form className="stack" onSubmit={submit}>
      <div className="ticket">
        {(['buy', 'sell'] as const).map((s) => <button type="button" key={s} className={`chip ${side === s ? 'chip--on' : ''}`} onClick={() => setSide(s)}>{s === 'buy' ? 'Buy' : 'Sell'}</button>)}
        <input className="research-input port-input" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="US ticker" aria-label="Ticker" spellCheck={false} required />
        <input className="research-input port-input" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="Whole shares" aria-label="Shares" inputMode="numeric" required />
        <button className="chip chip--on" type="submit" disabled={busy}>{busy ? 'Placing…' : 'Place order'}</button>
      </div>
      {error && <p className="bad small">{error}</p>}
      <p className="muted small">An order placed now fills at the closing price on {nextFill}, the first close still ahead. Market orders only. Commission follows a typical US broker: $0.0049 a share, $0.99 minimum.</p>
    </form>
  )
}

function AccountView({ accountId, preset, onReceipt, onOpen, onChanged }: { accountId: string; preset?: PaperPreset; onReceipt: (r: Receipt) => void; onOpen: (c: string) => void; onChanged: () => void }) {
  const [data, setData] = useState<PaperAccount | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [saved, setSaved] = useState(0)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    paperApi.account(accountId).then(
      (d) => { if (live) { setData(d); setError(null) } },
      (e) => { if (live) setError(e) },
    )
    return () => { live = false }
  }, [accountId, saved])

  const reload = useCallback(() => { setSaved((n) => n + 1); onChanged() }, [onChanged])

  function cancel(id: string) {
    setActionError(null)
    paperApi.cancel(id).then(reload, (e) => setActionError(e.message))
  }

  if (error && !data) return <Panel code="ACCT" title="Paper account" className="research-wide"><DataError error={error} what="this paper account" /></Panel>
  if (!data) return <Panel code="ACCT" title="Paper account" className="research-wide"><p className="muted">Bringing the account up to date…</p></Panel>
  const points = data.nav.map(([day, value]): [number, number] => [Date.parse(`${day}T00:00:00Z`), value])
  return (
    <>
      <Panel code="ACCT" title={`${data.label} · paper money, ${data.currency}`} className="research-wide">
        <div className="stack">
          {data.note && <p className="warn small">{data.note}</p>}
          {error && <p className="warn small">Showing the last figures: {error.message}</p>}
          <div className="figs">
            <div className="fig"><span className="muted small">Account value</span><Val r={data.value} onReceipt={onReceipt} className="fig__val" /></div>
            <div className="fig"><span className="muted small">Cash</span><Val r={data.cash} onReceipt={onReceipt} className="fig__val" /></div>
            <div className="fig"><span className="muted small">Profit</span><Val r={data.profit} onReceipt={onReceipt} className={`fig__val ${tone(data.profit?.value)}`} /></div>
            <div className="fig"><span className="muted small">Return</span><Val r={data.return} onReceipt={onReceipt} className={`fig__val ${tone(data.return?.value)}`} /></div>
            <div className="fig"><span className="muted small">Fees paid</span><Val r={data.fees} onReceipt={onReceipt} className="fig__val" /></div>
          </div>
          {!data.value && <p className="muted small">No close has settled yet. The account starts counting from {data.start_on}.</p>}
          {points.length > 1 && (
            <div className="research-chart">
              <XYChart height={200} zeroLine={false} series={[{ label: 'Account value', color: '#6cb6ff', points }]} xLabel={(x) => new Date(x).toISOString().slice(0, 10)} xTicks={[points[0][0], points[points.length - 1][0]]} yLabel={(y) => y.toLocaleString(undefined, { maximumFractionDigits: 0 })} />
            </div>
          )}
          {data.nav.length >= 21 && <SeriesReport title="Performance report" onReceipt={onReceipt} load={() => labApi.series(data.label, data.nav.map(([d]) => d), data.nav.map(([, v]) => v))} />}
          <p className="muted small">The account value is as of the last settled close{data.last_date ? ` (${data.last_date})` : ''}. Current prices below can be newer. Dividends may not be included.</p>
        </div>
      </Panel>
      <Panel code="POS" title="Positions" className="research-wide">
        {data.positions.length === 0 ? <p className="muted">No positions yet.</p> : (
          <table className="table">
            <thead><tr><th>Ticker</th><th className="num">Shares</th><th className="num">Avg cost</th><th className="num">Price now</th><th className="num">Value</th><th className="num">Profit</th></tr></thead>
            <tbody>
              {data.positions.map((p) => (
                <tr key={p.symbol}>
                  <td><button className="link" onClick={() => onOpen(`EQ ${p.symbol}`)}>{p.symbol}</button></td>
                  <td className="num">{p.shares.toLocaleString()}</td>
                  <td className="num">{money(p.average_cost)}</td>
                  <td className="num"><Val r={p.price ?? undefined} onReceipt={onReceipt} /></td>
                  <td className="num">{money(p.value)}</td>
                  <td className={`num ${tone(p.profit)}`}>{money(p.profit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <Panel code="ORDER" title="Place an order" className="research-wide">
        <div className="stack">
          <OrderForm key={JSON.stringify(preset ?? null)} accountId={accountId} preset={preset} nextFill={data.next_fill_day} onPlaced={reload} />
          {actionError && <p className="bad small">{actionError}</p>}
          {data.orders.length > 0 && (
            <table className="table">
              <thead><tr><th>Waiting to fill</th><th>Ticker</th><th className="num">Shares</th><th>Fills at the close on</th><th /></tr></thead>
              <tbody>
                {data.orders.map((o) => (
                  <tr key={o.id}>
                    <td>{o.side === 'buy' ? 'Buy' : 'Sell'}</td>
                    <td>{o.symbol}</td>
                    <td className="num">{o.quantity.toLocaleString()}</td>
                    <td>{o.fill_day}</td>
                    <td className="num"><button className="chip" onClick={() => cancel(o.id)}>Cancel</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </Panel>
      <Panel code="FILLS" title="Trades" className="research-wide">
        <div className="stack">
          {data.rejected.map((r, i) => <p key={`${r.date}-${r.symbol}-${i}`} className="warn small">{r.date}: {r.side} {r.shares} {r.symbol} was refused: {r.reason}</p>)}
          {data.fills.length === 0 ? <p className="muted">No trades have filled yet.</p> : (
            <>
              <div className="ticket"><CopyCsvButton rows={() => [['date', 'side', 'symbol', 'shares', 'price', 'fee'], ...data.fills.map((f) => [f.date, f.side, f.symbol, f.shares, f.price, f.fee])]} /></div>
              <table className="table">
                <thead><tr><th>Date</th><th>Trade</th><th>Ticker</th><th className="num">Shares</th><th className="num">Price</th><th className="num">Fee</th></tr></thead>
                <tbody>
                  {data.fills.map((f, i) => (
                    <tr key={`${f.date}-${f.symbol}-${i}`}>
                      <td className="cell-date">{f.date}</td>
                      <td>{f.side === 'buy' ? 'Buy' : 'Sell'}</td>
                      <td>{f.symbol}</td>
                      <td className="num">{f.shares.toLocaleString()}</td>
                      <td className="num">{money(f.price)}</td>
                      <td className="num">{money(f.fee)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Panel>
    </>
  )
}

export function PaperWorkspace({ preset, onReceipt, onOpen }: { preset?: PaperPreset; onReceipt: (r: Receipt) => void; onOpen: (c: string) => void }) {
  const [accounts, setAccounts] = useState<PaperAccountSummary[] | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [chosen, setChosen] = useState<string | null>(null)
  const [label, setLabel] = useState('')
  const [cash, setCash] = useState('100000')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  const refresh = useCallback(() => {
    paperApi.accounts().then(
      (list) => { setAccounts(list); setError(null); setChosen((c) => c ?? list[list.length - 1]?.id ?? null) },
      (e) => setError(e),
    )
  }, [])
  useEffect(refresh, [refresh])

  function create(e: React.FormEvent) {
    e.preventDefault()
    if (creating) return
    setCreating(true)
    setCreateError(null)
    paperApi.create(label || 'Practice', Number(cash)).then(
      (a) => { setChosen(a.id); setLabel(''); refresh() },
      (err) => setCreateError(err.message),
    ).finally(() => setCreating(false))
  }

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="PAPER" title="Paper trading" className="research-wide">
        <div className="stack">
          <p className="muted small">Real prices, fake money, no broker. Use this to practise and to test your own judgement. <code>SIM</code> is a made-up market, and <code>PORT</code> records trades you made elsewhere.</p>
          {!accounts && !error && <p className="muted">Starting the paper ledger… (this can take up to a minute the first time)</p>}
          {error && <p className="bad">{error.message}</p>}
          {error && /not installed/i.test(error.message) && <div className="ticket"><button className="chip" onClick={() => onOpen('SYS')}>Open SYS to install it</button></div>}
          {accounts && accounts.length > 0 && (
            <div className="ticket">
              <select className="research-select" value={chosen ?? ''} onChange={(e) => setChosen(e.target.value)} aria-label="Paper account">
                {accounts.map((a) => <option key={a.id} value={a.id}>{a.label} · started {timeAgo(a.created_at)}{a.pending ? ` · ${a.pending} waiting` : ''}</option>)}
              </select>
            </div>
          )}
          {accounts && (
            <form className="ticket" onSubmit={create}>
              <input className="research-input port-input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="New account name" aria-label="Account name" maxLength={80} />
              <input className="research-input port-input" value={cash} onChange={(e) => setCash(e.target.value)} placeholder="Starting cash (USD)" aria-label="Starting cash" inputMode="decimal" />
              <button className="chip" type="submit" disabled={creating}>{creating ? 'Creating…' : 'New account'}</button>
              {createError && <span className="bad small">{createError}</span>}
            </form>
          )}
        </div>
      </Panel>
      {chosen && <AccountView key={chosen} accountId={chosen} preset={preset} onReceipt={onReceipt} onOpen={onOpen} onChanged={refresh} />}
    </main>
  )
}
