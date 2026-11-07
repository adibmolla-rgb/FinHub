"""Research panels: ownership, options chains, calendars, filings, ETF holdings and the yield curve.

Headline figures are Quantities with receipts. Anything derived (a change, a ratio, days to cover) is
computed here from raw counts and prices, because providers disagree on percent versus fraction. Where
a figure can't be computed honestly it is omitted, never estimated.
"""

from __future__ import annotations

import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

from finhub_backend import market, store
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


# --------------------------------------------------------------------------------------------------
# Fama-French factors
# --------------------------------------------------------------------------------------------------

FACTOR_REGIONS = {
    "US": ("america", "United States"),
    "NA": ("north_america", "North America"),
    "EUROPE": ("europe", "Europe"),
    "JAPAN": ("japan", "Japan"),
    "ASIA": ("asia_pacific_ex_japan", "Asia Pacific excluding Japan"),
    "DEVELOPED": ("developed", "Developed markets"),
    "EXUS": ("developed_ex_us", "Developed markets excluding the US"),
    "EMERGING": ("emerging", "Emerging markets"),
}
FACTORS = (
    ("mkt_rf", "Market", "All stocks minus the 1-month T-bill"),
    ("smb", "Size", "Small companies minus big ones"),
    ("hml", "Value", "Cheap on book value minus expensive"),
    ("rmw", "Profitability", "Robust profits minus weak"),
    ("cma", "Investment", "Companies investing conservatively minus aggressively"),
    ("mom", "Momentum", "Recent winners minus recent losers"),
)


def _read(view, res: dict, *args) -> dict:
    """Run a view over a provider's answer. An answer it can't honestly read is a data error, not a crash."""
    try:
        return view(*args)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        raise market.MarketDataError(f"couldn't read the data from {res.get('provider_name')}: {exc}", res.get("attempts", [])) from exc


def factor_stats(key: str, label: str, description: str, rows: list[dict], meta: dict) -> dict | None:
    """Rows hold fractions. Fewer than two months can't give a volatility, so the factor is left out."""
    points = [(r["date"], r[key]) for r in rows if r.get(key) is not None]
    if len(points) < 2:
        return None
    values = [v for _, v in points]
    n = len(values)
    mean, sd = statistics.fmean(values), statistics.stdev(values)
    span = f"{points[0][0]} to {points[-1][0]}, {n} months"

    def computed(value: float, unit: Unit, name: str, formula: str) -> dict:
        return Quantity(value=value, unit=unit, label=f"{label}: {name}", source=_computed(), formula=f"{formula} ({span})").receipt()

    growth, curve = 1.0, []
    for day, value in points:
        growth *= 1 + value
        curve.append([day, growth])
    out = {
        "key": key,
        "label": label,
        "description": description,
        "months": n,
        "latest": Quantity(
            value=points[-1][1], unit=Unit.FRACTION, label=f"{label} ({points[-1][0]})", source=_source(meta, f"{key} · {points[-1][0]} · unit: {meta.get('unit_text')}"),
        ).receipt(),
        "annual_return": computed(mean * 12, Unit.FRACTION, "average return per year", "Mean monthly return × 12"),
        "annual_volatility": computed(sd * math.sqrt(12), Unit.FRACTION, "volatility per year", "Standard deviation of monthly returns × √12"),
        "t_stat": computed(mean / (sd / math.sqrt(n)), Unit.RATIO, "t-statistic", "Mean ÷ (standard deviation ÷ √months)") if sd > 0 else None,
        "curve": curve,
    }
    if n >= 12:
        last_year = 1.0
        for value in values[-12:]:
            last_year *= 1 + value
        out["last_12m"] = computed(last_year - 1, Unit.FRACTION, "last 12 months", "Compound of the latest 12 monthly returns")
    return out


