// Limit order book with price-time priority.
//
// Prices are integer ticks (1 tick = 0.01) so there is no floating-point drift in matching or cash.
// Every trade moves cash and position between exactly two accounts, so the sums of all positions and
// of all cash changes are always zero; the tests check that.

export type Side = 'buy' | 'sell'

export type Order = {
  id: number
  owner: string
  side: Side
  price: number // ticks
  qty: number
  remaining: number
  seq: number // arrival order, for time priority
}

export type Trade = {
  id: number
  price: number
  qty: number
  buyer: string
  seller: string
  aggressor: Side
  step: number
}

export type Account = { cash: number; position: number } // cash in ticks

export type Level = { price: number; qty: number; orders: number }

export class OrderBook {
  private bids: Order[] = [] // best (highest) first, then earliest
  private asks: Order[] = [] // best (lowest) first, then earliest
  private byId = new Map<number, Order>()
  private nextId = 1
  private nextSeq = 1
  private nextTrade = 1
  step = 0
  readonly accounts = new Map<string, Account>()
  readonly trades: Trade[] = []
  onTrade?: (t: Trade) => void

  account(owner: string): Account {
    let a = this.accounts.get(owner)
    if (!a) {
      a = { cash: 0, position: 0 }
      this.accounts.set(owner, a)
    }
    return a
  }

  bestBid(): number | null {
    return this.bids[0]?.price ?? null
  }

  bestAsk(): number | null {
    return this.asks[0]?.price ?? null
  }

  mid(): number | null {
    const b = this.bestBid()
    const a = this.bestAsk()
    if (b == null || a == null) return b ?? a ?? null
    return (a + b) / 2
  }

  /** Aggregated depth: up to `n` price levels per side, best first. */
  depth(n = 10): { bids: Level[]; asks: Level[] } {
    const agg = (orders: Order[]) => {
      const levels: Level[] = []
      for (const o of orders) {
        const last = levels[levels.length - 1]
        if (last && last.price === o.price) {
          last.qty += o.remaining
          last.orders += 1
        } else {
          if (levels.length === n) break
          levels.push({ price: o.price, qty: o.remaining, orders: 1 })
        }
      }
      return levels
    }
    return { bids: agg(this.bids), asks: agg(this.asks) }
  }

  ordersOf(owner: string): Order[] {
    return [...this.bids, ...this.asks].filter((o) => o.owner === owner)
  }

  private match(owner: string, side: Side, qty: number, limit: number | null): number {
    const book = side === 'buy' ? this.asks : this.bids
    let left = qty
    while (left > 0 && book.length) {
      const best = book[0]
      const crosses = limit == null || (side === 'buy' ? best.price <= limit : best.price >= limit)
      if (!crosses) break
      const q = Math.min(left, best.remaining)
      this.trade(side === 'buy' ? owner : best.owner, side === 'buy' ? best.owner : owner, best.price, q, side)
      best.remaining -= q
      left -= q
      if (best.remaining === 0) {
        book.shift()
        this.byId.delete(best.id)
      }
    }
    return left
  }

  private trade(buyer: string, seller: string, price: number, qty: number, aggressor: Side) {
    const b = this.account(buyer)
    const s = this.account(seller)
    b.cash -= price * qty
    b.position += qty
    s.cash += price * qty
    s.position -= qty
    const t: Trade = { id: this.nextTrade++, price, qty, buyer, seller, aggressor, step: this.step }
    this.trades.push(t)
    if (this.trades.length > 5000) this.trades.splice(0, this.trades.length - 5000)
    this.onTrade?.(t)
  }

  /** Limit order: matches what it crosses, rests the remainder. Returns the resting order, if any. */
  limit(owner: string, side: Side, price: number, qty: number): Order | null {
    if (!(qty > 0) || !Number.isInteger(price) || price <= 0) return null
    const left = this.match(owner, side, qty, price)
    if (left === 0) return null
    const order: Order = { id: this.nextId++, owner, side, price, qty, remaining: left, seq: this.nextSeq++ }
    const book = side === 'buy' ? this.bids : this.asks
    // Insert after every order that is better priced, or equally priced and earlier.
    let i = 0
    while (i < book.length && (side === 'buy' ? book[i].price >= price : book[i].price <= price)) i++
    book.splice(i, 0, order)
    this.byId.set(order.id, order)
    return order
  }

  /** Market order: takes liquidity until filled or the book runs out. Returns the unfilled quantity. */
  market(owner: string, side: Side, qty: number): number {
    if (!(qty > 0)) return 0
    return this.match(owner, side, qty, null)
  }

  cancel(id: number): boolean {
    const o = this.byId.get(id)
    if (!o) return false
    const book = o.side === 'buy' ? this.bids : this.asks
    book.splice(book.indexOf(o), 1)
    this.byId.delete(id)
    return true
  }

  cancelAll(owner: string): number {
    let n = 0
    for (const o of this.ordersOf(owner)) n += this.cancel(o.id) ? 1 : 0
    return n
  }
}
