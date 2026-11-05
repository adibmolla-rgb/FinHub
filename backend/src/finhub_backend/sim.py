"""Simulated exchange for AI agents (Python port of the app's SIM, with named participants).

A hidden fundamental value moves as a random walk with news jumps. Bots trade it: a market maker
(inventory skew, learns fair value from trade prices and signed order flow), noise traders, momentum,
mean reversion, and an informed trader that sees the true value. Outside participants (AI agents via
MCP, or the user) trade under their own names and are scored on the same leaderboard.

Prices are integer ticks (1 tick = 0.01) so matching and cash are exact. Every trade moves cash and
shares between two accounts, so totals across all accounts are always zero.
"""

from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass, field

TICK = 0.01
BOTS = {
    "maker": "Market maker: quotes both sides, skews against inventory, learns from order flow",
    "noise": "Noise traders: random, uninformed orders",
    "momentum": "Momentum: buys after rises, sells after falls",
    "meanrev": "Mean reversion: fades moves away from the recent average",
    "informed": "Informed trader: knows the true value",
}
NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,31}$")
MAX_QTY = 5_000


class XorShift:
    def __init__(self, seed: int):
        self.s = (seed & 0xFFFFFFFF) or 1

    def __call__(self) -> float:
        s = self.s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self.s = s & 0xFFFFFFFF
        return self.s / 4294967296


@dataclass
class Order:
    id: int
    owner: str
    side: str
    price: int
    qty: int
    remaining: int


@dataclass
class Trade:
    id: int
    price: int
    qty: int
    buyer: str
    seller: str
    aggressor: str
    step: int


@dataclass
class Account:
    cash: int = 0  # ticks
    position: int = 0


class OrderBook:
    def __init__(self) -> None:
        self.bids: list[Order] = []  # best first, then earliest
        self.asks: list[Order] = []
        self.by_id: dict[int, Order] = {}
        self.accounts: dict[str, Account] = {}
        self.trades: list[Trade] = []
        self.step = 0
        self._next_id = 1
        self._next_trade = 1

    def account(self, owner: str) -> Account:
        return self.accounts.setdefault(owner, Account())

    def best_bid(self) -> int | None:
        return self.bids[0].price if self.bids else None

    def best_ask(self) -> int | None:
        return self.asks[0].price if self.asks else None

    def mid(self) -> float | None:
        b, a = self.best_bid(), self.best_ask()
        if b is None or a is None:
            return b if b is not None else a
        return (a + b) / 2

    def depth(self, n: int = 10) -> dict:
        def agg(orders: list[Order]) -> list[dict]:
            levels: list[dict] = []
            for o in orders:
                if levels and levels[-1]["price"] == o.price:
                    levels[-1]["qty"] += o.remaining
                    levels[-1]["orders"] += 1
                else:
                    if len(levels) == n:
                        break
                    levels.append({"price": o.price, "qty": o.remaining, "orders": 1})
            return levels

        return {"bids": agg(self.bids), "asks": agg(self.asks)}

    def orders_of(self, owner: str) -> list[Order]:
        return [o for o in self.bids + self.asks if o.owner == owner]

    def _trade(self, buyer: str, seller: str, price: int, qty: int, aggressor: str) -> None:
        b, s = self.account(buyer), self.account(seller)
        b.cash -= price * qty
        b.position += qty
        s.cash += price * qty
        s.position -= qty
        self.trades.append(Trade(self._next_trade, price, qty, buyer, seller, aggressor, self.step))
        self._next_trade += 1
        if len(self.trades) > 5000:
            del self.trades[: len(self.trades) - 5000]

    def _match(self, owner: str, side: str, qty: int, limit: int | None) -> int:
        book = self.asks if side == "buy" else self.bids
        left = qty
        while left > 0 and book:
            best = book[0]
            crosses = limit is None or (best.price <= limit if side == "buy" else best.price >= limit)
            if not crosses:
                break
            q = min(left, best.remaining)
            self._trade(owner if side == "buy" else best.owner, best.owner if side == "buy" else owner, best.price, q, side)
            best.remaining -= q
            left -= q
            if best.remaining == 0:
                book.pop(0)
                self.by_id.pop(best.id, None)
        return left

    def limit(self, owner: str, side: str, price: int, qty: int) -> Order | None:
        if qty <= 0 or price <= 0:
            return None
        left = self._match(owner, side, qty, price)
        if left == 0:
            return None
        order = Order(self._next_id, owner, side, price, qty, left)
        self._next_id += 1
        book = self.bids if side == "buy" else self.asks
        i = 0
        while i < len(book) and (book[i].price >= price if side == "buy" else book[i].price <= price):
            i += 1
        book.insert(i, order)
        self.by_id[order.id] = order
        return order

    def market(self, owner: str, side: str, qty: int) -> int:
        return self._match(owner, side, qty, None) if qty > 0 else 0

    def cancel(self, order_id: int) -> bool:
        o = self.by_id.pop(order_id, None)
        if o is None:
            return False
        (self.bids if o.side == "buy" else self.asks).remove(o)
        return True

    def cancel_all(self, owner: str) -> int:
        return sum(self.cancel(o.id) for o in self.orders_of(owner))


