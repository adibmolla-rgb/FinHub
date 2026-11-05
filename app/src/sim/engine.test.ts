import { describe, expect, it } from 'vitest'
import { OrderBook } from './engine'
import { Market, YOU } from './market'

describe('order book', () => {
  it('matches at the resting price with price-time priority', () => {
    const b = new OrderBook()
    b.limit('a', 'sell', 101, 50)
    b.limit('b', 'sell', 100, 30) // better price: fills first
    b.limit('c', 'sell', 100, 30) // same price, later: fills after b
    b.limit('x', 'buy', 101, 70)
    const fills = b.trades.map((t) => [t.seller, t.price, t.qty])
    expect(fills).toEqual([['b', 100, 30], ['c', 100, 30], ['a', 101, 10]])
    expect(b.depth().asks).toEqual([{ price: 101, qty: 40, orders: 1 }])
  })

  it('rests the unfilled remainder of a limit order', () => {
    const b = new OrderBook()
    b.limit('s', 'sell', 100, 10)
    const rest = b.limit('x', 'buy', 100, 25)
    expect(rest?.remaining).toBe(15)
    expect(b.bestBid()).toBe(100)
    expect(b.bestAsk()).toBeNull()
  })

  it('market orders sweep levels and report what was not filled', () => {
    const b = new OrderBook()
    b.limit('s', 'sell', 100, 10)
    b.limit('s', 'sell', 102, 10)
    expect(b.market('x', 'buy', 25)).toBe(5)
    expect(b.account('x')).toEqual({ cash: -(100 * 10 + 102 * 10), position: 20 })
  })

  it('cancels and cancelAll remove only the right orders', () => {
    const b = new OrderBook()
    const o = b.limit('a', 'buy', 99, 10)!
    b.limit('a', 'buy', 98, 10)
    b.limit('b', 'buy', 97, 10)
    expect(b.cancel(o.id)).toBe(true)
    expect(b.cancel(o.id)).toBe(false)
    expect(b.cancelAll('a')).toBe(1)
    expect(b.depth().bids.map((l) => l.price)).toEqual([97])
  })

  it('rejects nonsense orders', () => {
    const b = new OrderBook()
    expect(b.limit('a', 'buy', 0, 10)).toBeNull()
    expect(b.limit('a', 'buy', 100.5, 10)).toBeNull()
    expect(b.limit('a', 'buy', 100, 0)).toBeNull()
  })
})

describe('market simulation', () => {
  it('conserves cash and shares across all accounts', () => {
    const m = new Market(7)
    for (let i = 0; i < 500; i++) {
      m.tick()
      if (i === 100) m.trigger('crash')
      if (i === 200) m.trigger('drain')
      if (i % 50 === 0) m.you('buy', 50)
    }
    let cash = 0
    let pos = 0
    for (const a of m.book.accounts.values()) {
      cash += a.cash
      pos += a.position
    }
    expect(pos).toBe(0)
    expect(cash).toBe(0)
    expect(m.book.trades.length).toBeGreaterThan(100)
  })

  it('price discovery: after a crash or news the price returns to the true value instead of running away', () => {
    for (const scenario of ['crash', 'news-up', 'news-down', 'drain'] as const) {
      for (let seed = 1; seed <= 5; seed++) {
        const m = new Market(seed)
        for (let i = 0; i < 200; i++) m.tick()
        m.trigger(scenario)
        for (let i = 0; i < 600; i++) m.tick()
        const last = m.history[m.history.length - 1]
        const gap = Math.abs((last.mid ?? 0) - last.value) / last.value
        expect(gap, `${scenario} seed ${seed}: mid ${last.mid} vs value ${last.value}`).toBeLessThan(0.03)
      }
    }
  })

  it('without shocks the price tracks the true value', () => {
    for (let seed = 1; seed <= 10; seed++) {
      const m = new Market(seed)
      for (let i = 0; i < 2000; i++) m.tick()
      const last = m.history[m.history.length - 1]
      expect(Math.abs((last.mid ?? 0) - last.value) / last.value).toBeLessThan(0.03)
    }
  })

  it('is reproducible from a seed', () => {
    const run = () => {
      const m = new Market(123)
      for (let i = 0; i < 300; i++) m.tick()
      return m.history.map((h) => h.mid)
    }
    expect(run()).toEqual(run())
  })

  it('splits your P&L into spread earned and what happened after the trade', () => {
    const m = new Market(9)
    for (let i = 0; i < 50; i++) m.tick()
    m.you('buy', 100) // crossing the spread costs money immediately
    const b = m.yourBreakdown()
    expect(b.spread).toBeLessThan(0)
    expect(b.total).toBeCloseTo(b.spread + b.afterTrade, 8)
    expect(m.book.account(YOU).position).toBe(100)
  })

  it('the informed trader makes money on average and the market maker earns the spread from noise', () => {
    let informed = 0
    for (let seed = 1; seed <= 10; seed++) {
      const m = new Market(seed)
      for (let i = 0; i < 1500; i++) m.tick()
      informed += m.pnl('informed')
    }
    expect(informed).toBeGreaterThan(0)
  })
})

