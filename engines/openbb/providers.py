"""Market data providers for FinHub, run inside the OpenBB engine environment.

Each request walks a provider chain (Yahoo via the yfinance library first, then OpenBB's free
providers) and returns the first success together with a record of every attempt. Field values are
returned raw, with the name of the provider field they came from, so the backend can build receipts.
Nothing here converts units: the backend owns that.
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import time
import urllib.request
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
    "insider": ["sec", "nasdaq"],
    "institutional": ["nasdaq"],
    "short_interest": ["nasdaq", "finra"],
    "options_chain": ["cboe_direct", "cboe", "nasdaq"],
    "earnings_calendar": ["nasdaq"],
    "economic_calendar": ["nasdaq"],
    "filings": ["sec"],
    "etf_holdings": ["nasdaq"],
    "yield_curve": ["treasury", "federal_reserve"],
    "factors": ["famafrench"],
    "cot_overview": ["cftc"],
    "cot_market": ["cftc"],
    "fed_rates": ["federal_reserve"],
    "fed_money": ["federal_reserve_h6"],
    "fed_expectations": ["federal_reserve"],
    "filing_text": ["edgar"],
    "find_symbols": ["financedatabase"],
    "find_options": ["financedatabase"],
}

PROVIDER_NAMES = {
    "cboe_direct": "Cboe delayed quotes (cdn.cboe.com)",
    "treasury": "US Treasury (home.treasury.gov)",
    "famafrench": "Kenneth French Data Library (via OpenBB)",
    "edgar": "SEC EDGAR (via edgartools)",
    "financedatabase": "FinanceDatabase",
    "federal_reserve_h6": "Federal Reserve H.6 release (federalreserve.gov)",
    "cftc": "CFTC Commitments of Traders (via OpenBB)",
    "federal_reserve": "Federal Reserve (via OpenBB)",
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

    kind is "fraction" when OpenBB marks the field as a normalised percent (x-frontend_multiply = 100) or the
    row itself says so (OECD CPI: 0.036 with a percent unit and unit_multiplier 100 is 3.6%), otherwise
    "as_reported" with whatever unit text the provider gives (or "not stated").
    """
    fields = getattr(type(row), "model_fields", {})
    extra = (fields.get("value").json_schema_extra if fields.get("value") else None) or {}
    measure = extra.get("x-unit_measurement") or extra.get("x-unit_measurment")  # OpenBB spells it both ways
    if extra.get("x-frontend_multiply") == 100 and measure == "percent":
        return "fraction", "fraction (OpenBB normalised percent)"
    data = row.model_dump() if hasattr(row, "model_dump") else dict(row)
    unit = str(data.get("unit") or "")
    if "percent" in unit.lower() and str(data.get("unit_multiplier")) in ("100", "100.0"):
        return "fraction", f"fraction ({unit}, multiplier 100)"
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


# --------------------------------------------------------------------------------------------------
# Research panels: ownership, options chains, calendars, filings, ETF holdings, yield curve.
# Rows are kept raw. Providers disagree on units (FINRA's change_pct of -12.29 means percent, Nasdaq's
# 0.0897 is a fraction), so only raw counts and prices cross this boundary and the backend derives the rest.
# --------------------------------------------------------------------------------------------------


def _date(value: Any) -> str | None:
    return None if value is None else str(value)[:10]


def _text(value: Any) -> str | None:
    """Provider text, with the placeholders they use for "nothing" turned into None."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text in ("", "-", "--", "N/A", "not-supplied") else text


def _unit_kind(model: Any, name: str, *fraction_measures: str) -> str:
    """"fraction" only when the provider's field metadata declares it; never guessed from the value."""
    fields = getattr(model if isinstance(model, type) else type(model), "model_fields", {})
    extra = (fields[name].json_schema_extra if name in fields else None) or {}
    measure = extra.get("x-unit_measurement") or extra.get("x-unit_measurment")
    if measure == "percent" and extra.get("x-frontend_multiply") == 100:
        return "fraction"
    return "fraction" if measure in fraction_measures else "as_reported"


def insider_rows(rows: list[dict]) -> list[dict]:
    out = [
        {
            "date": _date(r.get("transaction_date")),
            "filed": _date(r.get("filing_date")),
            "owner": _text(r.get("owner_name")),
            "title": _text(r.get("owner_title")),
            "type": _text(r.get("transaction_type")),
            "direction": _text(r.get("acquisition_or_disposition")),  # only SEC filings state this
            "security": _text(r.get("security_type")),
            "shares": _num(r.get("securities_transacted")),
            "price": _num(r.get("transaction_price")),
            "shares_after": _num(r.get("securities_owned") if r.get("securities_owned") is not None else r.get("shares_held")),
            "plan_10b5_1": "10b5-1" in str(r.get("footnote") or ""),
            "url": _text(r.get("filing_url") or r.get("url")),
        }
        for r in rows
    ]
    out = [r for r in out if r["date"] and r["shares"] is not None]
    if not out:
        raise NoData("no insider transactions")
    return sorted(out, key=lambda r: r["date"], reverse=True)


