// ALPHA: Vibe-Trading's library of published signals, tested on the S&P 500. No AI model is involved. A test takes
// minutes, so it runs in the background and its result is saved. What could flatter a result is shown beside it.

import { useCallback, useEffect, useMemo, useState } from 'react'
import { alphaApi, timeAgo, type AlphaDetail, type AlphaFactorResult, type AlphaInfo, type AlphaRun, type AlphaRunSummary } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'

const THEMES = ['momentum', 'reversal', 'volume', 'volatility', 'quality', 'value', 'liquidity', 'microstructure', 'sentiment', 'growth', 'leverage']
const ZOO_LABELS: Record<string, string> = { academic: 'Academic papers', alpha101: 'Alpha101', fundamental: 'Fundamental', qlib158: 'Qlib158' }
const POLL_MS = 3000
const finished = (status: string) => ['done', 'error', 'lost'].includes(status)
const num = (v: number | null | undefined, digits = 4) => (v == null ? '—' : v.toFixed(digits))
const stages: Record<string, string> = { loading_data: 'Downloading about 500 stocks', computing: 'Computing' }

function runLabel(run: AlphaRunSummary, names: Map<string, string>): string {
  if (run.kind === 'factor') return names.get(run.request.alpha_id ?? '') ?? run.request.alpha_id ?? 'Signal'
  return run.kind === 'bench' ? `${ZOO_LABELS[run.request.zoo ?? ''] ?? run.request.zoo} library` : `${run.request.alpha_ids?.length ?? 0} signals`
}

function periods(): { value: string; label: string }[] {
  const year = new Date().getFullYear()
  return [[year - 2, 'Last 3 years'], [year - 4, 'Last 5 years'], [year - 9, 'Last 10 years']].map(([from, label]) => ({ value: `${from}-${year}`, label: String(label) }))
}

