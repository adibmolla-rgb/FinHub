"""Stock screener over a universe FinHub quotes itself.

There is no free full-market screening feed, so the universe is explicit: a built-in list of large
caps across all sectors, the user's watchlist, or tickers the user types. Each row comes from a live
quote (same provider chain and receipts as everywhere else); sectors for the built-in list are a fixed
reference table, labelled as such.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from finhub_backend import market, store

# Fixed reference list (GICS sectors). Edit freely; it is only a starting universe.
LARGE_CAPS: dict[str, str] = {
    **dict.fromkeys(["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "INTC", "CSCO", "IBM", "QCOM", "TXN"], "Information Technology"),
    **dict.fromkeys(["GOOGL", "META", "NFLX", "DIS", "T", "VZ"], "Communication Services"),
    **dict.fromkeys(["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW"], "Consumer Discretionary"),
    **dict.fromkeys(["WMT", "PG", "KO", "PEP", "COST"], "Consumer Staples"),
    **dict.fromkeys(["JPM", "BAC", "WFC", "GS", "MS", "V", "MA", "BRK-B"], "Financials"),
    **dict.fromkeys(["UNH", "JNJ", "LLY", "PFE", "MRK", "ABBV", "TMO"], "Health Care"),
    **dict.fromkeys(["XOM", "CVX", "COP"], "Energy"),
    **dict.fromkeys(["CAT", "BA", "GE", "HON", "UPS", "RTX"], "Industrials"),
    **dict.fromkeys(["LIN", "SHW"], "Materials"),
    **dict.fromkeys(["NEE", "DUK"], "Utilities"),
    **dict.fromkeys(["PLD", "AMT"], "Real Estate"),
}

_cache: dict[str, tuple[float, dict | None, str | None]] = {}
_cache_lock = threading.Lock()
CACHE_SECONDS = 60


def _quote(symbol: str) -> tuple[dict | None, str | None]:
    now = time.time()
    with _cache_lock:
        hit = _cache.get(symbol)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1], hit[2]
    try:
        q, err = market.quote(symbol), None
    except market.MarketDataError as exc:
        q, err = None, str(exc)
    with _cache_lock:
        _cache[symbol] = (now, q, err)
    return q, err


@dataclass
class Filters:
    min_price: float | None = None
    max_price: float | None = None
    min_change: float | None = None  # fractions: 0.02 = +2% today
    max_change: float | None = None
    min_market_cap: float | None = None  # in the quote's currency
    max_from_high: float | None = None  # e.g. 0.05 = within 5% of the 52-week high
    min_from_low: float | None = None  # e.g. 0.20 = at least 20% above the 52-week low
    sectors: tuple[str, ...] = ()


def row_from_quote(symbol: str, q: dict, sector: str | None) -> dict:
    v = q["values"]
    val = lambda k: (v.get(k) or {}).get("value")  # noqa: E731
    price, low = val("price"), val("year_low")
    return {
        "symbol": symbol,
        "sector": sector,
        "price": price,
        "change_pct": val("change_pct"),
        "market_cap": val("market_cap"),
        "volume": val("volume"),
        "from_high_pct": val("from_high_pct"),  # ≤ 0: price ÷ 52w high − 1
        "from_low_pct": (price / low - 1) if price and low else None,
        "currency": q.get("currency"),
        "provider": q.get("provider_name"),
        "receipts": {k: v[k] for k in ("price", "change_pct", "market_cap", "from_high_pct") if k in v},
    }


def passes(row: dict, f: Filters) -> bool:
    """A row passes only if every filter that is set can be checked and holds (missing data fails)."""

    def need(key: str, ok) -> bool:
        x = row.get(key)
        return x is not None and ok(x)

    checks = [
        f.min_price is None or need("price", lambda x: x >= f.min_price),
        f.max_price is None or need("price", lambda x: x <= f.max_price),
        f.min_change is None or need("change_pct", lambda x: x >= f.min_change),
        f.max_change is None or need("change_pct", lambda x: x <= f.max_change),
        f.min_market_cap is None or need("market_cap", lambda x: x >= f.min_market_cap),
        f.max_from_high is None or need("from_high_pct", lambda x: x >= -f.max_from_high),
        f.min_from_low is None or need("from_low_pct", lambda x: x >= f.min_from_low),
        not f.sectors or row.get("sector") in f.sectors,
    ]
    return all(checks)


def universe(name: str, symbols: list[str] | None) -> dict[str, str | None]:
    if name == "large_caps":
        return dict(LARGE_CAPS)
    if name == "watchlist":
        return {s: LARGE_CAPS.get(s) for s in store.get_watchlist()}
    if name == "custom":
        clean = [s.strip().upper() for s in symbols or [] if s.strip()]
        if not clean or len(clean) > 100 or not all(store.SYMBOL.match(s) for s in clean):
            raise ValueError("custom universe needs 1-100 valid tickers")
        return {s: LARGE_CAPS.get(s) for s in clean}
    raise ValueError("universe must be large_caps, watchlist or custom")


def screen(name: str, filters: Filters, symbols: list[str] | None = None) -> dict:
    uni = universe(name, symbols)
    with ThreadPoolExecutor(max_workers=8) as pool:
        quotes = dict(zip(uni, pool.map(_quote, uni), strict=True))
    rows, failed = [], []
    for sym, (q, err) in quotes.items():
        if q is None:
            failed.append({"symbol": sym, "error": err})
        else:
            rows.append(row_from_quote(sym, q, uni[sym]))
    matches = [r for r in rows if passes(r, filters)]
    return {
        "universe": name,
        "size": len(uni),
        "quoted": len(rows),
        "failed": failed,
        "matches": sorted(matches, key=lambda r: -(r["market_cap"] or 0)),
        "sectors": sorted(set(LARGE_CAPS.values())),
    }
