// SWARM: Vibe-Trading's teams of AI agents. A team runs on the AI provider set with the AI command and uses far
// more of it than ASK, so a command only fills in the form. Nothing starts until Start team is pressed.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { agentApi, ApiError, swarmApi, timeAgo, type AgentSettings, type SwarmPreset, type SwarmRun, type SwarmRunSummary } from './api'
import { Panel } from './components'

const FINISHED = ['completed', 'failed', 'cancelled']
const POLL_MS = 3000
const DEFAULT_TEAM = 'investment_committee'
const statusTone = (status: string) => (status === 'completed' ? 'ok' : status === 'failed' ? 'bad' : status === 'cancelled' ? 'muted' : 'warn')
const words = (name: string) => name.replace(/_/g, ' ')

function RunView({ runId, onChanged }: { runId: string; onChanged: () => void }) {
  const [run, setRun] = useState<SwarmRun | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cancelling, setCancelling] = useState(false)

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const load = () => {
      swarmApi.run(runId).then(
        (r) => {
          if (!live) return
          setRun(r)
          setError(null)
          if (FINISHED.includes(r.status)) onChanged()
          else timer = setTimeout(load, POLL_MS)
        },
        (e) => {
          if (!live) return
          setError(e.message)
          // A run that doesn't exist won't appear later. Anything else may be the agent restarting.
          if (!(e instanceof ApiError && e.status === 404)) timer = setTimeout(load, POLL_MS * 3)
        },
      )
    }
    load()
    return () => { live = false; clearTimeout(timer) }
  }, [runId, onChanged])

  function cancel() {
    setCancelling(true)
    swarmApi.cancel(runId).catch((e) => setError(e.message)).finally(() => setCancelling(false))
  }

  if (!run) return <Panel code="RUN" title="Team run" className="research-wide">{error ? <p className="bad">{error}</p> : <p className="muted">Loading the run…</p>}</Panel>
  const roles = new Map(run.agents.map((a) => [a.id, a.role]))
  const running = !FINISHED.includes(run.status)
  const done = run.tasks.filter((t) => t.status === 'completed').length
  const tokens = (run.total_input_tokens ?? 0) + (run.total_output_tokens ?? 0)
  return (
    <>
      <Panel code="RUN" title={`${words(run.preset_name)} · ${Object.values(run.user_vars).join(' · ')}`} className="research-wide">
        <div className="stack">
          <p>
            <span className={statusTone(run.status)}>{run.status}</span>
            <span className="muted"> · {done} of {run.tasks.length} agents finished · started {timeAgo(run.created_at)}{run.model ? ` · ${run.provider ?? ''} ${run.model}` : ''}{tokens > 0 ? ` · ${tokens.toLocaleString()} tokens` : ''}</span>
          </p>
          {run.is_stale && <p className="warn small">This run looks stuck: its agents have stopped reporting.</p>}
          {error && <p className="bad small">{error}</p>}
          {running && <div className="ticket"><button className="chip" onClick={cancel} disabled={cancelling}>{cancelling ? 'Cancelling…' : 'Cancel team'}</button><span className="muted small">Closing FinHub also stops it. You can leave this screen and come back from Recent runs.</span></div>}
          <ul className="stack swarm-tasks">
            {run.tasks.map((t) => (
              <li key={t.id} className={`trace__step trace__step--${t.status === 'completed' ? 'ok' : t.status === 'failed' ? 'failed' : t.status === 'in_progress' ? 'running' : ''}`}>
                <div className="trace__head">
                  <strong>{roles.get(t.agent_id) ?? words(t.agent_id)}</strong>
                  <span className={statusTone(t.status)}>{words(t.status)}</span>
                  {t.iterations > 0 && <span className="muted">{t.iterations} steps</span>}
                </div>
                {t.error && <p className="bad small">{t.error}</p>}
                {t.summary && <details><summary className="muted small">Read this agent’s summary</summary><div className="answer small">{t.summary}</div></details>}
              </li>
            ))}
          </ul>
        </div>
      </Panel>
      <Panel code="ANS" title="Team report" className="research-wide">
        {run.final_report
          ? <div className="answer">{run.final_report}</div>
          : <p className="muted">{running ? 'The final report appears here when the team finishes.' : 'This run ended without a final report.'}</p>}
        {run.final_report && <p className="muted small">AI-written research, not financial advice. Check its numbers and sources before relying on them.</p>}
      </Panel>
    </>
  )
}

