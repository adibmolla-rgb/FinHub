"""PAPER: practice trading with real prices and fake money, on Vibe-Trading's paper ledger.

Vibe-Trading fills an order at the close of whichever day it's told to, so given a day that has already closed it
would fill at a price you could already see. FinHub keeps orders here until their fill day, which is the first
close still in the future when the order was placed, and only then hands them to the ledger.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from finhub_backend import agent, market
from finhub_backend.receipts import Quantity, Source, Unit

MARKET = "us"
NEW_YORK = ZoneInfo("America/New_York")
SETTLE_AFTER = (16, 30)  # the ledger settles a day from half an hour after the close
SYMBOL = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")
MAX_SHARES = 1e9
MAX_CASH = 1e12
LEDGER = "Vibe-Trading paper ledger"

_lock = threading.Lock()


class PaperError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _now() -> datetime:
    return datetime.now(UTC)


def _next_weekday(day: date) -> date:
    day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def fill_day(now: datetime) -> date:
    """The first close still ahead: today's while the market can still close today, otherwise the next weekday's."""
    here = now.astimezone(NEW_YORK)
    if here.weekday() < 5 and here.hour < 16:
        return here.date()
    return _next_weekday(here.date())


def latest_settled_day(now: datetime) -> date:
    """The last weekday whose close the ledger will accept. Holidays are found out when the ledger has no bar."""
    here = now.astimezone(NEW_YORK)
    day = here.date() if (here.hour, here.minute) >= SETTLE_AFTER else here.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


# --------------------------------------------------------------------------------------------------
# Orders waiting for their fill day
# --------------------------------------------------------------------------------------------------


def _path():
    return agent.data_dir() / "paper-orders.json"


def _load() -> list[dict]:
    path = _path()
    if not path.exists():
        return []
    try:
        orders = json.loads(path.read_text(encoding="utf-8"))["orders"]
        if not isinstance(orders, list):
            raise ValueError("orders is not a list")
        return orders
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Never overwrite a damaged file: it may be the only record of these orders.
        raise PaperError(f"{path} is damaged and won't be changed: {exc}", status=500) from exc


def _save(orders: list[dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"orders": orders}, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def clean_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper().removesuffix(".US")
    if not SYMBOL.match(cleaned):
        raise PaperError("use a US ticker, such as AAPL or BRK-B")
    return cleaned


def to_ledger(symbol: str) -> str:
    """FinHub and Yahoo write BRK-B. The ledger only knows BRK.B.US, and treats BRK-B.US as an unknown ticker."""
    return f"{symbol.replace('-', '.')}.US"


def from_ledger(symbol: str) -> str:
    return symbol.removesuffix(".US").replace(".", "-")


def place(account_id: str, symbol: str, side: str, quantity: float) -> dict:
    cleaned = clean_symbol(symbol)
    if side not in ("buy", "sell"):
        raise PaperError("side must be buy or sell")
    if not (1 <= quantity <= MAX_SHARES) or quantity != int(quantity):
        raise PaperError("shares must be a whole number of at least 1")
    _engine("GET", f"/api/paper-accounts/{account_id}")  # is there such an account?
    # One order on a ticker the ledger can't price would stop the whole account settling, so check it now.
    try:
        currency = market.quote(cleaned).get("currency")
    except market.MarketDataError as exc:
        raise PaperError(f"no quote for {cleaned}, so it can't be paper traded") from exc
    if currency != "USD":
        raise PaperError(f"{cleaned} is quoted in {currency}; paper accounts are US stocks in USD for now")
    now = _now()
    order = {
        "id": uuid.uuid4().hex[:12],
        "account_id": account_id,
        "symbol": cleaned,
        "side": side,
        "quantity": float(quantity),
        "placed_at": now.isoformat(),
        "fill_day": fill_day(now).isoformat(),
    }
    with _lock:
        _save([*_load(), order])
    return order


def cancel(order_id: str) -> bool:
    with _lock:
        orders = _load()
        left = [o for o in orders if o["id"] != order_id]
        if len(left) == len(orders):
            return False
        _save(left)
    return True


# --------------------------------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------------------------------


def _engine(method: str, path: str, **kwargs):
    try:
        return agent.call_engine(method, path, **kwargs)
    except agent.EngineError as exc:
        raise PaperError(str(exc), status=exc.status) from exc


def accounts() -> list[dict]:
    waiting = _load()
    return [
        {
            "id": a["id"], "label": a["label"], "currency": a["currency"], "created_at": a["created_at"], "last_date": a["last_date"],
            "pending": sum(1 for o in waiting if o["account_id"] == a["id"]),
        }
        for a in _engine("GET", "/api/paper-accounts")
    ]


def create(label: str, cash: float) -> dict:
    if not (0 < cash <= MAX_CASH):
        raise PaperError("starting cash must be more than zero")
    return _engine("POST", "/api/paper-accounts", json={"label": label.strip(), "market": MARKET, "account_state": {"cash": cash, "positions": []}})


def _earliest(account: dict) -> date:
    if account["last_date"]:
        return date.fromisoformat(account["last_date"]) + timedelta(days=1)
    return date.fromisoformat(account["start_on"])


def _advance(account: dict, day: date, orders: list[dict]) -> dict:
    wire = [{"symbol": to_ledger(o["symbol"]), "side": o["side"], "qty": o["quantity"]} for o in orders]
    return _engine(
        "POST", f"/api/paper-accounts/{account['id']}/advance",
        json={"expected_revision": account["revision"], "to_date": day.isoformat(), "orders": wire},
    )


def _closed(result: dict) -> bool:
    """A day the ledger looked at and found no session: a market holiday."""
    return "code" not in result and not result.get("nav_series")


def settle(account_id: str, now: datetime | None = None) -> str | None:
    """Fill every order whose close has passed, then value the account. Returns a note if something has to wait."""
    now = now or _now()
    latest = latest_settled_day(now)
    with _lock:
        account = _engine("GET", f"/api/paper-accounts/{account_id}")
        waiting = _load()
        mine = [o for o in waiting if o["account_id"] == account_id]
        while True:
            due = [o for o in mine if date.fromisoformat(o["fill_day"]) <= latest]
            if not due:
                break
            # An order never fills before its own fill day, or on a day the ledger has already settled.
            day = max(min(date.fromisoformat(o["fill_day"]) for o in due), _earliest(account))
            if day > latest:
                break
            batch = [o for o in due if date.fromisoformat(o["fill_day"]) <= day]
            answer = _advance(account, day, batch)
            result = answer.get("result") or {}
            if answer.get("committed"):
                account = answer["account"]
                done = {o["id"] for o in batch}
                mine = [o for o in mine if o["id"] not in done]
                waiting = [o for o in waiting if o["id"] not in done]
                _save(waiting)
            elif _closed(result):
                for o in batch:
                    o["fill_day"] = _next_weekday(day).isoformat()
                _save(waiting)
            else:
                symbols = ", ".join(sorted({o["symbol"] for o in batch}))
                return f"{day} can't be settled yet ({result.get('message') or result.get('code')}). Waiting: {symbols}. If a ticker is the problem, cancel its order."
        if _earliest(account) <= latest:
            answer = _advance(account, latest, [])
            result = answer.get("result") or {}
            if not answer.get("committed") and not _closed(result):
                return f"The account's value is as of {account['last_date'] or 'the start'}: {result.get('message') or result.get('code')}"
    return None


def _nav_points(history: list[dict]) -> list[dict]:
    by_day: dict[str, dict] = {}
    for step in history:
        for point in step.get("nav_series") or []:
            by_day[point["date"]] = point
    return [by_day[day] for day in sorted(by_day)]


def _quotes(symbols: list[str]) -> dict[str, dict]:
    def one(symbol: str):
        try:
            return symbol, market.quote(symbol)["values"]["price"]
        except (market.MarketDataError, KeyError):
            return symbol, None

    if not symbols:
        return {}
    with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as pool:
        return {s: q for s, q in pool.map(one, symbols) if q}


def account_view(account: dict, history: list[dict], orders: list[dict], prices: dict[str, dict]) -> dict:
    """Headline figures with receipts. A position with no current price is shown without a value, not at a guess."""
    currency = account["currency"]
    points = _nav_points(history)
    sources = sorted({str((s.get("data_provenance") or {}).get("source")) for s in history if s.get("fills") or s.get("nav_series")} - {"None", "unavailable"})
    detail = f"as of the close of {points[-1]['date']}" if points else "no day settled yet"
    ledger = Source(provider=LEDGER, detail=f"{detail}{'; prices from ' + ', '.join(sources) if sources else ''}")
    state = account["account_state"]
    initial = account["initial_state"]
    start_value = initial["cash"] + sum(p["qty"] * p["avg_cost"] for p in initial["positions"])
    money = lambda value, label, source=ledger: Quantity(value=value, unit=Unit.CURRENCY, currency=currency, label=label, source=source)  # noqa: E731
    start = money(start_value, "Starting value")
    out: dict = {"cash": money(state["cash"], "Cash").receipt(), "start": start.receipt()}
    if points:
        nav = money(points[-1]["nav"], f"Account value ({points[-1]['date']})")
        out["value"] = nav.receipt()
        out["profit"] = Quantity(value=nav.value - start.value, unit=Unit.CURRENCY, currency=currency, label="Profit since the start", source=Source(provider="computed by FinHub"), formula=f"{nav.label} − {start.label}", inputs=(nav, start)).receipt()
        out["return"] = Quantity(value=nav.value / start.value - 1, unit=Unit.FRACTION, label="Return since the start", source=Source(provider="computed by FinHub"), formula=f"{nav.label} ÷ {start.label} − 1", inputs=(nav, start)).receipt()

    positions = []
    for p in state["positions"]:
        symbol = from_ledger(p["symbol"])
        row = {"symbol": symbol, "shares": p["qty"], "average_cost": p["avg_cost"], "price": None, "value": None, "profit": None}
        price = prices.get(symbol)
        if price:
            row.update(price=price, value=price["value"] * p["qty"], profit=(price["value"] - p["avg_cost"]) * p["qty"])
        positions.append(row)

    fills, rejected = [], []
    for step in history:
        for f in step.get("fills") or []:
            fills.append({"date": f["trade_date"], "symbol": from_ledger(f["symbol"]), "side": f["side"], "shares": f["qty"], "price": f["price"], "fee": f["fee"]})
        for r in step.get("rejected_orders") or []:
            rejected.append({"date": r["trade_date"], "symbol": from_ledger(r["symbol"]), "side": r["side"], "shares": r["qty"], "reason": r.get("detail") or r.get("reason_code")})
    out["fees"] = money(sum(f["fee"] for f in fills), "Fees paid").receipt()
    return {
        **out,
        "id": account["id"],
        "label": account["label"],
        "currency": currency,
        "created_at": account["created_at"],
        "start_on": account["start_on"],
        "last_date": account["last_date"],
        "positions": positions,
        "orders": sorted(orders, key=lambda o: (o["fill_day"], o["placed_at"])),
        "fills": list(reversed(fills)),
        "rejected": list(reversed(rejected)),
        "nav": [[p["date"], p["nav"]] for p in points],
    }


def view(account_id: str, settle_first: bool = True) -> dict:
    note = settle(account_id) if settle_first else None
    account = _engine("GET", f"/api/paper-accounts/{account_id}")
    history = _engine("GET", f"/api/paper-accounts/{account_id}/history")
    orders = [o for o in _load() if o["account_id"] == account_id]
    prices = _quotes([from_ledger(p["symbol"]) for p in account["account_state"]["positions"]])
    return {**account_view(account, history, orders, prices), "note": note, "next_fill_day": fill_day(_now()).isoformat()}
