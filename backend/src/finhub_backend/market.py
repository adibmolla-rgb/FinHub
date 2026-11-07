"""Market data service: asks the OpenBB engine worker for data and returns it with receipts.

Rules:
- Every number leaves here as a Quantity with unit, provider, provider field and fetch time.
- Derived values (change, % change, distance from 52-week high) are computed here from raw inputs,
  never taken from a provider, because providers disagree on whether "1.5" means 1.5% or 150%.
- Every request records which providers were tried, so the UI can show data-source health.
"""

from __future__ import annotations

import re
import threading

from dataclasses import dataclass, field
from datetime import UTC, datetime

from finhub_backend.engines import engine_python, engines_dir
from finhub_backend.receipts import Quantity, Source, Unit
from finhub_backend.worker_client import EngineWorker, WorkerError

RANGES = ("1M", "3M", "6M", "1Y", "5Y", "MAX")

_worker: EngineWorker | None = None
_worker_lock = threading.Lock()


def worker() -> EngineWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = EngineWorker(engine_python("openbb"), engines_dir() / "openbb" / "worker.py")
        return _worker


def set_worker(w: EngineWorker | None) -> None:
    """For tests."""
    global _worker
    with _worker_lock:
        _worker = w


# --------------------------------------------------------------------------------------------------
# Data-source health
# --------------------------------------------------------------------------------------------------


@dataclass
class SourceHealth:
    provider: str
    status: str = "unknown"
    successes: int = 0
    failures: int = 0
    no_data: int = 0
    last_ok_at: str | None = None
    last_error_at: str | None = None
    last_error: str | None = None
    last_ms: int | None = None
    kinds: set[str] = field(default_factory=set)


_health: dict[str, SourceHealth] = {}
_health_lock = threading.Lock()


# The provider answered, and it has nothing for that ticker, date or country. That says something about the
# request, not about the provider, so SYS shouldn't call the provider failing.
_NO_DATA = re.compile(r"^NoData\b|EmptyDataError|\[Empty\]|CIK not found|Invalid value '|HTTP 404")


def record_attempts(kind: str, attempts: list[dict]) -> None:
    now = datetime.now(UTC).isoformat()
    with _health_lock:
        for a in attempts:
            h = _health.setdefault(a["provider"], SourceHealth(a["provider"]))
            h.kinds.add(kind)
            h.last_ms = a.get("ms")
            if a["ok"]:
                h.successes += 1
                h.last_ok_at = now
                h.status = "ok"
                continue
            h.last_error_at = now
            h.last_error = a.get("error")
            if _NO_DATA.search(a.get("error") or ""):
                h.no_data += 1
                h.status = "no data"
            else:
                h.failures += 1
                h.status = "failing"


def source_health() -> list[dict]:
    with _health_lock:
        out = [{**h.__dict__, "kinds": sorted(h.kinds)} for h in _health.values()]
        return sorted(out, key=lambda d: d["provider"])


class MarketDataError(Exception):
    def __init__(self, message: str, attempts: list[dict]):
        super().__init__(message)
        self.attempts = attempts


def _fetch(kind: str, params: dict, timeout: float = 90.0) -> dict:
    try:
        result = worker().call(kind, params, timeout=timeout)
    except WorkerError as exc:
        record_attempts(kind, exc.attempts)
        raise MarketDataError(str(exc), exc.attempts) from exc
    record_attempts(kind, result["attempts"])
    return result


def _source(result: dict, detail: str | None) -> Source:
    return Source(
        provider=result["provider_name"],
        fetched_at=datetime.fromisoformat(result["fetched_at"]),
        detail=detail,
    )


def _meta(result: dict) -> dict:
    return {
        "provider": result["provider"],
        "provider_name": result["provider_name"],
        "fetched_at": result["fetched_at"],
        "attempts": result["attempts"],
        "fallback_used": len(result["attempts"]) > 1,
    }


# --------------------------------------------------------------------------------------------------
# Quote
# --------------------------------------------------------------------------------------------------

_QUOTE_FIELDS: dict[str, tuple[str, Unit]] = {
    "price": ("Last price", Unit.CURRENCY),
    "previous_close": ("Previous close", Unit.CURRENCY),
    "open": ("Open", Unit.CURRENCY),
    "day_high": ("Day high", Unit.CURRENCY),
    "day_low": ("Day low", Unit.CURRENCY),
    "volume": ("Volume", Unit.SHARES),
    "market_cap": ("Market cap", Unit.CURRENCY),
    "year_high": ("52-week high", Unit.CURRENCY),
    "year_low": ("52-week low", Unit.CURRENCY),
}


def build_quote(result: dict) -> dict:
    """Turn a worker quote result into receipted values. Pure function: tested without a worker."""
    data = result["data"]
    currency = data.get("currency")
    values: dict[str, Quantity] = {}
    for key, (label, unit) in _QUOTE_FIELDS.items():
        raw = (data.get("fields") or {}).get(key)
        if not raw:
            continue
        values[key] = Quantity(
            value=raw["value"],
            unit=unit,
            label=label,
            currency=currency if unit == Unit.CURRENCY else None,
            source=_source(result, raw["field"]),
        )

    price, prev = values.get("price"), values.get("previous_close")
    if price and prev and prev.value:
        change = Quantity(
            value=price.value - prev.value,
            unit=Unit.CURRENCY,
            currency=currency,
            label="Change",
            source=Source(provider="computed by FinHub"),
            formula="Last price − Previous close",
            inputs=(price, prev),
        )
        values["change"] = change
        values["change_pct"] = Quantity(
            value=change.value / prev.value,
            unit=Unit.FRACTION,
            label="Change %",
            source=Source(provider="computed by FinHub"),
            formula="Change ÷ Previous close",
            inputs=(change, prev),
        )
    high = values.get("year_high")
    if price and high and high.value:
        values["from_high_pct"] = Quantity(
            value=price.value / high.value - 1,
            unit=Unit.FRACTION,
            label="Distance from 52-week high",
            source=Source(provider="computed by FinHub"),
            formula="Last price ÷ 52-week high − 1",
            inputs=(price, high),
        )

    return {
        "symbol": data["symbol"],
        "currency": currency,
        "exchange": data.get("exchange"),
        "values": {k: q.receipt() for k, q in values.items()},
        **_meta(result),
    }


def quote(symbol: str) -> dict:
    return build_quote(_fetch("quote", {"symbol": symbol}))


def history(symbol: str, range_: str = "1Y", adjusted: bool = False) -> dict:
    result = _fetch("history", {"symbol": symbol, "range": range_, "interval": "1d", "adjusted": adjusted})
    data = result["data"]
    return {
        "symbol": data["symbol"],
        "range": range_,
        "interval": data["interval"],
        "adjusted": data["adjusted"],
        "bars": data["bars"],
        **_meta(result),
    }


def profile(symbol: str) -> dict:
    result = _fetch("profile", {"symbol": symbol})
    return {**result["data"], **_meta(result)}


def news(symbol: str, limit: int = 20) -> dict:
    result = _fetch("news", {"symbol": symbol, "limit": limit})
    return {**result["data"], **_meta(result)}


def warmup() -> None:
    """Start the worker and load OpenBB in the background so the first request is fast."""

    def run() -> None:
        try:
            worker().call("warmup", timeout=180)
        except Exception:
            pass

    threading.Thread(target=run, daemon=True, name="market-warmup").start()


