import { describe, expect, it } from 'vitest'
import {
  binomial, blackScholes, bounds, breakevens, greeks, impliedVol, monteCarlo, normCdf,
  payoffAtExpiry, STRATEGIES, strategyCost, type OptionInput,
} from './options'

const base: OptionInput = { type: 'call', S: 100, K: 100, T: 1, r: 0.05, q: 0, sigma: 0.2 }

describe('normal CDF', () => {
  it('matches reference values', () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 15)
    expect(normCdf(1.96)).toBeCloseTo(0.9750021048517795, 12)
    expect(normCdf(-1)).toBeCloseTo(0.15865525393145707, 12)
    // Deep tail: check relative accuracy (absolute tolerance is meaningless at 1e-16).
    expect(Math.abs(normCdf(-8) / 6.22096057427178e-16 - 1)).toBeLessThan(1e-7)
  })
})

describe('Black–Scholes', () => {
  it('matches the textbook value (Hull: S=K=100, T=1, r=5%, σ=20% → call 10.4506)', () => {
    expect(blackScholes(base)).toBeCloseTo(10.450583572185565, 9)
    expect(blackScholes({ ...base, type: 'put' })).toBeCloseTo(5.573526022256971, 9)
  })

  it('satisfies put–call parity with dividends', () => {
    const o = { ...base, S: 112, K: 95, T: 0.6, r: 0.03, q: 0.02, sigma: 0.35 }
    const c = blackScholes(o)
    const p = blackScholes({ ...o, type: 'put' })
    expect(c - p).toBeCloseTo(o.S * Math.exp(-o.q * o.T) - o.K * Math.exp(-o.r * o.T), 10)
  })
})

describe('three methods agree', () => {
  for (const o of [base, { ...base, type: 'put' as const, K: 110, sigma: 0.3 }, { ...base, S: 50, K: 45, T: 0.25, q: 0.03 }]) {
    it(`${o.type} S=${o.S} K=${o.K}`, () => {
      const bs = blackScholes(o)
      expect(binomial(o, 1000)).toBeCloseTo(bs, 2)
      const mc = monteCarlo(o, 200_000)
      expect(Math.abs(mc.price - bs)).toBeLessThan(4 * mc.stderr) // within 4 standard errors
    })
  }

  it('American put is worth at least the European put, American call without dividends equals European', () => {
    const put = { ...base, type: 'put' as const, K: 110 }
    expect(binomial(put, 800, true)).toBeGreaterThan(binomial(put, 800, false) + 0.1)
    expect(binomial(base, 800, true)).toBeCloseTo(binomial(base, 800, false), 8)
  })
})

describe('Greeks', () => {
  it('match finite differences', () => {
    const g = greeks(base)
    const h = 1e-3
    const bump = (k: keyof OptionInput, d: number) => blackScholes({ ...base, [k]: (base[k] as number) + d })
    expect(g.delta).toBeCloseTo((bump('S', h) - bump('S', -h)) / (2 * h), 5)
    expect(g.gamma).toBeCloseTo((bump('S', h) - 2 * blackScholes(base) + bump('S', -h)) / (h * h), 3)
    expect(g.vega).toBeCloseTo((bump('sigma', h) - bump('sigma', -h)) / (2 * h) / 100, 6)
    expect(g.rho).toBeCloseTo((bump('r', h) - bump('r', -h)) / (2 * h) / 100, 5) // central-difference error ~1e-6 here
    expect(g.theta).toBeCloseTo(-(bump('T', h) - bump('T', -h)) / (2 * h) / 365, 6)
  })
})

describe('implied volatility', () => {
  it('recovers the volatility that produced a price', () => {
    for (const sigma of [0.05, 0.2, 0.8, 1.5]) {
      for (const type of ['call', 'put'] as const) {
        const o = { ...base, type, K: 90, sigma }
        expect(impliedVol(blackScholes(o), o)).toBeCloseTo(sigma, 6)
      }
    }
  })

  it('refuses prices outside no-arbitrage bounds', () => {
    const { lower, upper } = bounds(base)
    expect(impliedVol(lower - 0.01, base)).toBeNull()
    expect(impliedVol(upper + 0.01, base)).toBeNull()
  })
})

describe('strategies', () => {
  const m = { S: 100, T: 0.5, r: 0.04, q: 0, sigma: 0.25 }

  it('straddle profits on big moves either way and has two break-evens', () => {
    const legs = STRATEGIES.straddle.legs(100)
    const cost = strategyCost(legs, m)
    expect(payoffAtExpiry(legs, cost, 100)).toBeCloseTo(-cost, 10)
    const be = breakevens(legs, cost, 50, 150)
    expect(be).toHaveLength(2)
    expect(be[0]).toBeCloseTo(100 - cost, 2)
    expect(be[1]).toBeCloseTo(100 + cost, 2)
  })

  it('iron condor has capped loss equal to wing width minus credit', () => {
    const legs = STRATEGIES.iron_condor.legs(100)
    const cost = strategyCost(legs, m) // negative: a credit
    expect(cost).toBeLessThan(0)
    expect(payoffAtExpiry(legs, cost, 20)).toBeCloseTo(-(5 + cost), 10)
    expect(payoffAtExpiry(legs, cost, 200)).toBeCloseTo(-(5 + cost), 10)
  })
})