def factors_view(data: dict, meta: dict) -> dict:
    if data["unit_kind"] != "percent":
        raise ValueError("factor returns must be declared as percent")
    if not data["rows"]:
        raise ValueError("no factor rows")
    scale = Quantity(value=1, unit=Unit.PERCENT, label="scale", source=_computed()).to(Unit.FRACTION).value  # 1% as a fraction
    keys = [k for k, _, _ in FACTORS] + ["rf"]
    rows = [{"date": r["date"], **{k: (None if r.get(k) is None else r[k] * scale) for k in keys}} for r in data["rows"]]
    enriched = {**meta, "unit_text": data["unit"]}
    factors = [f for f in (factor_stats(k, label, text, rows, enriched) for k, label, text in FACTORS) if f]
    if not factors:
        raise ValueError("no factor has enough data")
    warnings = [f"Momentum is missing: {data['momentum_error']}"] if data.get("momentum_error") else []
    return {"start": rows[0]["date"], "end": rows[-1]["date"], "months": len(rows), "unit": data["unit"], "factors": factors, "rows": rows, "warnings": warnings}


def factors(region: str = "US", years: int = 30) -> dict:
    code = region.upper()
    if code not in FACTOR_REGIONS:
        raise ValueError(f"region must be one of {', '.join(FACTOR_REGIONS)}")
    name, label = FACTOR_REGIONS[code]
    res = market._fetch("factors", {"region": name, "years": years})
    view = _read(factors_view, res, res["data"], res)
    return {"region": code, "region_label": label, "regions": {k: v[1] for k, v in FACTOR_REGIONS.items()}, "years": years, **view, **market._meta(res)}


# --------------------------------------------------------------------------------------------------
# Commitments of Traders
# --------------------------------------------------------------------------------------------------

COT_SIDES = (("large_specs", "Large speculators"), ("small_specs", "Small speculators"), ("commercials", "Commercials (hedgers)"))
COT_HISTORY_WEEKS = 156


def cot_market_view(data: dict, meta: dict) -> dict:
    """Shares of open interest are worked out here from contract counts, not taken from the provider's percent."""
    rows = [r for r in data["rows"] if r.get("date") and r.get("open_interest")]
    if not rows:
        raise ValueError("no usable positioning rows")
    latest, before = rows[-1], rows[-2] if len(rows) > 1 else None
    day = latest["date"]

    def raw(field: str, label: str, row: dict) -> Quantity:
        return Quantity(value=row[field], unit=Unit.COUNT, label=f"{label} ({row['date']})", source=_source(meta, f"{field} · {row['date']} · contracts"))

    interest = raw("open_interest", "Open interest", latest)
    sides = []
    for side, label in COT_SIDES:
        net_field, score_field = f"{side}_net", f"{side}_score"
        if latest.get(net_field) is None:
            continue
        net = raw(net_field, f"{label} net position", latest)
        entry = {
            "key": side,
            "label": label,
            "net": net.receipt(),
            "share_of_oi": Quantity(
                value=net.value / interest.value, unit=Unit.FRACTION, label=f"{label} net ÷ open interest ({day})",
                source=_computed(), formula=f"{net.label} ÷ {interest.label}", inputs=(net, interest),
            ).receipt(),
            "zone": data.get("zones", {}).get(side),
        }
        if latest.get(score_field) is not None:
            weeks = data.get("lookback_weeks")
            entry["score"] = Quantity(
                value=latest[score_field], unit=Unit.RATIO, label=f"{label} score, 0 to 100 ({day})",
                source=_source(meta, f"{score_field} · {day} · position within its range over the last {weeks} weeks"),
            ).receipt()
        if before and before.get(net_field) is not None:
            past = raw(net_field, f"{label} net position", before)
            entry["change_1w"] = Quantity(
                value=net.value - past.value, unit=Unit.COUNT, label=f"{label}: change in net position since {before['date']}",
                source=_computed(), formula=f"{net.label} − {past.label}", inputs=(net, past),
            ).receipt()
        sides.append(entry)
    return {
        "query": data.get("query"),
        "market": data.get("market"),
        "contract": data.get("contract"),
        "report_date": day,
        "lookback_weeks": data.get("lookback_weeks"),
        "open_interest": interest.receipt(),
        "sides": sides,
        "matches": data.get("matches", []),
        "history": [
            {"date": r["date"], **{s: (r[f"{s}_net"] / r["open_interest"] if r.get(f"{s}_net") is not None else None) for s, _ in COT_SIDES}}
            for r in rows[-COT_HISTORY_WEEKS:]
        ],
    }


