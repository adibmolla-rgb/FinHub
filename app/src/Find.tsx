// FIND: FinanceDatabase, a reference list of about 70,000 stocks and ETFs. It says what exists, not what they cost today.

import { useEffect, useState } from 'react'
import { findApi, type FindOptions, type FindResult } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { DataError } from './Ticker'

const MAX_SCREEN = 100

export function FindWorkspace({ query: initialQuery, onOpen }: { query?: string; onOpen: (command: string) => void }) {
  const [kind, setKind] = useState<'equities' | 'etfs'>('equities')
  const [query, setQuery] = useState(initialQuery ?? '')
  const [country, setCountry] = useState('')
  const [sector, setSector] = useState('')
  const [cap, setCap] = useState('')
  const [options, setOptions] = useState<FindOptions | null>(null)
  const [data, setData] = useState<FindResult | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [searching, setSearching] = useState(false)

  useEffect(() => {
    findApi.options().then(setOptions, setError)
  }, [])

  const search = async (over?: { kind?: 'equities' | 'etfs'; query?: string }) => {
    const useKind = over?.kind ?? kind
    setSearching(true)
    setError(null)
    try {
      setData(await findApi.search({ kind: useKind, query: over?.query ?? query, country: useKind === 'equities' ? country : '', sector, market_cap: useKind === 'equities' ? cap : '' }))
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      setSearching(false)
    }
  }

  useEffect(() => {
    if (initialQuery) void search({ query: initialQuery })
    // Only the query it was opened with searches by itself; everything else waits for the button.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery])

  const changeKind = (next: 'equities' | 'etfs') => {
    setKind(next)
    setSector('')
    setData(null)
  }
  const rows = data?.rows ?? []
  const symbols = rows.slice(0, MAX_SCREEN).map((r) => r.symbol)

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="FIND" title="Find stocks and ETFs" className="research-wide">
        <div className="stack">
          <p className="muted small">Search by name, ticker or what the business does. This is FinanceDatabase, a reference list kept by its maintainers: sizes and descriptions can be out of date, and it holds no prices.</p>
          <form className="ticket searchbar" onSubmit={(e) => { e.preventDefault(); void search() }}>
            {(['equities', 'etfs'] as const).map((k) => (
              <button type="button" key={k} className={`chip ${kind === k ? 'chip--on' : ''}`} onClick={() => changeKind(k)}>{k === 'equities' ? 'Stocks' : 'ETFs'}</button>
            ))}
            <input className="cell" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="battery, semiconductor, Apple…" maxLength={80} spellCheck={false} aria-label="Search" />
            {kind === 'equities' && (
              <select className="cell" value={country} onChange={(e) => setCountry(e.target.value)} aria-label="Country">
                <option value="">Any country</option>
                {options?.countries.map((c) => <option key={c}>{c}</option>)}
              </select>
            )}
            <select className="cell" value={sector} onChange={(e) => setSector(e.target.value)} aria-label={kind === 'equities' ? 'Sector' : 'Group'}>
              <option value="">{kind === 'equities' ? 'Any sector' : 'Any group'}</option>
              {(kind === 'equities' ? options?.sectors : options?.etf_groups)?.map((s) => <option key={s}>{s}</option>)}
            </select>
            {kind === 'equities' && (
              <select className="cell" value={cap} onChange={(e) => setCap(e.target.value)} aria-label="Size">
                <option value="">Any size</option>
                {options?.market_caps.map((c) => <option key={c}>{c}</option>)}
              </select>
            )}
            <button className="chip chip--on" disabled={searching}>{searching ? 'Searching…' : 'Search'}</button>
          </form>
          {error && <DataError error={error} what="the list" />}
          {data && (
            <>
              <p className="muted small">{data.total.toLocaleString()} found{data.total > rows.length ? `, showing the first ${rows.length}` : ''} · {data.provider_name}. Click a ticker to open it.</p>
              {rows.length > 0 && (
                <div className="ticket">
                  <button className="chip" onClick={() => onOpen(`SCREEN ${symbols.join(' ')}`)}>Screen {rows.length > MAX_SCREEN ? `the first ${MAX_SCREEN}` : `these ${rows.length}`}</button>
                  <CopyCsvButton rows={() => [['symbol', 'name', 'group', 'detail', 'country', 'exchange', 'currency', 'size'], ...rows.map((r) => [r.symbol, r.name, r.sector ?? r.category_group, r.industry ?? r.category, r.country, r.exchange, r.currency, r.market_cap])]} />
                </div>
              )}
              <table className="table">
                <thead><tr><th>Ticker</th><th>Name</th><th>{kind === 'equities' ? 'Sector' : 'Group'}</th><th>{kind === 'equities' ? 'Industry' : 'Category'}</th>{kind === 'equities' && <th>Country</th>}<th>Exchange</th><th>Currency</th>{kind === 'equities' && <th>Size</th>}</tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.symbol}>
                      <td><button className="val" onClick={() => onOpen(r.symbol)}>{r.symbol}</button></td>
                      <td>{r.name ?? '—'}</td>
                      <td className="muted">{r.sector ?? r.category_group ?? '—'}</td>
                      <td className="muted">{r.industry ?? r.category ?? '—'}</td>
                      {kind === 'equities' && <td className="muted">{r.country ?? '—'}</td>}
                      <td className="muted">{r.exchange ?? '—'}</td>
                      <td className="muted">{r.currency ?? '—'}</td>
                      {kind === 'equities' && <td className="muted">{r.market_cap ?? '—'}</td>}
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
