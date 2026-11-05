// Technical indicators over a series of closes. Each output array has the same length as the input;
// positions without enough history are null (never a made-up value).

export function sma(x: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(x.length).fill(null)
  let sum = 0
  for (let i = 0; i < x.length; i++) {
    sum += x[i]
    if (i >= n) sum -= x[i - n]
    if (i >= n - 1) out[i] = sum / n
  }
  return out
}

/** Exponential moving average seeded with the SMA of the first n values (the usual convention). */
export function ema(x: number[], n: number): (number | null)[] {
  const out: (number | null)[] = new Array(x.length).fill(null)
  if (x.length < n) return out
  const k = 2 / (n + 1)
  let prev = x.slice(0, n).reduce((a, b) => a + b, 0) / n
  out[n - 1] = prev
  for (let i = n; i < x.length; i++) {
    prev = x[i] * k + prev * (1 - k)
    out[i] = prev
  }
  return out
}

/** Bollinger bands: SMA ± k population standard deviations over the same window. */
export function bollinger(x: number[], n = 20, k = 2) {
  const mid = sma(x, n)
  const upper: (number | null)[] = new Array(x.length).fill(null)
  const lower: (number | null)[] = new Array(x.length).fill(null)
  for (let i = n - 1; i < x.length; i++) {
    const m = mid[i]!
    let v = 0
    for (let j = i - n + 1; j <= i; j++) v += (x[j] - m) ** 2
    const sd = Math.sqrt(v / n)
    upper[i] = m + k * sd
    lower[i] = m - k * sd
  }
  return { mid, upper, lower }
}

/** Relative Strength Index with Wilder's smoothing (the standard definition). */
export function rsi(x: number[], n = 14): (number | null)[] {
  const out: (number | null)[] = new Array(x.length).fill(null)
  if (x.length <= n) return out
  let gain = 0
  let loss = 0
  for (let i = 1; i <= n; i++) {
    const d = x[i] - x[i - 1]
    gain += Math.max(d, 0)
    loss += Math.max(-d, 0)
  }
  gain /= n
  loss /= n
  const value = () => (loss === 0 ? (gain === 0 ? 50 : 100) : 100 - 100 / (1 + gain / loss))
  out[n] = value()
  for (let i = n + 1; i < x.length; i++) {
    const d = x[i] - x[i - 1]
    gain = (gain * (n - 1) + Math.max(d, 0)) / n
    loss = (loss * (n - 1) + Math.max(-d, 0)) / n
    out[i] = value()
  }
  return out
}

/** Growth of 1 from the first available close, for comparing several tickers on one scale. */
export function rebase(x: number[]): number[] {
  const first = x.find((v) => v > 0)
  return first ? x.map((v) => v / first) : x.map(() => NaN)
}
