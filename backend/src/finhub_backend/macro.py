"""Macro dashboard: OECD series for a country, with units taken from the data provider's metadata.

Series whose unit OpenBB declares (normalised percent) become fractions; anything else is shown
exactly as reported, labelled with the provider's own unit text, and never converted.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from finhub_backend import market
from finhub_backend.receipts import Quantity, Source, Unit

SERIES = ("unemployment", "rate_short", "rate_long", "cpi", "gdp_real")

COUNTRIES = {
    "US": "united_states", "GB": "united_kingdom", "UK": "united_kingdom", "JP": "japan", "DE": "germany",
    "FR": "france", "CA": "canada", "IT": "italy", "AU": "australia", "KR": "south_korea", "MX": "mexico",
    "ES": "spain", "NL": "netherlands", "CH": "switzerland", "SE": "sweden", "NO": "norway", "NZ": "new_zealand",
    "IE": "ireland", "PL": "poland", "TR": "turkey", "BR": "brazil", "ZA": "south_africa", "IN": "india", "CN": "china",
}


def country_name(code_or_name: str) -> str:
    key = code_or_name.strip()
    if key.upper() in COUNTRIES:
        return COUNTRIES[key.upper()]
    name = key.lower().replace(" ", "_").replace("-", "_")
    if not name.replace("_", "").isalpha() or len(name) > 40:
        raise ValueError("unknown country; use a code like US, GB, JP or a name like united_kingdom")
    return name


def summarise(raw: dict, meta: dict) -> dict:
    """Latest value and its change from a year earlier, as receipts."""
    pts = raw["points"]
    unit = Unit.FRACTION if raw["unit_kind"] == "fraction" else Unit.AS_REPORTED
    src = Source(provider=meta["provider_name"], fetched_at=datetime.fromisoformat(meta["fetched_at"]), detail=f"{raw['series']} · {raw['country']} · unit: {raw['unit']}")
    last = pts[-1]
    latest = Quantity(value=last["value"], unit=unit, label=f"{raw['label']} ({last['date']})", source=src)
    out = {"series": raw["series"], "label": raw["label"], "unit_kind": raw["unit_kind"], "unit": raw["unit"], "points": pts, "latest": latest.receipt()}
    # Same date a year earlier (or the closest earlier observation).
    target = f"{int(last['date'][:4]) - 1}{last['date'][4:]}"
    earlier = [p for p in pts if p["date"] <= target]
    if earlier:
        prev = earlier[-1]
        before = Quantity(value=prev["value"], unit=unit, label=f"{raw['label']} ({prev['date']})", source=src)
        out["change_1y"] = Quantity(
            value=last["value"] - prev["value"], unit=unit, label="Change over a year",
            source=Source(provider="computed by FinHub"), formula="Latest − value a year earlier", inputs=(latest, before),
        ).receipt()
    return out


def dashboard(country: str, years: int = 10) -> dict:
    name = country_name(country)

    def one(series: str):
        try:
            res = market.worker().call("macro", {"series": series, "country": name, "years": years}, timeout=120)
            market.record_attempts("macro", res["attempts"])
            return series, summarise(res["data"], res), None
        except market.WorkerError as exc:
            market.record_attempts("macro", exc.attempts)
            return series, None, str(exc)

    with ThreadPoolExecutor(max_workers=len(SERIES)) as pool:
        results = list(pool.map(one, SERIES))
    series = {s: r for s, r, _ in results if r}
    if not series:
        raise market.MarketDataError(f"no macro data for {name}: " + "; ".join(e for _, _, e in results if e), [])
    return {"country": name, "series": series, "errors": {s: e for s, _, e in results if e}}
