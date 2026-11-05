import { useCallback, useEffect, useRef, useState } from 'react'
import { api, BACKEND_URL, type EngineStatus, type Health, type ReceiptExample } from './api'
import { runCommand, type PanelId } from './commands'
import { HelpPanel, LogPanel, Panel, ReceiptPanel, SystemPanel, type LogEntry } from './components'

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  return now
}

export default function App() {
  const now = useClock()
  const inputRef = useRef<HTMLInputElement>(null)
  const [command, setCommand] = useState('')
  const [history, setHistory] = useState<string[]>([])
  const [historyIndex, setHistoryIndex] = useState<number | null>(null)
  const [log, setLog] = useState<LogEntry[]>([])
  const [active, setActive] = useState<PanelId>('SYS')

  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [engines, setEngines] = useState<EngineStatus[] | null>(null)
  const [enginesLoading, setEnginesLoading] = useState(false)
  const [example, setExample] = useState<ReceiptExample | null>(null)

  const checkHealth = useCallback(async () => {
    try {
      setHealth(await api.health())
      setHealthError(null)
    } catch (err) {
      setHealth(null)
      setHealthError(err instanceof Error && err.name !== 'AbortError' ? err.message : 'no response')
    }
  }, [])

  const loadEngines = useCallback(async (refresh = false) => {
    setEnginesLoading(true)
    try {
      setEngines(await api.engines(refresh))
    } catch {
      setEngines(null)
    } finally {
      setEnginesLoading(false)
    }
  }, [])

  // Poll the backend; load engine status once it comes online.
  useEffect(() => {
    checkHealth()
    const t = setInterval(checkHealth, 5000)
    return () => clearInterval(t)
  }, [checkHealth])

  const online = health !== null
  useEffect(() => {
    if (!online) return
    loadEngines()
    api.receiptExample().then(setExample, () => setExample(null))
  }, [online, loadEngines])

  // Ctrl/Cmd+K or "/" focuses the command bar from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = document.activeElement === inputRef.current
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  function submit() {
    const input = command.trim()
    if (!input) return
    const result = runCommand(input)
    setHistory((h) => [input, ...h].slice(0, 100))
    setHistoryIndex(null)
    setCommand('')
    if (result.kind === 'open') setActive(result.panel)
    if (result.kind === 'refresh') {
      checkHealth()
      loadEngines(true)
    }
    const entry: LogEntry = { at: new Date(), input, message: result.message, ok: result.kind !== 'error' }
    setLog((l) => (result.kind === 'clear' ? [] : [entry, ...l].slice(0, 200)))
  }

  function onCommandKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') submit()
    else if (e.key === 'Escape') inputRef.current?.blur()
    else if (e.key === 'ArrowUp' && history.length) {
      e.preventDefault()
      const i = historyIndex === null ? 0 : Math.min(historyIndex + 1, history.length - 1)
      setHistoryIndex(i)
      setCommand(history[i])
    } else if (e.key === 'ArrowDown' && historyIndex !== null) {
      e.preventDefault()
      const i = historyIndex - 1
      setHistoryIndex(i < 0 ? null : i)
      setCommand(i < 0 ? '' : history[i])
    }
  }

  const ready = engines?.filter((e) => e.available).length ?? 0

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <img src="/finhub.svg" alt="" width={20} height={20} />
          <span>FinHub</span>
        </div>
        <label className="command">
          <span className="command__prompt">&gt;</span>
          <input
            ref={inputRef}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={onCommandKey}
            placeholder="Type a command — HELP, SYS, RCPT…   (Ctrl+K)"
            spellCheck={false}
            autoComplete="off"
            autoFocus
            aria-label="Command"
          />
        </label>
        <div className="clock" title="Local time · UTC">
          {now.toLocaleTimeString([], { hour12: false })}
          <span className="muted"> · {now.toISOString().slice(11, 19)} UTC</span>
        </div>
      </header>

      <main className="grid">
        <Panel code="SYS" title="System status" active={active === 'SYS'} className="grid__sys">
          <SystemPanel health={health} healthError={healthError} engines={engines} enginesLoading={enginesLoading} />
        </Panel>
        <Panel code="RCPT" title="Receipts — where every number comes from" active={active === 'RCPT'} className="grid__rcpt">
          <ReceiptPanel example={example} />
        </Panel>
        <Panel code="HELP" title="Commands" active={active === 'HELP'} className="grid__help">
          <HelpPanel />
        </Panel>
        <Panel code="LOG" title="Activity" active={active === 'LOG'} className="grid__log">
          <LogPanel entries={log} />
        </Panel>
      </main>

      <footer className="statusbar">
        <span className={online ? 'ok' : 'bad'}>● {online ? 'backend online' : 'backend offline'}</span>
        <span className="muted">{BACKEND_URL}</span>
        <span className="muted">
          engines {engines ? `${ready}/${engines.length} ready` : '—'}
        </span>
        <span className="muted statusbar__right">FinHub v0.1.0 · Apache-2.0</span>
      </footer>
    </div>
  )
}