function FactorView({ data }: { data: AlphaFactorResult }) {
  const horizons = data.horizons.map((h) => h.horizon)
  return (
    <div className="stack">
      {data.meta.survivorship_bias && <p className="warn small">Survivorship bias: this tests today’s S&amp;P 500 members{data.meta.constituent_source_date ? ` (list from ${data.meta.constituent_source_date})` : ''}, so companies that later collapsed and left the index are missing. Results look better than they really were.</p>}
      {data.meta.degraded && <p className="warn small">The data for this test was incomplete.</p>}
      <p className="muted small">{data.start} to {data.end} · {data.stocks} stocks · split into {data.quantiles} groups each day, from the signal’s lowest ranks to its highest.</p>
      <h3 className="small">Does it predict, and over how long?</h3>
      <table className="table">
        <thead><tr><th>Holding period</th><th className="num">IC (average)</th><th className="num">t-statistic</th><th className="num">Days IC was positive</th><th className="num">Best minus worst group</th><th className="num">Alpha a year</th><th className="num">Beta</th></tr></thead>
        <tbody>
          {data.horizons.map((h) => (
            <tr key={h.horizon}>
              <td>{h.horizon}</td>
              <td className={`num ${(h.ic_mean ?? 0) < 0 ? 'bad' : ''}`}>{num(h.ic_mean)}</td>
              <td className="num">{num(h.ic_t, 2)}</td>
              <td className="num">{h.ic_positive == null ? '—' : `${(h.ic_positive * 100).toFixed(1)}%`}</td>
              <td className={`num ${(h.spread ?? 0) < 0 ? 'bad' : ''}`}>{h.spread == null ? '—' : `${(h.spread * 100).toFixed(3)}%`}</td>
              <td className={`num ${(h.annual_alpha ?? 0) < 0 ? 'bad' : ''}`}>{h.annual_alpha == null ? '—' : `${(h.annual_alpha * 100).toFixed(2)}%`}</td>
              <td className="num">{num(h.beta, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3 className="small">Average return of each group, relative to all stocks</h3>
      <table className="table">
        <thead><tr><th>Group</th>{horizons.map((h) => <th key={h} className="num">{h}</th>)}</tr></thead>
        <tbody>
          {data.by_quantile.map((q) => (
            <tr key={q.quantile}>
              <td>{q.quantile === 1 ? '1 (lowest)' : q.quantile === data.quantiles ? `${q.quantile} (highest)` : q.quantile}</td>
              {horizons.map((h) => <td key={h} className={`num ${(q[h] ?? 0) < 0 ? 'bad' : 'ok'}`}>{q[h] == null ? '—' : `${(q[h]! * 100).toFixed(3)}%`}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="small">A signal worth anything should climb steadily from group 1 to group {data.quantiles}. Each day, {data.turnover.top == null ? '—' : `${(data.turnover.top * 100).toFixed(1)}%`} of the top group changes, and its ranks repeat with a correlation of {num(data.turnover.rank_autocorrelation, 3)} from one day to the next. High turnover means high trading costs.</p>
      <p className="muted small">Group returns are for the whole holding period shown, before trading costs. Alpha here is flattered by the survivorship bias above and is a long-short paper figure, so don’t expect to earn it. Longer holding periods overlap from day to day, which makes their t-statistics look stronger than they are. Analysis by Alphalens. Prices from {data.meta.price_sources?.join(', ') ?? 'not stated'}.</p>
    </div>
  )
}

function RunView({ runId, names, onChanged }: { runId: string; names: Map<string, string>; onChanged: () => void }) {
  const [run, setRun] = useState<AlphaRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    let timer: ReturnType<typeof setTimeout>
    const load = () => {
      alphaApi.run(runId).then(
        (r) => {
          if (!live) return
          setRun(r)
          setError(null)
          if (finished(r.status)) onChanged()
          else timer = setTimeout(load, POLL_MS)
        },
        (e) => { if (live) setError(e.message) },
      )
    }
    load()
    return () => { live = false; clearTimeout(timer) }
  }, [runId, onChanged])

  if (!run) return <Panel code="TEST" title="Signal test" className="research-wide">{error ? <p className="bad">{error}</p> : <p className="muted">Loading the test…</p>}</Panel>
  const what = runLabel(run, names)
  const result = run.kind === 'factor' ? null : run.result
  const meta = result?.meta
  const stage = run.progress?.stage ? stages[run.progress.stage] ?? run.progress.stage : null
  return (
    <Panel code="TEST" title={`${what} · S&P 500 · ${run.request.period}`} className="research-wide">
      <div className="stack">
        {!finished(run.status) && (
          <p className="warn">
            Running{stage ? `: ${stage}` : ''}{run.progress?.n_total ? ` · ${run.progress.n_done} of ${run.progress.n_total} done` : ''}. This usually takes 5 to 10 minutes. You can leave this screen and come back, but closing FinHub stops it.
          </p>
        )}
        {run.error && <p className="bad">{run.error}</p>}
        {run.kind === 'factor' && run.result && <FactorView data={run.result as unknown as AlphaFactorResult} />}
        {result && (
          <>
            {meta?.survivorship_bias && <p className="warn small">Survivorship bias: this tests today’s S&amp;P 500 members{meta.constituent_source_date ? ` (list from ${meta.constituent_source_date})` : ''}, so companies that later collapsed and left the index are missing. Results look better than they really were.</p>}
            {meta?.degraded && <p className="warn small">The data for this test was incomplete.</p>}
            {(meta?.missing_instruments?.length ?? 0) > 0 && <p className="muted small">No prices for {meta!.missing_instruments!.length} of {meta!.requested_instruments} stocks ({meta!.missing_instruments!.slice(0, 6).join(', ')}{meta!.missing_instruments!.length > 6 ? ', …' : ''}).</p>}
            {result.n_alphas_tested != null && (
              <>
                <p>{result.n_alphas_tested} tested: <span className="ok">{result.alive ?? 0} still predictive</span>, {result.reversed ?? 0} reversed, {result.dead ?? 0} dead.</p>
                <p className="muted small">Still predictive means an average IC above 0.02, positive on at least 55% of days, and a t-statistic above 2. The best of many signals looks good by luck alone, so check a winner on a different period before believing it.</p>
                {result.by_theme && <p className="muted small">By theme: {Object.entries(result.by_theme).map(([name, t]) => `${name} ${t.alive} of ${t.count}`).join(' · ')}.</p>}
              </>
            )}
            <div className="ticket"><CopyCsvButton rows={() => [['id', 'ic_mean', 'ic_std', 'ir', 'ic_positive_ratio', 'ic_count'], ...result.rows.map((r) => [r.id, r.ic_mean, r.ic_std, r.ir, r.ic_positive_ratio, r.ic_count])]} /></div>
            {run.kind === 'bench' && <p className="muted small">A whole-library test only reports its best {result.rows.length}. To see every signal side by side, tick them and use Compare.</p>}
            <table className="table">
              <thead><tr><th>Signal</th><th className="num">IC (average)</th><th className="num">IR</th><th className="num">Days IC was positive</th><th className="num">Days</th></tr></thead>
              <tbody>
                {result.rows.slice(0, 50).map((r) => (
                  <tr key={r.id}>
                    <td>{names.get(r.id) ?? r.id}<div className="muted small">{r.id}</div></td>
                    <td className={`num ${(r.ic_mean ?? 0) < 0 ? 'bad' : ''}`}>{num(r.ic_mean)}</td>
                    <td className={`num ${(r.ir ?? 0) < 0 ? 'bad' : ''}`}>{num(r.ir, 3)}</td>
                    <td className="num">{r.ic_positive_ratio == null ? '—' : `${(r.ic_positive_ratio * 100).toFixed(1)}%`}</td>
                    <td className="num">{r.ic_count ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {result.rows.length > 50 && <p className="muted small">Showing the best 50 of {result.rows.length}. Copy CSV has them all.</p>}
            {(result.n_skipped ?? 0) > 0 && <p className="muted small">Skipped {result.n_skipped}{result.skipped.length > 0 ? `: ${result.skipped.slice(0, 3).map((s) => `${s.id} (${s.reason})`).join('; ')}${result.skipped.length > 3 ? '; …' : ''}` : ', usually for lack of data.'}</p>}
            <p className="muted small">IC is the correlation between a signal’s ranking of stocks and their next returns: 0.02 is a real but small edge, and 0.1 would be suspicious. IR is the average IC divided by how much it varies. These measure prediction before trading costs, not profit. Prices from {meta?.price_sources?.join(', ') ?? 'not stated'}.</p>
          </>
        )}
      </div>
    </Panel>
  )
}

export function AlphaWorkspace({ theme: initialTheme }: { theme?: string }) {
  const [alphas, setAlphas] = useState<AlphaInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [theme, setTheme] = useState(initialTheme ?? '')
  const [zoo, setZoo] = useState('academic')
  const [selected, setSelected] = useState<string[]>([])
  const [period, setPeriod] = useState(periods()[0].value)
  const [detail, setDetail] = useState<AlphaDetail | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)
  const [runs, setRuns] = useState<AlphaRunSummary[]>([])
  const [runId, setRunId] = useState<string | null>(null)

  const refreshRuns = useCallback(() => { alphaApi.runs().then(setRuns, () => {}) }, [])
  useEffect(() => {
    let live = true
    setAlphas(null)
    alphaApi.library(zoo, theme || undefined).then(
      (found) => { if (live) { setAlphas(found.alphas); setError(null) } },
      (e) => { if (live) setError(e.message) },
    )
    refreshRuns()
    return () => { live = false }
  }, [zoo, theme, refreshRuns])

  const active = runs.some((r) => !finished(r.status))
  useEffect(() => {
    if (!active) return
    const timer = setInterval(refreshRuns, POLL_MS * 2)
    return () => clearInterval(timer)
  }, [active, refreshRuns])

  const names = useMemo(() => new Map((alphas ?? []).map((a) => [a.id, a.nickname ?? a.id])), [alphas])

  function toggle(id: string) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
  }

  function start(call: Promise<{ id: string }>) {
    setStarting(true)
    setStartError(null)
    call.then((r) => { setRunId(r.id); refreshRuns() }, (e) => setStartError(e.message)).finally(() => setStarting(false))
  }

  function open(id: string) {
    alphaApi.detail(id).then(setDetail, (e) => setStartError(e.message))
  }

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="ALPHA" title="Signal library" className="research-wide">
        <div className="stack">
          <p className="muted small">281 published ways of predicting US stock returns, from academic papers to industry libraries. Test them on the S&amp;P 500 to see which still predict anything. This doesn’t use your AI provider.</p>
          {error && <p className="bad">{error}</p>}
          <div className="ticket">
            <select className="research-select" value={zoo} onChange={(e) => { setZoo(e.target.value); setSelected([]) }} aria-label="Library">
              {Object.entries(ZOO_LABELS).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
            <select className="research-select" value={theme} onChange={(e) => setTheme(e.target.value)} aria-label="Theme">
              <option value="">All themes</option>
              {THEMES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <select className="research-select" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period">
              {periods().map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
            <button className="chip chip--on" disabled={starting || active || selected.length < 2} onClick={() => start(alphaApi.compare(selected, period))}>Compare {selected.length || ''} selected</button>
            <button className="chip" disabled={starting || active} onClick={() => start(alphaApi.bench(zoo, period))}>Test the whole library</button>
            {alphas && alphas.length >= 2 && alphas.length <= 50 && <button className="chip" onClick={() => setSelected(alphas.map((a) => a.id))}>Tick all {alphas.length}</button>}
          </div>
          {active && <p className="muted small">A test is running. Wait for it to finish before starting another.</p>}
          {!active && selected.length < 2 && <p className="muted small">Tick at least 2 signals to compare them.</p>}
          {startError && <p className="bad small">{startError}</p>}
          {!alphas && !error && <p className="muted">Loading the library… (this can take up to a minute the first time)</p>}
          {alphas && (
            <table className="table">
              <thead><tr><th /><th>Signal</th><th>Theme</th><th /></tr></thead>
              <tbody>
                {alphas.map((a) => (
                  <tr key={a.id}>
                    <td><input type="checkbox" checked={selected.includes(a.id)} onChange={() => toggle(a.id)} aria-label={`Select ${a.id}`} /></td>
                    <td>{a.nickname ?? a.id}<div className="muted small">{a.id}</div></td>
                    <td className="muted">{a.theme?.join(', ')}</td>
                    <td className="num"><button className="chip" onClick={() => open(a.id)}>Details</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {alphas?.length === 0 && <p className="muted">No signals in this library match that theme.</p>}
        </div>
      </Panel>
      {detail && (
        <Panel code="SIGNAL" title={detail.meta?.nickname ?? detail.id} className="research-wide">
          <div className="stack">
            {detail.meta?.formula_latex && <p><code>{detail.meta.formula_latex}</code></p>}
            {detail.meta?.notes && <p className="small">{detail.meta.notes}</p>}
            <div className="ticket"><button className="chip chip--on" disabled={starting || active} onClick={() => start(alphaApi.factor(detail.id, period))}>Analyse this signal in depth</button></div>
            <p className="muted small">Needs {detail.meta?.min_warmup_bars ?? '?'} days of history. Typically fades over {detail.meta?.decay_horizon ?? '?'} days. {detail.id.startsWith('academic') ? 'Read its notes: some of these are price-only stand-ins for the original.' : ''}</p>
          </div>
        </Panel>
      )}
      {runId && <RunView key={runId} runId={runId} names={names} onChanged={refreshRuns} />}
      {runs.length > 0 && (
        <Panel code="RUNS" title="Saved tests" className="research-wide">
          <table className="table">
            <thead><tr><th>Test</th><th>Period</th><th>Status</th><th>Started</th><th /></tr></thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>{runLabel(r, names)}</td>
                  <td>{r.request.period}</td>
                  <td className={r.status === 'done' ? 'ok' : finished(r.status) ? 'bad' : 'warn'}>{r.status}</td>
                  <td className="muted">{timeAgo(r.started_at)}</td>
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
