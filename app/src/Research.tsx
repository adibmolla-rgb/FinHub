// Research panels: OWN, CHAIN, CAL, FILINGS, ETF, CURVE, FACTORS, COT and FED.
// Headline figures are clickable receipts. Table rows are the provider's own values, and each panel says
// which provider served them; figures FinHub derives from them are worked out by the backend.

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  compact, researchApi, timeAgo, watchApi,
  type CotMarket, type CotOverview, type EtfHoldings, type FedConditions, type Factors, type Filings, type InsiderRow, type MarketCalendar, type OptionContract, type OptionsChain,
  type Ownership, type Receipt, type SourceMeta, type YieldCurve,
} from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { Spark } from './Macro'
import { DataError, Val } from './Ticker'
import { XYChart } from './quant/XYChart'

type Common = { onReceipt: (r: Receipt) => void; onOpen: (command: string) => void }

export type ResearchView =
  | { view: 'own'; symbol: string }
  | { view: 'chain'; symbol: string; expiration?: string }
  | { view: 'cal'; days: number }
  | { view: 'filings'; symbol: string }
  | { view: 'etf'; symbol: string }
  | { view: 'curve' }
  | { view: 'factors'; region: string; years: number }
  | { view: 'cot'; market?: string }
  | { view: 'fed' }

/** Load once per `load` identity (memoise it with useCallback); a slower, older answer is ignored. */
function useLoad<T>(load: () => Promise<T>) {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({ data: null, error: null, loading: true })
  useEffect(() => {
    let live = true
    setState({ data: null, error: null, loading: true })
    load().then(
      (data) => { if (live) setState({ data, error: null, loading: false }) },
      (error) => { if (live) setState({ data: null, error, loading: false }) },
    )
    return () => { live = false }
  }, [load])
  return state
}

function Status({ what, error, loading }: { what: string; error: Error | null; loading: boolean }) {
  if (error) return <DataError error={error} what={what} />
  return loading ? <p className="muted">Loading {what}… (the first request after launch waits for the data engine to start)</p> : null
}

function Source({ meta, note }: { meta: SourceMeta; note?: string }) {
  const failed = meta.attempts.filter((a) => !a.ok).map((a) => a.provider)
  return (
    <p className="muted small">
      {meta.provider_name} · fetched {timeAgo(meta.fetched_at)}
      {failed.length > 0 && <span className="warn"> · fallback after {failed.join(', ')}</span>}
      {note && <> · {note}</>}
    </p>
  )
}

function Fig({ label, r, onReceipt, tone }: { label: string; r: Receipt | undefined; onReceipt: (r: Receipt) => void; tone?: string }) {
  return (
    <div className="fig">
      <span className="muted small">{label}</span>
      <Val r={r} onReceipt={onReceipt} className={`fig__val ${tone ?? ''}`} />
    </div>
  )
}