def openbb_insider(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        rows = insider_rows(_rows(obb().equity.ownership.insider_trading(symbol, provider=provider, limit=40)))
        return {"symbol": symbol.upper(), "rows": rows}

    return fetch


def openbb_institutional(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        # Nasdaq's market_value is dropped: it reads as thousands of dollars (Vanguard's 1.4bn AAPL shares
        # came back as 490m) and no unit is declared. Share counts are unambiguous.
        rows = [
            {"owner": _text(r.get("owner_name")), "date": _date(r.get("date")), "shares": _num(r.get("shares_held")), "change": _num(r.get("shares_change"))}
            for r in _rows(obb().equity.ownership.institutional(symbol, provider=provider))
        ]
        rows = [r for r in rows if r["owner"] and r["shares"] is not None]
        if not rows:
            raise NoData(f"no institutional holders for {symbol}")
        return {"symbol": symbol.upper(), "rows": sorted(rows, key=lambda r: r["shares"], reverse=True)[:25]}

    return fetch


def short_rows(rows: list[dict], keep: int = 48) -> list[dict]:
    out = [
        {
            "date": _date(r.get("settlement_date")),
            "short": _num(r.get("current_short_position")),
            "previous": _num(r.get("previous_short_position")),
            "avg_volume": _num(r.get("avg_daily_volume")),
        }
        for r in rows
    ]
    out = sorted((r for r in out if r["date"] and r["short"] is not None), key=lambda r: r["date"])
    if not out:
        raise NoData("no short interest")
    return out[-keep:]


def openbb_short_interest(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        return {"symbol": symbol.upper(), "rows": short_rows(_rows(obb().equity.shorts.short_interest(symbol, provider=provider)))}

    return fetch


def chain_view(rows: list[dict], symbol: str, expiration: str | None, today: date, iv_unit: str) -> dict:
    """One expiration of a chain. A default of a week or more out avoids contracts that expire today."""
    if not rows:
        raise NoData(f"no options for {symbol}")
    expirations = sorted({_date(r.get("expiration")) for r in rows if r.get("expiration")})
    if not expirations:
        raise NoData(f"no expirations for {symbol}")
    if expiration is None:
        week_out = (today + timedelta(days=7)).isoformat()
        expiration = next((e for e in expirations if e >= week_out), expirations[-1])
    elif expiration not in expirations:
        raise NoData(f"{symbol} has no {expiration} expiration")
    contracts = []
    for r in rows:
        strike = _num(r.get("strike"))
        kind = str(r.get("option_type") or "").lower()
        if _date(r.get("expiration")) != expiration or strike is None or kind not in ("call", "put"):
            continue
        contracts.append({
            "strike": strike,
            "type": kind,
            "bid": _num(r.get("bid")),
            "ask": _num(r.get("ask")),
            "last": _num(r.get("last_trade_price")),
            "volume": _num(r.get("volume")),
            "open_interest": _num(r.get("open_interest")),
            "iv": _num(r.get("implied_volatility")),
            "delta": _num(r.get("delta")),
        })
    if not contracts:
        raise NoData(f"no usable {symbol} contracts for {expiration}")
    underlying = next((_num(r.get("underlying_price")) for r in rows if _num(r.get("underlying_price")) is not None), None)
    return {
        "symbol": symbol.upper(),
        "underlying": None if underlying is None else {"value": underlying, "field": "underlying_price"},
        "expirations": expirations,
        "expiration": expiration,
        "iv_unit": iv_unit,
        "contracts": contracts,
    }


def openbb_options_chain(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str, expiration: str | None = None) -> dict:
        result = obb().derivatives.options.chains(symbol, provider=provider).results
        # Cboe declares implied volatility as a decimal (0.2656 = 26.56%).
        return chain_view(result.model_dump(), symbol, expiration, date.today(), _unit_kind(result, "implied_volatility", "decimal"))

    return fetch


CBOE_FEED = "https://cdn.cboe.com/api/global/delayed_quotes/options/{symbol}.json"
_OCC_SYMBOL = re.compile(r"(.+?)(\d{2})(\d{2})(\d{2})([CP])(\d{8})")


def cboe_chain_rows(payload: dict, symbol: str) -> list[dict]:
    """Cboe's delayed-quotes feed -> chain rows. A contract's symbol holds its root, expiry, type and strike.

    The feed mixes in other products (roots like B1SPY) with blank trade times. Keep only this symbol's
    own contracts; an index has several roots of its own (SPX and SPXW).
    """
    data = payload["data"]
    name = symbol.lstrip("^").upper()
    rows = []
    for option in data.get("options") or []:
        match = _OCC_SYMBOL.fullmatch(str(option.get("option") or ""))
        if not match:
            continue
        contract_root, yy, mm, dd, kind, strike = match.groups()
        if not (contract_root.startswith(name) if symbol.startswith("^") else contract_root == name):
            continue
        rows.append({
            "expiration": f"20{yy}-{mm}-{dd}",
            "strike": int(strike) / 1000,
            "option_type": "call" if kind == "C" else "put",
            "bid": option.get("bid"),
            "ask": option.get("ask"),
            "last_trade_price": option.get("last_trade_price"),
            "volume": option.get("volume"),
            "open_interest": option.get("open_interest"),
            "implied_volatility": option.get("iv"),
            "delta": option.get("delta"),
            "underlying_price": data.get("current_price"),
        })
    return rows


def cboe_direct_chain(symbol: str, expiration: str | None = None) -> dict:
    # Read directly because OpenBB's reader crashes on chains containing those other products (SPY, IWM,
    # TSLA and NVDA, as of November 2026). It's the same feed: every value matched on 3,476 AAPL contracts.
    # OpenBB's model declares this feed's iv as a decimal, so 0.2656 means 26.56%.
    if not re.fullmatch(r"\^?[A-Z]{1,6}", symbol.upper()):
        raise NoData(f"Cboe's feed has no contracts under the name {symbol}")
    feed = symbol.upper().replace("^", "_")
    request = urllib.request.Request(CBOE_FEED.format(symbol=feed), headers={"User-Agent": "FinHub"})
    with urllib.request.urlopen(request, timeout=25) as response:
        payload = json.load(response)
    return chain_view(cboe_chain_rows(payload, symbol.upper()), symbol, expiration, date.today(), "fraction")


def earnings_rows(rows: list[dict]) -> list[dict]:
    out = [
        {
            "date": _date(r.get("report_date")),
            "symbol": _text(r.get("symbol")),
            "name": _text(r.get("name")),
            "eps_consensus": _num(r.get("eps_consensus")),
            "eps_previous": _num(r.get("eps_previous")),
            "estimates": _num(r.get("num_estimates")),
            "period": _text(r.get("period_ending")),
            "time": _text(r.get("reporting_time")),
            "market_cap": _num(r.get("market_cap")),
        }
        for r in rows
    ]
    return [r for r in out if r["date"] and r["symbol"]]


def openbb_earnings_calendar(provider: str) -> Callable[..., dict]:
    def fetch(days: int = 7) -> dict:
        today = date.today()
        rows = earnings_rows(_rows(obb().equity.calendar.earnings(start_date=today, end_date=today + timedelta(days=days), provider=provider)))
        if not rows:
            raise NoData("no earnings in that window")
        return {"rows": rows}

    return fetch


def economic_rows(rows: list[dict]) -> list[dict]:
    # Actual, consensus and previous stay text ("1,178.4B", "0.3%"): each event has its own unit.
    out = [
        {
            "date": str(r.get("date"))[:16] if r.get("date") else None,
            "country": _text(r.get("country")),
            "event": _text(r.get("event")),
            "actual": _text(r.get("actual")),
            "consensus": _text(r.get("consensus")),
            "previous": _text(r.get("previous")),
        }
        for r in rows
    ]
    return sorted((r for r in out if r["date"] and r["event"]), key=lambda r: r["date"])


def openbb_economic_calendar(provider: str) -> Callable[..., dict]:
    def fetch(days: int = 7) -> dict:
        today = date.today()
        rows = economic_rows(_rows(obb().economy.calendar(start_date=today, end_date=today + timedelta(days=days), provider=provider)))
        if not rows:
            raise NoData("no economic events in that window")
        return {"rows": rows}

    return fetch


def openbb_filings(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        rows = [
            {
                "date": _date(r.get("filing_date")),
                "form": _text(r.get("report_type")),
                "description": _text(r.get("primary_doc_description")),
                "items": _text(r.get("items")),
                "accession": _text(r.get("accession_number")),
                "url": _text(r.get("report_url")),
            }
            for r in _rows(obb().equity.fundamental.filings(symbol=symbol, provider=provider, limit=100))
        ]
        rows = [r for r in rows if r["date"] and r["form"]]
        if not rows:
            raise NoData(f"no filings for {symbol}")
        return {"symbol": symbol.upper(), "rows": rows}

    return fetch


def is_fund(symbol: str, provider: str) -> bool:
    """Whether a symbol is an ETF or mutual fund. Yahoo labels it; failing that, only funds report costs."""
    try:
        kind = _yf().Ticker(symbol).fast_info.get("quoteType")
    except Exception:
        kind = None
    if kind:
        return str(kind).upper() in ("ETF", "MUTUALFUND")
    info = _first(obb().etf.info(symbol, provider=provider))
    return info.get("expense_ratio") is not None or info.get("aum") is not None


def openbb_etf_holdings(provider: str) -> Callable[..., dict]:
    def fetch(symbol: str) -> dict:
        # Ask first: for a stock, Nasdaq answers with the funds that hold it, in the same shape as a fund's
        # own holdings, so AAPL would show "GXPT, 21%" as if Apple held that fund.
        if not is_fund(symbol, provider):
            raise NoData(f"{symbol} isn't an ETF")
        results = obb().etf.holdings(symbol, provider=provider).results
        rows = [
            {"symbol": _text(d.get("symbol")), "name": _text(d.get("name")), "weight": _num(d.get("weight"))}
            for d in (r.model_dump() for r in results)
        ]
        rows = [r for r in rows if r["weight"] is not None and r["symbol"]]
        if not rows:
            raise NoData(f"no holdings published for {symbol}")
        return {"symbol": symbol.upper(), "weight_kind": _unit_kind(results[0], "weight"), "rows": sorted(rows, key=lambda r: r["weight"], reverse=True)}

    return fetch


def _tenor_years(tenor: str) -> float | None:
    """Years to maturity from a label like "1 Mo", "1.5 Month", "10 Yr" or month_3, year_10, week_4."""
    m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)\s*(mo|month|yr|year|wk|week)s?|(month|year|week)_(\d+))", tenor.strip().lower())
    if not m:
        return None
    number, unit = (float(m[1]), m[2]) if m[1] else (float(m[4]), m[3])
    return number * {"m": 1 / 12, "y": 1.0, "w": 1 / 52}[unit[0]]


def parse_treasury_csv(text: str) -> list[dict]:
    """Treasury's daily par yield curve CSV (percent, newest first) -> curves, oldest first."""
    table = list(csv.reader(io.StringIO(text)))
    if len(table) < 2 or table[0][0].strip().lower() != "date":
        raise NoData("unexpected Treasury file layout")
    tenors = [(i, name.strip(), _tenor_years(name)) for i, name in enumerate(table[0]) if i and _tenor_years(name) is not None]
    curves = []
    for row in table[1:]:
        try:
            day = datetime.strptime(row[0].strip(), "%m/%d/%Y").date().isoformat()
        except (ValueError, IndexError):
            continue
        points = [
            {"tenor": name, "years": years, "value": _num(row[i])}
            for i, name, years in tenors
            if i < len(row) and _num(row[i]) is not None
        ]
        if points:
            curves.append({"date": day, "points": sorted(points, key=lambda p: p["years"])})
    if not curves:
        raise NoData("the Treasury file had no yields")
    return sorted(curves, key=lambda c: c["date"])


TREASURY_CSV = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
    "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)


def treasury_curve() -> dict:
    curves: list[dict] = []
    errors: list[str] = []
    year = date.today().year
    for y in (year - 1, year):  # last year too, for the comparison a year back and for early January
        try:
            request = urllib.request.Request(TREASURY_CSV.format(year=y), headers={"User-Agent": "FinHub"})
            with urllib.request.urlopen(request, timeout=25) as response:
                curves += parse_treasury_csv(response.read().decode("utf-8-sig"))
        except Exception as exc:
            errors.append(f"{y}: {type(exc).__name__}: {str(exc)[:120]}")
    if not curves or curves[-1]["date"][:4] != str(year) and date.today().month > 1:
        raise NoData("; ".join(errors) or f"no {year} Treasury data")
    return {"unit_kind": "percent", "unit": "percent, as published by the Treasury", "curves": sorted(curves, key=lambda c: c["date"])}


def federal_reserve_curve() -> dict:
    results = obb().fixedincome.government.treasury_rates(provider="federal_reserve", start_date=date.today() - timedelta(days=400)).results
    if not results:
        raise NoData("no Federal Reserve yields")
    curves = []
    names = [n for n in type(results[0]).model_fields if _tenor_years(n) is not None]
    for r in results:
        d = r.model_dump()
        points = [{"tenor": n, "years": _tenor_years(n), "value": _num(d.get(n))} for n in names if _num(d.get(n)) is not None]
        if points and d.get("date"):
            curves.append({"date": _date(d["date"]), "points": sorted(points, key=lambda p: p["years"])})
    if not curves:
        raise NoData("no usable Federal Reserve yields")
    kind = _unit_kind(results[0], names[0])
    return {
        "unit_kind": kind,
        "unit": "fraction (OpenBB normalised percent)" if kind == "fraction" else "not stated by the provider",
        "curves": sorted(curves, key=lambda c: c["date"]),
    }


# --------------------------------------------------------------------------------------------------
# Factors, positioning and the Federal Reserve
# --------------------------------------------------------------------------------------------------

FACTOR_REGIONS = ("america", "north_america", "europe", "japan", "asia_pacific_ex_japan", "developed", "developed_ex_us", "emerging")
FACTOR_FIELDS = ("mkt_rf", "smb", "hml", "rmw", "cma", "rf")


def _percent_declared(model: Any, name: str) -> bool:
    fields = getattr(model if isinstance(model, type) else type(model), "model_fields", {})
    extra = (fields[name].json_schema_extra if name in fields else None) or {}
    measure = extra.get("x-unit_measurement") or extra.get("x-unit_measurment")
    return measure == "percent" and extra.get("x-frontend_multiply") != 100


def merge_factor_rows(five: list[dict], momentum: list[dict]) -> list[dict]:
    """One row per month. The US data calls momentum `mom`; every other region calls it `wml`."""
    rows = {_date(r["date"]): {"date": _date(r["date"]), **{k: _num(r.get(k)) for k in FACTOR_FIELDS}, "mom": None} for r in five if r.get("date")}
    for r in momentum:
        day = _date(r.get("date"))
        if day in rows:
            value = r.get("mom") if r.get("mom") is not None else r.get("wml")
            rows[day]["mom"] = _num(value)
    return [rows[day] for day in sorted(rows)]


def famafrench_factors(region: str = "america", years: int = 30) -> dict:
    if region not in FACTOR_REGIONS:
        raise ValueError(f"region must be one of {FACTOR_REGIONS}")

    def call(factor: str) -> list:
        start = date(date.today().year - int(years), 1, 1).isoformat()
        return obb().famafrench.factors(region=region, factor=factor, frequency="monthly", start_date=start, provider="famafrench").results

    five = call("5_factors")
    if not five:
        raise NoData(f"no factor data for {region}")
    if not _percent_declared(five[0], "mkt_rf"):
        raise NoData("the provider no longer declares factor returns as percent")
    momentum, problem = [], None
    try:
        momentum = [r.model_dump() for r in call("momentum")]
    except Exception as exc:  # the five main factors are still worth showing
        problem = f"{type(exc).__name__}: {str(exc)[:160]}"
    return {
        "region": region,
        "unit_kind": "percent",
        "unit": "percent per month, as published in the Data Library",
        "rows": merge_factor_rows([r.model_dump() for r in five], momentum),
        "momentum_error": problem,
    }


def _once_more_on_timeout(call: Callable[[], Any]) -> Any:
    """CFTC's first download can run past OpenBB's 10-second limit, and a second try usually finds it ready."""
    try:
        return call()
    except Exception as exc:
        if "Timeout" not in f"{type(exc).__name__}: {exc}":
            raise
        return call()


def _rank_market(query: str, name: str) -> tuple:
    q, n = query.strip().lower(), name.strip().lower()
    return (0 if n == q else 1 if n.startswith(q) else 2, len(n), n)


def best_cot_matches(query: str, rows: list[dict]) -> list[dict]:
    """Closest name first. The provider sorts by name, so "s&p" would otherwise land on an interest rate swap."""
    return sorted(rows, key=lambda r: _rank_market(query, r.get("name") or ""))


def _cot_sides(meta: dict) -> dict:
    return {side: (meta.get(side) or {}).get("zone") for side in ("large_specs", "small_specs", "commercials")}


COT_ALIASES = {"oil": "WTI Oil", "crude": "WTI Oil", "crude oil": "WTI Oil", "natural gas": "Nat Gas", "spx": "S&P 500", "sp500": "S&P 500"}
_COT_CODE = re.compile(r"(?:CFTC_)?(?=[0-9A-Z]*[0-9])[0-9A-Z]{6}")


def curated_cot_code(query: str, labels: dict[str, str]) -> str | None:
    """The code for one of the major markets: its name, an alias, or a part of the name only it has ("wti")."""
    q = COT_ALIASES.get(query.strip().lower(), query).strip().lower()
    by_label = {label.lower(): code for label, code in labels.items()}
    if q in by_label:
        return by_label[q]
    partial = [code for label, code in by_label.items() if q in label]  # too short a fragment is a guess, so it goes to the search
    return partial[0] if len(q) >= 3 and len(partial) == 1 else None


def cot_market(market: str) -> dict:
    """Positioning for one market. Always asks by contract code: given a name, the provider returns one row per
    similar contract in the same shape as a history ("Gold" gave three rows, not 30 years of gold)."""
    query = market.strip()
    if not query:
        raise ValueError("market is empty")
    from openbb_cftc.utils.cot_markets import COT_MARKETS

    cftc = obb().cftc
    matches: list[dict] = []
    code = query if _COT_CODE.fullmatch(query) else curated_cot_code(query, {m["label"]: m["code"] for m in COT_MARKETS})
    if not code:
        found = best_cot_matches(query, [r.model_dump() for r in cftc.cot_search(query=query, provider="cftc").results])
        if not found:
            raise NoData(f"no CFTC market matches {query}")
        matches = [{"name": r.get("name"), "category": r.get("category")} for r in found[:12]]
        code = found[0]["code"]
    result = _once_more_on_timeout(lambda: cftc.cot_positioning(code=code, provider="cftc"))
    rows = [r.model_dump() for r in result.results]
    if not rows:
        raise NoData(f"no positioning data for {query}")
    meta = (result.extra or {}).get("results_metadata") or {}
    return {
        "query": query,
        "market": meta.get("market") or query,
        "contract": meta.get("contract"),
        "lookback_weeks": meta.get("lookback_weeks"),
        "zones": _cot_sides(meta),
        "matches": matches,
        "rows": [
            {
                "date": _date(r.get("report_date")),
                "open_interest": _num(r.get("open_interest")),
                **{f"{side}_net": _num(r.get(f"{side}_net")) for side in ("large_specs", "small_specs", "commercials")},
                **{f"{side}_score": _num(r.get(f"{side}_score")) for side in ("large_specs", "small_specs", "commercials")},
            }
            for r in sorted(rows, key=lambda r: str(r.get("report_date")))
        ],
    }


def cot_overview() -> dict:
    rows = _once_more_on_timeout(lambda: obb().cftc.cot_index(provider="cftc")).results
    if not rows:
        raise NoData("no CFTC overview")
    return {
        "unit": "net position as a percent of open interest",
        "rows": [
            {
                "market": d.get("market"),
                "date": _date(d.get("report_date")),
                "open_interest": _num(d.get("open_interest")),
                **{
                    f"{side}_{field}": _num(d.get(f"{side}{suffix}"))
                    for side in ("large_specs", "small_specs", "commercials")
                    for field, suffix in (("score", ""), ("change", "_change"), ("pct", "_net_pct_oi"))
                },
                **{f"{side}_zone": d.get(f"{side}_zone") for side in ("large_specs", "small_specs", "commercials")},
            }
            for d in (r.model_dump() for r in rows)
        ],
    }


def fed_rates(years: int = 5) -> dict:
    start = (date.today() - timedelta(days=366 * int(years))).isoformat()
    rate = obb().fixedincome.rate
    effr, sofr = rate.effr(provider="federal_reserve", start_date=start).results, rate.sofr(provider="federal_reserve", start_date=start).results
    if not effr:
        raise NoData("no effective federal funds rate")
    return {
        "unit_kind": _unit_kind(effr[0], "rate"),
        "unit": "fraction (OpenBB normalised percent)",
        "effr": [{"date": _date(r.date), "rate": _num(r.rate), "upper": _num(r.target_range_upper), "lower": _num(r.target_range_lower)} for r in effr],
        "sofr": [{"date": _date(r.date), "rate": _num(r.rate)} for r in sofr] if sofr and _unit_kind(sofr[0], "rate") == _unit_kind(effr[0], "rate") else [],
    }


H6_CSV = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H6&series=798e2796917702a5f8423426ba7e6b42"
    "&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package"
)


def parse_h6_csv(text: str) -> list[dict]:
    """The Fed's H.6 file, billions of dollars. `M2.M` is seasonally adjusted and `M2_N.M` is not."""
    table = list(csv.reader(io.StringIO(text)))
    header = next((row for row in table if row and row[0].strip() == "Time Period"), None)
    if not header or "M1.M" not in header or "M2.M" not in header:
        raise NoData("unexpected H.6 file layout")
    m1, m2 = header.index("M1.M"), header.index("M2.M")
    rows = []
    for row in table[table.index(header) + 1:]:
        if len(row) <= max(m1, m2) or not re.fullmatch(r"\d{4}-\d{2}", row[0].strip()):
            continue
        billions = _num(row[m2])
        if billions is not None:
            first = _num(row[m1])
            rows.append({"date": f"{row[0].strip()}-01", "m1": None if first is None else first * 1e9, "m2": billions * 1e9})
    if not rows:
        raise NoData("the H.6 file had no M2 values")
    return rows


def fed_money(years: int = 6) -> dict:
    """Read directly: OpenBB's money_measures has `adjusted` backwards, so True returns the unadjusted series."""
    request = urllib.request.Request(H6_CSV, headers={"User-Agent": "FinHub"})
    with urllib.request.urlopen(request, timeout=25) as response:
        rows = parse_h6_csv(response.read().decode("utf-8-sig"))
    start = date(date.today().year - int(years), 1, 1).isoformat()
    return {"unit": "US dollars, seasonally adjusted", "rows": [r for r in rows if r["date"] >= start]}


def fed_expectations() -> dict:
    results = obb().economy.survey.inflation_expectations(provider="federal_reserve").results
    if not results:
        raise NoData("no inflation expectations")
    if not _percent_declared(results[0], "infcpi1yr"):
        raise NoData("the provider no longer declares inflation expectations as percent")
    return {
        "unit_kind": "percent",
        "unit": "percent, Survey of Professional Forecasters median",
        "rows": [{"date": _date(r.date), "cpi_1y": _num(r.infcpi1yr), "cpi_10y": _num(r.infcpi10yr)} for r in results if r.infcpi1yr is not None or r.infcpi10yr is not None],
    }


# --------------------------------------------------------------------------------------------------
# Reading filings
# --------------------------------------------------------------------------------------------------


def _section_title(item: str, text: str) -> str:
    """ "Item 1A.    Risk Factors" from the section's own first line, with the part added where one is named."""
    part, _, short = item.rpartition(", ")
    first = next((line.strip() for line in text.splitlines() if line.strip()), short)
    title = " ".join(first.split())
    if not title.lower().startswith("item"):
        title = short
    elif len(title) > 90:
        title = f"{title[:87].rstrip()}…"
    return f"{part} · {title}" if part else title


def _tidy(text: str) -> str:
    return text.replace("\xa0", " ").strip()


def filing_sections(report, whole_text: Callable[[], str]) -> list[dict]:
    """The filing's own items where it has them. Otherwise the whole text, as one section. Empty items are left out."""
    sections = []
    for item in getattr(report, "items", None) or []:
        try:
            text = _tidy(str(report[item] or ""))
        except Exception:  # one unreadable item shouldn't lose the rest
            continue
        if text:
            sections.append({"id": item, "title": _section_title(item, text), "text": text})
    if not sections:
        text = _tidy(whole_text() or "")
        if not text:
            raise NoData("this filing has no readable text")
        sections = [{"id": "full", "title": "Full text", "text": text}]
    return sections


def edgar_filing(identity: str, symbol: str | None = None, form: str = "10-K", accession: str | None = None) -> dict:
    data = os.environ.get("FINHUB_DATA_DIR")
    if data:  # keep edgartools' downloads with FinHub's other files
        os.environ.setdefault("EDGAR_LOCAL_DATA_DIR", os.path.join(data, "edgar"))
    import edgar

    edgar.set_identity(identity)
    if accession:
        filing = edgar.find(accession)
        if filing is None:
            raise NoData(f"no filing with accession number {accession}")
    else:
        filing = edgar.Company(symbol).get_filings(form=form).latest()
        if filing is None:
            raise NoData(f"{symbol} has no {form} filings")
    report = None
    try:
        report = filing.obj()
    except Exception:  # some forms have no structured reader, and the plain text is still worth having
        pass
    return {
        "company": filing.company,
        "form": filing.form,
        "filed": str(filing.filing_date)[:10],
        "accession": filing.accession_no,
        "url": getattr(filing, "homepage_url", None) or getattr(filing, "filing_url", None),
        "sections": filing_sections(report, filing.text),
    }


# --------------------------------------------------------------------------------------------------
# Finding symbols
# --------------------------------------------------------------------------------------------------

CAP_ORDER = {"Mega Cap": 0, "Large Cap": 1, "Mid Cap": 2, "Small Cap": 3, "Micro Cap": 4, "Nano Cap": 5}
US_EXCHANGES = ("NYQ", "NMS", "NGM", "NCM", "ASE", "PCX", "BTS")
_find_frames: dict[str, Any] = {}
_find_everything: dict[str, Any] = {}


def _find_frame(kind: str):
    """Each company's main listing, and its US one. The raw list has an Apple row for every exchange in the world, but
    main listings alone would hide TSM, ASML and BP, which count their home markets as the main one."""
    if kind not in _find_frames:
        import financedatabase as fd

        database = {"equities": fd.Equities, "etfs": fd.ETFs}[kind]()
        everything = database.select(only_primary_listing=False, exclude_delisted=True)
        main = database.select(only_primary_listing=True, exclude_delisted=True)
        _find_everything[kind] = everything
        _find_frames[kind] = everything[everything.index.isin(main.index) | everything["exchange"].isin(US_EXCHANGES)]
    return _find_frames[kind]


def rank_found(rows: list[dict], query: str) -> list[dict]:
    """The exact ticker, then the word in the name ("gold" before "Golden"), then descriptions, biggest first within each."""
    q = query.strip().lower()
    word = re.compile(rf"\b{re.escape(q)}\b") if q else None

    def order(row: dict) -> tuple:
        name = (row.get("name") or "").lower()
        place = 0 if q and row["symbol"].lower() == q else 1 if q and word.search(name) else 2 if q and q in name else 3
        return (place, CAP_ORDER.get(row.get("market_cap"), 9), "." in row["symbol"], name)

    return sorted(rows, key=order)


def find_symbols(kind: str = "equities", query: str = "", country: str | None = None, sector: str | None = None, market_cap: str | None = None, limit: int = 200) -> dict:
    frame = _find_frame(kind)
    if country and "country" in frame:
        frame = frame[frame["country"] == country]
    if sector:
        frame = frame[frame["sector" if "sector" in frame else "category_group"] == sector]
    if market_cap and "market_cap" in frame:
        frame = frame[frame["market_cap"] == market_cap]
    q = query.strip()
    if q:
        # A ticker typed in full is found on any exchange, however minor.
        everything = _find_everything.get(kind)
        if everything is not None and not (country or sector or market_cap):
            exact = everything[everything.index.str.lower() == q.lower()]
            if len(exact) and not exact.index.isin(frame.index).all():
                frame = everything[everything.index.isin(frame.index) | everything.index.isin(exact.index)]
        matches = frame.index.str.lower() == q.lower()
        for column in ("name", "summary"):
            if column in frame:
                matches = matches | frame[column].fillna("").str.contains(q, case=False, regex=False)
        frame = frame[matches]
    fields = ("name", "sector", "industry", "category_group", "category", "country", "exchange", "currency", "market_cap")
    total = int(len(frame))
    if "market_cap" in frame:  # the biggest first, so a broad search is still ranked when it's cut to the first few thousand
        frame = frame.iloc[frame["market_cap"].map(CAP_ORDER).fillna(9).argsort(kind="stable")]
    rows = [{"symbol": str(symbol), **{f: (None if row.get(f) != row.get(f) else row.get(f)) for f in fields if f in row}} for symbol, row in frame.head(5000).to_dict("index").items()]
    return {"kind": kind, "total": total, "rows": rank_found(rows, q)[: int(limit)]}


def find_options() -> dict:
    frame = _find_frame("equities")
    etfs = _find_frame("etfs")
    values = lambda column, f=frame: sorted(str(v) for v in f[column].dropna().unique())  # noqa: E731
    return {"countries": values("country"), "sectors": values("sector"), "market_caps": list(CAP_ORDER), "etf_groups": values("category_group", etfs)}


FETCHERS: dict[str, dict[str, Callable[..., dict]]] = {
    "find_symbols": {"financedatabase": find_symbols},
    "find_options": {"financedatabase": find_options},
    "filing_text": {"edgar": edgar_filing},
    "factors": {"famafrench": on_obb_thread(famafrench_factors)},
    "cot_overview": {"cftc": on_obb_thread(cot_overview)},
    "cot_market": {"cftc": on_obb_thread(cot_market)},
    "fed_rates": {"federal_reserve": on_obb_thread(fed_rates)},
    "fed_money": {"federal_reserve_h6": fed_money},
    "fed_expectations": {"federal_reserve": on_obb_thread(fed_expectations)},
    "insider": {p: on_obb_thread(openbb_insider(p)) for p in ("sec", "nasdaq")},
    "institutional": {"nasdaq": on_obb_thread(openbb_institutional("nasdaq"))},
    "short_interest": {p: on_obb_thread(openbb_short_interest(p)) for p in ("nasdaq", "finra")},
    "options_chain": {"cboe_direct": cboe_direct_chain, **{p: on_obb_thread(openbb_options_chain(p)) for p in ("cboe", "nasdaq")}},
    "earnings_calendar": {"nasdaq": on_obb_thread(openbb_earnings_calendar("nasdaq"))},
    "economic_calendar": {"nasdaq": on_obb_thread(openbb_economic_calendar("nasdaq"))},
    "filings": {"sec": on_obb_thread(openbb_filings("sec"))},
    "etf_holdings": {"nasdaq": on_obb_thread(openbb_etf_holdings("nasdaq"))},
    "yield_curve": {"treasury": treasury_curve, "federal_reserve": on_obb_thread(federal_reserve_curve)},
    "quote": {"yahoo": yahoo_quote, **{p: on_obb_thread(openbb_quote(p)) for p in ("cboe", "nasdaq", "tmx")}},
    "history": {"yahoo": yahoo_history, **{p: on_obb_thread(openbb_history(p)) for p in ("cboe", "nasdaq", "tmx")}},
    "profile": {"yahoo": yahoo_profile, **{p: on_obb_thread(openbb_profile(p)) for p in ("nasdaq", "tmx", "finra")}},
    "news": {"yahoo": yahoo_news, **{p: on_obb_thread(openbb_news(p)) for p in ("nasdaq", "tmx")}},
    "macro": {"oecd": on_obb_thread(macro_series)},
    "statement": {"yahoo": yahoo_statement, **{p: on_obb_thread(openbb_statement(p)) for p in ("sec", "nasdaq", "tmx")}},
}
