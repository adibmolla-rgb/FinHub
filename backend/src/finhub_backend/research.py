"""Research panels: ownership, options chains, calendars, filings, ETF holdings and the yield curve.

Headline figures are Quantities with receipts. Anything derived (a change, a ratio, days to cover) is
computed here from raw counts and prices, because providers disagree on percent versus fraction. Where
a figure can't be computed honestly it is omitted, never estimated.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

from finhub_backend import market
from finhub_backend.receipts import Quantity, Source, Unit

INSIDER_WINDOW_DAYS = 90


def _source(meta: dict, detail: str) -> Source:
    return Source(provider=meta["provider_name"], fetched_at=datetime.fromisoformat(meta["fetched_at"]), detail=detail)


def _computed() -> Source:
    return Source(provider="computed by FinHub")


def _sections(calls: dict) -> tuple[dict, dict, list[dict]]:
    """Run data calls side by side, so one failing provider doesn't blank the whole panel."""

    def one(item):
        name, (kind, params) = item
        try:
            return name, market._fetch(kind, params), None, []
        except market.MarketDataError as exc:
            return name, None, str(exc), exc.attempts

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        results = list(pool.map(one, calls.items()))
    found = {name: res for name, res, _, _ in results if res}
    errors = {name: err for name, _, err, _ in results if err}
    attempts = [a for _, _, _, tried in results for a in tried]
    return found, errors, attempts


# --------------------------------------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------------------------------------


def insider_summary(rows: list[dict], meta: dict, today: date) -> dict | None:
    """Open-market or private trades in common stock over the last 90 days.

    Grants, option exercises, gifts and tax withholding are excluded: they aren't decisions to buy or sell
    at a price. Only SEC filings say enough to tell them apart, so other providers get no summary.
    """
    if not any(r.get("direction") for r in rows):
        return None
    start = (today - timedelta(days=INSIDER_WINDOW_DAYS)).isoformat()
    trades = [
        r for r in rows
        if r["date"] >= start
        and (r.get("type") or "").lower().startswith("open market or private")
        and (r.get("security") or "").lower() == "common stock"
        and (r.get("price") or 0) > 0 and (r.get("shares") or 0) > 0
    ]
    out: dict = {"window_days": INSIDER_WINDOW_DAYS, "trades": len(trades)}
    for key, direction, word in (("sold", "disposition", "sold"), ("bought", "acquisition", "bought")):
        side = [r for r in trades if (r.get("direction") or "").lower() == direction]
        detail = f"SEC Form 4 · {len(side)} trades since {start} · securities_transacted, transaction_price"
        shares = Quantity(value=sum(r["shares"] for r in side), unit=Unit.SHARES, label=f"Shares {word} by insiders", source=_source(meta, detail))
        out[f"{key}_shares"] = shares.receipt()
        out[f"{key}_value"] = Quantity(
            value=sum(r["shares"] * r["price"] for r in side), unit=Unit.CURRENCY, label=f"Value {word} by insiders",
            source=_computed(), formula="Sum of shares × price for each trade", inputs=(shares,),
        ).receipt()
        if key == "sold" and side:
            planned = Quantity(
                value=sum(r["shares"] for r in side if r.get("plan_10b5_1")), unit=Unit.SHARES,
                label="Shares sold with a 10b5-1 plan footnote", source=_source(meta, "Filing footnotes that mention Rule 10b5-1"),
            )
            out["sold_on_plan"] = Quantity(
                value=planned.value / shares.value, unit=Unit.FRACTION, label="Share of sales footnoted as a 10b5-1 plan (a minimum)",
                source=_computed(), formula="Shares sold with a 10b5-1 plan footnote ÷ Shares sold", inputs=(planned, shares),
            ).receipt()
    return out


