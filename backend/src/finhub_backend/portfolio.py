"""PORT: a ledger of your own buys and sells, valued at live prices.

This only records what you type. FinHub has no broker connection and can't place orders.

Cost basis is first-in, first-out, with fees counted in. Nothing is guessed: if an open position has no
live price, the totals it would change are left out rather than understated, and values in different
currencies are never added together. Dividends aren't recorded, so returns are price returns.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

from finhub_backend import market
from finhub_backend.agent import data_dir
from finhub_backend.receipts import Quantity, Source, Unit

SYMBOL = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-^=]{0,14}$")
SIDES = ("buy", "sell", "split")
MAX_TRANSACTIONS = 5000
_DUST = 1e-9  # share counts below this are rounding left over from fractional sales, not a holding

_lock = threading.RLock()


class LedgerError(ValueError):
    """A transaction that can't be recorded, or a ledger file that can't be trusted."""


def _path():
    return data_dir() / "portfolio.json"


def load() -> list[dict]:
    """The saved transactions. A damaged file is an error, because saving over it would destroy the ledger."""
    path = _path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise LedgerError(f"couldn't read {path}: {exc}") from exc
    try:
        transactions = json.loads(text)["transactions"]
        if not isinstance(transactions, list):
            raise TypeError("transactions isn't a list")
        replay(transactions)
    except (ValueError, KeyError, TypeError) as exc:
        raise LedgerError(f"{path} is damaged, so FinHub won't change it: {exc}") from exc
    return transactions


def _save(transactions: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"transactions": transactions}, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _ordered(transactions: list[dict]) -> list[dict]:
    # By trade date, then in the order they were entered. Sorted is stable, so same-day entries keep theirs.
    return sorted(transactions, key=lambda t: t["date"])


def replay(transactions: list[dict]) -> dict[str, dict]:
    """Work through the ledger in date order: FIFO lots and realised profit for each ticker."""
    books: dict[str, dict] = {}
    for t in _ordered(transactions):
        book = books.setdefault(t["symbol"], {"lots": deque(), "realized": 0.0, "sells": 0, "fees": 0.0})
        lots = book["lots"]
        if t["side"] == "buy":
            fees = t.get("fees") or 0.0
            lots.append([t["quantity"], t["price"] + fees / t["quantity"]])
            book["fees"] += fees
        elif t["side"] == "split":
            ratio = t["quantity"]
            for lot in lots:
                lot[0] *= ratio
                lot[1] /= ratio
        else:
            held = sum(lot[0] for lot in lots)
            if t["quantity"] > held + _DUST:
                raise LedgerError(f"{t['date']}: can't sell {t['quantity']:g} {t['symbol']} with {held:g} held at that date")
            fees = t.get("fees") or 0.0
            book["fees"] += fees
            book["sells"] += 1
            book["realized"] -= fees
            left = t["quantity"]
            while left > _DUST and lots:
                lot = lots[0]
                sold = min(left, lot[0])
                book["realized"] += sold * (t["price"] - lot[1])
                lot[0] -= sold
                left -= sold
                if lot[0] <= _DUST:
                    lots.popleft()
    return books


# Far beyond any real trade, and small enough that multiplying these can't overflow into a value the API can't send.
MAX_AMOUNT = 1e15


def _clean(symbol: str, side: str, quantity: float, price: float | None, fees: float, day: str | None) -> dict:
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        raise LedgerError("invalid ticker")
    if side not in SIDES:
        raise LedgerError(f"side must be one of {SIDES}")
    if not (math.isfinite(quantity) and quantity > 0):
        raise LedgerError("quantity must be more than zero" if side != "split" else "split ratio must be more than zero")
    if side == "split":
        if quantity == 1:
            raise LedgerError("a 1-for-1 split changes nothing")
        price, fees = 0.0, 0.0
    elif price is None or not (math.isfinite(price) and price >= 0):
        raise LedgerError("price must be zero or more")
    if not (math.isfinite(fees) and fees >= 0):
        raise LedgerError("fees must be zero or more")
    if max(quantity, price, fees) > MAX_AMOUNT:
        raise LedgerError("that number is too large to record")
    day = day or datetime.now(UTC).date().isoformat()
    try:
        if date.fromisoformat(day) > datetime.now(UTC).date():
            raise LedgerError("the trade date is in the future")
    except ValueError as exc:
        if isinstance(exc, LedgerError):
            raise
        raise LedgerError("date must be YYYY-MM-DD") from exc
    return {"id": uuid.uuid4().hex[:12], "symbol": symbol, "side": side, "quantity": quantity, "price": price, "fees": fees, "date": day}


def add(symbol: str, side: str, quantity: float, price: float | None = None, fees: float = 0.0, day: str | None = None) -> dict:
    transaction = _clean(symbol, side, quantity, price, fees, day)
    with _lock:
        transactions = load()
        if len(transactions) >= MAX_TRANSACTIONS:
            raise LedgerError(f"at most {MAX_TRANSACTIONS} transactions")
        updated = [*transactions, transaction]
        replay(updated)  # refuses a sale of more than was held, even when back-dated
        _save(updated)
    return transaction


def remove(transaction_id: str) -> bool:
    with _lock:
        transactions = load()
        updated = [t for t in transactions if t["id"] != transaction_id]
        if len(updated) == len(transactions):
            return False
        try:
            replay(updated)
        except LedgerError as exc:
            raise LedgerError(f"Deleting this would leave a sale with nothing to sell ({exc})") from exc
        _save(updated)
    return True


# --------------------------------------------------------------------------------------------------
# Valuation
# --------------------------------------------------------------------------------------------------


def _price_quantity(quote: dict, key: str) -> Quantity | None:
    receipt = (quote.get("values") or {}).get(key)
    if not receipt:
        return None
    src = receipt["source"]
    return Quantity(
        value=receipt["value"], unit=Unit(receipt["unit"]), label=receipt["label"], currency=receipt.get("currency"),
        source=Source(provider=src["provider"], fetched_at=datetime.fromisoformat(src["fetched_at"]), detail=src.get("detail")),
    )


def _money(value: float, label: str, currency: str | None, formula: str, inputs: tuple[Quantity, ...] = ()) -> Quantity:
    return Quantity(value=value, unit=Unit.CURRENCY, label=label, currency=currency, source=Source(provider="computed by FinHub"), formula=formula, inputs=inputs)


def _ledger_source(symbol: str, detail: str) -> Source:
    return Source(provider="your FinHub ledger", detail=f"{symbol} · {detail}")


def value(transactions: list[dict], quotes: dict[str, dict]) -> dict:
    """Positions and totals from the ledger and whatever quotes arrived. Pure, so it's testable offline."""
    books = replay(transactions)
    positions = []
    closed = []
    warnings = []
    groups: dict[str | None, dict] = {}

    for symbol in sorted(books):
        book = books[symbol]
        quote = quotes.get(symbol)
        currency = (quote or {}).get("currency")
        group = groups.setdefault(currency, {"cost": [], "value": [], "unrealized": [], "day": [], "realized": [], "missing_price": [], "missing_day": []})
        quantity = sum(lot[0] for lot in book["lots"])
        realized = None
        if book["sells"]:
            realized = _money(
                book["realized"], f"{symbol} realised profit", currency, "Sale proceeds − FIFO cost of the shares sold − fees",
            )
            group["realized"].append(realized)
        if quantity <= _DUST:
            closed.append({"symbol": symbol, "realized": realized.receipt() if realized else None, "currency": currency})
            continue

        shares = Quantity(value=quantity, unit=Unit.SHARES, label=f"{symbol} shares held", source=_ledger_source(symbol, "buys, sells and splits"))
        cost = Quantity(
            value=sum(lot[0] * lot[1] for lot in book["lots"]), unit=Unit.CURRENCY, label=f"{symbol} cost basis", currency=currency,
            source=_ledger_source(symbol, f"{len(book['lots'])} open FIFO lots, fees included"),
        )
        group["cost"].append(cost)
        row: dict = {
            "symbol": symbol, "currency": currency, "shares": shares.receipt(), "cost_basis": cost.receipt(), "lots": len(book["lots"]),
            "average_cost": _money(cost.value / quantity, f"{symbol} average cost per share", currency, "Cost basis ÷ Shares held", (cost, shares)).receipt(),
        }
        if realized:
            row["realized"] = realized.receipt()

        price = _price_quantity(quote, "price") if quote else None
        if price is None:
            group["missing_price"].append(symbol)
            row["provider_name"] = None
            warnings.append(f"No live price for {symbol}, so totals that depend on it are left out.")
            positions.append(row)
            continue

        worth = _money(quantity * price.value, f"{symbol} market value", currency, "Shares held × Last price", (shares, price))
        gain = _money(worth.value - cost.value, f"{symbol} unrealised profit", currency, "Market value − Cost basis", (worth, cost))
        row.update({"price": price.receipt(), "value": worth.receipt(), "unrealized": gain.receipt(), "provider_name": quote.get("provider_name"), "fallback_used": bool(quote.get("fallback_used"))})
        group["value"].append(worth)
        group["unrealized"].append(gain)
        if cost.value > 0:
            row["unrealized_pct"] = Quantity(
                value=gain.value / cost.value, unit=Unit.FRACTION, label=f"{symbol} unrealised return", source=Source(provider="computed by FinHub"),
                formula="Unrealised profit ÷ Cost basis", inputs=(gain, cost),
            ).receipt()
        change = _price_quantity(quote, "change")
        if change is None:
            group["missing_day"].append(symbol)
        else:
            day = _money(quantity * change.value, f"{symbol} change today", currency, "Shares held × Change", (shares, change))
            row["day_change"] = day.receipt()
            group["day"].append(day)
        positions.append(row)

    # A holding with no quote has no known currency either, so it could belong to any total. Every value
    # and cost total is held back until it has a price; a smaller, wrong total would look complete.
    unpriced = sorted(symbol for group in groups.values() for symbol in group["missing_price"])
    totals = []
    for currency, group in sorted(groups.items(), key=lambda kv: kv[0] or "~"):
        name = currency or "currency not stated"
        if unpriced and not group["realized"] and not currency and len(groups) > 1:
            continue  # only the unpriced holdings are here, and the warnings already name them
        total: dict = {"currency": currency, "complete": not unpriced, "missing": unpriced}

        def summed(key: str, label: str) -> Quantity:
            items = group[key]
            return _money(sum(q.value for q in items), f"{label} ({name})", currency, " + ".join(q.label for q in items) or "Nothing yet", tuple(items))

        if group["realized"]:
            total["realized"] = summed("realized", "Total realised profit").receipt()
        if group["cost"] and total["complete"]:
            cost_total = summed("cost", "Total cost basis")
            total["cost_basis"] = cost_total.receipt()
            worth_total = summed("value", "Total market value")
            gain_total = summed("unrealized", "Total unrealised profit")
            total["value"] = worth_total.receipt()
            total["unrealized"] = gain_total.receipt()
            if cost_total.value > 0:
                total["unrealized_pct"] = Quantity(
                    value=gain_total.value / cost_total.value, unit=Unit.FRACTION, label=f"Total unrealised return ({name})", source=Source(provider="computed by FinHub"),
                    formula="Total unrealised profit ÷ Total cost basis", inputs=(gain_total, cost_total),
                ).receipt()
            if not group["missing_day"]:
                total["day_change"] = summed("day", "Total change today").receipt()
            if worth_total.value > 0:
                for row in positions:
                    if row["currency"] == currency and "value" in row:
                        worth = _price_free(row["value"])
                        row["weight"] = Quantity(
                            value=worth.value / worth_total.value, unit=Unit.FRACTION, label=f"{row['symbol']} weight in the {name} holdings", source=Source(provider="computed by FinHub"),
                            formula="Market value ÷ Total market value", inputs=(worth, worth_total),
                        ).receipt()
        totals.append(total)

    held_currencies = {p["currency"] for p in positions if p["currency"]}  # an unpriced holding's currency isn't known
    risk_holdings = None
    if len(held_currencies) == 1 and positions and all("weight" in p for p in positions):
        risk_holdings = [{"symbol": p["symbol"], "weight": round(p["weight"]["value"] * 100, 2)} for p in positions if p["weight"]["value"] > 0]
    elif len(held_currencies) > 1:
        warnings.append("Holdings are in more than one currency, so each currency has its own totals. They aren't converted or added together.")
    return {
        "positions": positions, "closed": closed, "totals": totals, "warnings": warnings, "risk_holdings": risk_holdings,
        "transactions": [*reversed(_ordered(transactions))],
    }


def _price_free(receipt: dict) -> Quantity:
    return Quantity(value=receipt["value"], unit=Unit(receipt["unit"]), label=receipt["label"], currency=receipt.get("currency"), source=Source(provider="computed by FinHub"))


def report() -> dict:
    transactions = load()
    symbols = sorted({t["symbol"] for t in transactions})
    quotes: dict[str, dict] = {}

    def one(symbol: str) -> None:
        try:
            quotes[symbol] = market.quote(symbol)
        except market.MarketDataError:
            pass  # value() reports the missing price

    if symbols:
        with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as pool:
            list(pool.map(one, symbols))
    return value(transactions, quotes)
