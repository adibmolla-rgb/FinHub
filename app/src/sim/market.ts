// A simulated market: a hidden fundamental value, an order book, and bots with different strategies.
//
// The fundamental value moves as a random walk, with jumps when news arrives. Only the informed bot
// sees it. Everyone else sees prices. That gap is what makes market making hard: the market maker earns
// the spread from uninformed traders and loses it to informed ones (adverse selection).

import { OrderBook, type Side, type Trade } from './engine'

export const YOU = 'you'
const TICK = 0.01

/** Small deterministic PRNG so a seed reproduces a session exactly. */
export function rng(seed: number) {
  let s = seed >>> 0 || 1
  return () => {
    s ^= s << 13
    s ^= s >>> 17
    s ^= s << 5
    return (s >>> 0) / 4294967296
  }
}

export type BotKind = 'maker' | 'noise' | 'momentum' | 'meanrev' | 'informed'

export const BOT_INFO: Record<BotKind, { label: string; about: string }> = {
  maker: { label: 'Market maker', about: 'Quotes both sides around mid, skews quotes against its inventory' },
  noise: { label: 'Noise traders', about: 'Buy and sell at random: uninformed flow' },
  momentum: { label: 'Momentum', about: 'Buys after rises, sells after falls' },
  meanrev: { label: 'Mean reversion', about: 'Fades moves away from the recent average' },
  informed: { label: 'Informed trader', about: 'Knows the true value and trades when price is wrong' },
}

export type Scenario = 'news-up' | 'news-down' | 'crash' | 'drain'

export type YourFill = { step: number; side: Side; price: number; qty: number; mid: number }

export type Snapshot = {
  step: number
  value: number // fundamental, in price units (revealed to the player only after the fact)
  mid: number | null
  last: number | null
}

export class Market {
  readonly book = new OrderBook()
  readonly history: Snapshot[] = [] // price units, for display
  private mids: number[] = [] // ticks, for the bots (never mix the two)
  /** The market maker's fair-value estimate (ticks), learned from trade prices. */
  private makerFair: number
  private lastSeenTradeId = 0
  readonly yourFills: YourFill[] = []
  private rand: () => number
  value: number // ticks
  private sigma: number // per-step volatility of value, in ticks
  private makerPausedUntil = 0
  private informedBoostUntil = 0
  private crashUntil = 0
  /** Spread captured by you: for each fill, how much better than mid you traded. */
  spreadEarned = 0
  events: { step: number; text: string }[] = []

  constructor(seed = 42, startPrice = 100) {
    this.rand = rng(seed)
    this.value = Math.round(startPrice / TICK)
    this.sigma = 2.5
    this.makerFair = this.value
    this.book.onTrade = (t) => this.recordYourFill(t)
    for (const k of Object.keys(BOT_INFO)) this.book.account(k)
    this.book.account(YOU)
    // Seed the book so there is something to trade against from the start.
    this.quoteMaker()
  }

  private gauss(): number {
    // Box–Muller
    const u = Math.max(this.rand(), 1e-12)
    const v = this.rand()
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
  }

  private recordYourFill(t: Trade) {
    if (t.buyer !== YOU && t.seller !== YOU) return
    const side: Side = t.buyer === YOU ? 'buy' : 'sell'
    const mid = this.book.mid() ?? t.price
    this.yourFills.push({ step: t.step, side, price: t.price, qty: t.qty, mid })
    // Buying below mid or selling above mid earns spread; crossing the spread pays it.
    this.spreadEarned += (side === 'buy' ? mid - t.price : t.price - mid) * t.qty
  }

  // ---------------- bots ----------------

  private quoteMaker() {
    const b = this.book
    b.cancelAll('maker')
    if (b.step < this.makerPausedUntil) return
    // Learn fair value from recent trade prices. Anchoring on the last mid instead would feed the
    // maker's own skewed quotes back into its reference and make prices drift without limit.
    // Track by trade id, not array index: the trade log is trimmed, so indexes shift.
    for (const t of b.trades.slice(-200)) {
      if (t.id <= this.lastSeenTradeId) continue
      this.lastSeenTradeId = t.id
      this.makerFair += 0.05 * (t.price - this.makerFair)
      // Order flow carries information (Kyle's lambda): when someone keeps hitting the maker's quotes
      // in one direction, they probably know something, so the maker moves its fair value that way.
      if (t.buyer === 'maker' || t.seller === 'maker') {
        this.makerFair += 0.04 * (t.aggressor === 'buy' ? t.qty : -t.qty)
      }
    }
    const ref = this.makerFair
    const inv = b.account('maker').position
    const stressed = b.step < this.crashUntil
    // Inventory skew (Avellaneda–Stoikov in spirit): long inventory lowers both quotes to sell it off.
    // Capped, and applied on top of the fair estimate rather than compounding step after step.
    const skew = Math.max(-30, Math.min(30, -inv * 0.01))
    const half = (stressed ? 12 : 3) + Math.min(6, Math.abs(inv) * 0.004)
    const bid = Math.round(ref + skew - half)
    const ask = Math.max(bid + 1, Math.round(ref + skew + half))
    for (let lvl = 0; lvl < 5; lvl++) {
      const size = 100 + lvl * 60
      b.limit('maker', 'buy', bid - lvl * 2, size)
      b.limit('maker', 'sell', ask + lvl * 2, size)
    }
  }