def short_summary(rows: list[dict], meta: dict) -> dict:
    last = rows[-1]
    src = _source(meta, f"settlement {last['date']} · current_short_position")
    short = Quantity(value=last["short"], unit=Unit.SHARES, label=f"Short interest ({last['date']})", source=src)
    out = {"date": last["date"], "short": short.receipt()}
    if last.get("previous"):
        previous = Quantity(value=last["previous"], unit=Unit.SHARES, label="Previous short interest", source=_source(meta, "previous_short_position"))
        out["change"] = Quantity(
            value=short.value / previous.value - 1, unit=Unit.FRACTION, label="Change since the previous report",
            source=_computed(), formula="Short interest ÷ Previous short interest − 1", inputs=(short, previous),
        ).receipt()
    if last.get("avg_volume"):
        volume = Quantity(value=last["avg_volume"], unit=Unit.SHARES, label="Average daily volume", source=_source(meta, "avg_daily_volume"))
        out["days_to_cover"] = Quantity(
            value=short.value / volume.value, unit=Unit.RATIO, label="Days to cover",
            source=_computed(), formula="Short interest ÷ Average daily volume", inputs=(short, volume),
        ).receipt()
    return out


def ownership(symbol: str) -> dict:
    found, errors, attempts = _sections({
        "insider": ("insider", {"symbol": symbol}),
        "institutional": ("institutional", {"symbol": symbol}),
        "short": ("short_interest", {"symbol": symbol}),
    })
    if not found:
        raise market.MarketDataError(f"no ownership data for {symbol}: " + "; ".join(errors.values()), attempts)
    out: dict = {"symbol": symbol, "errors": errors}
    if res := found.get("insider"):
        out["insider"] = {
            **market._meta(res), "rows": res["data"]["rows"],
            "summary": insider_summary(res["data"]["rows"], res, datetime.now(UTC).date()),
        }
    if res := found.get("institutional"):
        rows = [
            # A holder that just appeared has no base to measure against, so its change stays empty.
            {**r, "change_pct": r["change"] / (r["shares"] - r["change"]) if r.get("change") is not None and r["shares"] - r["change"] > 0 else None}
            for r in res["data"]["rows"]
        ]
        out["institutional"] = {**market._meta(res), "rows": rows}
    if res := found.get("short"):
        rows = res["data"]["rows"]
        out["short"] = {**market._meta(res), "rows": rows, "summary": short_summary(rows, res)}
    return out


# --------------------------------------------------------------------------------------------------
# Options chain
# --------------------------------------------------------------------------------------------------


def _has_market(c: dict | None) -> bool:
    """Quoted on both sides. Without a real bid, a provider's implied volatility is an artefact."""
    return bool(c and (c.get("bid") or 0) > 0 and (c.get("ask") or 0) > 0)


def _sum_receipt(contracts: list[dict], kind: str, field: str, label: str, meta: dict) -> Quantity:
    return Quantity(
        value=sum(c.get(field) or 0 for c in contracts if c["type"] == kind), unit=Unit.COUNT, label=label,
        source=_source(meta, f"{field}, all {kind}s at this expiration"),
    )


