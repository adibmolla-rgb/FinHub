import { describe, expect, it } from 'vitest'
import { align, correlation, stats } from './compare'

describe('compare', () => {
  it('aligns on dates every series shares', () => {
    const a = align([
      { symbol: 'A', dates: ['d1', 'd2', 'd3', 'd4'], closes: [1, 2, 3, 4] },
      { symbol: 'B', dates: ['d2', 'd3', 'd5'], closes: [20, 30, 50] },
    ])
    expect(a.dates).toEqual(['d2', 'd3'])
    expect(a.closes).toEqual({ A: [2, 3], B: [20, 30] })
  })

  it('stats: total return, drawdown and a flat series', () => {
    const s = stats([100, 120, 90, 110])
    expect(s.total).toBeCloseTo(0.1, 12)
    expect(s.maxDrawdown).toBeCloseTo(90 / 120 - 1, 12)
    expect(stats([5, 5, 5]).vol).toBe(0)
  })

  it('correlation is ±1 for proportional series and NaN without variation', () => {
    expect(correlation([1, 2, 3], [2, 4, 6])).toBeCloseTo(1, 12)
    expect(correlation([1, 2, 3], [3, 2, 1])).toBeCloseTo(-1, 12)
    expect(correlation([1, 1, 1], [1, 2, 3])).toBeNaN()
  })
})
