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
  optional?: boolean
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

export type SourceMeta = {
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
  status: 'ok' | 'failing' | 'no data' | 'unknown'
  no_data: number
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

async function send<T>(path: string, method: 'POST' | 'PUT' | 'DELETE', body?: unknown, timeoutMs = 240_000): Promise<T> {
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
// Research panels (OWN, CHAIN, CAL, FILINGS, ETF, CURVE)
// ---------------------------------------------------------------------------------------------

export type InsiderRow = {
  date: string; filed: string | null; owner: string | null; title: string | null; type: string | null
  direction: string | null; security: string | null; shares: number; price: number | null
  shares_after: number | null; plan_10b5_1: boolean; url: string | null
}
export type InsiderSummary = {
  window_days: number; trades: number
  sold_shares: Receipt; sold_value: Receipt; bought_shares: Receipt; bought_value: Receipt; sold_on_plan?: Receipt
}
export type HolderRow = { owner: string; date: string | null; shares: number; change: number | null; change_pct: number | null }
export type ShortRow = { date: string; short: number; previous: number | null; avg_volume: number | null }
export type Ownership = {
  symbol: string
  errors: Record<string, string>
  insider?: SourceMeta & { rows: InsiderRow[]; summary: InsiderSummary | null }
  institutional?: SourceMeta & { rows: HolderRow[] }
  short?: SourceMeta & { rows: ShortRow[]; summary: { date: string; short: Receipt; change?: Receipt; days_to_cover?: Receipt } }
}

export type OptionContract = {
  strike: number; type: 'call' | 'put'; bid: number | null; ask: number | null; mid: number | null; last: number | null
  volume: number | null; open_interest: number | null; iv: number | null; delta: number | null
}
export type OptionsChain = SourceMeta & {
  symbol: string; expiration: string; expirations: string[]; iv_unit: 'fraction' | 'as_reported'
  summary: { underlying?: Receipt; atm_iv?: Receipt; put_call_volume?: Receipt; put_call_oi?: Receipt }
  rows: { strike: number; call: OptionContract | null; put: OptionContract | null }[]
  smile: { strike: number; call_iv: number | null; put_iv: number | null }[]
}

export type EarningsRow = {
  date: string; symbol: string; name: string | null; eps_consensus: number | null; eps_previous: number | null
  estimates: number | null; period: string | null; time: string | null; market_cap: number | null
}
export type EconomicRow = { date: string; country: string | null; event: string; actual: string | null; consensus: string | null; previous: string | null }
export type MarketCalendar = {
  days: number
  errors: Record<string, string>
  earnings?: SourceMeta & { total: number; rows: EarningsRow[] }
  economic?: SourceMeta & { rows: EconomicRow[] }
}

export type FilingRow = { date: string; form: string; description: string | null; items: string | null; accession: string | null; url: string | null }
export type Filings = SourceMeta & { symbol: string; rows: FilingRow[] }

export type EtfHoldings = SourceMeta & {
  symbol: string; listed: number; listed_weight?: Receipt
  rows: { symbol: string; name: string | null; weight: Receipt }[]
}

export type FactorStat = {
  key: string; label: string; description: string; months: number; latest: Receipt; last_12m?: Receipt
  annual_return: Receipt; annual_volatility: Receipt; t_stat: Receipt | null; curve: [string, number][]
}
export type Factors = SourceMeta & {
  region: string; region_label: string; regions: Record<string, string>; years: number; start: string; end: string; months: number; unit: string
  factors: FactorStat[]; rows: (Record<string, number | null> & { date: string })[]; warnings: string[]
}
export type CotSideKey = 'large_specs' | 'small_specs' | 'commercials'
export type CotOverview = SourceMeta & {
  view: 'overview'; report_date: string | null; sides: { key: CotSideKey; label: string }[]
  rows: { market: string; date: string | null; open_interest: number | null; sides: Record<CotSideKey, { score: number | null; change: number | null; share_of_oi: number | null; zone: string | null }> }[]
}
export type CotMarket = SourceMeta & {
  view: 'market'; query: string; market: string; contract: string | null; report_date: string; lookback_weeks: number | null; open_interest: Receipt
  sides: { key: CotSideKey; label: string; net: Receipt; share_of_oi: Receipt; zone: string | null; score?: Receipt; change_1w?: Receipt }[]
  matches: { name: string; category: string | null }[]
  history: ({ date: string } & Record<CotSideKey, number | null>)[]
}
export type FedConditions = {
  errors: Record<string, string>; real_rate?: Receipt
  rates?: SourceMeta & { unit: string; effr?: Receipt; target_lower?: Receipt; target_upper?: Receipt; sofr?: Receipt; sofr_minus_effr?: Receipt; series: [string, number, number | null, number | null, number | null][] }
  money?: SourceMeta & { unit: string; m1?: Receipt; m2?: Receipt; m2_growth?: Receipt; series: [string, number][] }
  expectations?: SourceMeta & { unit: string; cpi_1y?: Receipt; cpi_10y?: Receipt; series: [string, number | null, number | null][] }
}
export type YieldCurve = SourceMeta & {
  date: string; month_ago_date: string | null; year_ago_date: string | null
  unit_kind: 'fraction' | 'as_reported'; unit: string
  tenors: { tenor: string; years: number; latest: Receipt; month_ago: number | null; year_ago: number | null }[]
  spreads: { '10y_2y'?: Receipt; '10y_3m'?: Receipt }
}

export type PortfolioSide = 'buy' | 'sell' | 'split'
export type PortfolioTransaction = { id: string; symbol: string; side: PortfolioSide; quantity: number; price: number; fees: number; date: string }
export type PortfolioPosition = {
  symbol: string; currency: string | null; lots: number
  shares: Receipt; average_cost: Receipt; cost_basis: Receipt
  price?: Receipt; value?: Receipt; unrealized?: Receipt; unrealized_pct?: Receipt; day_change?: Receipt; weight?: Receipt; realized?: Receipt
}
export type PortfolioTotal = {
  currency: string | null; complete: boolean; missing: string[]
  cost_basis?: Receipt; value?: Receipt; unrealized?: Receipt; unrealized_pct?: Receipt; day_change?: Receipt; realized?: Receipt
}
export type Portfolio = {
  positions: PortfolioPosition[]
  closed: { symbol: string; currency: string | null; realized: Receipt | null }[]
  totals: PortfolioTotal[]
  warnings: string[]
  risk_holdings: { symbol: string; weight: number }[] | null
  transactions: PortfolioTransaction[]
}
export const portfolioApi = {
  get: () => get<Portfolio>('/portfolio', DATA_TIMEOUT),
  add: (t: { symbol: string; side: PortfolioSide; quantity: number; price?: number; fees?: number; date?: string }) => send<PortfolioTransaction>('/portfolio/transactions', 'POST', t),
  remove: (id: string) => send<{ deleted: string }>(`/portfolio/transactions/${enc(id)}`, 'DELETE'),
}

export const researchApi = {
  ownership: (symbol: string) => get<Ownership>(`/research/ownership/${enc(symbol)}`, DATA_TIMEOUT),
  options: (symbol: string, expiration?: string) =>
    get<OptionsChain>(`/research/options/${enc(symbol)}${expiration ? `?expiration=${enc(expiration)}` : ''}`, DATA_TIMEOUT),
  calendar: (days: number) => get<MarketCalendar>(`/research/calendar?days=${days}`, DATA_TIMEOUT),
  filings: (symbol: string) => get<Filings>(`/research/filings/${enc(symbol)}`, DATA_TIMEOUT),
  etf: (symbol: string) => get<EtfHoldings>(`/research/etf/${enc(symbol)}`, DATA_TIMEOUT),
  curve: () => get<YieldCurve>('/research/curve', DATA_TIMEOUT),
  factors: (region: string, years: number) => get<Factors>(`/research/factors?region=${enc(region)}&years=${years}`, DATA_TIMEOUT),
  cot: (market?: string) => get<CotOverview | CotMarket>(`/research/cot${market ? `?market=${enc(market)}` : ''}`, DATA_TIMEOUT),
  fed: () => get<FedConditions>('/research/fed', DATA_TIMEOUT),
}

export type SwarmPreset = { name: string; title: string; description: string; agent_count: number; variables: { name: string; description: string; required: boolean }[] }
export type SwarmRunSummary = { id: string; preset_name: string; status: string; is_stale: boolean; created_at: string; completed_at: string | null; task_count: number; completed_count: number }
export type SwarmTask = { id: string; agent_id: string; status: string; summary: string | null; iterations: number; error: string | null }
export type SwarmRun = {
  id: string; preset_name: string; status: string; is_stale: boolean; user_vars: Record<string, string>; created_at: string; completed_at: string | null
  agents: { id: string; role: string }[]; tasks: SwarmTask[]; final_report: string | null
  total_input_tokens: number | null; total_output_tokens: number | null; provider: string | null; model: string | null
}

export type FilingText = SourceMeta & { company: string; form: string; filed: string; accession: string; url: string | null; sections: { id: string; title: string; text: string }[] }
export const readApi = {
  identity: () => get<{ configured: boolean }>('/settings/sec-identity', 15_000),
  saveIdentity: (name: string, email: string) => send<{ configured: boolean }>('/settings/sec-identity', 'PUT', { name, email }, 15_000),
  filing: (symbol: string, form: string, accession?: string) => get<FilingText>(accession ? `/research/read?accession=${enc(accession)}` : `/research/read?symbol=${enc(symbol)}&form=${enc(form)}`, DATA_TIMEOUT),
}

export type OptimRow = { name: string; yours: boolean; annual_return: Receipt | null; annual_volatility: Receipt | null; sharpe: Receipt | null; max_drawdown: Receipt | null; weights: Record<string, number | null> }
export type OptimResult = { symbols: string[]; rows: OptimRow[]; problems: { name: string; error: string }[]; train_days: number; test_days: number; held_days: number; windows: number; start: string; end: string; warnings: string[] }
export type LabMetric = { key: string; label: string; unit: string; value: number; receipt: Receipt; benchmark?: Receipt | null }
export type LabReport = {
  label: string; benchmark_label: string | null; days: number; start: string; end: string; metrics: LabMetric[]; relative: LabMetric[]; warnings?: string[]
  monthly: (Record<string, number | null> & { year: number })[]
  drawdowns: { start: string; low: string; end: string; days: number; depth: number | null }[]
}
export type VolResult = {
  symbol: string; days: number; start: string; end: string; warnings: string[]
  current: Receipt | null; last_month: Receipt | null; sample: Receipt | null; long_run: Receipt | null
  persistence: number | null; half_life_days: number | null; alpha: number | null; beta: number | null
  forecasts: { days: number; annual_volatility: number; receipt: Receipt }[]
  check: { months: number; model_error: number | null; naive_error: number | null; average_miss: number | null; rows: { date: string; forecast: number | null; naive: number | null; realised: number | null }[] }
  series: [string, number | null][]
}
export type BondResult = {
  label: string; price_given: boolean; settlement: string; maturity: string; coupon: number; years: number
  clean_price: number; dirty_price: number; accrued: number; yield: number; macaulay_duration: number; modified_duration: number; convexity: number; dv01: number; fair_price: number | null
  yield_receipt: Receipt; modified_receipt: Receipt; convexity_receipt: Receipt; fair_receipt?: Receipt
  cashflows: { date: string; amount: number }[]; cashflow_count: number
}
export type MoodRow = { headline: string; label: 'positive' | 'neutral' | 'negative'; positive: number; neutral: number; negative: number; confidence: Receipt; url?: string; source?: string; published?: string }
export type MoodResult = { symbol: string; rows: MoodRow[]; counts: Record<'positive' | 'neutral' | 'negative', number>; model: string; news_provider?: string; fetched_at?: string }
export type FindRow = { symbol: string; name?: string; sector?: string; industry?: string; category_group?: string; category?: string; country?: string; exchange?: string; currency?: string; market_cap?: string }
export type FindResult = { kind: string; total: number; rows: FindRow[]; provider_name: string }
export type FindOptions = { countries: string[]; sectors: string[]; market_caps: string[]; etf_groups: string[] }
export const findApi = {
  search: (q: { kind: string; query: string; country: string; sector: string; market_cap: string }) => {
    const params = new URLSearchParams(Object.entries(q).filter(([, v]) => v))
    return get<FindResult>(`/find?${params}`, DATA_TIMEOUT)
  },
  options: () => get<FindOptions>('/find/options', DATA_TIMEOUT),
}
export type JobKind = 'agents' | 'qlib'
export type JobRun<T> = { id: string; kind: JobKind; status: 'running' | 'done' | 'error'; request: Record<string, unknown>; started_at: string; finished_at?: string; error: string | null; result: T | null }
export type AgentsResult = { symbol: string; date: string; rating: string | null; provider: string; model: string; sections: { key: string; title: string; text: string }[] }
export type QlibResult = {
  segments: Record<'train' | 'valid' | 'test', [string, string]>; stocks: number; left_out: string[]; price_provider: string; rounds_used: number; rounds_allowed: number
  test: { ic: Receipt; icir: Receipt | null; rank_ic: Receipt; ic_positive: Receipt; long_short_annual: Receipt; long_short_t: number | null; days: number }
  top_features: { name: string; score: number | null }[]; latest_day: string; highest: { symbol: string }[]; lowest: { symbol: string }[]; distinct_predictions: number
}
export const jobsApi = {
  list: <T,>(kind: JobKind) => get<JobRun<T>[]>(`/jobs?kind=${kind}`, 10_000),
  get: <T,>(id: string) => get<JobRun<T>>(`/jobs/${enc(id)}`, 10_000),
  agents: <T,>(symbol: string) => send<JobRun<T>>('/jobs/agents', 'POST', { symbol }, 30_000),
  qlib: <T,>() => send<JobRun<T>>('/jobs/qlib', 'POST', {}, 30_000),
}
export const labApi = {
  volatility: (symbol: string) => send<VolResult>('/lab/volatility', 'POST', { symbol }),
  bond: (coupon: number, years: number, price?: number) => send<BondResult>('/lab/bond', 'POST', { coupon, years, price: price ?? null }),
  mood: (symbol: string) => send<MoodResult>('/lab/mood', 'POST', { symbol }, 1_800_000), // the first use downloads the model
  optimise: (holdings: { symbol: string; weight: number }[], range: string) => send<OptimResult>('/lab/optimise', 'POST', { holdings, range }),
  report: (symbol: string, benchmark: string | undefined, range: string) => send<LabReport>('/lab/report', 'POST', { symbol, benchmark, range }),
  series: (label: string, dates: string[], equity: number[]) => send<LabReport>('/lab/report/series', 'POST', { label, dates, equity }),
  backtest: (request: BacktestRequest) => send<LabReport>('/lab/report/backtest', 'POST', request),
}

export type PaperSide = 'buy' | 'sell'
export type PaperAccountSummary = { id: string; label: string; currency: string; created_at: string; last_date: string | null; pending: number }
export type PaperOrder = { id: string; symbol: string; side: PaperSide; quantity: number; placed_at: string; fill_day: string }
export type PaperAccount = {
  id: string; label: string; currency: string; created_at: string; start_on: string; last_date: string | null; note: string | null; next_fill_day: string
  value?: Receipt; cash: Receipt; start: Receipt; profit?: Receipt; return?: Receipt; fees: Receipt
  positions: { symbol: string; shares: number; average_cost: number; price: Receipt | null; value: number | null; profit: number | null }[]
  orders: PaperOrder[]
  fills: { date: string; symbol: string; side: PaperSide; shares: number; price: number; fee: number }[]
  rejected: { date: string; symbol: string; side: PaperSide; shares: number; reason: string }[]
  nav: [string, number][]
}
// The first call starts the engine, which can take a while.
export const paperApi = {
  accounts: () => get<PaperAccountSummary[]>('/paper/accounts', 240_000),
  account: (id: string) => get<PaperAccount>(`/paper/accounts/${enc(id)}`, 240_000),
  create: (label: string, cash: number) => send<{ id: string }>('/paper/accounts', 'POST', { label, cash }),
  place: (id: string, symbol: string, side: PaperSide, quantity: number) => send<PaperOrder>(`/paper/accounts/${enc(id)}/orders`, 'POST', { symbol, side, quantity }),
  cancel: (orderId: string) => send<unknown>(`/paper/orders/${enc(orderId)}`, 'DELETE', undefined, 15_000),
}

export type AlphaInfo = { id: string; zoo: string; theme?: string[]; nickname?: string; decay_horizon?: number; min_warmup_bars?: number }
export type AlphaDetail = { id: string; zoo: string; meta?: { nickname?: string; formula_latex?: string; notes?: string; decay_horizon?: number; min_warmup_bars?: number } }
export type AlphaRunSummary = {
  id: string; kind: 'compare' | 'bench' | 'factor'; status: string; started_at: string; finished_at?: string; error: string | null
  request: { period: string; zoo?: string; alpha_ids?: string[]; alpha_id?: string }
  progress: { n_done?: number; n_total?: number; stage?: string; current_alpha_id?: string | null } | null
}
export type AlphaFactorResult = {
  alpha_id: string; period: string; quantiles: number; observations: number; stocks: number; start: string; end: string
  horizons: { horizon: string; ic_mean: number | null; ic_std: number | null; ic_t: number | null; ic_positive: number | null; days: number; spread: number | null; annual_alpha: number | null; beta: number | null }[]
  by_quantile: (Record<string, number | null> & { quantile: number })[]
  turnover: { top: number | null; bottom: number | null; rank_autocorrelation: number | null }
  meta: { survivorship_bias?: boolean; constituent_source_date?: string; missing_instruments?: string[]; requested_instruments?: number; price_sources?: string[]; degraded?: boolean }
}
export type AlphaRun = AlphaRunSummary & {
  factor?: never
  result: {
    rows: { id: string; ic_mean: number | null; ic_std: number | null; ir: number | null; ic_positive_ratio: number | null; ic_count: number | null; theme?: string[] }[]
    skipped: { id: string; reason: string }[]
    meta: { survivorship_bias?: boolean; constituent_source_date?: string; requested_instruments?: number; fetched_instruments?: number; missing_instruments?: string[]; price_sources?: string[]; degraded?: boolean }
    n_skipped?: number; alive?: number; reversed?: number; dead?: number; n_alphas_tested?: number
    by_theme?: Record<string, { alive: number; reversed: number; dead: number; count: number }>
  } | null
}
export const alphaApi = {
  library: (zoo: string, theme?: string) => get<{ alphas: AlphaInfo[]; total: number }>(`/alpha/library?zoo=${enc(zoo)}${theme ? `&theme=${enc(theme)}` : ''}`, 240_000),
  detail: (id: string) => get<AlphaDetail>(`/alpha/library/${enc(id)}`, 60_000),
  runs: () => get<AlphaRunSummary[]>('/alpha/runs', 15_000),
  run: (id: string) => get<AlphaRun>(`/alpha/runs/${enc(id)}`, 15_000),
  compare: (alpha_ids: string[], period: string) => send<{ id: string }>('/alpha/compare', 'POST', { alpha_ids, period }),
  bench: (zoo: string, period: string) => send<{ id: string }>('/alpha/bench', 'POST', { zoo, period }),
  factor: (alpha_id: string, period: string) => send<{ id: string }>('/alpha/factor', 'POST', { alpha_id, period }),
}

// The first call starts the agent, which can take a while.
export const swarmApi = {
  presets: () => get<SwarmPreset[]>('/agent/swarm/presets', 240_000),
  runs: () => get<SwarmRunSummary[]>('/agent/swarm/runs', 30_000),
  run: (id: string) => get<SwarmRun>(`/agent/swarm/runs/${enc(id)}`, 30_000),
  start: (preset: string, variables: Record<string, string>) => send<{ id: string; status: string }>('/agent/swarm/runs', 'POST', { preset, variables }),
  cancel: (id: string) => send<unknown>(`/agent/swarm/runs/${enc(id)}/cancel`, 'POST', {}, 15_000),
}

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

// ---------------------------------------------------------------------------------------------
// Screener
// ---------------------------------------------------------------------------------------------

export type ScreenRow = {
  symbol: string; sector: string | null; price: number | null; change_pct: number | null; market_cap: number | null
  volume: number | null; from_high_pct: number | null; from_low_pct: number | null; currency: string | null; provider: string
  receipts: Partial<Record<'price' | 'change_pct' | 'market_cap' | 'from_high_pct', Receipt>>
}
export type ScreenRequest = {
  universe: 'large_caps' | 'watchlist' | 'custom'; symbols?: string[]
  min_price?: number; max_price?: number; min_change?: number; max_change?: number
  min_market_cap?: number; max_from_high?: number; min_from_low?: number; sectors: string[]
}
export type ScreenResult = { universe: string; size: number; quoted: number; failed: { symbol: string; error: string }[]; matches: ScreenRow[]; sectors: string[] }
export const screenApi = { run: (req: ScreenRequest) => send<ScreenResult>('/screen', 'POST', req, 240_000) }