import { runCommand, suggest } from '../commands'

describe('command bar', () => {
  it('suggests commands by prefix and stops once arguments start', () => {
    expect(suggest('BA').map((c) => c.name)).toContain('BACKTEST')
    expect(suggest('BACKTEST SPY')).toEqual([])
    expect(suggest('')).toEqual([])
  })

  it('parses the main commands', () => {
    expect(runCommand('aapl')).toMatchObject({ kind: 'ticker', symbol: 'AAPL' })
    expect(runCommand('RISK SPY 60 TLT 40')).toMatchObject({ kind: 'risk', holdings: [{ symbol: 'SPY', weight: 60 }, { symbol: 'TLT', weight: 40 }] })
    expect(runCommand('BACKTEST QQQ momentum 126')).toMatchObject({ kind: 'backtest', symbol: 'QQQ', strategy: 'momentum', params: [126] })
    expect(runCommand('W -NVDA')).toMatchObject({ kind: 'watch', remove: 'NVDA' })
    expect(runCommand('WATCH NVDA')).toMatchObject({ kind: 'watch', add: 'NVDA' })
    expect(runCommand('CMP A')).toMatchObject({ kind: 'error' })
    expect(runCommand('OPT msft')).toMatchObject({ kind: 'opt', symbol: 'MSFT' })
    expect(runCommand('ASK what moved oil?')).toMatchObject({ kind: 'agent', ask: 'ask', text: 'what moved oil?' })
  })
})

describe('ALERT parsing', () => {
  it('reads price and move alerts and rejects ambiguous ones', () => {
    expect(runCommand('ALERT aapl > 200')).toMatchObject({ kind: 'alerts', add: { symbol: 'AAPL', kind: 'above', threshold: 200 } })
    expect(runCommand('ALERT AAPL<150.5')).toMatchObject({ add: { kind: 'below', threshold: 150.5 } })
    expect(runCommand('ALERT NVDA +5%')).toMatchObject({ add: { kind: 'move_up', threshold: 0.05 } })
    expect(runCommand('ALERT NVDA -2.5%')).toMatchObject({ add: { kind: 'move_down', threshold: 0.025 } })
    expect(runCommand('ALERT NVDA +5')).toMatchObject({ kind: 'error' })
    expect(runCommand('ALERT NVDA > 5%')).toMatchObject({ kind: 'error' })
    expect(runCommand('ALERTS')).toMatchObject({ kind: 'alerts' })
  })
})

describe('index tickers', () => {
  it('accepts a leading ^ (e.g. ^GSPC) but not ^ alone', () => {
    expect(runCommand('^gspc')).toMatchObject({ kind: 'ticker', symbol: '^GSPC' })
    expect(runCommand('W ^VIX')).toMatchObject({ kind: 'watch', add: '^VIX' })
    expect(runCommand('^')).toMatchObject({ kind: 'error' })
  })
})
