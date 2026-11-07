// READ: an SEC filing inside FinHub, split into its sections. Text comes straight from the filing, unchanged.
// The SEC asks automated tools to declare who is calling, so this asks once for a name and email and keeps them on
// this computer.

import { useEffect, useMemo, useState } from 'react'
import { readApi, type FilingText } from './api'
import { Panel } from './components'
import { DataError } from './Ticker'

const FORMS = ['10-K', '10-Q', '8-K', 'DEF 14A']

function IdentityForm({ onSaved }: { onSaved: () => void }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    readApi.saveIdentity(name, email).then(onSaved, (err) => setError(err.message)).finally(() => setBusy(false))
  }

  return (
    <form className="stack" onSubmit={submit}>
      <p className="small">The SEC asks automated tools to say who’s making requests, so it can get in touch if one misbehaves. Enter your real name and an email you can receive messages at. You only need to do this once.</p>
      <div className="ticket">
        <input className="research-input port-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" aria-label="Your name" maxLength={100} required />
        <input className="research-input port-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Your email" aria-label="Your email" maxLength={200} required />
        <button className="chip chip--on" type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button>
      </div>
      {error && <p className="bad small">{error}</p>}
      <p className="muted small">Stored only in your FinHub data folder and sent only to the SEC. No registration is involved, and the SEC’s data is open to anyone, wherever you live.</p>
    </form>
  )
}

function countOf(text: string, query: string): number {
  if (!query) return 0
  const haystack = text.toLowerCase()
  const needle = query.toLowerCase()
  let count = 0
  for (let at = haystack.indexOf(needle); at >= 0; at = haystack.indexOf(needle, at + needle.length)) count++
  return count
}

function Highlighted({ text, query }: { text: string; query: string }) {
  if (query.length < 2) return <>{text}</>
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))
  return <>{parts.map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : part))}</>
}

export function ReadWorkspace({ symbol, form: initialForm, accession, onOpen }: { symbol: string; form: string; accession?: string; onOpen: (command: string) => void }) {
  const [form, setForm] = useState(initialForm)
  const [data, setData] = useState<FilingText | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [needsIdentity, setNeedsIdentity] = useState<boolean | null>(null)
  const [saved, setSaved] = useState(0)
  const [section, setSection] = useState(0)
  const [query, setQuery] = useState('')

  useEffect(() => {
    let live = true
    readApi.identity().then((i) => { if (live) setNeedsIdentity(!i.configured) }, (e) => { if (live) setError(e) })
    return () => { live = false }
  }, [saved])

  useEffect(() => {
    if (needsIdentity !== false) return
    let live = true
    setData(null)
    setError(null)
    setSection(0)
    readApi.filing(symbol, form, accession).then((d) => { if (live) setData(d) }, (e) => { if (live) setError(e) })
    return () => { live = false }
  }, [symbol, form, accession, needsIdentity])

  const matches = useMemo(() => (data ? data.sections.map((s) => countOf(s.text, query.trim())) : []), [data, query])
  const total = matches.reduce((a, b) => a + b, 0)
  const current = data?.sections[section]

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="READ" title={data ? `${data.company} · ${data.form} · filed ${data.filed}` : `${symbol} · SEC filing`} className="research-wide">
        <div className="stack">
          {needsIdentity && <IdentityForm onSaved={() => setSaved((n) => n + 1)} />}
          {error && <DataError error={error} what={`the ${form} for ${symbol}`} />}
          {needsIdentity === false && (
            <div className="ticket">
              {!accession && FORMS.map((f) => <button key={f} className={`chip ${form === f ? 'chip--on' : ''}`} onClick={() => setForm(f)}>{f}</button>)}
              <button className="chip" onClick={() => onOpen(`FILINGS ${symbol}`)}>All filings</button>
              {data?.url && <a className="chip" href={data.url} target="_blank" rel="noreferrer">Open at the SEC</a>}
            </div>
          )}
          {needsIdentity === false && !data && !error && <p className="muted">Fetching the filing from the SEC… (the first one after launch can take a minute)</p>}
          {data && (
            <>
              <div className="ticket">
                <input className="research-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find in this filing" aria-label="Find in this filing" spellCheck={false} />
                {query.trim().length >= 2 && <span className="muted small">{total} found</span>}
              </div>
              <div className="read">
                <ul className="read__sections">
                  {data.sections.map((s, i) => (
                    <li key={s.id}>
                      <button className={`read__section ${i === section ? 'read__section--on' : ''}`} onClick={() => setSection(i)}>
                        <span>{s.title}</span>
                        <span className="muted small">{query.trim().length >= 2 && matches[i] ? `${matches[i]} found` : `${Math.ceil(s.text.length / 1000)}k`}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                <div className="read__text answer">{current && <Highlighted text={current.text} query={query.trim()} />}</div>
              </div>
              <p className="muted small">The company’s own words from {data.provider_name}, unchanged. A company’s filing is what it chose to say, so check the numbers against the statements. Tables may lose some of their layout as plain text.</p>
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}
