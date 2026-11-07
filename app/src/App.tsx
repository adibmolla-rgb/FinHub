import { useCallback, useEffect, useRef, useState } from 'react'
import { api, watchApi, BACKEND_URL, type EngineStatus, type Health, type InstallState, type Range, type Receipt, type ReceiptExample, type SourceHealth } from './api'
import { backendPhase, inDesktopApp, type BackendPhase } from './tauri'
import { runCommand, suggest, type PanelId } from './commands'
import { HelpPanel, LogPanel, Panel, ReceiptDrawer, ReceiptPanel, SystemPanel, type LogEntry } from './components'
import { ChartPanel, NewsPanel, ProfilePanel, QuoteStrip } from './Ticker'
import { useTicker } from './useTicker'
import { AgentSettingsPanel, AgentWorkspace } from './Agent'
import { WatchPanel } from './Watch'
import { NotesWorkspace } from './Notes'
import { McpPanel } from './Mcp'
import { FundamentalsWorkspace } from './Fundamentals'
import { CompareWorkspace } from './quant/CompareView'
import { ArenaWorkspace } from './sim/Arena'
import { MacroWorkspace } from './Macro'
import { ResearchWorkspace, type ResearchView } from './Research'
import { PortfolioWorkspace } from './Portfolio'
import { openExternalLinksInBrowser } from './links'
import { AlertsWorkspace } from './Alerts'
import { ScreenerWorkspace } from './Screener'
import { DemoHome } from './DemoHome'
import { DEMO_COMMANDS, WEB_DEMO } from './demo'
import { notify } from './notify'
import { alertsApi, portfolioApi, type AlertEvent } from './api'
import { SimWorkspace } from './sim/Sim'
import { OptionsWorkspace } from './quant/OptionsLab'
import { BacktestWorkspace, type BacktestPreset } from './quant/Backtest'
import { RiskWorkspace } from './quant/Risk'
import { LearnWorkspace } from './learn/Learn'
import type { AskKind } from './api'

function useClock() {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])
  return now
}

type Workspace =
  | { kind: 'home' }
  | { kind: 'ticker'; symbol: string; range: Range }
  | { kind: 'agent'; ask: AskKind; text: string; nonce: number }
  | { kind: 'ai' }
  | { kind: 'sim' }
  | { kind: 'notes'; nonce: number }
  | { kind: 'rcpt' }
  | { kind: 'mcp' }
  | { kind: 'fa'; symbol: string; nonce: number }
  | { kind: 'cmp'; symbols: string[]; nonce: number }
  | { kind: 'arena' }
  | { kind: 'learn' }
  | { kind: 'macro'; country: string; nonce: number }
  | { kind: 'research'; view: ResearchView; nonce: number }
  | { kind: 'portfolio' }
  | { kind: 'alerts' }
  | { kind: 'screen' }
  | { kind: 'opt'; symbol?: string; nonce: number }
  | { kind: 'backtest'; preset: BacktestPreset; nonce: number }
  | { kind: 'risk'; holdings: { symbol: string; weight: number }[]; nonce: number }

function TickerWorkspace({ symbol, range, onRange, onReceipt, log }: {
  symbol: string; range: Range; onRange: (r: Range) => void; onReceipt: (r: Receipt) => void; log: LogEntry[]
}) {
  const t = useTicker(symbol, range)
  return (
    <main className="grid grid--ticker">
      <div className="grid__quote">
        <QuoteStrip symbol={symbol} quote={t.quote} profile={t.profile} onReceipt={onReceipt} />
      </div>
      <ChartPanel history={t.history} range={range} onRange={onRange} />
      <NewsPanel news={t.news} />
      <ProfilePanel profile={t.profile} />
      <Panel code="LOG" title="Activity" className="grid__log">
        <LogPanel entries={log} />
      </Panel>
    </main>
  )
}

