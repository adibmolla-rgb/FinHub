// Client for the local FinHub backend (backend/src/finhub_backend/server.py).

export const BACKEND_URL = import.meta.env.VITE_FINHUB_BACKEND_URL ?? 'http://127.0.0.1:8765'

export type Health = {
  status: string
  version: string
  python: string
  platform: string
}

export type EngineStatus = {
  id: string
  name: string
  role: string
  license: string
  homepage: string
  available: boolean
  version: string | null
  reason: string | null
}

export type Receipt = {
  label: string
  value: number
  unit: 'fraction' | 'percent' | 'bp' | 'currency' | 'shares' | 'ratio' | 'count' | 'as_reported'
  currency: string | null
  source: { provider: string; fetched_at: string; detail: string | null }
  formula: string | null
  inputs: Receipt[]
}

export type ReceiptExample = { note: string; receipt: Receipt }

export type Attempt = { provider: string; ok: boolean; error: string | null; ms: number | null }

type SourceMeta = {
  provider: string
  provider_name: string
  fetched_at: string
  attempts: Attempt[]
  fallback_used: boolean
}

export type QuoteKey =
  | 'price' | 'previous_close' | 'open' | 'day_high' | 'day_low' | 'volume'
  | 'market_cap' | 'year_high' | 'year_low' | 'change' | 'change_pct' | 'from_high_pct'

export type Quote = SourceMeta & {
  symbol: string
  currency: string | null
  exchange: string | null
  values: Partial<Record<QuoteKey, Receipt>>
}

export type Bar = { time: string | number; open: number; high: number; low: number; close: number; volume: number }
export type History = SourceMeta & { symbol: string; range: string; interval: string; adjusted: boolean; bars: Bar[] }

export type Profile = SourceMeta & {
  symbol: string
  name: string
  sector: string | null
  industry: string | null
  country: string | null
  website: string | null
  employees: number | null
  description: string | null
}

export type NewsItem = { title: string; url: string | null; published: string | null; source: string | null; summary: string | null }
export type News = SourceMeta & { symbol: string; items: NewsItem[] }

export type SourceHealth = {
  provider: string
  status: 'ok' | 'failing' | 'unknown'
  successes: number
  failures: number
  last_ok_at: string | null
  last_error_at: string | null
  last_error: string | null
  last_ms: number | null
  kinds: string[]
}

export const RANGES = ['1M', '3M', '6M', '1Y', '5Y', 'MAX'] as const
export type Range = (typeof RANGES)[number]

/** A failed request. For data requests, `attempts` lists every provider tried and why it failed. */
export class ApiError extends Error {
  status: number
  attempts: Attempt[]
  constructor(message: string, status: number, attempts: Attempt[] = []) {
    super(message)
    this.status = status
    this.attempts = attempts
  }
}

export type InstallState = {
  engine: string
  state: 'idle' | 'running' | 'done' | 'failed'
  started_at: number | null
  finished_at: number | null
  error: string | null
  log_tail: string[]
}

async function get<T>(path: string, timeoutMs = 4000, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, { signal: ctrl.signal, method })
    if (!res.ok) {
      let body: { error?: string; detail?: string; attempts?: Attempt[] } = {}
      try {
        body = await res.json()
      } catch {
        /* non-JSON error */
      }
      throw new ApiError(body.error ?? body.detail ?? `HTTP ${res.status}`, res.status, body.attempts ?? [])
    }
    return (await res.json()) as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw new ApiError(`timed out after ${timeoutMs / 1000}s`, 0)
    throw err
  } finally {
    clearTimeout(timer)
  }
}

const enc = encodeURIComponent
// Data calls may walk several providers, and the first one after launch waits for OpenBB to load.
const DATA_TIMEOUT = 120_000

export const api = {
  health: () => get<Health>('/health', 2000),
  // Engine probes start each engine's own interpreter, so allow them longer.
  engines: (refresh = false) => get<EngineStatus[]>(refresh ? '/engines?refresh=true' : '/engines', 120_000),
  receiptExample: () => get<ReceiptExample>('/examples/receipt'),
  quote: (s: string) => get<Quote>(`/market/quote/${enc(s)}`, DATA_TIMEOUT),
  history: (s: string, range: Range, adjusted = false) => get<History>(`/market/history/${enc(s)}?range=${range}${adjusted ? '&adjusted=true' : ''}`, DATA_TIMEOUT),
  profile: (s: string) => get<Profile>(`/market/profile/${enc(s)}`, DATA_TIMEOUT),
  news: (s: string) => get<News>(`/market/news/${enc(s)}?limit=20`, DATA_TIMEOUT),
  sources: () => get<SourceHealth[]>('/market/sources'),
  installEngine: (id: string) => get<InstallState>(`/engines/${enc(id)}/install`, 10_000, 'POST'),
  installStatus: (id: string) => get<InstallState>(`/engines/${enc(id)}/install`),
}

export function timeAgo(iso: string | null, now = Date.now()): string {
  if (!iso) return '—'
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return `${Math.round(s / 86400)}d ago`
}