def cot_overview_view(data: dict) -> dict:
    scale = Quantity(value=1, unit=Unit.PERCENT, label="scale", source=_computed()).to(Unit.FRACTION).value
    rows = []
    for r in data["rows"]:
        rows.append({
            "market": r["market"],
            "date": r["date"],
            "open_interest": r.get("open_interest"),
            "sides": {
                side: {
                    "score": r.get(f"{side}_score"),
                    "change": r.get(f"{side}_change"),
                    "share_of_oi": None if r.get(f"{side}_pct") is None else r[f"{side}_pct"] * scale,
                    "zone": r.get(f"{side}_zone"),
                }
                for side, _ in COT_SIDES
            },
        })
    return {"rows": rows, "sides": [{"key": k, "label": label} for k, label in COT_SIDES], "report_date": max((r["date"] for r in rows if r["date"]), default=None)}


def cot(market_name: str | None = None) -> dict:
    if market_name:
        res = market._fetch("cot_market", {"market": market_name})
        return {"view": "market", **_read(cot_market_view, res, res["data"], res), **market._meta(res)}
    res = market._fetch("cot_overview", {})
    return {"view": "overview", **_read(cot_overview_view, res, res["data"]), **market._meta(res)}


# --------------------------------------------------------------------------------------------------
# Federal Reserve
# --------------------------------------------------------------------------------------------------


def _last(rows: list[dict], field: str) -> dict | None:
    return next((r for r in reversed(rows) if r.get(field) is not None), None)


def fed_rates_view(data: dict, meta: dict) -> dict:
    if data["unit_kind"] != "fraction":
        raise ValueError("the Fed's rates must be declared as normalised percent")

    def quantity(row: dict, field: str, label: str, source_field: str) -> Quantity:
        return Quantity(value=row[field], unit=Unit.FRACTION, label=f"{label} ({row['date']})", source=_source(meta, f"{source_field} · {row['date']} · unit: {data['unit']}"))

    out: dict = {"unit": data["unit"]}
    effr_row = _last(data["effr"], "rate")
    if effr_row:
        effr = quantity(effr_row, "rate", "Effective federal funds rate", "effr.rate")
        out["effr"] = effr.receipt()
        if effr_row.get("lower") is not None:
            out["target_lower"] = quantity(effr_row, "lower", "Target range, lower", "effr.target_range_lower").receipt()
        if effr_row.get("upper") is not None:
            out["target_upper"] = quantity(effr_row, "upper", "Target range, upper", "effr.target_range_upper").receipt()
        sofr_row = _last(data["sofr"], "rate")
        if sofr_row:
            sofr = quantity(sofr_row, "rate", "SOFR", "sofr.rate")
            out["sofr"] = sofr.receipt()
            out["sofr_minus_effr"] = Quantity(
                value=sofr.value - effr.value, unit=Unit.FRACTION, label="SOFR minus effective federal funds rate",
                source=_computed(), formula=f"{sofr.label} − {effr.label}", inputs=(sofr, effr),
            ).to(Unit.BASIS_POINTS).receipt()
    by_day = {r["date"]: r["rate"] for r in data["sofr"]}
    out["series"] = [[r["date"], r["rate"], by_day.get(r["date"]), r.get("lower"), r.get("upper")] for r in data["effr"] if r.get("rate") is not None]
    return out


def fed_money_view(data: dict, meta: dict) -> dict:
    rows = [r for r in data["rows"] if r.get("m2") is not None]
    if not rows:
        raise ValueError("no M2 values")
    source = lambda r, f: _source(meta, f"money_measures.{f} · {r['date']} · unit: {data['unit']}")  # noqa: E731
    latest = rows[-1]
    m2 = Quantity(value=latest["m2"], unit=Unit.CURRENCY, currency="USD", label=f"M2 money supply ({latest['date']})", source=source(latest, "m2"))
    out: dict = {"unit": data["unit"], "m2": m2.receipt()}
    if latest.get("m1") is not None:
        out["m1"] = Quantity(value=latest["m1"], unit=Unit.CURRENCY, currency="USD", label=f"M1 money supply ({latest['date']})", source=source(latest, "m1")).receipt()
    by_day = {r["date"]: r["m2"] for r in rows}

    def year_before(day: str) -> str:
        return f"{int(day[:4]) - 1}{day[4:]}"

    past = by_day.get(year_before(latest["date"]))
    if past:
        before = Quantity(value=past, unit=Unit.CURRENCY, currency="USD", label=f"M2 money supply ({year_before(latest['date'])})", source=source({"date": year_before(latest["date"])}, "m2"))
        out["m2_growth"] = Quantity(
            value=m2.value / before.value - 1, unit=Unit.FRACTION, label="M2 growth over a year", source=_computed(),
            formula=f"{m2.label} ÷ {before.label} − 1", inputs=(m2, before),
        ).receipt()
    out["series"] = [[r["date"], r["m2"] / by_day[year_before(r["date"])] - 1] for r in rows if by_day.get(year_before(r["date"]))]
    return out