export default function App() {
  const now = useClock()
  const inputRef = useRef<HTMLInputElement>(null)
  const [command, setCommand] = useState('')
  // Command history survives restarts (per-computer convenience; failures are harmless).
  const [history, setHistory] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem('finhub.history') ?? '[]')
    } catch {
      return []
    }
  })
  useEffect(() => {
    try {
      localStorage.setItem('finhub.history', JSON.stringify(history.slice(0, 100)))
    } catch {
      /* storage unavailable */
    }
  }, [history])
  const [watchVersion, setWatchVersion] = useState(0)
  const [alertsVersion, setAlertsVersion] = useState(0)
  const [portfolioVersion, setPortfolioVersion] = useState(0)
  const [toast, setToast] = useState<AlertEvent | null>(null)
  const [flash, setFlash] = useState<string | null>(null)
  useEffect(() => {
    if (!flash) return
    const t = setTimeout(() => setFlash(null), 7000)
    return () => clearTimeout(t)
  }, [flash])
  const seenEvents = useRef<Set<string> | null>(null)
  const [historyIndex, setHistoryIndex] = useState<number | null>(null)
  const [log, setLog] = useState<LogEntry[]>([])
  const [active, setActive] = useState<PanelId>('SYS')
  const [workspace, setWorkspace] = useState<Workspace>({ kind: 'home' })
  const [refreshKey, setRefreshKey] = useState(0)
  const [receipt, setReceipt] = useState<Receipt | null>(null)

  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [engines, setEngines] = useState<EngineStatus[] | null>(null)
  const [enginesLoading, setEnginesLoading] = useState(false)
  const [example, setExample] = useState<ReceiptExample | null>(null)
  const [sources, setSources] = useState<SourceHealth[] | null>(null)
  const [installs, setInstalls] = useState<Record<string, InstallState>>({})
  const [phase, setPhase] = useState<BackendPhase | null>(null)

  const checkHealth = useCallback(async () => {
    try {
      setHealth(await api.health())
      setHealthError(null)
    } catch (err) {
      setHealth(null)
      setHealthError(err instanceof Error ? err.message : 'no response')
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

  // Poll the backend; load engine status and examples once it comes online.
  useEffect(() => {
    if (WEB_DEMO) return // no backend in the web demo
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

  // While the desktop app prepares the backend (first launch installs Python), show what it is doing.
  useEffect(() => {
    if (!inDesktopApp || health) return
    const poll = () => backendPhase().then(setPhase)
    poll()
    const t = setInterval(poll, 1000)
    return () => clearInterval(t)
  }, [health])

  // Track engine installs (started automatically on first launch, or from the SYS panel).
  const anyInstalling = Object.values(installs).some((i) => i.state === 'running')
  useEffect(() => {
    if (!online || !engines) return
    const poll = async () => {
      const entries = await Promise.all(
        engines.map((e) => api.installStatus(e.id).then((s) => [e.id, s] as const, () => null)),
      )
      const next = Object.fromEntries(entries.filter((x): x is readonly [string, InstallState] => x !== null))
      setInstalls((prev) => {
        // An install just finished: re-probe engines.
        const finished = Object.entries(next).some(([id, s]) => prev[id]?.state === 'running' && s.state !== 'running')
        if (finished) loadEngines(true)
        return next
      })
    }
    poll()
    const t = setInterval(poll, anyInstalling ? 1500 : 10_000)
    return () => clearInterval(t)
  }, [online, engines, anyInstalling, loadEngines])

  const startInstall = useCallback((id: string) => {
    api.installEngine(id).then((s) => setInstalls((prev) => ({ ...prev, [id]: s })), () => {})
  }, [])

  // Watch for alerts fired by the backend's background check; announce new ones.
  useEffect(() => {
    if (!online) return
    const poll = () =>
      alertsApi.list().then(({ events }) => {
        if (seenEvents.current === null) {
          seenEvents.current = new Set(events.map((e) => e.id)) // don't re-announce old events on launch
          return
        }
        for (const e of events) {
          if (seenEvents.current.has(e.id)) continue
          seenEvents.current.add(e.id)
          setToast(e)
          notify(`FinHub alert: ${e.symbol}`, e.text)
          setAlertsVersion((v) => v + 1)
        }
      }, () => {})
    poll()
    const t = setInterval(poll, 20_000)
    return () => clearInterval(t)
  }, [online])

  // Data-source health is cheap to fetch; keep it fresh while the backend is up.
  useEffect(() => {
    if (!online) return
    const load = () => api.sources().then(setSources, () => {})
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [online])

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

  useEffect(() => openExternalLinksInBrowser(), [])

  const closeReceipt = useCallback(() => setReceipt(null), [])

  function submit(text?: string) {
    const input = (text ?? command).trim()
    if (!input) return
    let result = runCommand(input)
    if (WEB_DEMO && !DEMO_COMMANDS.has(result.kind)) {
      result = { kind: 'error', message: `${input.split(/\s+/)[0].toUpperCase()} needs the desktop app (live data and the local engine). The web demo runs LEARN, OPT and SIM.` }
    }
    if (WEB_DEMO && result.kind === 'opt') result = { ...result, symbol: undefined } // no live quotes in the demo
    setHistory((h) => [input, ...h].slice(0, 100))
    setHistoryIndex(null)
    setCommand('')
    switch (result.kind) {
      case 'open':
        setWorkspace({ kind: 'home' })
        setActive(result.panel)
        break
      case 'home':
        setWorkspace({ kind: 'home' })
        break
      case 'ticker': {
        const range = result.range ?? (workspace.kind === 'ticker' ? workspace.range : '1Y')
        setWorkspace({ kind: 'ticker', symbol: result.symbol, range })
        break
      }
      case 'range':
        if (workspace.kind === 'ticker') setWorkspace({ ...workspace, range: result.range })
        else result = { kind: 'error', message: 'Open a ticker first, e.g. AAPL' }
        break
      case 'agent':
        setWorkspace({ kind: 'agent', ask: result.ask, text: result.text, nonce: Date.now() })
        break
      case 'ai':
        setWorkspace({ kind: 'ai' })
        break
      case 'sim':
        setWorkspace({ kind: 'sim' })
        break
      case 'notes':
        setWorkspace({ kind: 'notes', nonce: Date.now() })
        break
      case 'rcpt':
        setWorkspace({ kind: 'rcpt' })
        break
      case 'mcp':
        setWorkspace({ kind: 'mcp' })
        break
      case 'screen':
        setWorkspace({ kind: 'screen' })
        break
      case 'alerts':
        setWorkspace({ kind: 'alerts' })
        if (result.add) {
          const { symbol, kind, threshold } = result.add
          alertsApi.add(symbol, kind, threshold).then(() => setAlertsVersion((v) => v + 1), (e) => setLog((l) => [{ at: new Date(), input, message: `Alert not added: ${e.message}`, ok: false }, ...l]))
        }
        break
      case 'macro':
        setWorkspace({ kind: 'macro', country: result.country, nonce: Date.now() })
        break
      case 'portfolio':
        setWorkspace({ kind: 'portfolio' })
        if (result.add) {
          portfolioApi.add(result.add).then(() => setPortfolioVersion((v) => v + 1), (e) => {
            setFlash(`Not recorded: ${e.message}`)
            setLog((l) => [{ at: new Date(), input, message: `Not recorded: ${e.message}`, ok: false }, ...l])
          })
        }
        break
      case 'research':
        setWorkspace({ kind: 'research', view: result.view, nonce: Date.now() })
        break
      case 'learn':
        setWorkspace({ kind: 'learn' })
        break
      case 'arena':
        setWorkspace({ kind: 'arena' })
        break
      case 'cmp':
        setWorkspace({ kind: 'cmp', symbols: result.symbols, nonce: Date.now() })
        break
      case 'fa':
        setWorkspace({ kind: 'fa', symbol: result.symbol, nonce: Date.now() })
        break
      case 'watch': {
        setWorkspace({ kind: 'home' })
        setActive('WATCH')
        const { add, remove } = result
        if (add || remove) {
          watchApi.get().then(({ symbols }) =>
            watchApi.set(add ? [...symbols, add] : symbols.filter((x) => x !== remove)).then(() => setWatchVersion((v) => v + 1)),
          ).catch(() => {})
        }
        break
      }
      case 'risk':
        setWorkspace({ kind: 'risk', holdings: result.holdings, nonce: Date.now() })
        break
      case 'backtest':
        setWorkspace({ kind: 'backtest', preset: { symbol: result.symbol, strategy: result.strategy, params: result.params }, nonce: Date.now() })
        break
      case 'opt':
        setWorkspace({ kind: 'opt', symbol: result.symbol, nonce: Date.now() })
        break
      case 'refresh':
        checkHealth()
        loadEngines(true)
        setRefreshKey((k) => k + 1)
        break
    }
    // Not every workspace has an activity log, so command errors also show briefly as a banner.
    setFlash(result.kind === 'error' ? result.message : null)
    const entry: LogEntry = { at: new Date(), input, message: result.message, ok: result.kind !== 'error' }
    setLog((l) => (result.kind === 'clear' ? [] : [entry, ...l].slice(0, 200)))
  }

  const suggestions = suggest(command)
  const [focused, setFocused] = useState(false)

  function complete(name: string) {
    setCommand(`${name} `)
    inputRef.current?.focus()
  }

  function onCommandKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Tab' && suggestions.length) {
      e.preventDefault()
      complete(suggestions[0].name)
    } else if (e.key === 'Enter') submit()
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
  const failing = sources?.filter((s) => s.status === 'failing').length ?? 0

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <img src={`${import.meta.env.BASE_URL}finhub.svg`} alt="" width={20} height={20} />
          <span>FinHub</span>
        </div>
        <label className="command">
          <span className="command__prompt">&gt;</span>
          <input
            ref={inputRef}
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={onCommandKey}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 150)}
            placeholder={WEB_DEMO ? 'Try LEARN, OPT or SIM   (Ctrl+K)' : 'Ticker or command — AAPL, LEARN, BACKTEST, RISK, OPT, SIM, ASK …, AI, HELP   (Ctrl+K)'}
            spellCheck={false}
            autoComplete="off"
            autoFocus
            aria-label="Command"
          />
          {focused && suggestions.length > 0 && (
            <ul className="suggest" role="listbox">
              {suggestions.map((c, i) => (
                <li key={c.name} role="option" aria-selected={i === 0}>
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => complete(c.name)}>
                    <code>{c.name}</code>
                    <span className="muted">{c.description}</span>
                    <span className="suggest__eg">{c.usage}</span>
                  </button>
                </li>
              ))}
              <li className="suggest__hint muted">Tab completes the first suggestion</li>
            </ul>
          )}
        </label>
        <div className="clock" title="Local time · UTC">
          {now.toLocaleTimeString([], { hour12: false })}
          <span className="muted"> · {now.toISOString().slice(11, 19)} UTC</span>
        </div>
      </header>

      {!online && phase && phase.phase !== 'running' && (
        <div className={`banner ${phase.phase === 'failed' ? 'banner--bad' : ''}`} role="status">
          <strong>{phase.phase === 'failed' ? 'FinHub could not start its backend.' : 'Starting FinHub…'}</strong> {phase.detail}
          {phase.logs_dir && <span className="muted"> Logs: {phase.logs_dir}</span>}
        </div>
      )}
      {online && installs.openbb?.state === 'running' && (
        <div className="banner" role="status">
          <strong>Installing the market-data engine (OpenBB).</strong> This happens once and takes a few minutes; market
          data works as soon as it finishes. Progress is in SYS.
        </div>
      )}
      {flash && (
        <div className="banner banner--bad banner--flash" role="status" onClick={() => setFlash(null)}>
          {flash}
        </div>
      )}
      {toast && (
        <div className="banner banner--alert" role="alert">
          <strong>Alert:</strong> {toast.text}
          <button className="chip" onClick={() => setToast(null)}>Dismiss</button>
        </div>
      )}
      {workspace.kind === 'agent' ? (
        <AgentWorkspace
          key={workspace.nonce}
          kind={workspace.ask}
          text={workspace.text}
          onOpenSettings={() => setWorkspace({ kind: 'ai' })}
        />
      ) : workspace.kind === 'risk' ? (
        <RiskWorkspace key={workspace.nonce} initial={workspace.holdings} />
      ) : workspace.kind === 'backtest' ? (
        <BacktestWorkspace key={workspace.nonce} preset={workspace.preset} />
      ) : workspace.kind === 'opt' ? (
        <OptionsWorkspace key={workspace.nonce} symbol={workspace.symbol} />
      ) : workspace.kind === 'notes' ? (
        <NotesWorkspace key={workspace.nonce} onRerun={(cmd) => submit(cmd)} />
      ) : workspace.kind === 'screen' ? (
        <ScreenerWorkspace onOpen={(s) => submit(s)} onReceipt={setReceipt} />
      ) : workspace.kind === 'alerts' ? (
        <AlertsWorkspace version={alertsVersion} />
      ) : workspace.kind === 'macro' ? (
        <MacroWorkspace key={workspace.nonce} country={workspace.country} onReceipt={setReceipt} />
      ) : workspace.kind === 'portfolio' ? (
        <PortfolioWorkspace key={refreshKey} version={portfolioVersion} onReceipt={setReceipt} onOpen={(cmd) => submit(cmd)} />
      ) : workspace.kind === 'research' ? (
        <ResearchWorkspace key={`${workspace.nonce}-${refreshKey}`} view={workspace.view} onReceipt={setReceipt} onOpen={(cmd) => submit(cmd)} />
      ) : workspace.kind === 'learn' ? (
        <LearnWorkspace onRun={(cmd) => submit(cmd)} canRun={WEB_DEMO ? (cmd) => DEMO_COMMANDS.has(runCommand(cmd).kind) : undefined} />
      ) : workspace.kind === 'arena' ? (
        <ArenaWorkspace />
      ) : workspace.kind === 'cmp' ? (
        <CompareWorkspace key={workspace.nonce} symbols={workspace.symbols} />
      ) : workspace.kind === 'fa' ? (
        <FundamentalsWorkspace key={workspace.nonce} symbol={workspace.symbol} onReceipt={setReceipt} />
      ) : workspace.kind === 'mcp' ? (
        <main className="grid grid--single">
          <Panel code="MCP" title="Use FinHub from AI assistants" className="grid__single">
            <McpPanel />
          </Panel>
        </main>
      ) : workspace.kind === 'rcpt' ? (
        <main className="grid grid--single">
          <Panel code="RCPT" title="Receipts — where every number comes from" className="grid__single">
            <ReceiptPanel example={example} />
          </Panel>
        </main>
      ) : workspace.kind === 'sim' ? (
        <SimWorkspace />
      ) : workspace.kind === 'ai' ? (
        <main className="grid grid--single">
          <Panel code="AI" title="AI provider for ASK, BT and DEBATE" className="grid__single">
            <AgentSettingsPanel onSaved={() => {}} />
          </Panel>
        </main>
      ) : workspace.kind === 'ticker' ? (
        <TickerWorkspace
          key={`${workspace.symbol}-${refreshKey}`}
          symbol={workspace.symbol}
          range={workspace.range}
          onRange={(range) => setWorkspace({ ...workspace, range })}
          onReceipt={setReceipt}
          log={log}
        />
      ) : WEB_DEMO ? (
        <DemoHome onRun={(cmd) => submit(cmd)} />
      ) : (
        <main className="grid">
          <Panel code="SYS" title="System status" active={active === 'SYS'} className="grid__sys">
            <SystemPanel
              health={health} healthError={healthError} engines={engines} enginesLoading={enginesLoading}
              sources={sources} installs={installs} onInstall={startInstall}
            />
          </Panel>
          <Panel code="WATCH" title="Watchlist" active={active === 'WATCH'} className="grid__rcpt">
            <WatchPanel
              online={online}
              version={watchVersion}
              onReceipt={setReceipt}
              onOpen={(symbol) => submit(symbol)}
            />
          </Panel>
          <Panel code="HELP" title="Commands — click an example to run it" active={active === 'HELP'} className="grid__help">
            <HelpPanel onRun={(cmd) => submit(cmd)} />
          </Panel>
          <Panel code="LOG" title="Activity" active={active === 'LOG'} className="grid__log">
            <LogPanel entries={log} />
          </Panel>
        </main>
      )}

      <ReceiptDrawer receipt={receipt} onClose={closeReceipt} />

      <footer className="statusbar">
        {WEB_DEMO ? (
          <span className="ok">● web demo · runs in your browser</span>
        ) : (
          <span className={online ? 'ok' : 'bad'}>● {online ? 'backend online' : 'backend offline'}</span>
        )}
        {!WEB_DEMO && <span className="muted">engines {engines ? `${ready}/${engines.length} ready` : '—'}</span>}
        {!WEB_DEMO && <span className={failing ? 'warn' : 'muted'}>
          data sources {sources?.length ? `${sources.length - failing}/${sources.length} ok` : '—'}
        </span>}
        {workspace.kind === 'ticker' && <span className="muted">{workspace.symbol} · {workspace.range}</span>}
        <span className="muted statusbar__right">{WEB_DEMO ? '' : `${BACKEND_URL} · `}FinHub v0.4.0</span>
      </footer>
    </div>
  )
}