export function compact(n: number): string {
  return Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 2 }).format(n)
}

export function formatValue(r: Pick<Receipt, 'value' | 'unit' | 'currency'>): string {
  switch (r.unit) {
    case 'fraction':
      return `${(r.value * 100).toFixed(2)}%`
    case 'percent':
      return `${r.value.toFixed(2)}%`
    case 'bp':
      return `${r.value.toFixed(0)} bp`
    case 'currency': {
      const n = Math.abs(r.value) >= 1e6 ? compact(r.value) : r.value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      return `${r.currency ?? ''} ${n}`.trim()
    }
    case 'shares':
      return compact(r.value)
    case 'as_reported':
      // Unit not declared by the provider: show the number exactly, never as a percent.
      return Math.abs(r.value) >= 1e5 ? compact(r.value) : r.value.toLocaleString(undefined, { maximumFractionDigits: 4 })
    default:
      return r.value.toLocaleString(undefined, { maximumFractionDigits: 4 })
  }
}

// ---------------------------------------------------------------------------------------------
// Reasoning agent
// ---------------------------------------------------------------------------------------------

export type AgentProvider = 'anthropic' | 'openai' | 'ollama'

export type AgentSettings = {
  provider: AgentProvider
  model: string
  ollama_url: string
  has_api_key: boolean
  api_key_hint: string
  configured: boolean
  providers: Record<AgentProvider, { label: string; default_model: string }>
}

export type AskKind = 'ask' | 'bt' | 'debate'
export type AskStarted = { session_id: string; prompt: string; kind: AskKind; text: string }
export type AgentMessage = { message_id: string; role: string; content: string; created_at: string }

async function send<T>(path: string, method: 'POST' | 'PUT', body: unknown, timeoutMs = 240_000): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      method,
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : data.detail ? JSON.stringify(data.detail) : undefined
      throw new ApiError(data.error ?? detail ?? `HTTP ${res.status}`, res.status, data.attempts ?? [])
    }
    return data as T
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw new ApiError(`timed out after ${timeoutMs / 1000}s`, 0)
    throw err
  } finally {
    clearTimeout(timer)
  }
}

export const agentApi = {
  settings: () => get<AgentSettings>('/agent/settings'),
  saveSettings: (update: Partial<{ provider: AgentProvider; model: string; api_key: string; ollama_url: string }>) =>
    send<AgentSettings>('/agent/settings', 'PUT', update, 15_000),
  // Starting the agent the first time can take a while (it launches Vibe-Trading).
  ask: (kind: AskKind, text: string) => send<AskStarted>('/agent/ask', 'POST', { kind, text }),
  messages: (id: string) => get<AgentMessage[]>(`/agent/sessions/${enc(id)}/messages`, 30_000),
  state: (id: string) => get<{ session_status: string; attempt: { status: string; error: string | null } | null }>(`/agent/sessions/${enc(id)}/state`, 15_000),
  cancel: (id: string) => send<unknown>(`/agent/sessions/${enc(id)}/cancel`, 'POST', {}, 15_000),
  eventsUrl: (id: string) => `${BACKEND_URL}/agent/sessions/${enc(id)}/events`,
}

// ---------------------------------------------------------------------------------------------
// Backtester
// ---------------------------------------------------------------------------------------------

export type StrategyInfo = { name: string; label: string; params: string[]; defaults: Record<string, number>; grid: Record<string, number[]> }

export type Metrics = {
  total_return: number; cagr: number; volatility: number; sharpe: number; sortino: number
  max_drawdown: number; calmar: number; days: number; years: number
  exposure?: number; trades?: number; turnover_per_year?: number
}

export type BacktestResult = {
  symbol: string
  strategy: string
  label: string
  params: Record<string, number>
  allow_short: boolean
  costs: { commission_bps: number; slippage_bps: number }
  fills: string
  period: { start: string; end: string; days: number }
  metrics: { strategy: Metrics; strategy_before_costs: Metrics; buy_hold: Metrics }
  causality_check: boolean
  walk_forward:
    | { available: false; reason: string; trials: number }
    | { available: true; trials: number; oos_start: string; out_of_sample: Metrics; surface: { params: Record<string, number>; sharpe: number }[]
        folds: { fold: number; params: Record<string, number>; in_sample_sharpe: number; out_of_sample_sharpe: number }[] }
  deflated_sharpe: { dsr: number; trials: number; sr0_annual: number; skew?: number; kurtosis?: number }
  warnings: string[]
  curve: { time: string; strategy: number; buy_hold: number; drawdown: number }[]
  data: { provider: string; fetched_at: string; adjusted: boolean; attempts: Attempt[]; bars: number }
}

export type BacktestRequest = {
  symbol: string; strategy: string; params: Record<string, number>; range: '1Y' | '5Y' | 'MAX'
  cost_bps: number; slippage_bps: number; allow_short: boolean
}

export const backtestApi = {
  strategies: () => get<StrategyInfo[]>('/backtest/strategies'),
  run: (req: BacktestRequest) => send<BacktestResult>('/backtest', 'POST', req, 180_000),
}

