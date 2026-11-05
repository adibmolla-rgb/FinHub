import { useCallback, useEffect, useState } from 'react'
import { formatValue, watchApi, type Receipt, type WatchQuote } from './api'

/** Watchlist panel: live quotes for saved tickers. Click a ticker to open it, a number for its receipt. */
export function WatchPanel({ online, onOpen, onReceipt, version }: {
  online: boolean; onOpen: (symbol: string) => void; onReceipt: (r: Receipt) => void; version: number
}) {
  const [symbols, setSymbols] = useState<string[]>([])
  const [quotes, setQuotes] = useState<Record<string, WatchQuote>>({})
  const [loading, setLoading] = useState(false)
  const [add, setAdd] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const { symbols } = await watchApi.get()
      setSymbols(symbols)
      const qs = await watchApi.quotes()
      setQuotes(Object.fromEntries(qs.map((q) => [q.symbol, q])))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!online) return
    load()
    const t = setInterval(load, 60_000)
    return () => clearInterval(t)
  }, [online, load, version])

  const save = async (next: string[]) => {
    try {
      const r = await watchApi.set(next)
      setSymbols(r.symbols)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!online) return <p className="muted">Needs the backend.</p>
  return (
    <div className="stack">
      <form className="ticket" onSubmit={(e) => { e.preventDefault(); if (add.trim()) save([...symbols, add.trim().toUpperCase()]); setAdd('') }}>
        <input className="cell" value={add} onChange={(e) => setAdd(e.target.value)} placeholder="Add ticker" spellCheck={false} aria-label="Add ticker" />
        <button className="chip" type="submit">Add</button>
        <button className="chip" type="button" onClick={load} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
      </form>
      {error && <p className="bad small">{error}</p>}
      <table className="table watch">
        <thead><tr><th>Ticker</th><th className="num">Last</th><th className="num">Change</th><th className="num">%</th><th /></tr></thead>
        <tbody>
          {symbols.map((s) => {
            const q = quotes[s]
            const v = q?.ok ? q.quote.values : undefined
            const dir = (v?.change?.value ?? 0) >= 0 ? 'ok' : 'bad'
            return (
              <tr key={s}>
                <td><button className="link" onClick={() => onOpen(s)}>{s}</button></td>
                {q && !q.ok ? (
                  <td colSpan={3} className="muted small" title={q.error}>unavailable</td>
                ) : (
                  <>
                    <td className="num">{v?.price ? <button className="val" onClick={() => onReceipt(v.price!)}>{formatValue(v.price)}</button> : <span className="muted">{loading ? '…' : '—'}</span>}</td>
                    <td className={`num ${dir}`}>{v?.change ? <button className={`val ${dir}`} onClick={() => onReceipt(v.change!)}>{v.change.value.toFixed(2)}</button> : ''}</td>
                    <td className={`num ${dir}`}>{v?.change_pct ? <button className={`val ${dir}`} onClick={() => onReceipt(v.change_pct!)}>{formatValue(v.change_pct)}</button> : ''}</td>
                  </>
                )}
                <td><button className="chip" title={`Remove ${s}`} onClick={() => save(symbols.filter((x) => x !== s))}>✕</button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="muted small">W TICKER adds, W -TICKER removes. Refreshes every minute.</p>
    </div>
  )
}
