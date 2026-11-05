import { describe, expect, it } from 'vitest'
import { bollinger, ema, rebase, rsi, sma } from './indicators'

describe('indicators', () => {
  it('SMA leaves warm-up positions empty and averages the window', () => {
    expect(sma([1, 2, 3, 4, 5], 3)).toEqual([null, null, 2, 3, 4])
  })

  it('EMA is seeded with the SMA and then smooths with k = 2/(n+1)', () => {
    const out = ema([2, 4, 6, 8], 3)
    expect(out.slice(0, 2)).toEqual([null, null])
    expect(out[2]).toBeCloseTo(4, 12)
    expect(out[3]).toBeCloseTo(8 * 0.5 + 4 * 0.5, 12)
  })

  it('Bollinger bands use the population standard deviation', () => {
    const { mid, upper, lower } = bollinger([2, 4, 4, 4, 5, 5, 7, 9], 8, 2) // classic example: σ = 2
    expect(mid[7]).toBeCloseTo(5, 12)
    expect(upper[7]).toBeCloseTo(9, 12)
    expect(lower[7]).toBeCloseTo(1, 12)
  })

  it('RSI matches Wilder’s worked example', () => {
    // Closes from Wilder (1978) as reproduced in common references; RSI(14) on day 15 ≈ 70.53.
    const closes = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931, 46.0328, 45.614, 46.282, 46.282, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439]
    const out = rsi(closes, 14)
    expect(out[13]).toBeNull()
    expect(out[14]).toBeCloseTo(70.53, 1)
    expect(out[15]).toBeCloseTo(66.32, 1)
  })

  it('RSI is 100 for a series that only rises and 0 for one that only falls', () => {
    expect(rsi([1, 2, 3, 4, 5, 6], 3)[5]).toBe(100)
    expect(rsi([6, 5, 4, 3, 2, 1], 3)[5]).toBe(0)
  })

  it('rebase starts every series at 1', () => {
    expect(rebase([50, 55, 45])).toEqual([1, 1.1, 0.9])
  })
})
