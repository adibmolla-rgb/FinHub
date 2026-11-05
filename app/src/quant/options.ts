// Option pricing: three independent methods that should agree, plus Greeks and implied volatility.
//
// Conventions: S spot, K strike, T years to expiry, r continuously compounded risk-free rate,
// q continuous dividend yield, sigma annualised volatility. All rates and vols are fractions
// (0.05 = 5%), never percent; the UI converts at the edges.

export type OptionType = 'call' | 'put'

export type OptionInput = {
  type: OptionType
  S: number
  K: number
  T: number
  r: number
  q: number
  sigma: number
}

/** Standard normal CDF, accurate to ~1e-15 (Hart 1968 / West 2005 double-precision algorithm). */
export function normCdf(x: number): number {
  const z = Math.abs(x)
  let c: number
  if (z > 37) {
    c = 0
  } else {
    const e = Math.exp((-z * z) / 2)
    if (z < 7.07106781186547) {
      let n = 3.52624965998911e-2 * z + 0.700383064443688
      n = n * z + 6.37396220353165
      n = n * z + 33.912866078383
      n = n * z + 112.079291497871
      n = n * z + 221.213596169931
      n = n * z + 220.206867912376
      let d = 8.83883476483184e-2 * z + 1.75566716318264
      d = d * z + 16.064177579207
      d = d * z + 86.7807322029461
      d = d * z + 296.564248779674
      d = d * z + 637.333633378831
      d = d * z + 793.826512519948
      d = d * z + 440.413735824752
      c = (e * n) / d
    } else {
      let d = z + 0.65
      d = z + 4 / d
      d = z + 3 / d
      d = z + 2 / d
      d = z + 1 / d
      c = e / d / 2.506628274631
    }
  }
  return x > 0 ? 1 - c : c
}

export const normPdf = (x: number) => Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI)

export function validate(o: OptionInput): string | null {
  if (!(o.S > 0)) return 'Spot must be positive'
  if (!(o.K > 0)) return 'Strike must be positive'
  if (!(o.T > 0)) return 'Time to expiry must be positive'
  if (!(o.sigma > 0)) return 'Volatility must be positive'
  if (!Number.isFinite(o.r) || !Number.isFinite(o.q)) return 'Rates must be numbers'
  return null
}

function d1d2(o: OptionInput) {
  const vt = o.sigma * Math.sqrt(o.T)
  const d1 = (Math.log(o.S / o.K) + (o.r - o.q + 0.5 * o.sigma * o.sigma) * o.T) / vt
  return { d1, d2: d1 - vt }
}

/** Black–Scholes–Merton closed form (European). */
export function blackScholes(o: OptionInput): number {
  const { d1, d2 } = d1d2(o)
  const df = Math.exp(-o.r * o.T)
  const dq = Math.exp(-o.q * o.T)
  return o.type === 'call'
    ? o.S * dq * normCdf(d1) - o.K * df * normCdf(d2)
    : o.K * df * normCdf(-d2) - o.S * dq * normCdf(-d1)
}

export type Greeks = {
  delta: number // per 1.00 move in spot
  gamma: number // delta change per 1.00 move in spot
  vega: number // price change per 1 volatility point (0.01)
  theta: number // price change per calendar day
  rho: number // price change per 1 rate point (0.01)
}

export function greeks(o: OptionInput): Greeks {
  const { d1, d2 } = d1d2(o)
  const df = Math.exp(-o.r * o.T)
  const dq = Math.exp(-o.q * o.T)
  const sqT = Math.sqrt(o.T)
  const call = o.type === 'call'
  const delta = call ? dq * normCdf(d1) : dq * (normCdf(d1) - 1)
  const gamma = (dq * normPdf(d1)) / (o.S * o.sigma * sqT)
  const vega = (o.S * dq * normPdf(d1) * sqT) / 100
  const common = -(o.S * dq * normPdf(d1) * o.sigma) / (2 * sqT)
  const thetaYear = call
    ? common - o.r * o.K * df * normCdf(d2) + o.q * o.S * dq * normCdf(d1)
    : common + o.r * o.K * df * normCdf(-d2) - o.q * o.S * dq * normCdf(-d1)
  const rho = (call ? o.K * o.T * df * normCdf(d2) : -o.K * o.T * df * normCdf(-d2)) / 100
  return { delta, gamma, vega, theta: thetaYear / 365, rho }
}

