import { useEffect, useState, type ReactNode } from 'react'
import { formatValue, timeAgo, type EngineStatus, type Health, type Receipt, type ReceiptExample, type SourceHealth } from './api'
import { COMMANDS } from './commands'

export function Panel(props: { code: string; title: string; active?: boolean; children: ReactNode; className?: string }) {
  return (
    <section className={`panel ${props.active ? 'panel--active' : ''} ${props.className ?? ''}`}>
      <header className="panel__header">
        <span className="panel__code">{props.code}</span>
        <span className="panel__title">{props.title}</span>
      </header>
      <div className="panel__body">{props.children}</div>
    </section>
  )
}

export function SystemPanel(props: {
  health: Health | null; healthError: string | null; engines: EngineStatus[] | null; enginesLoading: boolean; sources: SourceHealth[] | null
}) {
  const { health, healthError, engines, enginesLoading, sources } = props
  return (
    <div className="stack">
      <div className="kv">
        <span>Backend</span>
        {health ? (
          <span className="ok">● online · v{health.version}</span>
        ) : (
          <span className="bad">● offline{healthError ? ` · ${healthError}` : ''}</span>
        )}
        <span>Python</span>
        <span>{health?.python ?? '—'}</span>
        <span>Platform</span>
        <span>{health?.platform ?? '—'}</span>
      </div>
      <h3 className="subhead">Engines</h3>
      {!health && <p className="muted">Start the backend to see engine status.</p>}
      {health && enginesLoading && !engines && <p className="muted">Probing engines…</p>}
      {engines && (
        <table className="table">
          <thead>
            <tr>
              <th>Engine</th>
              <th>Role</th>
              <th>Status</th>
              <th>Licence</th>
            </tr>
          </thead>
          <tbody>
            {engines.map((e) => (
              <tr key={e.id}>
                <td>
                  <a href={e.homepage} target="_blank" rel="noreferrer">
                    {e.name}
                  </a>
                </td>
                <td className="muted">{e.role}</td>
                <td>{e.available ? <span className="ok">ready {e.version}</span> : <span className="warn">{e.reason}</span>}</td>
                <td className="muted">{e.license}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <h3 className="subhead">Data sources</h3>
      {!sources?.length ? (
        <p className="muted">No data requested yet. Open a ticker (e.g. type AAPL) and each provider tried shows up here.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Status</th>
              <th>OK / failed</th>
              <th>Last error</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((s) => (
              <tr key={s.provider}>
                <td>{s.provider}</td>
                <td className={s.status === 'ok' ? 'ok' : s.status === 'failing' ? 'bad' : 'muted'}>
                  {s.status}
                  {s.status === 'ok' && s.last_ok_at ? <span className="muted"> · {timeAgo(s.last_ok_at)}</span> : null}
                </td>
                <td className="muted">{s.successes} / {s.failures}</td>
                <td className="muted error-text">{s.last_error ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

export function HelpPanel() {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Command</th>
          <th>Does</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {COMMANDS.map((c) => (
          <tr key={c.name}>
            <td>
              <code>{c.usage}</code>
            </td>
            <td className="muted">{c.description}</td>
            <td>{c.status === 'ready' ? <span className="ok">ready</span> : <span className="muted">planned</span>}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function ReceiptNode({ r, depth = 0 }: { r: Receipt; depth?: number }) {
  const [open, setOpen] = useState(depth === 0)
  return (
    <div className="receipt" style={{ marginLeft: depth ? 14 : 0 }}>
      <button className="receipt__row" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="receipt__caret">{r.inputs.length ? (open ? '▾' : '▸') : '·'}</span>
        <span className="receipt__label">{r.label}</span>
        <span className="receipt__value">{formatValue(r)}</span>
      </button>
      {open && (
        <div className="receipt__meta">
          <span>unit</span>
          <span>{r.unit}</span>
          <span>source</span>
          <span>
            {r.source.provider}
            {r.source.detail ? ` · ${r.source.detail}` : ''}
          </span>
          <span>time</span>
          <span>{new Date(r.source.fetched_at).toLocaleString()}</span>
          {r.formula && (
            <>
              <span>formula</span>
              <span>
                <code>{r.formula}</code>
              </span>
            </>
          )}
        </div>
      )}
      {open && r.inputs.map((child, i) => <ReceiptNode key={i} r={child} depth={depth + 1} />)}
    </div>
  )
}

export function ReceiptPanel({ example }: { example: ReceiptExample | null }) {
  if (!example) return <p className="muted">Needs the backend.</p>
  return (
    <div className="stack">
      <p className="muted">{example.note}</p>
      <ReceiptNode r={example.receipt} />
    </div>
  )
}

export type LogEntry = { at: Date; input: string; message: string; ok: boolean }

export function LogPanel({ entries }: { entries: LogEntry[] }) {
  if (!entries.length) return <p className="muted">Commands you run appear here.</p>
  return (
    <ol className="log">
      {entries.map((e, i) => (
        <li key={i} className={e.ok ? '' : 'log--err'}>
          <time>{e.at.toLocaleTimeString([], { hour12: false })}</time>
          <code>&gt; {e.input}</code>
          <span>{e.message}</span>
        </li>
      ))}
    </ol>
  )
}

/** Slide-over showing the full receipt tree for one number. Esc closes it. */
export function ReceiptDrawer({ receipt, onClose }: { receipt: Receipt | null; onClose: () => void }) {
  useEffect(() => {
    if (!receipt) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [receipt, onClose])
  if (!receipt) return null
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-label={`Receipt for ${receipt.label}`} onClick={(e) => e.stopPropagation()}>
        <header className="panel__header">
          <span className="panel__code">RCPT</span>
          <span className="panel__title">{receipt.label}</span>
          <button className="drawer__close" onClick={onClose} aria-label="Close">Esc ✕</button>
        </header>
        <div className="panel__body">
          <ReceiptNode r={receipt} />
        </div>
      </aside>
    </div>
  )
}