def fed_expectations_view(data: dict, meta: dict) -> dict:
    if data["unit_kind"] != "percent":
        raise ValueError("inflation expectations must be declared as percent")

    def quantity(row: dict, field: str, label: str) -> dict:
        return Quantity(value=row[field], unit=Unit.PERCENT, label=f"{label} ({row['date']})", source=_source(meta, f"{field} · {row['date']} · unit: {data['unit']}")).to(Unit.FRACTION).receipt()

    out: dict = {"unit": data["unit"]}
    one, ten = _last(data["rows"], "cpi_1y"), _last(data["rows"], "cpi_10y")
    if one:
        out["cpi_1y"] = quantity(one, "cpi_1y", "Expected CPI inflation, next year")
    if ten:
        out["cpi_10y"] = quantity(ten, "cpi_10y", "Expected CPI inflation, next 10 years")
    scale = Quantity(value=1, unit=Unit.PERCENT, label="scale", source=_computed()).to(Unit.FRACTION).value
    out["series"] = [[r["date"], None if r.get("cpi_1y") is None else r["cpi_1y"] * scale, None if r.get("cpi_10y") is None else r["cpi_10y"] * scale] for r in data["rows"]][-60:]
    return out


def fed() -> dict:
    found, errors, attempts = _sections({"rates": ("fed_rates", {}), "money": ("fed_money", {}), "expectations": ("fed_expectations", {})})
    if not found:
        raise market.MarketDataError("no Federal Reserve data: " + "; ".join(errors.values()), attempts)
    views = {"rates": fed_rates_view, "money": fed_money_view, "expectations": fed_expectations_view}
    out: dict = {"errors": errors}
    for name, res in found.items():
        try:
            out[name] = {**_read(views[name], res, res["data"], res), **market._meta(res)}
        except market.MarketDataError as exc:
            errors[name] = str(exc)
    if not any(name in out for name in views):
        raise market.MarketDataError("no Federal Reserve data: " + "; ".join(errors.values()), attempts)
    rates, expectations = out.get("rates", {}), out.get("expectations", {})
    if rates.get("effr") and expectations.get("cpi_1y"):
        nominal = Quantity(**{k: rates["effr"][k] for k in ("value", "unit", "label", "source")})
        expected = Quantity(**{k: expectations["cpi_1y"][k] for k in ("value", "unit", "label", "source")})
        out["real_rate"] = Quantity(
            value=nominal.value - expected.value, unit=Unit.FRACTION, label="Real federal funds rate (approximate)", source=_computed(),
            formula=f"{nominal.label} − {expected.label}", inputs=(nominal, expected),
        ).receipt()
    return out


# --------------------------------------------------------------------------------------------------
# Reading a filing
# --------------------------------------------------------------------------------------------------


class IdentityNeeded(Exception):
    """The SEC asks automated tools to declare who is calling, and none has been entered."""


def read_filing(symbol: str | None, form: str = "10-K", accession: str | None = None) -> dict:
    identity = store.get_sec_identity()
    if not identity:
        raise IdentityNeeded("the SEC asks for a name and email first: type READ in FinHub to enter them")
    params = {"identity": f"{identity['name']} {identity['email']}", "form": form}
    if accession:
        params["accession"] = accession
    else:
        params["symbol"] = symbol
    res = market._fetch("filing_text", params)
    return {**res["data"], **market._meta(res)}