export function SwarmWorkspace({ preset, value, onOpen }: { preset?: string; value?: string; onOpen: (command: string) => void }) {
  const [presets, setPresets] = useState<SwarmPreset[] | null>(null)
  const [settings, setSettings] = useState<AgentSettings | null>(null)
  const [loadError, setLoadError] = useState<ApiError | Error | null>(null)
  const [chosen, setChosen] = useState(preset ?? DEFAULT_TEAM)
  const [values, setValues] = useState<Record<string, string>>({})
  const [starting, setStarting] = useState(false)
  const startingNow = useRef(false) // state only changes on the next render, too late for a fast second click
  const [startError, setStartError] = useState<string | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [runs, setRuns] = useState<SwarmRunSummary[]>([])

  const refreshRuns = useCallback(() => { swarmApi.runs().then(setRuns, () => {}) }, [])
  // One team at a time: a team is expensive, and a second click shouldn't quietly start another.
  const active = runs.some((r) => !FINISHED.includes(r.status) && !r.is_stale)
  useEffect(() => {
    if (!active) return
    const timer = setInterval(refreshRuns, POLL_MS * 2)
    return () => clearInterval(timer)
  }, [active, refreshRuns])

  useEffect(() => {
    let live = true
    swarmApi.presets().then(
      (list) => {
        if (!live) return
        setPresets(list)
        refreshRuns()
        // The value typed after the team's name fills its first question.
        const first = list.find((p) => p.name === (preset ?? DEFAULT_TEAM))?.variables[0]
        if (value && first) setValues({ [first.name]: value })
      },
      (e) => { if (live) setLoadError(e) },
    )
    agentApi.settings().then((s) => { if (live) setSettings(s) }, () => {})
    return () => { live = false }
  }, [preset, value, refreshRuns])

  const team = useMemo(() => presets?.find((p) => p.name === chosen), [presets, chosen])
  const missing = team?.variables.filter((v) => v.required && !values[v.name]?.trim()) ?? []

  function start(e: React.FormEvent) {
    e.preventDefault()
    if (!team) return
    if (active || startingNow.current) return
    startingNow.current = true
    setStarting(true)
    setStartError(null)
    const answers = Object.fromEntries(team.variables.map((v) => [v.name, values[v.name] ?? '']))
    swarmApi.start(team.name, answers).then(
      (r) => { setRunId(r.id); refreshRuns() },
      (err) => setStartError(err.message),
    ).finally(() => { startingNow.current = false; setStarting(false) })
  }

  const needsSetup = loadError && /provider|not installed/i.test(loadError.message)
  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="SWARM" title="Teams of AI agents" className="research-wide">
        <div className="stack">
          {!presets && !loadError && <p className="muted">Starting the agent… (this can take up to a minute the first time)</p>}
          {loadError && <p className="bad">{loadError.message}</p>}
          {needsSetup && (
            <div className="ticket">
              {/provider/i.test(loadError.message) ? <button className="chip" onClick={() => onOpen('AI')}>Choose an AI provider</button> : <button className="chip" onClick={() => onOpen('SYS')}>Open SYS to install it</button>}
            </div>
          )}
          {preset && presets && !presets.some((p) => p.name === preset) && <p className="warn small">There’s no team called “{preset}”. Pick one below.</p>}
          {presets && (
            <form className="stack" onSubmit={start}>
              <div className="ticket">
                <select className="research-select" value={chosen} onChange={(e) => { setChosen(e.target.value); setValues({}); setStartError(null) }} aria-label="Team">
                  {!team && <option value={chosen}>Pick a team</option>}
                  {[...presets].sort((a, b) => a.title.localeCompare(b.title)).map((p) => <option key={p.name} value={p.name}>{p.title} ({p.agent_count} agents)</option>)}
                </select>
              </div>
              {team && (
                <>
                  <p className="muted small">{team.description}</p>
                  {team.variables.map((v) => (
                    <label key={v.name} className="stack swarm-field">
                      <span className="small">{words(v.name)}{v.required ? '' : ' (optional)'}</span>
                      <input className="research-input" value={values[v.name] ?? ''} onChange={(e) => setValues((all) => ({ ...all, [v.name]: e.target.value }))} placeholder={v.description} spellCheck={false} maxLength={500} />
                    </label>
                  ))}
                  <p className="warn small">
                    This runs {team.agent_count} agents one after another or side by side, and uses far more of your AI provider than ASK{settings?.provider === 'ollama' ? '. On a small local model it can take a very long time, and may fail' : ', so it costs more on a paid key'}.
                    {settings?.configured && <> Runs on {settings.providers[settings.provider]?.label} · {settings.model}.</>}
                  </p>
                  <div className="ticket">
                    <button className="chip chip--on" type="submit" disabled={starting || active || missing.length > 0}>{starting ? 'Starting…' : 'Start team'}</button>
                    {active && <span className="muted small">A team is already running. Wait for it to finish, or cancel it first.</span>}
                    {!active && missing.length > 0 && <span className="muted small">Fill in {missing.map((v) => words(v.name)).join(', ')} first.</span>}
                  </div>
                </>
              )}
              {startError && <p className="bad small">{startError}</p>}
            </form>
          )}
        </div>
      </Panel>
      {runId && <RunView key={runId} runId={runId} onChanged={refreshRuns} />}
      {runs.length > 0 && (
        <Panel code="RUNS" title="Recent runs" className="research-wide">
          <table className="table">
            <thead><tr><th>Team</th><th>Status</th><th className="num">Agents finished</th><th>Started</th><th /></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{words(r.preset_name)}</td>
                  <td className={statusTone(r.status)}>{r.status}</td>
                  <td className="num">{r.completed_count} / {r.task_count}</td>
                  <td className="muted">{timeAgo(r.created_at)}</td>
                  <td className="num"><button className="chip" onClick={() => setRunId(r.id)}>Open</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
    </main>
  )
}