/** Cox–Ross–Rubinstein binomial tree. Supports early exercise (American). */
export function binomial(o: OptionInput, steps = 500, american = false): number {
  const dt = o.T / steps
  const u = Math.exp(o.sigma * Math.sqrt(dt))
  const d = 1 / u
  const p = (Math.exp((o.r - o.q) * dt) - d) / (u - d)
  if (!(p > 0 && p < 1)) throw new Error('Binomial tree unstable for these inputs; increase steps')
  const disc = Math.exp(-o.r * dt)
  const payoff = (s: number) => (o.type === 'call' ? Math.max(s - o.K, 0) : Math.max(o.K - s, 0))
  const v = new Float64Array(steps + 1)
  for (let i = 0; i <= steps; i++) v[i] = payoff(o.S * u ** (steps - i) * d ** i)
  for (let n = steps - 1; n >= 0; n--) {
    for (let i = 0; i <= n; i++) {
      const cont = disc * (p * v[i] + (1 - p) * v[i + 1])
      v[i] = american ? Math.max(cont, payoff(o.S * u ** (n - i) * d ** i)) : cont
    }
  }
  return v[0]
}

/** Seeded PRNG (xorshift) so Monte Carlo results are reproducible. */
function rng(seed: number) {
  let s = seed >>> 0 || 1
  return () => {
    s ^= s << 13
    s ^= s >>> 17
    s ^= s << 5
    return (s >>> 0) / 4294967296
  }
}

/** Monte Carlo under GBM with antithetic variates. Returns the price and its standard error. */
export function monteCarlo(o: OptionInput, paths = 100_000, seed = 7): { price: number; stderr: number } {
  const rand = rng(seed)
  const drift = (o.r - o.q - 0.5 * o.sigma * o.sigma) * o.T
  const vol = o.sigma * Math.sqrt(o.T)
  const df = Math.exp(-o.r * o.T)
  const payoff = (s: number) => (o.type === 'call' ? Math.max(s - o.K, 0) : Math.max(o.K - s, 0))
  const pairs = Math.floor(paths / 2)
  let sum = 0
  let sumSq = 0
  for (let i = 0; i < pairs; i++) {
    const u1 = Math.max(rand(), 1e-12)
    const u2 = rand()
    const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
    // Antithetic pair: average of +z and -z paths is one (lower-variance) sample.
    const x = 0.5 * (payoff(o.S * Math.exp(drift + vol * z)) + payoff(o.S * Math.exp(drift - vol * z)))
    sum += x
    sumSq += x * x
  }
  const mean = sum / pairs
  const variance = Math.max(0, sumSq / pairs - mean * mean)
  return { price: df * mean, stderr: df * Math.sqrt(variance / pairs) }
}

/** No-arbitrage bounds for a European option price. */
export function bounds(o: Omit<OptionInput, 'sigma'>): { lower: number; upper: number } {
  const fwdS = o.S * Math.exp(-o.q * o.T)
  const pvK = o.K * Math.exp(-o.r * o.T)
  return o.type === 'call'
    ? { lower: Math.max(fwdS - pvK, 0), upper: fwdS }
    : { lower: Math.max(pvK - fwdS, 0), upper: pvK }
}

/**
 * Implied volatility from a market price: Newton's method with a bisection fallback.
 * Returns null when the price is outside no-arbitrage bounds (no volatility can produce it).
 */
export function impliedVol(price: number, o: Omit<OptionInput, 'sigma'>): number | null {
  const { lower, upper } = bounds(o)
  if (!(price > lower + 1e-12) || !(price < upper - 1e-12)) return null
  let lo = 1e-6
  let hi = 5
  let sigma = 0.3
  for (let i = 0; i < 100; i++) {
    const p = blackScholes({ ...o, sigma })
    const diff = p - price
    if (Math.abs(diff) < 1e-10) return sigma
    if (diff > 0) hi = sigma
    else lo = sigma
    const v = greeks({ ...o, sigma }).vega * 100
    let next = v > 1e-10 ? sigma - diff / v : NaN
    if (!(next > lo && next < hi)) next = (lo + hi) / 2 // Newton left the bracket: bisect instead
    sigma = next
  }
  return sigma
}

// ---------------------------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------------------------

export type Leg = { kind: 'call' | 'put' | 'stock'; strike: number; qty: number } // qty < 0 = short

