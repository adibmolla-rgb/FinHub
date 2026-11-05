import type { Load } from './useTicker'
import {
  ApiError, formatValue, RANGES, timeAgo,
  type History, type News, type Profile, type Quote, type QuoteKey, type Range, type Receipt,
} from './api'
import { PriceChart } from './Chart'
import { Panel } from './components'

type Meta = { provider_name: string; fetched_at: string; fallback_used: boolean; attempts: { provider: string; ok: boolean; error: string | null }[] }

function SourceBadge({ meta }: { meta: Meta }) {
  const failed = meta.attempts.filter((a) => !a.ok)
  const title = meta.attempts.map((a) => `${a.ok ? '✓' : '✗'} ${a.provider}${a.error ? ` — ${a.error}` : ''}`).join('\n')
  return (
    <span className="badge" title={title}>
      via {meta.provider_name} · {timeAgo(meta.fetched_at)}
      {meta.fallback_used && <span className="warn"> · fallback after {failed.map((a) => a.provider).join(', ')}</span>}
    </span>
  )
}

function DataError({ error, what }: { error: ApiError | Error; what: string }) {
  const attempts = error instanceof ApiError ? error.attempts : []
  const engineMissing = /engine not installed/.test(error.message)
  return (
    <div className="data-error">
      <p>
        <span className="bad">Couldn’t load {what}.</span> <span className="muted">{error.message}</span>
      </p>
      {engineMissing && (
        <p className="warn">The market-data engine isn’t installed yet. It installs automatically on first launch; check progress or start it in SYS, then REFRESH.</p>
      )}
      {attempts.length > 0 && (
        <table className="table">
          <tbody>
            {attempts.map((a, i) => (
              <tr key={i}>
                <td className={a.ok ? 'ok' : 'bad'}>{a.ok ? '✓' : '✗'} {a.provider}</td>
                <td className="muted">{a.ms != null ? `${a.ms} ms` : ''}</td>
                <td className="muted error-text">{a.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function Loading({ what }: { what: string }) {
  return <p className="muted">Loading {what}… (the first request after launch waits for the data engine to start)</p>
}

function Val({ r, onReceipt, className }: { r: Receipt | undefined; onReceipt: (r: Receipt) => void; className?: string }) {
  if (!r) return <span className="muted">—</span>
  return (
    <button className={`val ${className ?? ''}`} onClick={() => onReceipt(r)} title="Show receipt">
      {formatValue(r)}
    </button>
  )
}

const STATS: [QuoteKey, string][] = [
  ['previous_close', 'Prev close'], ['open', 'Open'], ['day_low', 'Day low'], ['day_high', 'Day high'],
  ['year_low', '52w low'], ['year_high', '52w high'], ['from_high_pct', 'From 52w high'],
  ['volume', 'Volume'], ['market_cap', 'Market cap'],
]

export function QuoteStrip({ symbol, quote, profile, onReceipt }: {
  symbol: string; quote: Load<Quote>; profile: Load<Profile>; onReceipt: (r: Receipt) => void
}) {
  const q = quote.data
  const dir = (q?.values.change?.value ?? 0) >= 0 ? 'ok' : 'bad'
  return (
    <section className="quote">
      <div className="quote__id">
        <span className="quote__sym">{symbol}</span>
        <span className="quote__name">{profile.data?.name ?? ''}</span>
        {q?.exchange && <span className="muted"> · {q.exchange}</span>}
      </div>
      {quote.loading && !q && <Loading what="quote" />}
      {quote.error && <DataError error={quote.error} what="the quote" />}
      {q && (
        <>
          <div className="quote__price">
            <Val r={q.values.price} onReceipt={onReceipt} className="quote__last" />
            <Val r={q.values.change} onReceipt={onReceipt} className={dir} />
            <Val r={q.values.change_pct} onReceipt={onReceipt} className={dir} />
          </div>
          <dl className="quote__stats">
            {STATS.map(([k, label]) => (
              <div key={k}>
                <dt>{label}</dt>
                <dd><Val r={q.values[k]} onReceipt={onReceipt} /></dd>
              </div>
            ))}
          </dl>
          <SourceBadge meta={q} />
        </>
      )}
    </section>
  )
}

export function ChartPanel({ history, range, onRange }: { history: Load<History>; range: Range; onRange: (r: Range) => void }) {
  const h = history.data
  return (
    <Panel code="GP" title="Price chart (daily, unadjusted)" className="grid__chart">
      <div className="chart-wrap">
        <div className="chart-toolbar">
          {RANGES.map((r) => (
            <button key={r} className={`chip ${r === range ? 'chip--on' : ''}`} onClick={() => onRange(r)}>{r}</button>
          ))}
          {h && <SourceBadge meta={h} />}
        </div>
        {history.loading && !h && <Loading what="price history" />}
        {history.error && <DataError error={history.error} what="price history" />}
        {h && <PriceChart bars={h.bars} />}
      </div>
    </Panel>
  )
}

export function ProfilePanel({ profile }: { profile: Load<Profile> }) {
  const p = profile.data
  return (
    <Panel code="DES" title="Company" className="grid__profile">
      {profile.loading && !p && <Loading what="profile" />}
      {profile.error && <DataError error={profile.error} what="the company profile" />}
      {p && (
        <div className="stack">
          <div className="kv">
            <span>Name</span><span>{p.name}</span>
            <span>Sector</span><span>{p.sector ?? '—'}</span>
            <span>Industry</span><span>{p.industry ?? '—'}</span>
            <span>Country</span><span>{p.country ?? '—'}</span>
            <span>Employees</span><span>{p.employees?.toLocaleString() ?? '—'}</span>
            <span>Website</span>
            <span>{p.website ? <a href={p.website} target="_blank" rel="noreferrer">{p.website.replace(/^https?:\/\//, '')}</a> : '—'}</span>
          </div>
          {p.description && <p className="description">{p.description}</p>}
          <SourceBadge meta={p} />
        </div>
      )}
    </Panel>
  )
}

export function NewsPanel({ news }: { news: Load<News> }) {
  const n = news.data
  return (
    <Panel code="CN" title="News" className="grid__news">
      {news.loading && !n && <Loading what="news" />}
      {news.error && <DataError error={news.error} what="news" />}
      {n && (
        <div className="stack">
          <ol className="news">
            {n.items.map((item, i) => (
              <li key={i}>
                {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a> : item.title}
                <span className="muted">
                  {' '}· {item.source ?? 'unknown source'} · {item.published ? timeAgo(item.published) : 'undated'}
                </span>
              </li>
            ))}
          </ol>
          <SourceBadge meta={n} />
        </div>
      )}
    </Panel>
  )
}