class Market:
    def __init__(self, seed: int = 42, start_price: float = 100.0) -> None:
        self.rand = XorShift(seed)
        self.seed = seed
        self.book = OrderBook()
        self.value = round(start_price / TICK)
        self.sigma = 2.5
        self.maker_fair = float(self.value)
        self.last_seen_trade = 0
        self.mids: list[float] = []
        self.history: list[dict] = []
        self.events: list[dict] = []
        self.maker_paused_until = 0
        self.informed_boost_until = 0
        self.crash_until = 0
        self.lock = threading.RLock()
        for b in BOTS:
            self.book.account(b)
        self._quote_maker()

    def _gauss(self) -> float:
        u = max(self.rand(), 1e-12)
        v = self.rand()
        return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    # ---------------- bots ----------------

    def _quote_maker(self) -> None:
        b = self.book
        b.cancel_all("maker")
        if b.step < self.maker_paused_until:
            return
        for t in b.trades[-200:]:
            if t.id <= self.last_seen_trade:
                continue
            self.last_seen_trade = t.id
            self.maker_fair += 0.05 * (t.price - self.maker_fair)
            if "maker" in (t.buyer, t.seller):
                self.maker_fair += 0.04 * (t.qty if t.aggressor == "buy" else -t.qty)
        inv = b.account("maker").position
        stressed = b.step < self.crash_until
        skew = max(-30.0, min(30.0, -inv * 0.01))
        half = (12 if stressed else 3) + min(6.0, abs(inv) * 0.004)
        bid = round(self.maker_fair + skew - half)
        ask = max(bid + 1, round(self.maker_fair + skew + half))
        for lvl in range(5):
            size = 100 + lvl * 60
            b.limit("maker", "buy", bid - lvl * 2, size)
            b.limit("maker", "sell", ask + lvl * 2, size)

    def _noise(self) -> None:
        if self.rand() < 0.35:
            side = "buy" if self.rand() < 0.5 else "sell"
            self.book.market("noise", side, 10 + int(self.rand() * 60))
        if self.rand() < 0.25:
            mid = self.book.mid()
            if mid is not None:
                side = "buy" if self.rand() < 0.5 else "sell"
                off = 2 + int(self.rand() * 10)
                self.book.limit("noise", side, round(mid - off if side == "buy" else mid + off), 20 + int(self.rand() * 40))

    def _trend(self, kind: str) -> None:
        h = self.mids
        if len(h) < 30:
            return
        now, then = h[-1], h[-20]
        avg = sum(h[-30:]) / 30
        pos = self.book.account(kind).position
        if kind == "momentum":
            move = now - then
            if move > 6 and pos < 600 and self.rand() < 0.3:
                self.book.market(kind, "buy", 40)
            if move < -6 and pos > -600 and self.rand() < 0.3:
                self.book.market(kind, "sell", 40)
        else:
            dev = now - avg
            if dev > 8 and pos > -600 and self.rand() < 0.25:
                self.book.market(kind, "sell", 40)
            if dev < -8 and pos < 600 and self.rand() < 0.25:
                self.book.market(kind, "buy", 40)

    def _informed(self) -> None:
        b = self.book
        bid, ask = b.best_bid(), b.best_ask()
        boosted = b.step < self.informed_boost_until
        pos = b.account("informed").position
        act = 0.8 if boosted else 0.2
        if ask is not None and self.value - ask > 4 and pos < 3000 and self.rand() < act:
            b.market("informed", "buy", 150 if boosted else 60)
        if bid is not None and bid - self.value > 4 and pos > -3000 and self.rand() < act:
            b.market("informed", "sell", 150 if boosted else 60)
        if bid is not None and ask is not None and pos != 0 and abs((bid + ask) / 2 - self.value) <= 3 and self.rand() < 0.3:
            b.market("informed", "sell" if pos > 0 else "buy", min(abs(pos), 60))

    # ---------------- public API ----------------

    def trigger(self, scenario: str) -> str:
        with self.lock:
            step = self.book.step
            if scenario in ("news-up", "news-down"):
                jump = round(self.value * 0.04) * (1 if scenario == "news-up" else -1)
                self.value += jump
                self.maker_fair += jump / 2
                self.informed_boost_until = step + 60
                text = f"News: true value {'jumps' if jump > 0 else 'drops'} 4%. Only the informed trader knows."
            elif scenario == "crash":
                drop = round(self.value * 0.08)
                self.value -= drop
                self.maker_fair -= drop / 2
                self.informed_boost_until = step + 120
                self.crash_until = step + 120
                text = "Flash crash: value −8%, informed selling, market maker widens its quotes."
            elif scenario == "drain":
                self.maker_paused_until = step + 80
                self.book.cancel_all("maker")
                text = "Liquidity drain: the market maker pulls all quotes for 80 steps."
            else:
                raise ValueError("scenario must be news-up, news-down, crash or drain")
            self.events.append({"step": step, "text": text})
            return text

    def tick(self, steps: int = 1) -> None:
        with self.lock:
            for _ in range(steps):
                b = self.book
                b.step += 1
                self.value = max(100, round(self.value + self.sigma * self._gauss()))
                self._quote_maker()
                self._noise()
                self._trend("momentum")
                self._trend("meanrev")
                self._informed()
                mid = b.mid()
                if mid is not None:
                    self.mids.append(mid)
                    del self.mids[:-4000]
                last = b.trades[-1].price * TICK if b.trades else None
                self.history.append({"step": b.step, "value": self.value * TICK, "mid": mid * TICK if mid is not None else None, "last": last})
                del self.history[:-4000]

    def order(self, owner: str, side: str, qty: int, price: float | None = None) -> dict:
        """Place an order for a named participant. Market order if price is None."""
        if not NAME.match(owner) or owner in BOTS:
            raise ValueError("participant name must be letters/digits/_/- (max 32) and not a bot's name")
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        if not 0 < qty <= MAX_QTY:
            raise ValueError(f"qty must be between 1 and {MAX_QTY}")
        with self.lock:
            first_id = self.book.trades[-1].id if self.book.trades else 0
            if price is None:
                unfilled = self.book.market(owner, side, qty)
                resting = None
            else:
                ticks = round(price / TICK)
                if ticks <= 0:
                    raise ValueError("price must be positive")
                o = self.book.limit(owner, side, ticks, qty)
                unfilled = 0
                resting = {"order_id": o.id, "price": o.price * TICK, "remaining": o.remaining} if o else None
            fills = [t for t in self.book.trades if t.id > first_id and owner in (t.buyer, t.seller)]
            filled = sum(t.qty for t in fills)
            return {
                "filled": filled,
                "avg_price": (sum(t.price * t.qty for t in fills) / filled * TICK) if filled else None,
                "unfilled_market_qty": unfilled,
                "resting": resting,
                "account": self.account_view(owner),
            }

    def cancel_all(self, owner: str) -> int:
        with self.lock:
            return self.book.cancel_all(owner)

    def pnl(self, owner: str) -> float:
        a = self.book.account(owner)
        mark = self.book.mid() or self.value
        return (a.cash + a.position * mark) * TICK

    def account_view(self, owner: str) -> dict:
        a = self.book.account(owner)
        return {
            "name": owner,
            "position": a.position,
            "cash": a.cash * TICK,
            "pnl_marked_to_mid": self.pnl(owner),
            "open_orders": [{"order_id": o.id, "side": o.side, "price": o.price * TICK, "remaining": o.remaining} for o in self.book.orders_of(owner)],
        }

    def state(self, history: int = 300, reveal_value: bool = False) -> dict:
        with self.lock:
            b = self.book
            depth = b.depth(10)
            participants = [name for name in b.accounts if name not in BOTS]
            board = sorted(
                [{"name": k, "kind": "bot", "about": BOTS[k], "pnl": self.pnl(k), "position": b.account(k).position} for k in BOTS]
                + [{"name": k, "kind": "participant", "pnl": self.pnl(k), "position": b.account(k).position} for k in participants],
                key=lambda r: -r["pnl"],
            )
            hist = self.history[-history:]
            return {
                "step": b.step,
                "seed": self.seed,
                "best_bid": b.best_bid() * TICK if b.best_bid() is not None else None,
                "best_ask": b.best_ask() * TICK if b.best_ask() is not None else None,
                "mid": b.mid() * TICK if b.mid() is not None else None,
                "depth": {s: [{**lvl, "price": lvl["price"] * TICK} for lvl in depth[s]] for s in depth},
                "recent_trades": [
                    {"price": t.price * TICK, "qty": t.qty, "buyer": t.buyer, "seller": t.seller, "aggressor": t.aggressor, "step": t.step}
                    for t in reversed(b.trades[-20:])
                ],
                "leaderboard": board,
                "events": self.events[-5:],
                "history": [{k: v for k, v in h.items() if reveal_value or k != "value"} for h in hist],
            }


# One shared arena per FinHub process, so agents and the ARENA screen see the same market.
_arena: Market | None = None
_arena_lock = threading.Lock()


def arena() -> Market:
    global _arena
    with _arena_lock:
        if _arena is None:
            _arena = Market(seed=42)
            _arena.tick(50)  # warm up so there is price history and a book
        return _arena


def reset_arena(seed: int = 42) -> Market:
    global _arena
    with _arena_lock:
        _arena = Market(seed=seed)
        _arena.tick(50)
        return _arena