def options_view(data: dict, meta: dict) -> dict:
    contracts = data["contracts"]
    fraction = data["iv_unit"] == "fraction"
    strikes: dict[float, dict] = {}
    for c in contracts:
        row = strikes.setdefault(c["strike"], {"strike": c["strike"], "call": None, "put": None})
        mid = (c["bid"] + c["ask"]) / 2 if _has_market(c) else None
        row[c["type"]] = {**c, "mid": mid, "iv": c["iv"] if c.get("iv") and fraction else None}
    rows = [strikes[s] for s in sorted(strikes)]
    summary: dict = {}

    spot = None
    if data.get("underlying"):
        spot = Quantity(
            value=data["underlying"]["value"], unit=Unit.CURRENCY, label=f"{data['symbol']} price the chain was quoted against",
            source=_source(meta, data["underlying"]["field"]),
        )
        summary["underlying"] = spot.receipt()

    if spot and fraction:
        quoted = [
            r for r in rows
            if any(_has_market(r[k]) and (r[k] or {}).get("iv") for k in ("call", "put"))
        ]
        if quoted:
            atm = min(quoted, key=lambda r: abs(r["strike"] - spot.value))
            ivs = [
                Quantity(value=atm[k]["iv"], unit=Unit.FRACTION, label=f"{k.title()} implied vol, strike {atm['strike']:g}", source=_source(meta, "implied_volatility"))
                for k in ("call", "put") if _has_market(atm[k]) and atm[k].get("iv")
            ]
            summary["atm_iv"] = Quantity(
                value=sum(q.value for q in ivs) / len(ivs), unit=Unit.FRACTION, label=f"At-the-money implied vol ({data['expiration']})",
                source=_computed(), formula="Mean of the call and put implied vol at the strike nearest the price", inputs=tuple(ivs),
            ).receipt()

    for key, field, label in (("put_call_volume", "volume", "Put/call volume"), ("put_call_oi", "open_interest", "Put/call open interest")):
        puts = _sum_receipt(contracts, "put", field, f"Put {field.replace('_', ' ')}", meta)
        calls = _sum_receipt(contracts, "call", field, f"Call {field.replace('_', ' ')}", meta)
        if calls.value > 0:
            summary[key] = Quantity(
                value=puts.value / calls.value, unit=Unit.RATIO, label=f"{label} ({data['expiration']})",
                source=_computed(), formula=f"{puts.label} ÷ {calls.label}", inputs=(puts, calls),
            ).receipt()

    smile = [
        {"strike": r["strike"], "call_iv": r["call"]["iv"] if _has_market(r["call"]) else None, "put_iv": r["put"]["iv"] if _has_market(r["put"]) else None}
        for r in rows
    ]
    return {
        "symbol": data["symbol"],
        "expiration": data["expiration"],
        "expirations": data["expirations"],
        "iv_unit": data["iv_unit"],
        "summary": summary,
        "rows": rows,
        "smile": [p for p in smile if p["call_iv"] or p["put_iv"]],
    }


def options_chain(symbol: str, expiration: str | None = None) -> dict:
    res = market._fetch("options_chain", {"symbol": symbol, "expiration": expiration})
    return {**options_view(res["data"], res), **market._meta(res)}


# --------------------------------------------------------------------------------------------------
# Calendars and filings
# --------------------------------------------------------------------------------------------------


def calendar(days: int = 7, symbols: list[str] | None = None, limit: int | None = None) -> dict:
    found, errors, attempts = _sections({
        "earnings": ("earnings_calendar", {"days": days}),
        "economic": ("economic_calendar", {"days": days}),
    })
    if not found:
        raise market.MarketDataError("no calendar data: " + "; ".join(errors.values()), attempts)
    out: dict = {"days": days, "errors": errors}
    if res := found.get("earnings"):
        rows = res["data"]["rows"]
        total = len(rows)
        if symbols:
            wanted = {s.upper() for s in symbols}
            rows = [r for r in rows if r["symbol"].upper() in wanted]
        rows = sorted(rows, key=lambda r: (r["date"], -(r.get("market_cap") or 0)))
        out["earnings"] = {**market._meta(res), "total": total, "rows": rows[:limit] if limit else rows}
    if res := found.get("economic"):
        out["economic"] = {**market._meta(res), "rows": res["data"]["rows"]}
    return out


def filings(symbol: str) -> dict:
    res = market._fetch("filings", {"symbol": symbol})
    return {"symbol": symbol, "rows": res["data"]["rows"], **market._meta(res)}


# --------------------------------------------------------------------------------------------------
# ETF holdings
# --------------------------------------------------------------------------------------------------