const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }))
const big = (v: number | null | undefined) => (v == null ? '—' : compact(v))
const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
const signedPct = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`)

// ---------------------------------------------------------------------------------------------
// OWN: insiders, institutions, short interest
// ---------------------------------------------------------------------------------------------

/** SEC transaction descriptions run to a whole sentence; the full text stays in the tooltip. */
function action(row: InsiderRow): string {
  const t = (row.type ?? '').toLowerCase()
  if (t.startsWith('open market or private')) return row.direction?.toLowerCase() === 'acquisition' ? 'Purchase' : 'Sale'
  if (t.startsWith('exercise')) return 'Option exercise'
  if (t.startsWith('grant')) return 'Grant or award'
  if (t.startsWith('payment of exercise')) return 'Tax or exercise payment'
  if (t.startsWith('bona fide gift')) return 'Gift'
  return row.type ?? '—'
}

export function OwnershipWorkspace({ symbol, onReceipt }: { symbol: string; onReceipt: Common['onReceipt'] }) {
  const { data, error, loading } = useLoad<Ownership>(useCallback(() => researchApi.ownership(symbol), [symbol]))
  const insider = data?.insider
  const holders = data?.institutional
  const short = data?.short
  const shortSeries = useMemo(
    () => ({ unit_kind: 'as_reported' as const, points: (short?.rows ?? []).map((r) => ({ date: r.date, value: r.short })) }),
    [short],
  )
  return (
    <main className="grid grid--research">
      {!data && (
        <Panel code="OWN" title={`${symbol} · ownership`} className="research-wide">
          <Status what="ownership data" error={error} loading={loading} />
        </Panel>
      )}
      {data && (
        <Panel code="OWN" title={`${symbol} · insider trades`} className="research-wide">
          {insider ? (
            <div className="stack">
              {insider.summary ? (
                <>
                  <div className="figs">
                    <Fig label={`Sold, last ${insider.summary.window_days} days`} r={insider.summary.sold_value} onReceipt={onReceipt} />
                    <Fig label="Shares sold" r={insider.summary.sold_shares} onReceipt={onReceipt} />
                    <Fig label="Of that, footnoted as a 10b5-1 plan" r={insider.summary.sold_on_plan} onReceipt={onReceipt} />
                    <Fig label={`Bought, last ${insider.summary.window_days} days`} r={insider.summary.bought_value} onReceipt={onReceipt} />
                  </div>
                  <p className="muted small">
                    Totals count open-market or private trades in common stock only ({insider.summary.trades} trades). Grants, option exercises, gifts and tax
                    withholding aren’t decisions to buy or sell, so they’re left out. Sales under a 10b5-1 plan were scheduled in advance; this only counts those a
                    footnote mentions, so the real share may be higher.
                  </p>
                </>
              ) : (
                <p className="warn small">No totals: this provider doesn’t say enough to separate real trades from grants and option exercises.</p>
              )}
              <table className="table">
                <thead><tr><th>Date</th><th>Insider</th><th>Action</th><th className="num">Shares</th><th className="num">Price</th><th className="num">Value</th><th className="num">Held after</th><th>Filing</th></tr></thead>
                <tbody>
                  {insider.rows.map((r, i) => (
                    <tr key={i}>
                      <td className="cell-date">{r.date}</td>
                      <td>{r.owner ?? '—'}{r.title && <div className="muted small">{r.title}</div>}</td>
                      <td title={r.type ?? undefined}>{action(r)}{r.plan_10b5_1 && <span className="muted small"> · 10b5-1</span>}</td>
                      <td className="num">{big(r.shares)}</td>
                      <td className="num">{r.price ? num(r.price) : '—'}</td>
                      <td className="num">{r.price ? big(r.shares * r.price) : '—'}</td>
                      <td className="num">{big(r.shares_after)}</td>
                      <td>{r.url ? <a href={r.url} target="_blank" rel="noreferrer">Open</a> : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Source meta={insider} />
            </div>
          ) : <p className="bad small">{data.errors.insider}</p>}
        </Panel>
      )}
      {data && (
        <Panel code="13F" title={`${symbol} · largest institutional holders`}>
          {holders ? (
            <div className="stack">
              <table className="table">
                <thead><tr><th>Holder</th><th>As of</th><th className="num">Shares</th><th className="num">Change</th></tr></thead>
                <tbody>
                  {holders.rows.map((r, i) => (
                    <tr key={i}>
                      <td>{r.owner}</td>
                      <td className="cell-date muted">{r.date ?? '—'}</td>
                      <td className="num">{big(r.shares)}</td>
                      <td className={`num ${(r.change ?? 0) >= 0 ? 'ok' : 'bad'}`} title={r.change != null ? `${big(r.change)} shares` : undefined}>{signedPct(r.change_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Source meta={holders} note="from 13F filings, which arrive up to 45 days after quarter end; holders can report different dates" />
            </div>
          ) : <p className="bad small">{data.errors.institutional}</p>}
        </Panel>
      )}
      {data && (
        <Panel code="SHORT" title={`${symbol} · short interest`} className="macro-card">
          {short ? (
            <div className="stack research-fill">
              <div className="figs">
                <Fig label={`Short shares (${short.summary.date})`} r={short.summary.short} onReceipt={onReceipt} />
                <Fig label="Since previous report" r={short.summary.change} onReceipt={onReceipt} />
                <Fig label="Days to cover" r={short.summary.days_to_cover} onReceipt={onReceipt} />
              </div>
              <Spark s={shortSeries} format={compact} />
              <Source meta={short} note="reported twice a month, so it lags" />
            </div>
          ) : <p className="bad small">{data.errors.short}</p>}
        </Panel>
      )}
    </main>
  )
}

// ---------------------------------------------------------------------------------------------
// CHAIN: live options chain and volatility smile
// ---------------------------------------------------------------------------------------------

function contractCells(c: OptionContract | null) {
  return [num(c?.bid), num(c?.ask), pct(c?.iv), big(c?.volume), big(c?.open_interest)]
}

export function ChainWorkspace({ symbol, expiration: initial, onReceipt }: { symbol: string; expiration?: string; onReceipt: Common['onReceipt'] }) {
  const [expiration, setExpiration] = useState(initial)
  const [allStrikes, setAllStrikes] = useState(false)
  const { data, error, loading } = useLoad<OptionsChain>(useCallback(() => researchApi.options(symbol, expiration), [symbol, expiration]))
  const spot = data?.summary.underlying?.value
  // Far-from-the-money strikes are thinly quoted and swamp both the table and the chart.
  const near = (strike: number) => spot == null || Math.abs(strike / spot - 1) <= 0.25
  const rows = data ? data.rows.filter((r) => allStrikes || near(r.strike)) : []
  const atmStrike = spot == null || !rows.length ? null : rows.reduce((best, r) => (Math.abs(r.strike - spot) < Math.abs(best - spot) ? r.strike : best), rows[0].strike)
  // The smile uses out-of-the-money options: deep in-the-money quotes give unreliable implied vols.
  const smile = data ? data.smile.filter((p) => near(p.strike)) : []
  const calls = smile.filter((p) => p.call_iv != null && (spot == null || p.strike >= spot)).map((p): [number, number] => [p.strike, p.call_iv!])
  const puts = smile.filter((p) => p.put_iv != null && (spot == null || p.strike <= spot)).map((p): [number, number] => [p.strike, p.put_iv!])
  return (
    <main className="grid grid--research">
      <Panel code="CHAIN" title={`${symbol} · options${data ? ` expiring ${data.expiration}` : ''}`} className="research-wide">
        <Status what={`${symbol} options`} error={error} loading={loading} />
        {data && (
          <div className="stack">
            <div className="ticket">
              <label className="muted small">Expiration{' '}
                <select className="research-select" value={data.expiration} onChange={(e) => setExpiration(e.target.value)}>
                  {data.expirations.map((x) => <option key={x} value={x}>{x}</option>)}
                </select>
              </label>
              <button className={`chip ${allStrikes ? 'chip--on' : ''}`} onClick={() => setAllStrikes((v) => !v)}>All strikes</button>
              <CopyCsvButton rows={() => [
                ['strike', 'call_bid', 'call_ask', 'call_iv', 'call_volume', 'call_oi', 'put_bid', 'put_ask', 'put_iv', 'put_volume', 'put_oi'],
                ...rows.map((r) => [r.strike, r.call?.bid, r.call?.ask, r.call?.iv, r.call?.volume, r.call?.open_interest, r.put?.bid, r.put?.ask, r.put?.iv, r.put?.volume, r.put?.open_interest]),
              ]} />
            </div>
            <div className="figs">
              <Fig label="Underlying" r={data.summary.underlying} onReceipt={onReceipt} />
              <Fig label="At-the-money implied vol" r={data.summary.atm_iv} onReceipt={onReceipt} />
              <Fig label="Put/call volume" r={data.summary.put_call_volume} onReceipt={onReceipt} />
              <Fig label="Put/call open interest" r={data.summary.put_call_oi} onReceipt={onReceipt} />
            </div>
            {data.smile.length === 0 && <p className="warn small">No implied volatility here: {data.provider_name} didn’t supply it in a declared unit for this chain, or nothing is quoted on both sides.</p>}
            {(calls.length > 1 || puts.length > 1) && (
              <div className="research-chart">
                <XYChart
                  height={190}
                  zeroLine={false}
                  series={[{ label: 'Out-of-the-money puts', color: '#f0a35e', points: puts }, { label: 'Out-of-the-money calls', color: '#6cb6ff', points: calls }]}
                  xLabel={(x) => x.toFixed(0)}
                  yLabel={(y) => `${(y * 100).toFixed(0)}%`}
                  markers={spot != null ? [{ x: spot, label: 'price' }] : []}
                />
              </div>
            )}
            <table className="table chain">
              <thead>
                <tr><th className="num">Bid</th><th className="num">Ask</th><th className="num">IV</th><th className="num">Vol</th><th className="num">OI</th><th className="chain__strike">Strike</th><th className="num">Bid</th><th className="num">Ask</th><th className="num">IV</th><th className="num">Vol</th><th className="num">OI</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.strike} className={r.strike === atmStrike ? 'chain__atm' : undefined}>
                    {contractCells(r.call).map((v, i) => <td key={i} className={`num ${spot != null && r.strike < spot ? 'chain__itm' : ''}`}>{v}</td>)}
                    <td className="chain__strike">{r.strike.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                    {contractCells(r.put).map((v, i) => <td key={i} className={`num ${spot != null && r.strike > spot ? 'chain__itm' : ''}`}>{v}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
            <Source meta={data} note="calls left, puts right, in-the-money shaded; quotes can be delayed; the chart shows out-of-the-money strikes within 25% of the price that have a two-sided quote" />
          </div>
        )}
      </Panel>
    </main>
  )
}

// ---------------------------------------------------------------------------------------------
// CAL: earnings and economic calendars
// ---------------------------------------------------------------------------------------------

const MAX_EARNINGS_ROWS = 300

export function CalendarWorkspace({ days: initial, onOpen }: { days: number; onOpen: Common['onOpen'] }) {
  const [days, setDays] = useState(initial)
  const [filter, setFilter] = useState('')
  const [country, setCountry] = useState('')
  const [watchOnly, setWatchOnly] = useState(false)
  const [watchlist, setWatchlist] = useState<string[] | null>(null)
  const { data, error, loading } = useLoad<MarketCalendar>(useCallback(() => researchApi.calendar(days), [days]))
  useEffect(() => {
    if (watchOnly && watchlist === null) watchApi.get().then(({ symbols }) => setWatchlist(symbols), () => setWatchlist([]))
  }, [watchOnly, watchlist])

  const earnings = data?.earnings
  const economic = data?.economic
  const needle = filter.trim().toUpperCase()
  const matching = (earnings?.rows ?? []).filter((r) =>
    (!watchOnly || (watchlist ?? []).includes(r.symbol)) && (!needle || r.symbol.includes(needle) || (r.name ?? '').toUpperCase().includes(needle)))
  // Keep the biggest companies when there are too many to show, then list them by date.
  const shown = [...matching].sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0)).slice(0, MAX_EARNINGS_ROWS)
    .sort((a, b) => a.date.localeCompare(b.date) || (b.market_cap ?? 0) - (a.market_cap ?? 0))
  const countries = [...new Set((economic?.rows ?? []).map((r) => r.country).filter((c): c is string => !!c))].sort()
  const events = (economic?.rows ?? []).filter((r) => !country || r.country === country)

  return (
    <main className="grid grid--research">
      <Panel code="CAL" title={`Earnings · next ${days} days`}>
        <Status what="the calendar" error={error} loading={loading} />
        {data && (
          <div className="stack">
            <div className="ticket">
              {[7, 14, 31].map((d) => <button key={d} className={`chip ${days === d ? 'chip--on' : ''}`} onClick={() => setDays(d)}>{d} days</button>)}
              <button className={`chip ${watchOnly ? 'chip--on' : ''}`} onClick={() => setWatchOnly((v) => !v)}>Watchlist</button>
              <input className="research-input" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by ticker or name" aria-label="Filter earnings" />
            </div>
            {earnings ? (
              <>
                <table className="table">
                  <thead><tr><th>Date</th><th>Ticker</th><th>Company</th><th className="num">EPS est.</th><th className="num">Last year</th><th className="num">Mkt cap</th></tr></thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={`${r.date}-${r.symbol}`}>
                        <td className="cell-date">{r.date}{r.time && <div className="muted small">{r.time}</div>}</td>
                        <td><button className="link" onClick={() => onOpen(`EQ ${r.symbol}`)}>{r.symbol}</button></td>
                        <td className="muted small" title={r.period ? `Period ending ${r.period}` : undefined}>{r.name ?? '—'}</td>
                        <td className="num">{num(r.eps_consensus)}</td>
                        <td className="num">{num(r.eps_previous)}</td>
                        <td className="num">{big(r.market_cap)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {!shown.length && <p className="muted small">Nothing matches in this window.</p>}
                <Source meta={earnings} note={`showing ${shown.length} of ${matching.length}${matching.length > shown.length ? ', largest first' : ''}; EPS is as reported by the provider`} />
              </>
            ) : <p className="bad small">{data.errors.earnings}</p>}
          </div>
        )}
      </Panel>
      <Panel code="ECON" title={`Economic events · next ${days} days`}>
        {data && (
          <div className="stack">
            <div className="ticket">
              <label className="muted small">Country{' '}
                <select className="research-select" value={country} onChange={(e) => setCountry(e.target.value)}>
                  <option value="">All</option>
                  {countries.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
            </div>
            {economic ? (
              <>
                <table className="table">
                  <thead><tr><th>When</th><th>Country</th><th>Event</th><th className="num">Actual</th><th className="num">Forecast</th><th className="num">Previous</th></tr></thead>
                  <tbody>
                    {events.map((r, i) => (
                      <tr key={i}>
                        <td className="cell-date">{r.date}</td>
                        <td className="muted small">{r.country ?? '—'}</td>
                        <td>{r.event}</td>
                        <td className="num">{r.actual ?? '—'}</td>
                        <td className="num">{r.consensus ?? '—'}</td>
                        <td className="num">{r.previous ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Source meta={economic} note="times as published; the provider doesn’t state a time zone" />
              </>
            ) : <p className="bad small">{data.errors.economic}</p>}
          </div>
        )}
      </Panel>
    </main>
  )
}

// ---------------------------------------------------------------------------------------------
// FILINGS: SEC filings
// ---------------------------------------------------------------------------------------------

const FORM_GROUPS: [string, (form: string) => boolean][] = [
  ['All', () => true],
  ['10-K', (f) => f.startsWith('10-K')],
  ['10-Q', (f) => f.startsWith('10-Q')],
  ['8-K', (f) => f.startsWith('8-K')],
  ['Insiders', (f) => /^(3|4|5|144)(\/A)?$/.test(f)],
]

export function FilingsWorkspace({ symbol, onOpen }: { symbol: string; onOpen: Common['onOpen'] }) {
  const [group, setGroup] = useState('All')
  const { data, error, loading } = useLoad<Filings>(useCallback(() => researchApi.filings(symbol), [symbol]))
  const test = FORM_GROUPS.find(([name]) => name === group)?.[1] ?? (() => true)
  const rows = (data?.rows ?? []).filter((r) => test(r.form))
  return (
    <main className="grid grid--research">
      <Panel code="FILINGS" title={`${symbol} · SEC filings`} className="research-wide">
        <Status what={`${symbol} filings`} error={error} loading={loading} />
        {data && (
          <div className="stack">
            <div className="ticket">
              {FORM_GROUPS.map(([name]) => <button key={name} className={`chip ${group === name ? 'chip--on' : ''}`} onClick={() => setGroup(name)}>{name}</button>)}
              <CopyCsvButton rows={() => [['date', 'form', 'description', 'accession', 'url'], ...rows.map((r) => [r.date, r.form, r.description, r.accession, r.url])]} />
            </div>
            <table className="table">
              <thead><tr><th>Filed</th><th>Form</th><th>Description</th><th>Accession number</th><th>Document</th><th /></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.accession ?? i}>
                    <td className="cell-date">{r.date}</td>
                    <td>{r.form}</td>
                    <td className="muted small">{r.description ?? '—'}{r.items && ` · items ${r.items}`}</td>
                    <td className="muted small">{r.accession ?? '—'}</td>
                    <td>{r.url ? <a href={r.url} target="_blank" rel="noreferrer">Open</a> : '—'}</td>
                    <td className="num">{r.accession && <button className="chip" onClick={() => onOpen(`READ ${symbol} ${r.form} ${r.accession}`)}>Read</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!rows.length && <p className="muted small">No {group} filings among the latest {data.rows.length}.</p>}
            <Source meta={data} note={`latest ${data.rows.length} filings; US-listed companies only`} />
          </div>
        )}
      </Panel>
    </main>
  )
}

// ---------------------------------------------------------------------------------------------
// ETF: holdings
// ---------------------------------------------------------------------------------------------

export function EtfWorkspace({ symbol, onReceipt, onOpen }: { symbol: string } & Common) {
  const { data, error, loading } = useLoad<EtfHoldings>(useCallback(() => researchApi.etf(symbol), [symbol]))
  return (
    <main className="grid grid--research">
      <Panel code="ETF" title={`${symbol} · holdings`} className="research-wide">
        <Status what={`${symbol} holdings`} error={error} loading={loading} />
        {data && (
          <div className="stack">
            <div className="figs">
              <Fig label={`Weight of the ${data.listed} holdings listed`} r={data.listed_weight} onReceipt={onReceipt} />
            </div>
            <p className="warn small">This is only part of the fund: the provider lists its largest {data.listed} holdings, not all of them.</p>
            <table className="table">
              <thead><tr><th>Ticker</th><th>Holding</th><th className="num">Weight</th></tr></thead>
              <tbody>
                {data.rows.map((r) => (
                  <tr key={r.symbol}>
                    <td><button className="link" onClick={() => onOpen(`EQ ${r.symbol}`)}>{r.symbol}</button></td>
                    <td className="muted small">{r.name ?? '—'}</td>
                    <td className="num"><Val r={r.weight} onReceipt={onReceipt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Source meta={data} />
          </div>
        )}
      </Panel>
    </main>
  )
}

// ---------------------------------------------------------------------------------------------
// CURVE: US Treasury yield curve
// ---------------------------------------------------------------------------------------------

export function CurveWorkspace({ onReceipt }: { onReceipt: Common['onReceipt'] }) {
  const { data, error, loading } = useLoad<YieldCurve>(useCallback(() => researchApi.curve(), []))
  const fraction = data?.unit_kind === 'fraction'
  const show = (v: number | null | undefined) => (v == null ? '—' : fraction ? pct(v, 2) : v.toLocaleString(undefined, { maximumFractionDigits: 4 }))
  // Maturities sit evenly along the axis: on a true time scale, everything under 2 years would overlap.
  const line = (key: 'month_ago' | 'year_ago') => (data?.tenors ?? []).flatMap((t, i): [number, number][] => (t[key] == null ? [] : [[i, t[key]!]]))
  const inverted = (r: Receipt | undefined) => (r && r.value < 0 ? 'bad' : '')
  return (
    <main className="grid grid--research">
      <Panel code="CURVE" title={`US Treasury yield curve${data ? ` · ${data.date}` : ''}`} className="research-wide">
        <Status what="the yield curve" error={error} loading={loading} />
        {data && (
          <div className="stack">
            <div className="figs">
              <Fig label="10-year minus 2-year" r={data.spreads['10y_2y']} onReceipt={onReceipt} tone={inverted(data.spreads['10y_2y'])} />
              <Fig label="10-year minus 3-month" r={data.spreads['10y_3m']} onReceipt={onReceipt} tone={inverted(data.spreads['10y_3m'])} />
            </div>
            <div className="research-chart">
              <XYChart
                height={240}
                zeroLine={false}
                series={[
                  { label: data.date, color: '#6cb6ff', points: data.tenors.map((t, i): [number, number] => [i, t.latest.value]) },
                  ...(data.month_ago_date ? [{ label: data.month_ago_date, color: '#7d8794', dashed: true, points: line('month_ago') }] : []),
                  ...(data.year_ago_date ? [{ label: data.year_ago_date, color: '#f0a35e', dashed: true, points: line('year_ago') }] : []),
                ]}
                xTicks={data.tenors.map((_, i) => i).filter((i) => i % 2 === 0)}
                xLabel={(x) => data.tenors[x]?.tenor ?? ''}
                yLabel={(y) => (fraction ? `${(y * 100).toFixed(1)}%` : y.toFixed(2))}
              />
            </div>
            <div className="ticket">
              <CopyCsvButton rows={() => [['tenor', data.date, data.month_ago_date ?? 'month_ago', data.year_ago_date ?? 'year_ago'], ...data.tenors.map((t) => [t.tenor, t.latest.value, t.month_ago, t.year_ago])]} />
            </div>
            <table className="table">
              <thead><tr><th>Maturity</th><th className="num">{data.date}</th><th className="num">{data.month_ago_date ?? 'A month ago'}</th><th className="num">{data.year_ago_date ?? 'A year ago'}</th></tr></thead>
              <tbody>
                {data.tenors.map((t) => (
                  <tr key={t.tenor}>
                    <td>{t.tenor}</td>
                    <td className="num"><Val r={t.latest} onReceipt={onReceipt} /></td>
                    <td className="num">{show(t.month_ago)}</td>
                    <td className="num">{show(t.year_ago)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Source meta={data} note={`unit: ${data.unit}. A negative spread means the curve is inverted`} />
          </div>
        )}
      </Panel>
    </main>
  )
}

// Dates on a chart's x-axis, as evenly spaced years.
const dayMs = (day: string) => Date.parse(`${day}T00:00:00Z`)
const yearLabel = (ms: number) => String(new Date(ms).getUTCFullYear())
function yearTicks(points: string[], count = 6): number[] {
  if (points.length < 2) return points.map(dayMs)
  const first = new Date(dayMs(points[0])).getUTCFullYear()
  const last = new Date(dayMs(points[points.length - 1])).getUTCFullYear()
  const step = Math.max(1, Math.ceil((last - first) / count))
  const out: number[] = []
  for (let y = first + 1; y <= last; y += step) out.push(Date.UTC(y, 0, 1))
  return out.length ? out : [dayMs(points[0])] // all within one year: an empty list would mean no labels at all
}

const FACTOR_COLORS: Record<string, string> = { mkt_rf: '#6cb6ff', smb: '#f0a35e', hml: '#7ee787', rmw: '#d2a8ff', cma: '#ff7b72', mom: '#e3b341' }

export function FactorsWorkspace({ region: initialRegion, years: initialYears, onReceipt }: { region: string; years: number; onReceipt: Common['onReceipt'] }) {
  const [region, setRegion] = useState(initialRegion)
  const [years, setYears] = useState(initialYears)
  const { data, error, loading } = useLoad<Factors>(useCallback(() => researchApi.factors(region, years), [region, years]))
  const signed = (r: Receipt | null | undefined) => (r && r.value < 0 ? 'bad' : '')
  return (
    <main className="grid grid--research">
      <Panel code="FACTORS" title={`Fama-French factors${data ? ` · ${data.region_label}` : ''}`} className="research-wide">
        <div className="stack">
          <div className="ticket">
            <select className="research-select" value={region} onChange={(e) => setRegion(e.target.value)} aria-label="Region">
              {Object.entries(data?.regions ?? { [region]: region }).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
            </select>
            {[5, 10, 30].map((y) => <button key={y} className={`chip ${years === y ? 'chip--on' : ''}`} onClick={() => setYears(y)}>{y}Y</button>)}
          </div>
          <Status what="factor returns" error={error} loading={loading} />
          {data && (
            <>
              <div className="research-chart">
                <XYChart
                  height={260}
                  zeroLine={false}
                  series={data.factors.map((f) => ({ label: f.label, color: FACTOR_COLORS[f.key] ?? '#7d8794', points: f.curve.map(([day, v]): [number, number] => [dayMs(day), v]) }))}
                  xTicks={yearTicks(data.factors[0].curve.map(([day]) => day))}
                  xLabel={yearLabel}
                  yLabel={(y) => y.toFixed(1)}
                />
              </div>
              {data.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
              <p className="muted small">Growth of 1 in each factor’s paper portfolio. {data.start.slice(0, 7)} to {data.end.slice(0, 7)}.</p>
              <div className="ticket">
                <CopyCsvButton rows={() => [['date', 'mkt_rf', 'smb', 'hml', 'rmw', 'cma', 'mom', 'rf'], ...data.rows.map((r) => [r.date, r.mkt_rf, r.smb, r.hml, r.rmw, r.cma, r.mom, r.rf])]} />
              </div>
              <table className="table">
                <thead><tr><th>Factor</th><th className="num">Latest month</th><th className="num">Last 12 months</th><th className="num">Average a year</th><th className="num">Volatility a year</th><th className="num">t-statistic</th></tr></thead>
                <tbody>
                  {data.factors.map((f) => (
                    <tr key={f.key}>
                      <td>{f.label}<div className="muted small">{f.description}</div></td>
                      <td className="num"><Val r={f.latest} onReceipt={onReceipt} className={signed(f.latest)} /></td>
                      <td className="num"><Val r={f.last_12m} onReceipt={onReceipt} className={signed(f.last_12m)} /></td>
                      <td className="num"><Val r={f.annual_return} onReceipt={onReceipt} className={signed(f.annual_return)} /></td>
                      <td className="num"><Val r={f.annual_volatility} onReceipt={onReceipt} /></td>
                      <td className="num"><Val r={f.t_stat ?? undefined} onReceipt={onReceipt} className={signed(f.t_stat)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted small">These are paper long-short portfolios before trading costs, so you couldn’t have earned them exactly. A t-statistic near 2 is weak evidence: many factors have been tried, and the ones published are the ones that looked good. Published monthly, so the latest month lags.</p>
              <Source meta={data} note={`unit: ${data.unit}`} />
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}

function CotOverviewView({ data, onOpen }: { data: CotOverview; onOpen: Common['onOpen'] }) {
  const zone = (z: string | null) => (z === 'neutral' || !z ? 'muted' : 'warn')
  return (
    <div className="stack">
      <p className="muted small">Positions reported on {data.report_date}. A score shows where a group’s net position sits in its own recent range: 0 is its most short, 100 its most long. Pick a market for its history.</p>
      <div className="ticket">
        <CopyCsvButton rows={() => [['market', 'date', 'open_interest', ...data.sides.flatMap((s) => [`${s.key}_share_of_oi`, `${s.key}_score`, `${s.key}_zone`])], ...data.rows.map((r) => [r.market, r.date, r.open_interest, ...data.sides.flatMap((s) => [r.sides[s.key].share_of_oi, r.sides[s.key].score, r.sides[s.key].zone])])]} />
      </div>
      <table className="table">
        <thead>
          <tr><th>Market</th><th className="num">Open interest</th>{data.sides.map((s) => <th key={s.key} className="num">{s.label}</th>)}</tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.market}>
              <td><button className="link" onClick={() => onOpen(`COT ${r.market}`)}>{r.market}</button></td>
              <td className="num">{r.open_interest == null ? '—' : compact(r.open_interest)}</td>
              {data.sides.map((s) => {
                const side = r.sides[s.key]
                return (
                  <td key={s.key} className="num">
                    {pct(side.share_of_oi)} <span className="muted small">· {side.score ?? '—'}</span>
                    {side.zone && side.zone !== 'neutral' && <div className={`${zone(side.zone)} small`}>{side.zone}</div>}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <Source meta={data} note="net position as a share of open interest · score" />
    </div>
  )
}

function CotMarketView({ data, onReceipt, onOpen }: { data: CotMarket; onReceipt: Common['onReceipt']; onOpen: Common['onOpen'] }) {
  const colors: Record<string, string> = { large_specs: '#6cb6ff', small_specs: '#f0a35e', commercials: '#7ee787' }
  const others = data.matches.filter((m) => m.name !== data.market)
  return (
    <div className="stack">
      {others.length > 0 && (
        <div className="stack">
          <p className="warn small">“{data.query}” matched {data.matches.length} contracts. This is the closest name. Others:</p>
          <div className="ticket">{others.slice(0, 8).map((m) => <button key={m.name} className="chip" onClick={() => onOpen(`COT ${m.name}`)}>{m.name}</button>)}</div>
        </div>
      )}
      <div className="figs">
        <Fig label="Open interest (contracts)" r={data.open_interest} onReceipt={onReceipt} />
      </div>
      <table className="table">
        <thead><tr><th>Group</th><th className="num">Net position</th><th className="num">Share of open interest</th><th className="num">Change in a week</th><th className="num">Score (0 to 100)</th><th>Zone</th></tr></thead>
        <tbody>
          {data.sides.map((s) => (
            <tr key={s.key}>
              <td>{s.label}</td>
              <td className="num"><Val r={s.net} onReceipt={onReceipt} /></td>
              <td className="num"><Val r={s.share_of_oi} onReceipt={onReceipt} /></td>
              <td className="num"><Val r={s.change_1w} onReceipt={onReceipt} /></td>
              <td className="num"><Val r={s.score} onReceipt={onReceipt} /></td>
              <td className={s.zone && s.zone !== 'neutral' ? 'warn' : 'muted'}>{s.zone ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="research-chart">
        <XYChart
          height={240}
          series={data.sides.map((s) => ({
            label: s.label,
            color: colors[s.key],
            points: data.history.flatMap((h): [number, number][] => (h[s.key] == null ? [] : [[dayMs(h.date), h[s.key]!]])),
          }))}
          xTicks={yearTicks(data.history.map((h) => h.date))}
          xLabel={yearLabel}
          yLabel={(y) => `${(y * 100).toFixed(0)}%`}
        />
      </div>
      <div className="ticket">
        <CopyCsvButton rows={() => [['date', 'large_specs', 'small_specs', 'commercials'], ...data.history.map((h) => [h.date, h.large_specs, h.small_specs, h.commercials])]} />
      </div>
      <p className="muted small">Net position as a share of open interest, last 3 years. Speculators are mostly funds. Commercials are mostly producers and users hedging, so they usually sit on the other side. {data.lookback_weeks ? `Scores compare with the last ${data.lookback_weeks} weeks. ` : ''}Reported weekly and published days later, so this isn’t today’s position.</p>
      <Source meta={data} note={`report of ${data.report_date}`} />
    </div>
  )
}

export function CotWorkspace({ market, onReceipt, onOpen }: { market?: string } & Common) {
  const { data, error, loading } = useLoad<CotOverview | CotMarket>(useCallback(() => researchApi.cot(market), [market]))
  const title = data?.view === 'market' ? `COT · ${data.market}` : 'Commitments of Traders'
  return (
    <main className="grid grid--research">
      <Panel code="COT" title={title} className="research-wide">
        <div className="stack">
          {market && <div className="ticket"><button className="chip" onClick={() => onOpen('COT')}>All major markets</button></div>}
          <Status what="positioning data" error={error} loading={loading} />
          {data?.view === 'overview' && <CotOverviewView data={data} onOpen={onOpen} />}
          {data?.view === 'market' && <CotMarketView data={data} onReceipt={onReceipt} onOpen={onOpen} />}
        </div>
      </Panel>
    </main>
  )
}

export function FedWorkspace({ onReceipt }: { onReceipt: Common['onReceipt'] }) {
  const { data, error, loading } = useLoad<FedConditions>(useCallback(() => researchApi.fed(), []))
  const rates = data?.rates
  const money = data?.money
  const expectations = data?.expectations
  const twoDp = (y: number) => `${(y * 100).toFixed(1)}%`
  return (
    <main className="grid grid--research">
      <Panel code="FED" title="Federal Reserve" className="research-wide">
        <div className="stack">
          <Status what="Federal Reserve data" error={error} loading={loading} />
          {data && Object.entries(data.errors).map(([section, message]) => <p key={section} className="warn small">No {section} data: {message}</p>)}
          {data && (
            <div className="figs">
              <Fig label="Effective funds rate" r={rates?.effr} onReceipt={onReceipt} />
              <Fig label="Target, lower" r={rates?.target_lower} onReceipt={onReceipt} />
              <Fig label="Target, upper" r={rates?.target_upper} onReceipt={onReceipt} />
              <Fig label="SOFR" r={rates?.sofr} onReceipt={onReceipt} />
              <Fig label="SOFR minus funds rate" r={rates?.sofr_minus_effr} onReceipt={onReceipt} />
              <Fig label="Real funds rate (approx.)" r={data.real_rate} onReceipt={onReceipt} />
              <Fig label="M2 money supply" r={money?.m2} onReceipt={onReceipt} />
              <Fig label="M2 growth, a year" r={money?.m2_growth} onReceipt={onReceipt} />
              <Fig label="Expected inflation, 1 year" r={expectations?.cpi_1y} onReceipt={onReceipt} />
              <Fig label="Expected inflation, 10 years" r={expectations?.cpi_10y} onReceipt={onReceipt} />
            </div>
          )}
          {rates && rates.series.length > 0 && (
            <>
              <h3 className="small">Short-term rates, last 5 years</h3>
              <div className="research-chart">
                <XYChart
                  height={220}
                  zeroLine={false}
                  series={[
                    { label: 'Effective funds rate', color: '#6cb6ff', points: rates.series.map(([d, v]): [number, number] => [dayMs(d), v]) },
                    { label: 'SOFR', color: '#f0a35e', points: rates.series.flatMap(([d, , v]): [number, number][] => (v == null ? [] : [[dayMs(d), v]])) },
                  ]}
                  xTicks={yearTicks(rates.series.map(([d]) => d))}
                  xLabel={yearLabel}
                  yLabel={twoDp}
                />
              </div>
            </>
          )}
          {money && money.series.length > 0 && (
            <>
              <h3 className="small">M2 growth over a year</h3>
              <div className="research-chart">
                <XYChart height={180} series={[{ label: 'M2 growth', color: '#7ee787', points: money.series.map(([d, v]): [number, number] => [dayMs(d), v]) }]} xTicks={yearTicks(money.series.map(([d]) => d))} xLabel={yearLabel} yLabel={twoDp} />
              </div>
            </>
          )}
          {data && <p className="muted small">The real rate here is the funds rate minus forecasters’ expected inflation for the next year, a rough guide only. Expectations come from a quarterly survey, so they change less often than the rates.</p>}
          {rates && <Source meta={rates} note={rates.series.length ? `rates to ${rates.series[rates.series.length - 1][0]}` : undefined} />}
        </div>
      </Panel>
    </main>
  )
}

export function ResearchWorkspace({ view, onReceipt, onOpen }: { view: ResearchView } & Common) {
  switch (view.view) {
    case 'own': return <OwnershipWorkspace symbol={view.symbol} onReceipt={onReceipt} />
    case 'chain': return <ChainWorkspace symbol={view.symbol} expiration={view.expiration} onReceipt={onReceipt} />
    case 'cal': return <CalendarWorkspace days={view.days} onOpen={onOpen} />
    case 'filings': return <FilingsWorkspace symbol={view.symbol} onOpen={onOpen} />
    case 'etf': return <EtfWorkspace symbol={view.symbol} onReceipt={onReceipt} onOpen={onOpen} />
    case 'curve': return <CurveWorkspace onReceipt={onReceipt} />
    case 'factors': return <FactorsWorkspace region={view.region} years={view.years} onReceipt={onReceipt} />
    case 'cot': return <CotWorkspace market={view.market} onReceipt={onReceipt} onOpen={onOpen} />
    case 'fed': return <FedWorkspace onReceipt={onReceipt} />
  }
}
