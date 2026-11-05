import { useEffect, useRef, useState } from 'react'
import { agentApi, api, ApiError, type AgentProvider, type AgentSettings, type AskKind, type AskStarted } from './api'
import { Panel } from './components'

// ---------------------------------------------------------------------------------------------
// Event stream
// ---------------------------------------------------------------------------------------------

type Step = {
  id: string
  tool: string
  args: Record<string, unknown>
  status: 'running' | 'ok' | 'error' | string
  preview: string | null
  ms: number | null
}

type RunState = {
  status: 'starting' | 'running' | 'completed' | 'failed' | 'cancelled'
  answer: string
  steps: Step[]
  thinking: boolean
  error: string | null
  events: number
}

const initial: RunState = { status: 'starting', answer: '', steps: [], thinking: false, error: null, events: 0 }

type SseEvent = { type: string; data: Record<string, unknown> }

/** Read a server-sent-events stream with fetch, so every event name can be handled (EventSource can't). */
async function readSse(url: string, signal: AbortSignal, onEvent: (e: SseEvent) => void) {
  const res = await fetch(url, { signal, headers: { Accept: 'text/event-stream' } })
  if (!res.ok || !res.body) throw new Error(`event stream: HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true })
    let cut: number
    while ((cut = buffer.search(/\r?\n\r?\n/)) >= 0) {
      const frame = buffer.slice(0, cut)
      buffer = buffer.slice(cut).replace(/^\r?\n\r?\n/, '')
      let type = 'message'
      const data: string[] = []
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) type = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (!data.length) continue
      try {
        onEvent({ type, data: JSON.parse(data.join('\n')) })
      } catch {
        onEvent({ type, data: { raw: data.join('\n') } })
      }
    }
  }
}

function preview(value: unknown): string | null {
  if (value == null) return null
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return text.length > 600 ? `${text.slice(0, 600)}…` : text
}

function reduce(state: RunState, e: SseEvent): RunState {
  const d = e.data
  const next = { ...state, events: state.events + 1 }
  switch (e.type) {
    case 'attempt.started':
      return { ...next, status: 'running' }
    case 'thinking':
      return { ...next, thinking: true, status: 'running' }
    case 'thinking_done':
      return { ...next, thinking: false }
    case 'text_delta':
      return { ...next, thinking: false, status: 'running', answer: next.answer + String(d.delta ?? d.text ?? '') }
    case 'stream_reset':
      return { ...next, answer: '' }
    case 'tool_call': {
      const id = String(d.call_id ?? `${d.tool}-${state.steps.length}`)
      const args = (d.arguments ?? d.args ?? {}) as Record<string, unknown>
      return { ...next, status: 'running', steps: [...state.steps, { id, tool: String(d.tool ?? 'tool'), args, status: 'running', preview: null, ms: null }] }
    }
    case 'tool_result': {
      const id = String(d.call_id ?? '')
      const steps = [...state.steps]
      let i = steps.findIndex((s) => s.id === id && s.status === 'running')
      if (i < 0) i = steps.findIndex((s) => s.tool === d.tool && s.status === 'running')
      const update = {
        status: String(d.status ?? 'ok'),
        preview: preview(d.preview ?? d.result ?? d.output ?? d.error),
        ms: typeof d.elapsed_ms === 'number' ? d.elapsed_ms : null,
      }
      if (i >= 0) steps[i] = { ...steps[i], ...update }
      else steps.push({ id: id || String(steps.length), tool: String(d.tool ?? 'tool'), args: {}, ...update })
      return { ...next, steps }
    }
    case 'attempt.completed':
      return { ...next, status: 'completed', thinking: false }
    case 'attempt.failed':
      return { ...next, status: 'failed', thinking: false, error: String(d.error ?? d.reason ?? d.message ?? 'the agent run failed') }
    case 'attempt.cancelled':
      return { ...next, status: 'cancelled', thinking: false }
    case 'relay.error':
      return { ...next, status: 'failed', error: String(d.error) }
    default:
      return next
  }
}

function useAgentRun(started: AskStarted | null) {
  const [state, setState] = useState<RunState>(initial)
  useEffect(() => {
    if (!started) return
    setState(initial)
    const ctrl = new AbortController()
    readSse(agentApi.eventsUrl(started.session_id), ctrl.signal, (e) => setState((s) => reduce(s, e))).catch((err) => {
      if (!ctrl.signal.aborted) setState((s) => ({ ...s, status: s.status === 'completed' ? s.status : 'failed', error: String(err) }))
    })
    return () => ctrl.abort()
  }, [started])

  // The event stream only replays runs still in progress; poll the stored run state as a backstop so a
  // run that ends before (or without) us seeing its final event still shows its outcome.
  const finished = ['completed', 'failed', 'cancelled'].includes(state.status)
  useEffect(() => {
    if (!started || finished) return
    const t = setInterval(() => {
      agentApi.state(started.session_id).then((st) => {
        const a = st.attempt
        if (!a) return
        if (a.status === 'failed') setState((s) => ({ ...s, status: 'failed', thinking: false, error: a.error ?? 'the agent run failed' }))
        else if (a.status === 'completed') setState((s) => ({ ...s, status: 'completed', thinking: false }))
        else if (a.status === 'cancelled') setState((s) => ({ ...s, status: 'cancelled', thinking: false }))
      }, () => {})
    }, 3000)
    return () => clearInterval(t)
  }, [started, finished])

  // When the run ends, take the stored assistant message as the authoritative answer.
  const done = state.status === 'completed'
  useEffect(() => {
    if (!started || !done) return
    agentApi.messages(started.session_id).then(
      (msgs) => {
        const last = [...msgs].reverse().find((m) => m.role === 'assistant')
        if (last?.content) setState((s) => ({ ...s, answer: last.content }))
      },
      () => {},
    )
  }, [started, done])
  return state
}

// ---------------------------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------------------------

const KIND_LABEL: Record<AskKind, string> = { ask: 'Question', bt: 'Backtest', debate: 'Debate' }

export function AgentWorkspace({ kind, text, onOpenSettings }: { kind: AskKind; text: string; onOpenSettings: () => void }) {
  const [started, setStarted] = useState<AskStarted | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [installing, setInstalling] = useState(false)
  const run = useAgentRun(started)
  const [showPrompt, setShowPrompt] = useState(false)
  const startedAt = useRef(Date.now())

  useEffect(() => {
    let live = true
    startedAt.current = Date.now()
    agentApi.ask(kind, text).then(
      (s) => live && setStarted(s),
      (err) => live && setStartError(err instanceof ApiError ? err.message : String(err)),
    )
    return () => {
      live = false
    }
  }, [kind, text])

  const notInstalled = startError?.includes('not installed')
  const notConfigured = startError?.includes('no AI provider configured')
  const status = startError ? 'failed' : started ? run.status : 'starting'

  return (
    <main className="grid grid--agent">
      <section className="agent-head">
        <span className="panel__code">{kind.toUpperCase()}</span>
        <div className="agent-head__q">
          <span className="muted">{KIND_LABEL[kind]}</span>
          <strong>{text}</strong>
        </div>
        <span className={`agent-status agent-status--${status}`}>
          {status === 'starting' ? 'starting agent…' : status}
          {run.thinking && ' · thinking'}
        </span>
        {started && status === 'running' && (
          <button className="chip" onClick={() => agentApi.cancel(started.session_id).catch(() => {})}>Cancel</button>
        )}
        {started && (
          <button className="chip" onClick={() => setShowPrompt((v) => !v)}>{showPrompt ? 'Hide prompt' : 'Show prompt'}</button>
        )}
      </section>

      {showPrompt && started && <pre className="agent-prompt">{started.prompt}</pre>}

      {startError && (
        <section className="data-error agent-error">
          <p><span className="bad">The agent couldn’t start.</span> <span className="muted">{startError}</span></p>
          {notConfigured && <button className="chip chip--on" onClick={onOpenSettings}>Set up an AI provider</button>}
          {notInstalled && (
            <button
              className="chip chip--on"
              disabled={installing}
              onClick={() => {
                setInstalling(true)
                api.installEngine('vibe-trading').catch(() => {})
              }}
            >
              {installing ? 'Installing… (watch progress in SYS, then run the command again)' : 'Install the agent engine'}
            </button>
          )}
        </section>
      )}

      <Panel code="TRACE" title={`Reasoning trace · ${run.steps.length} step${run.steps.length === 1 ? '' : 's'}`} className="grid__trace">
        {!run.steps.length && <p className="muted">Each tool the agent uses (data fetches, code it runs, backtests) appears here with its inputs and result.</p>}
        <ol className="trace">
          {run.steps.map((s, i) => (
            <li key={s.id + i} className={`trace__step trace__step--${s.status}`}>
              <div className="trace__head">
                <span className="trace__n">{i + 1}</span>
                <code>{s.tool}</code>
                <span className="muted">{s.status}{s.ms != null ? ` · ${(s.ms / 1000).toFixed(1)}s` : ''}</span>
              </div>
              {Object.keys(s.args).length > 0 && <pre className="trace__args">{preview(s.args)}</pre>}
              {s.preview && <pre className="trace__result">{s.preview}</pre>}
            </li>
          ))}
        </ol>
      </Panel>

      <Panel code="ANS" title="Answer" className="grid__answer">
        {run.error && <p className="bad">{run.error}</p>}
        {run.error && /401|authentication|api[_ -]?key|x-api-key/i.test(run.error) && (
          <p>
            <span className="warn">The AI provider rejected the API key. </span>
            <button className="chip chip--on" onClick={onOpenSettings}>Check the key (AI)</button>
          </p>
        )}
        {run.error && /ollama|11434|connection refused/i.test(run.error) && (
          <p className="warn">Couldn’t reach the AI provider. For Ollama, make sure it is running and the model is pulled.</p>
        )}
        {!run.answer && !run.error && !startError && <p className="muted">The answer streams in here as the agent writes it.</p>}
        {run.answer && <div className="answer">{run.answer}</div>}
        {status === 'completed' && (
          <p className="muted small">
            Finished in {Math.round((Date.now() - startedAt.current) / 1000)}s. Research output from an AI agent, not financial advice; check the
            trace for the data and code behind each claim.
          </p>
        )}
      </Panel>
    </main>
  )
}

// ---------------------------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------------------------

export function AgentSettingsPanel({ onSaved }: { onSaved: (s: AgentSettings) => void }) {
  const [settings, setSettings] = useState<AgentSettings | null>(null)
  const [provider, setProvider] = useState<AgentProvider>('anthropic')
  const [model, setModel] = useState('')
  const [key, setKey] = useState('')
  const [ollamaUrl, setOllamaUrl] = useState('')
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    agentApi.settings().then((s) => {
      setSettings(s)
      setProvider(s.provider)
      setModel(s.model)
      setOllamaUrl(s.ollama_url)
    }, (e) => setMessage(String(e)))
  }, [])

  if (!settings) return <p className="muted">{message ?? 'Loading…'}</p>
  const needsKey = provider !== 'ollama'

  async function save() {
    try {
      const update: Parameters<typeof agentApi.saveSettings>[0] = { provider, model: model.trim(), ollama_url: ollamaUrl.trim() }
      if (key.trim()) update.api_key = key.trim()
      const s = await agentApi.saveSettings(update)
      setSettings(s)
      setKey('')
      setMessage(s.configured ? 'Saved. Try: ASK what drove NVDA over the last 3 months?' : 'Saved, but this provider still needs an API key.')
      onSaved(s)
    } catch (e) {
      setMessage(`Couldn’t save: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  return (
    <form className="settings" onSubmit={(e) => { e.preventDefault(); save() }}>
      <label>
        <span>Provider</span>
        <select
          value={provider}
          onChange={(e) => {
            const p = e.target.value as AgentProvider
            setProvider(p)
            setModel(settings.providers[p].default_model)
          }}
        >
          {(Object.keys(settings.providers) as AgentProvider[]).map((p) => (
            <option key={p} value={p}>{settings.providers[p].label}</option>
          ))}
        </select>
      </label>
      <label>
        <span>Model</span>
        <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={settings.providers[provider].default_model} spellCheck={false} />
      </label>
      {needsKey && (
        <label>
          <span>API key</span>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={settings.provider === provider && settings.has_api_key ? `saved (${settings.api_key_hint}) — leave blank to keep` : 'paste your key'}
            autoComplete="off"
          />
        </label>
      )}
      {provider === 'ollama' && (
        <label>
          <span>Ollama URL</span>
          <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} spellCheck={false} />
        </label>
      )}
      <div className="settings__actions">
        <button className="chip chip--on" type="submit">Save</button>
        {message && <span className="muted">{message}</span>}
      </div>
      <p className="muted small">
        The key is stored in FinHub’s data folder on this computer and is sent only to the provider you choose.
        {provider === 'ollama' && ' Ollama runs models locally for free: install it from ollama.com and run “ollama pull ' + (model || settings.providers.ollama.default_model) + '”.'}
      </p>
    </form>
  )
}