def etf_view(data: dict, meta: dict) -> dict:
    fraction = data["weight_kind"] == "fraction"
    unit = Unit.FRACTION if fraction else Unit.AS_REPORTED
    rows = []
    weights = []
    for r in data["rows"]:
        weight = Quantity(value=r["weight"], unit=unit, label=f"{r['symbol']} weight in {data['symbol']}", source=_source(meta, "weight"))
        weights.append(weight)
        rows.append({"symbol": r["symbol"], "name": r["name"], "weight": weight.receipt()})
    out = {"symbol": data["symbol"], "rows": rows, "listed": len(rows)}
    if fraction:
        out["listed_weight"] = Quantity(
            value=sum(w.value for w in weights), unit=Unit.FRACTION, label=f"Weight of the {len(rows)} holdings listed",
            source=_computed(), formula="Sum of the listed weights", inputs=tuple(weights),
        ).receipt()
    return out


def etf_holdings(symbol: str) -> dict:
    res = market._fetch("etf_holdings", {"symbol": symbol})
    return {**etf_view(res["data"], res), **market._meta(res)}


# --------------------------------------------------------------------------------------------------
# Yield curve
# --------------------------------------------------------------------------------------------------


def _curve_before(curves: list[dict], day: str) -> dict | None:
    """The last curve on or before a date. Curves are oldest first."""
    earlier = [c for c in curves if c["date"] <= day]
    return earlier[-1] if earlier else None


def curve_view(data: dict, meta: dict) -> dict:
    curves = data["curves"]
    latest = curves[-1]
    latest_day = date.fromisoformat(latest["date"])
    kind = data["unit_kind"]
    unit = {"percent": Unit.PERCENT, "fraction": Unit.FRACTION}.get(kind, Unit.AS_REPORTED)

    def quantity(point: dict, day: str) -> Quantity:
        q = Quantity(
            value=point["value"], unit=unit, label=f"{point['tenor']} yield ({day})",
            source=_source(meta, f"{point['tenor']} · {day} · unit: {data['unit']}"),
        )
        return q if unit == Unit.AS_REPORTED else q.to(Unit.FRACTION)  # undeclared units are never converted

    def values(curve: dict | None) -> dict[float, float]:
        return {p["years"]: quantity(p, curve["date"]).value for p in curve["points"]} if curve else {}

    month = _curve_before(curves, (latest_day - timedelta(days=30)).isoformat())
    year = _curve_before(curves, (latest_day - timedelta(days=365)).isoformat())
    month_values, year_values = values(month), values(year)
    by_years = {p["years"]: quantity(p, latest["date"]) for p in latest["points"]}
    tenors = [
        {
            "tenor": p["tenor"],
            "years": p["years"],
            "latest": by_years[p["years"]].receipt(),
            "month_ago": month_values.get(p["years"]),
            "year_ago": year_values.get(p["years"]),
        }
        for p in latest["points"]
    ]

    spreads: dict = {}
    if unit != Unit.AS_REPORTED:
        for key, label, long_years, short_years in (("10y_2y", "10-year minus 2-year", 10.0, 2.0), ("10y_3m", "10-year minus 3-month", 10.0, 3 / 12)):
            long_leg = by_years.get(long_years)
            short_leg = next((q for y, q in by_years.items() if abs(y - short_years) < 1e-9), None)
            if long_leg and short_leg:
                spreads[key] = Quantity(
                    value=long_leg.value - short_leg.value, unit=Unit.FRACTION, label=f"{label} ({latest['date']})",
                    source=_computed(), formula=f"{long_leg.label} − {short_leg.label}", inputs=(long_leg, short_leg),
                ).to(Unit.BASIS_POINTS).receipt()
    return {
        "date": latest["date"],
        "month_ago_date": month["date"] if month else None,
        "year_ago_date": year["date"] if year else None,
        "unit_kind": "as_reported" if unit == Unit.AS_REPORTED else "fraction",
        "unit": data["unit"],
        "tenors": tenors,
        "spreads": spreads,
    }


def yield_curve() -> dict:
    res = market._fetch("yield_curve", {})
    return {**curve_view(res["data"], res), **market._meta(res)}