// ---------------------------------------------------------------------------------------------
// Portfolio risk
// ---------------------------------------------------------------------------------------------

export type RiskRequest = { holdings: { symbol: string; weight: number }[]; range: '1Y' | '5Y' | 'MAX'; confidence: number; value: number }
type VarEs = { var: number; es: number }
type PortStats = { weights: number[]; expected_return: number; volatility: number; sharpe: number; weight_sd?: number[] }
type Worst = { return: number; start: string; end: string }

export type RiskResult = {
  symbols: string[]
  weights: number[]
  period: { start: string; end: string; days: number }
  confidence: number
  value: number
  var: { historical: VarEs; parametric: VarEs; monte_carlo: VarEs }
  var_backtest: { available: false; reason: string } | { available: true; window: number; days: number; exceptions: number; expected: number; p_value: number; verdict: string }
  portfolio: { volatility: number; expected_return: number; max_drawdown: number; skew: number; kurtosis: number; worst_day: Worst; worst_week: Worst; worst_month: Worst }
  assets: { symbol: string; weight: number; volatility: number; expected_return: number; risk_contribution: number }[]
  correlation: number[][]
  optimisation: { current: PortStats; min_variance: PortStats; max_sharpe: PortStats }
  histogram: { counts: number[]; edges: number[] }
  warnings: string[]
  data: { symbol: string; provider: string; fetched_at: string; adjusted: boolean; bars: number }[]
}

export const riskApi = { run: (req: RiskRequest) => send<RiskResult>('/risk', 'POST', req, 240_000) }

// ---------------------------------------------------------------------------------------------
// Watchlist and saved research
// ---------------------------------------------------------------------------------------------

export type WatchQuote = { symbol: string; ok: true; quote: Quote } | { symbol: string; ok: false; error: string }
export type NoteSummary = { id: string; title: string; kind: AskKind; created_at: string; status: string; error: string | null; preview: string }
export type NoteStep = { id: string; tool: string; args: Record<string, unknown>; status: string; preview: string | null }
export type Note = NoteSummary & { prompt: string; answer: string; steps: NoteStep[] }

export const watchApi = {
  get: () => get<{ symbols: string[] }>('/watchlist'),
  set: (symbols: string[]) => send<{ symbols: string[] }>('/watchlist', 'PUT', { symbols }, 10_000),
  quotes: () => get<WatchQuote[]>('/watchlist/quotes', 180_000),
}

export const notesApi = {
  list: () => get<NoteSummary[]>('/notes', 15_000),
  get: (id: string) => get<Note>(`/notes/${enc(id)}`, 15_000),
}

// ---------------------------------------------------------------------------------------------
// Fundamentals
// ---------------------------------------------------------------------------------------------

export type Statement = SourceMeta & { statement: 'income' | 'balance' | 'cash'; period: string; periods: string[]; currency: string | null; rows: { field: string; values: (number | null)[] }[] }
export type Fundamentals = {
  symbol: string
  period: 'annual' | 'quarter'
  statements: Partial<Record<'income' | 'balance' | 'cash', Statement>>
  errors: Partial<Record<'income' | 'balance' | 'cash', { error: string; attempts: Attempt[] }>>
  ratios: Record<string, Receipt>
}
export const fundamentalsApi = {
  get: (s: string, period: 'annual' | 'quarter') => get<Fundamentals>(`/market/fundamentals/${enc(s)}?period=${period}`, DATA_TIMEOUT),
}

// ---------------------------------------------------------------------------------------------
// Macro
// ---------------------------------------------------------------------------------------------

export type MacroSeries = {
  series: string; label: string; unit_kind: 'fraction' | 'as_reported'; unit: string
  points: { date: string; value: number }[]; latest: Receipt; change_1y?: Receipt
}
export type MacroDashboard = { country: string; series: Record<string, MacroSeries>; errors: Record<string, string> }
export const macroApi = { get: (country: string) => get<MacroDashboard>(`/macro/${enc(country)}`, DATA_TIMEOUT) }

// ---------------------------------------------------------------------------------------------
// Price alerts
// ---------------------------------------------------------------------------------------------

export type AlertKind = 'above' | 'below' | 'move_up' | 'move_down'
export type Alert = { id: string; symbol: string; kind: AlertKind; threshold: number; active: boolean; created_at: string; description: string; triggered_at?: string; triggered_price?: number }
export type AlertEvent = { id: string; alert_id: string; at: string; symbol: string; text: string; provider?: string }

export const alertsApi = {
  list: () => get<{ alerts: Alert[]; events: AlertEvent[] }>('/alerts', 10_000),
  add: (symbol: string, kind: AlertKind, threshold: number) => send<Alert>('/alerts', 'POST', { symbol, kind, threshold }, 10_000),
  remove: async (id: string) => {
    const res = await fetch(`${BACKEND_URL}/alerts/${enc(id)}`, { method: 'DELETE' })
    if (!res.ok) throw new ApiError(`HTTP ${res.status}`, res.status)
  },
  checkNow: () => send<{ fired: AlertEvent[] }>('/alerts/check', 'POST', {}, 180_000),
}