export const STRATEGIES: Record<string, { label: string; legs: (S: number) => Leg[] }> = {
  long_call: { label: 'Long call', legs: (S) => [{ kind: 'call', strike: round(S), qty: 1 }] },
  long_put: { label: 'Long put', legs: (S) => [{ kind: 'put', strike: round(S), qty: 1 }] },
  covered_call: { label: 'Covered call', legs: (S) => [{ kind: 'stock', strike: 0, qty: 1 }, { kind: 'call', strike: round(S * 1.05), qty: -1 }] },
  protective_put: { label: 'Protective put', legs: (S) => [{ kind: 'stock', strike: 0, qty: 1 }, { kind: 'put', strike: round(S * 0.95), qty: 1 }] },
  bull_call: { label: 'Bull call spread', legs: (S) => [{ kind: 'call', strike: round(S), qty: 1 }, { kind: 'call', strike: round(S * 1.1), qty: -1 }] },
  bear_put: { label: 'Bear put spread', legs: (S) => [{ kind: 'put', strike: round(S), qty: 1 }, { kind: 'put', strike: round(S * 0.9), qty: -1 }] },
  straddle: { label: 'Long straddle', legs: (S) => [{ kind: 'call', strike: round(S), qty: 1 }, { kind: 'put', strike: round(S), qty: 1 }] },
  strangle: { label: 'Long strangle', legs: (S) => [{ kind: 'call', strike: round(S * 1.05), qty: 1 }, { kind: 'put', strike: round(S * 0.95), qty: 1 }] },
  iron_condor: {
    label: 'Iron condor',
    legs: (S) => [
      { kind: 'put', strike: round(S * 0.9), qty: 1 },
      { kind: 'put', strike: round(S * 0.95), qty: -1 },
      { kind: 'call', strike: round(S * 1.05), qty: -1 },
      { kind: 'call', strike: round(S * 1.1), qty: 1 },
    ],
  },
  butterfly: {
    label: 'Call butterfly',
    legs: (S) => [
      { kind: 'call', strike: round(S * 0.95), qty: 1 },
      { kind: 'call', strike: round(S), qty: -2 },
      { kind: 'call', strike: round(S * 1.05), qty: 1 },
    ],
  },
}

function round(x: number): number {
  const step = x >= 200 ? 5 : x >= 50 ? 1 : 0.5
  return Math.round(x / step) * step
}

type Market = Omit<OptionInput, 'type' | 'K'>

/** Value of the strategy now (Black–Scholes) and its cost to enter. */
export function legValue(leg: Leg, m: Market): number {
  if (leg.kind === 'stock') return m.S
  return blackScholes({ ...m, type: leg.kind, K: leg.strike })
}

export function strategyCost(legs: Leg[], m: Market): number {
  return legs.reduce((s, l) => s + l.qty * legValue(l, m), 0)
}

/** Profit at expiry for each spot price, net of the entry cost. */
export function payoffAtExpiry(legs: Leg[], entryCost: number, spot: number): number {
  let v = 0
  for (const l of legs) {
    const intrinsic = l.kind === 'stock' ? spot : l.kind === 'call' ? Math.max(spot - l.strike, 0) : Math.max(l.strike - spot, 0)
    v += l.qty * intrinsic
  }
  return v - entryCost
}

export function strategyGreeks(legs: Leg[], m: Market): Greeks {
  const out: Greeks = { delta: 0, gamma: 0, vega: 0, theta: 0, rho: 0 }
  for (const l of legs) {
    if (l.kind === 'stock') {
      out.delta += l.qty
      continue
    }
    const g = greeks({ ...m, type: l.kind, K: l.strike })
    for (const k of Object.keys(out) as (keyof Greeks)[]) out[k] += l.qty * g[k]
  }
  return out
}

/** Break-even spots at expiry, found where the payoff crosses zero on a fine grid. */
export function breakevens(legs: Leg[], entryCost: number, lo: number, hi: number, n = 4000): number[] {
  const out: number[] = []
  let prevX = lo
  let prevY = payoffAtExpiry(legs, entryCost, lo)
  for (let i = 1; i <= n; i++) {
    const x = lo + ((hi - lo) * i) / n
    const y = payoffAtExpiry(legs, entryCost, x)
    if ((prevY < 0 && y >= 0) || (prevY > 0 && y <= 0)) out.push(prevX + ((x - prevX) * Math.abs(prevY)) / (Math.abs(prevY) + Math.abs(y)))
    prevX = x
    prevY = y
  }
  return out
}
