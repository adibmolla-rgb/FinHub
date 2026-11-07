import { useEffect, useState } from 'react'
import { compact, formatValue, screenApi, type Receipt, type ScreenRequest, type ScreenResult, type ScreenRow } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'

const SECTORS = ['Communication Services', 'Consumer Discretionary', 'Consumer Staples', 'Energy', 'Financials', 'Health Care', 'Industrials', 'Information Technology', 'Materials', 'Real Estate', 'Utilities']
type SortKey = 'symbol' | 'price' | 'change_pct' | 'market_cap' | 'from_high_pct' | 'from_low_pct'

// Percent inputs are typed as percent and converted to fractions once, here.
const pctOrUndef = (s: string) => (s.trim() === '' ? undefined : parseFloat(s) / 100)
const numOrUndef = (s: string) => (s.trim() === '' ? undefined : parseFloat(s))

export function ScreenerWorkspace({ symbols, onOpen, onReceipt }: { symbols?: string[]; onOpen: (symbol: string) => void; onReceipt: (r: Receipt) => void }) {
  const [universe, setUniverse] = useState<ScreenRequest['universe']>(symbols ? 'custom' : 'large_caps')
  const [custom, setCustom] = useState(symbols?.join(' ') ?? '')
  const [f, setF] = useState({ minPrice: '', maxPrice: '', minChange: '', maxChange: '', minCapB: '', withinHigh: '', aboveLow: '' })
  const [sectors, setSectors] = useState<string[]>([])
  const [result, setResult] = useState<ScreenResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'market_cap', desc: true })

  const run = async () => {
    setRunning(true)
    setError(null)
    try {
      const capB = numOrUndef(f.minCapB)
      setResult(await screenApi.run({
        universe,
        symbols: universe === 'custom' ? custom.split(/[\s,]+/).filter(Boolean) : undefined,
        min_price: numOrUndef(f.minPrice), max_price: numOrUndef(f.maxPrice),
        min_change: pctOrUndef(f.minChange), max_change: pctOrUndef(f.maxChange),
        min_market_cap: capB === undefined ? undefined : capB * 1e9,
        max_from_high: pctOrUndef(f.withinHigh), min_from_low: pctOrUndef(f.aboveLow),
        sectors,
      }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  // Opened with a list of tickers (from FIND or SCREEN AAPL MSFT): show them straight away.
  useEffect(() => {
    if (symbols) void run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const rows = [...(result?.matches ?? [])].sort((a, b) => {
    const av = a[sort.key], bv = b[sort.key]
    if (av == null) return 1
    if (bv == null) return -1
    const c = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number)
    return sort.desc ? -c : c
  })
  const th = (key: SortKey, label: string) => (
    <th className={key === 'symbol' ? '' : 'num'}>
      <button className="link" onClick={() => setSort({ key, desc: sort.key === key ? !sort.desc : true })}>{label}{sort.key === key ? (sort.desc ? ' ▾' : ' ▴') : ''}</button>
    </th>
  )
  const field = (k: keyof typeof f, label: string, suffix?: string) => (
    <label className="numfield"><span>{label}</span><input type="number" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />{suffix && <em>{suffix}</em>}</label>
  )
  const cell = (r: ScreenRow, k: 'price' | 'change_pct' | 'market_cap' | 'from_high_pct', text: string, cls = '') =>
    r.receipts[k] ? <button className={`val ${cls}`} onClick={() => onReceipt(r.receipts[k]!)}>{text}</button> : <span className="muted">—</span>

  return (
    <main className="grid grid--screen">
      <Panel code="SCREEN" title="Screen" className="grid__screenform">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); run() }}>
          <div className="ticket">
            {([['large_caps', 'Large caps'], ['watchlist', 'Watchlist'], ['custom', 'Custom']] as const).map(([k, l]) => (
              <button type="button" key={k} className={`chip ${universe === k ? 'chip--on' : ''}`} onClick={() => setUniverse(k)}>{l}</button>
            ))}
          </div>
          {universe === 'custom' && (
            <label className="numfield"><span>Tickers</span><input value={custom} onChange={(e) => setCustom(e.target.value.toUpperCase())} placeholder="AAPL MSFT ASML SHEL …" spellCheck={false} /></label>
          )}
          <div className="numgrid">
            {field('minPrice', 'Min price')}
            {field('maxPrice', 'Max price')}
            {field('minChange', 'Min change today', '%')}
            {field('maxChange', 'Max change today', '%')}
            {field('minCapB', 'Min market cap', 'bn')}
            {field('withinHigh', 'Within x% of 52w high', '%')}
            {field('aboveLow', 'At least x% above 52w low', '%')}
          </div>
          <div className="sectors">
            {SECTORS.map((s) => (
              <label key={s} className="inline small"><input type="checkbox" checked={sectors.includes(s)} onChange={(e) => setSectors(e.target.checked ? [...sectors, s] : sectors.filter((x) => x !== s))} /> {s}</label>
            ))}
          </div>
          <button className="btn btn--buy" type="submit" disabled={running}>{running ? 'Fetching quotes…' : 'Run screen'}</button>
          <p className="muted small">Empty fields are ignored. A ticker missing data for a filter you set is excluded, not guessed. Sectors are a fixed reference for the built-in list.</p>
        </form>
      </Panel>
      <Panel code="RESULTS" title={result ? `${rows.length} match${rows.length === 1 ? '' : 'es'} · ${result.quoted}/${result.size} quoted` : 'Results'} className="grid__screenres">
        {error && <p className="bad">{error}</p>}
        {!result && !error && <p className="muted">Set filters and run. Quotes are fetched live (cached for a minute).</p>}
        {result && (
          <div className="stack">
            {result.failed.length > 0 && <p className="warn small">No quote for {result.failed.map((x) => x.symbol).join(', ')}: they could not be screened.</p>}
            <div className="ticket">
              <CopyCsvButton rows={() => [['symbol', 'sector', 'price', 'change_pct', 'market_cap', 'from_52w_high', 'from_52w_low', 'currency', 'provider'],
                ...rows.map((r) => [r.symbol, r.sector, r.price, r.change_pct, r.market_cap, r.from_high_pct, r.from_low_pct, r.currency, r.provider])]} />
            </div>
            <table className="table">
              <thead><tr>{th('symbol', 'Ticker')}<th>Sector</th>{th('price', 'Price')}{th('change_pct', 'Today')}{th('market_cap', 'Mkt cap')}{th('from_high_pct', 'vs 52w high')}{th('from_low_pct', 'vs 52w low')}</tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol}>
                    <td><button className="link" onClick={() => onOpen(r.symbol)}>{r.symbol}</button></td>
                    <td className="muted small">{r.sector ?? '—'}</td>
                    <td className="num">{cell(r, 'price', r.price != null ? r.price.toFixed(2) : '—')}</td>
                    <td className="num">{cell(r, 'change_pct', r.receipts.change_pct ? formatValue(r.receipts.change_pct) : '—', (r.change_pct ?? 0) >= 0 ? 'ok' : 'bad')}</td>
                    <td className="num">{cell(r, 'market_cap', r.market_cap != null ? compact(r.market_cap) : '—')}</td>
                    <td className="num">{cell(r, 'from_high_pct', r.receipts.from_high_pct ? formatValue(r.receipts.from_high_pct) : '—')}</td>
                    <td className="num">{r.from_low_pct != null ? `+${(r.from_low_pct * 100).toFixed(1)}%` : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </main>
  )
}
