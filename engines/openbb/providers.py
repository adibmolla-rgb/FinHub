"""Market data providers for FinHub, run inside the OpenBB engine environment.

Each request walks a provider chain (Yahoo via the yfinance library first, then OpenBB's free
providers) and returns the first success together with a record of every attempt. Field values are
returned raw, with the name of the provider field they came from, so the backend can build receipts.
Nothing here converts units: the backend owns that.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Any

# --------------------------------------------------------------------------------------------------
# Provider chain
# --------------------------------------------------------------------------------------------------

CHAINS: dict[str, list[str]] = {
    "quote": ["yahoo", "cboe", "nasdaq", "tmx"],
    "history": ["yahoo", "cboe", "nasdaq", "tmx"],
    "profile": ["yahoo", "nasdaq", "tmx", "finra"],
    "news": ["yahoo", "nasdaq", "tmx"],
    "statement": ["yahoo", "sec", "nasdaq", "tmx"],
    "macro": ["oecd"],
}

PROVIDER_NAMES = {
    "yahoo": "Yahoo Finance (yfinance)",
    "cboe": "Cboe (via OpenBB)",
    "nasdaq": "Nasdaq (via OpenBB)",
    "tmx": "TMX (via OpenBB)",
    "finra": "FINRA (via OpenBB)",
    "sec": "SEC filings (via OpenBB)",
    "oecd": "OECD (via OpenBB)",
}


class NoData(Exception):
    """The provider answered but had nothing usable for this request."""


def run_chain(
    kind: str,
    fetchers: dict[str, Callable[..., dict]],
    params: dict,
    chain: list[str] | None = None,
) -> dict:
    """Try providers in order. Returns {"provider", "data", "attempts"} or raises with every attempt."""
    attempts: list[dict] = []
    for provider in chain or CHAINS[kind]:
        fetch = fetchers.get(provider)
        if fetch is None:
            continue
        started = time.perf_counter()
        try:
            data = fetch(**params)
        except Exception as exc:  # any provider failure moves on to the next provider
            attempts.append(
                {
                    "provider": provider,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "ms": round((time.perf_counter() - started) * 1000),
                }
            )
            continue
        attempts.append({"provider": provider, "ok": True, "error": None, "ms": round((time.perf_counter() - started) * 1000)})
        return {
            "provider": provider,
            "provider_name": PROVIDER_NAMES.get(provider, provider),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "attempts": attempts,
        }
    raise ChainFailed(kind, attempts)


class ChainFailed(Exception):
    def __init__(self, kind: str, attempts: list[dict]):
        self.kind = kind
        self.attempts = attempts
        tried = ", ".join(a["provider"] for a in attempts) or "none"
        super().__init__(f"no provider could serve {kind} (tried: {tried})")


# --------------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------------


def _num(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def field(record: dict, *candidates: str) -> dict | None:
    """First present, non-null candidate as {"value", "field"}; keeps which provider field was used."""
    for name in candidates:
        if name in record and record[name] is not None:
            value = record[name]
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                continue
            return {"value": value, "field": name}
    return None


def numeric(record: dict, *candidates: str) -> dict | None:
    for name in candidates:
        found = field(record, name)
        if found and _num(found["value"]) is not None:
            return {"value": _num(found["value"]), "field": name}
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc).isoformat()
    return str(value)


RANGE_DAYS = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1827, "MAX": 365 * 40}


def start_date(range_: str) -> date:
    return date.today() - timedelta(days=RANGE_DAYS.get(range_.upper(), 366))


# --------------------------------------------------------------------------------------------------
# Yahoo (yfinance library, Apache-2.0)
# --------------------------------------------------------------------------------------------------


def _yf():
    import yfinance

    return yfinance


_FAST_INFO_FIELDS = {
    "price": "lastPrice",
    "previous_close": "previousClose",
    "open": "open",
    "day_high": "dayHigh",
    "day_low": "dayLow",
    "volume": "lastVolume",
    "market_cap": "marketCap",
    "year_high": "yearHigh",
    "year_low": "yearLow",
}


def yahoo_quote(symbol: str) -> dict:
    fi = _yf().Ticker(symbol).fast_info

    # fast_info fetches lazily and raises a bare KeyError for any field it could not get, which hides
    # the real cause (e.g. a network error). Read each field on its own and keep the first real error.
    errors: list[str] = []

    def get(name: str):
        try:
            return fi[name]
        except Exception as exc:
            cause = exc.__cause__ or exc.__context__ or exc
            errors.append(f"{name}: {type(cause).__name__}: {cause}")
            return None

    fields = {}
    for key, name in _FAST_INFO_FIELDS.items():
        value = _num(get(name))
        if value is not None:
            fields[key] = {"value": value, "field": f"fast_info.{name}"}
    if "price" not in fields:
        raise NoData(f"no price for {symbol}" + (f" ({errors[0][:200]})" if errors else ""))
    return {
        "symbol": symbol.upper(),
        "currency": get("currency"),
        "exchange": get("exchange"),
        "fields": fields,
    }


def yahoo_history(symbol: str, range: str = "1Y", interval: str = "1d", adjusted: bool = False) -> dict:
    # adjusted=True: prices adjusted for splits and dividends (needed for backtests: an unadjusted
    # 4-for-1 split looks like a 75% crash). Charts show unadjusted prices, as traded.
    df = _yf().Ticker(symbol).history(start=start_date(range).isoformat(), interval=interval, auto_adjust=adjusted)
    if df is None or df.empty:
        raise NoData(f"no history for {symbol}")
    bars = []
    for ts, row in df.iterrows():
        o, h, l, c = (_num(row.get(k)) for k in ("Open", "High", "Low", "Close"))
        if None in (o, h, l, c):
            continue
        bars.append({"time": ts.date().isoformat() if interval.endswith(("d", "wk", "mo")) else int(ts.timestamp()),
                     "open": o, "high": h, "low": l, "close": c, "volume": _num(row.get("Volume")) or 0})
    if not bars:
        raise NoData(f"no usable bars for {symbol}")
    return {"symbol": symbol.upper(), "interval": interval, "adjusted": adjusted, "bars": bars}


def yahoo_profile(symbol: str) -> dict:
    info = _yf().Ticker(symbol).info or {}
    if not (info.get("longName") or info.get("shortName")):
        raise NoData(f"no profile for {symbol}")
    return {
        "symbol": symbol.upper(),
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "employees": info.get("fullTimeEmployees"),
        "description": info.get("longBusinessSummary"),
    }


def yahoo_news(symbol: str, limit: int = 20) -> dict:
    items = []
    for raw in (_yf().Ticker(symbol).news or [])[:limit]:
        c = raw.get("content", raw)  # yfinance changed shape in 2025; support both
        url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
        items.append({
            "title": c.get("title"),
            "url": url,
            "published": _iso(c.get("pubDate") or c.get("providerPublishTime")),
            "source": (c.get("provider") or {}).get("displayName") or c.get("publisher"),
            "summary": c.get("summary"),
        })
    items = [i for i in items if i["title"]]
    if not items:
        raise NoData(f"no news for {symbol}")
    return {"symbol": symbol.upper(), "items": items}


STATEMENTS = ("income", "balance", "cash")


def _check_statement(statement: str, period: str) -> None:
    if statement not in STATEMENTS:
        raise ValueError(f"statement must be one of {STATEMENTS}")
    if period not in ("annual", "quarter"):
        raise ValueError("period must be 'annual' or 'quarter'")


def statement_from_frame(df, statement: str, period: str, symbol: str) -> dict:
    """yfinance statement DataFrame (rows = line items, columns = period end dates) -> FinHub shape."""
    if df is None or getattr(df, "empty", True):
        raise NoData(f"no {statement} statement for {symbol}")
    cols = list(df.columns)[:8]
    periods = [c.date().isoformat() if hasattr(c, "date") else str(c) for c in cols]
    rows = []
    for item in df.index:
        values = [_num(df.at[item, c]) for c in cols]
        if any(v is not None for v in values):
            rows.append({"field": str(item), "values": values})
    if not rows:
        raise NoData(f"empty {statement} statement for {symbol}")
    return {"symbol": symbol.upper(), "statement": statement, "period": period, "periods": periods, "rows": rows, "currency": None}


def yahoo_statement(symbol: str, statement: str = "income", period: str = "annual") -> dict:
    _check_statement(statement, period)
    t = _yf().Ticker(symbol)
    attr = {"income": "income_stmt", "balance": "balance_sheet", "cash": "cashflow"}[statement]
    df = getattr(t, ("quarterly_" if period == "quarter" else "") + attr)
    out = statement_from_frame(df, statement, period, symbol)
    try:
        out["currency"] = (t.fast_info or {}).get("currency")
    except Exception:
        pass
    return out


_META_FIELDS = {"period_ending", "fiscal_period", "fiscal_year", "symbol", "cik", "currency", "reported_currency", "filing_date", "accepted_date", "calendar_year", "period"}


def statement_from_records(records: list[dict], statement: str, period: str, symbol: str) -> dict:
    """OpenBB statement records (one dict per period) -> FinHub shape (transposed)."""
    records = [r for r in records if r][:8]
    if not records:
        raise NoData(f"no {statement} statement for {symbol}")
    periods = [str(r.get("period_ending") or r.get("fiscal_year") or i)[:10] for i, r in enumerate(records)]
    fields: list[str] = []
    for r in records:
        for k in r:
            if k not in _META_FIELDS and k not in fields:
                fields.append(k)
    rows = []
    for f in fields:
        values = [_num(r.get(f)) for r in records]
        if any(v is not None for v in values):
            rows.append({"field": f, "values": values})
    if not rows:
        raise NoData(f"empty {statement} statement for {symbol}")
    currency = next((r.get("currency") or r.get("reported_currency") for r in records if r.get("currency") or r.get("reported_currency")), None)
    return {"symbol": symbol.upper(), "statement": statement, "period": period, "periods": periods, "rows": rows, "currency": currency}


# --------------------------------------------------------------------------------------------------
# OpenBB providers (cboe, nasdaq, tmx, finra) — imported lazily because OpenBB takes ~30s to load
# --------------------------------------------------------------------------------------------------

_obb = None

# OpenBB's providers hold asyncio locks that are bound to the event loop that first used them, so
# concurrent calls from different threads fail ("Lock ... is bound to a different event loop"). Every
# OpenBB call therefore runs on this one thread. Yahoo calls do not need this and stay parallel.
_OBB_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="openbb")


def on_obb_thread(fn: Callable[..., dict]) -> Callable[..., dict]:
    def run(**kwargs) -> dict:
        return _OBB_THREAD.submit(fn, **kwargs).result()

    run.__name__ = getattr(fn, "__name__", "openbb_call")
    return run


def obb():
    global _obb
    if _obb is None:
        from openbb import obb as loaded

        _obb = loaded
    return _obb


def _first(results) -> dict:
    rows = results.results if hasattr(results, "results") else results
    if isinstance(rows, list):
        if not rows:
            raise NoData("empty result")
        row = rows[0]
    else:
        row = rows
    return row.model_dump() if hasattr(row, "model_dump") else dict(row)


def _rows(results) -> list[dict]:
    rows = results.results if hasattr(results, "results") else results
    rows = rows if isinstance(rows, list) else [rows]
    return [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rows]


def openbb_quote(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        r = _first(obb().equity.price.quote(symbol=symbol, provider=provider))
        price = numeric(r, "last_price", "price", "close", "bid")
        if price is None:
            raise NoData(f"no price for {symbol}")
        return {
            "symbol": symbol.upper(),
            "currency": (field(r, "currency") or {}).get("value"),
            "exchange": (field(r, "exchange", "exchange_name") or {}).get("value"),
            "fields": {
                "price": price,
                "previous_close": numeric(r, "prev_close", "previous_close"),
                "open": numeric(r, "open"),
                "day_high": numeric(r, "high"),
                "day_low": numeric(r, "low"),
                "volume": numeric(r, "volume"),
                "market_cap": numeric(r, "market_cap"),
                "year_high": numeric(r, "year_high", "fifty_two_week_high"),
                "year_low": numeric(r, "year_low", "fifty_two_week_low"),
            },
        }

    return fetch


def openbb_history(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str, range: str = "1Y", interval: str = "1d", adjusted: bool = False) -> dict:
        # These providers return prices as traded; adjusted is reported False so callers can warn.
        rows = _rows(obb().equity.price.historical(symbol=symbol, start_date=start_date(range), interval=interval, provider=provider))
        bars = []
        for r in rows:
            o, h, l, c = (_num(r.get(k)) for k in ("open", "high", "low", "close"))
            if None in (o, h, l, c):
                continue
            d = r.get("date")
            bars.append({"time": d.isoformat()[:10] if hasattr(d, "isoformat") else str(d)[:10],
                         "open": o, "high": h, "low": l, "close": c, "volume": _num(r.get("volume")) or 0})
        if not bars:
            raise NoData(f"no history for {symbol}")
        return {"symbol": symbol.upper(), "interval": interval, "adjusted": False, "bars": bars}

    return fetch


def openbb_profile(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        r = _first(obb().equity.profile(symbol=symbol, provider=provider))
        name = (field(r, "name", "company_name") or {}).get("value")
        if not name:
            raise NoData(f"no profile for {symbol}")
        g = lambda *k: (field(r, *k) or {}).get("value")  # noqa: E731
        return {
            "symbol": symbol.upper(),
            "name": name,
            "sector": g("sector"),
            "industry": g("industry_category", "industry"),
            "country": g("hq_country", "country"),
            "website": g("company_url", "website"),
            "employees": g("employees", "full_time_employees"),
            "description": g("long_description", "short_description", "description"),
        }

    return fetch


def openbb_news(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str, limit: int = 20) -> dict:
        rows = _rows(obb().news.company(symbol=symbol, limit=limit, provider=provider))
        items = [
            {
                "title": r.get("title"),
                "url": r.get("url"),
                "published": _iso(r.get("date")),
                "source": r.get("source") or r.get("publisher"),
                "summary": r.get("text") or r.get("summary"),
            }
            for r in rows[:limit]
            if r.get("title")
        ]
        if not items:
            raise NoData(f"no news for {symbol}")
        return {"symbol": symbol.upper(), "items": items}

    return fetch


def openbb_statement(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str, statement: str = "income", period: str = "annual") -> dict:
        _check_statement(statement, period)
        fn = getattr(obb().equity.fundamental, statement)
        return statement_from_records(_rows(fn(symbol=symbol, period=period, limit=8, provider=provider)), statement, period, symbol)

    return fetch


# --------------------------------------------------------------------------------------------------
# Macro series (OECD). Units come from OpenBB's own field metadata, never from guessing.
# --------------------------------------------------------------------------------------------------

MACRO_SERIES = {
    "unemployment": ("Unemployment rate", lambda o, c, start: o.economy.unemployment(country=c, start_date=start, provider="oecd")),
    "rate_short": ("Short-term interest rate", lambda o, c, start: o.economy.interest_rates(country=c, duration="short", start_date=start, provider="oecd")),
    "rate_long": ("Long-term interest rate (10y)", lambda o, c, start: o.economy.interest_rates(country=c, duration="long", start_date=start, provider="oecd")),
    "cpi": ("CPI inflation (year on year)", lambda o, c, start: o.economy.cpi(country=c, transform="yoy", start_date=start, provider="oecd")),
    "gdp_real": ("Real GDP", lambda o, c, start: o.economy.gdp.real(country=c, start_date=start, provider="oecd")),
}


def unit_of(row) -> tuple[str, str]:
    """(kind, description) for a result row's `value` field.

    kind is "fraction" when OpenBB marks the field as a normalised percent (x-frontend_multiply = 100),
    otherwise "as_reported" with whatever unit text the provider gives (or "not stated").
    """
    fields = getattr(type(row), "model_fields", {})
    extra = (fields.get("value").json_schema_extra if fields.get("value") else None) or {}
    measure = extra.get("x-unit_measurement") or extra.get("x-unit_measurment")  # OpenBB spells it both ways
    if extra.get("x-frontend_multiply") == 100 and measure == "percent":
        return "fraction", "fraction (OpenBB normalised percent)"
    data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
    text = " ".join(str(data[k]) for k in ("unit", "unit_multiplier") if data.get(k) not in (None, "", 0))
    return "as_reported", text or "not stated by the provider"


def macro_series(series: str, country: str = "united_states", years: int = 10) -> dict:
    if series not in MACRO_SERIES:
        raise ValueError(f"series must be one of {list(MACRO_SERIES)}")
    if not re.fullmatch(r"[a-z_]{2,40}", country):
        raise ValueError("country must be lowercase words joined by _, e.g. united_states")
    label, call = MACRO_SERIES[series]
    rows = call(obb(), country, date.today() - timedelta(days=365 * years))
    rows = rows.results if hasattr(rows, "results") else rows
    if not rows:
        raise NoData(f"no {series} data for {country}")
    kind, unit_text = unit_of(rows[0])
    points = []
    for r in rows:
        d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        v = _num(d.get("value"))
        if v is not None and d.get("date") is not None:
            points.append({"date": str(d["date"])[:10], "value": v})
    if not points:
        raise NoData(f"no usable {series} values for {country}")
    points.sort(key=lambda p: p["date"])
    return {"series": series, "label": label, "country": country, "unit_kind": kind, "unit": unit_text, "points": points}


FETCHERS: dict[str, dict[str, Callable[..., dict]]] = {
    "quote": {"yahoo": yahoo_quote, **{p: on_obb_thread(openbb_quote(p)) for p in ("cboe", "nasdaq", "tmx")}},
    "history": {"yahoo": yahoo_history, **{p: on_obb_thread(openbb_history(p)) for p in ("cboe", "nasdaq", "tmx")}},
    "profile": {"yahoo": yahoo_profile, **{p: on_obb_thread(openbb_profile(p)) for p in ("nasdaq", "tmx", "finra")}},
    "news": {"yahoo": yahoo_news, **{p: on_obb_thread(openbb_news(p)) for p in ("nasdaq", "tmx")}},
    "macro": {"oecd": on_obb_thread(macro_series)},
    "statement": {"yahoo": yahoo_statement, **{p: on_obb_thread(openbb_statement(p)) for p in ("sec", "nasdaq", "tmx")}},
}