  private noise() {
    if (this.rand() < 0.35) {
      const side: Side = this.rand() < 0.5 ? 'buy' : 'sell'
      this.book.market('noise', side, 10 + Math.floor(this.rand() * 60))
    }
    // Noise traders also post passive orders a few ticks away, which adds depth.
    if (this.rand() < 0.25) {
      const mid = this.book.mid()
      if (mid != null) {
        const side: Side = this.rand() < 0.5 ? 'buy' : 'sell'
        const off = 2 + Math.floor(this.rand() * 10)
        this.book.limit('noise', side, Math.round(side === 'buy' ? mid - off : mid + off), 20 + Math.floor(this.rand() * 40))
      }
    }
  }

  private trend(kind: 'momentum' | 'meanrev') {
    const h = this.mids
    if (h.length < 30) return
    const now = h[h.length - 1]
    const then = h[h.length - 20]
    const avg = h.slice(-30).reduce((s, x) => s + x, 0) / 30
    const pos = this.book.account(kind).position
    if (kind === 'momentum') {
      const move = now - then
      if (move > 6 && pos < 600 && this.rand() < 0.3) this.book.market(kind, 'buy', 40)
      if (move < -6 && pos > -600 && this.rand() < 0.3) this.book.market(kind, 'sell', 40)
    } else {
      const dev = now - avg
      if (dev > 8 && pos > -600 && this.rand() < 0.25) this.book.market(kind, 'sell', 40)
      if (dev < -8 && pos < 600 && this.rand() < 0.25) this.book.market(kind, 'buy', 40)
    }
  }

  private informed() {
    const b = this.book
    const bid = b.bestBid()
    const ask = b.bestAsk()
    const boosted = b.step < this.informedBoostUntil
    const pos = b.account('informed').position
    const limit = 3000 // constant: shrinking it after an event would strand the trader past its limit
    const act = boosted ? 0.8 : 0.2
    if (ask != null && this.value - ask > 4 && pos < limit && this.rand() < act) b.market('informed', 'buy', boosted ? 150 : 60)
    if (bid != null && bid - this.value > 4 && pos > -limit && this.rand() < act) b.market('informed', 'sell', boosted ? 150 : 60)
    // Take profit once the price has converged, which frees capacity for the next mispricing. Without
    // this an informed trader that hit its position limit would stop correcting the price.
    if (bid != null && ask != null && pos !== 0 && Math.abs((bid + ask) / 2 - this.value) <= 3 && this.rand() < 0.3) {
      b.market('informed', pos > 0 ? 'sell' : 'buy', Math.min(Math.abs(pos), 60))
    }
  }

  // ---------------- scenarios ----------------

  trigger(s: Scenario) {
    const step = this.book.step
    if (s === 'news-up' || s === 'news-down') {
      const jump = Math.round(this.value * 0.04) * (s === 'news-up' ? 1 : -1)
      this.value += jump
      this.makerFair += jump / 2 // the headline is public; the informed trader knows the rest
      this.informedBoostUntil = step + 60
      this.events.push({ step, text: `News: true value ${s === 'news-up' ? 'jumps' : 'drops'} 4%. Only the informed trader knows.` })
    } else if (s === 'crash') {
      const drop = Math.round(this.value * 0.08)
      this.value -= drop
      this.makerFair -= drop / 2 // everyone sees prices gapping down; only the informed knows how far
      this.informedBoostUntil = step + 120
      this.crashUntil = step + 120
      this.events.push({ step, text: 'Flash crash: value −8%, informed selling, market maker widens its quotes.' })
    } else if (s === 'drain') {
      this.makerPausedUntil = step + 80
      this.book.cancelAll('maker')
      this.events.push({ step, text: 'Liquidity drain: the market maker pulls all quotes for 80 steps.' })
    }
  }

  // ---------------- your orders ----------------

  you(side: Side, qty: number, price?: number) {
    if (price == null) return this.book.market(YOU, side, qty)
    this.book.limit(YOU, side, Math.round(price / TICK), qty)
    return 0
  }

  // ---------------- clock ----------------

  tick() {
    const b = this.book
    b.step += 1
    this.value = Math.max(100, Math.round(this.value + this.sigma * this.gauss()))
    this.quoteMaker()
    this.noise()
    this.trend('momentum')
    this.trend('meanrev')
    this.informed()
    const midTicks = b.mid()
    if (midTicks != null) this.mids.push(midTicks)
    if (this.mids.length > 4000) this.mids.splice(0, this.mids.length - 4000)
    const lastTrade = b.trades[b.trades.length - 1]
    this.history.push({
      step: b.step,
      value: this.value * TICK,
      mid: b.mid() != null ? b.mid()! * TICK : null,
      last: lastTrade ? lastTrade.price * TICK : null,
    })
    if (this.history.length > 4000) this.history.splice(0, this.history.length - 4000)
  }

  /** Mark-to-market P&L in price units, valued at mid. */
  pnl(owner: string): number {
    const a = this.book.account(owner)
    const mark = this.book.mid() ?? this.value
    return (a.cash + a.position * mark) * TICK
  }

  yourBreakdown() {
    const total = this.pnl(YOU)
    const spread = this.spreadEarned * TICK
    // Whatever is not spread came from the price moving after you traded: adverse selection when it
    // moved against you, a favourable move when it moved your way.
    return { total, spread, afterTrade: total - spread, position: this.book.account(YOU).position, fills: this.yourFills.length }
  }
}

export const toPrice = (ticks: number) => ticks * TICK
