// Comparison statistics for several price series aligned on common dates.

export type SeriesIn = { symbol: string; dates: string[]; closes: number[] }
export type Aligned = { dates: string[]; closes: Record<string, number[]> }

/** Keep only dates every series has, so returns are compared over identical days. */
export function align(series: SeriesIn[]): Aligned {
  const maps = series.map((s) => new Map(s.dates.map((d, i) => [d, s.closes[i]])))
  const dates = series.length ? series[0].dates.filter((d) => maps.every((m) => m.has(d))) : []
  return { dates, closes: Object.fromEntries(series.map((s, k) => [s.symbol, dates.map((d) => maps[k].get(d)!)])) }
}

export function returns(closes: number[]): number[] {
  const r: number[] = []
  for (let i = 1; i < closes.length; i++) r.push(closes[i] / closes[i - 1] - 1)
  return r
}

const mean = (x: number[]) => x.reduce((a, b) => a + b, 0) / (x.length || 1)
const sd = (x: number[]) => {
  const m = mean(x)
  return Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, x.length - 1))
}

export function stats(closes: number[]) {
  const r = returns(closes)
  const years = r.length / 252
  const total = closes[closes.length - 1] / closes[0] - 1
  let peak = closes[0]
  let mdd = 0
  for (const c of closes) {
    peak = Math.max(peak, c)
    mdd = Math.min(mdd, c / peak - 1)
  }
  const vol = sd(r) * Math.sqrt(252)
  return {
    total,
    cagr: years > 0 ? (1 + total) ** (1 / years) - 1 : NaN,
    vol,
    sharpe: vol > 0 ? (mean(r) * 252) / vol : 0,
    maxDrawdown: mdd,
  }
}

export function correlation(a: number[], b: number[]): number {
  const ma = mean(a)
  const mb = mean(b)
  let num = 0
  let da = 0
  let db = 0
  for (let i = 0; i < a.length; i++) {
    num += (a[i] - ma) * (b[i] - mb)
    da += (a[i] - ma) ** 2
    db += (b[i] - mb) ** 2
  }
  return da > 0 && db > 0 ? num / Math.sqrt(da * db) : NaN
}
