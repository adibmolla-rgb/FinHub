"""HTTP API the terminal UI talks to. Runs locally on 127.0.0.1 only."""

from __future__ import annotations

import os
import platform
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from finhub_backend import __version__, engines, market

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm the engine cache in the background so the first /engines call is fast.
    threading.Thread(target=engines.statuses, daemon=True).start()
    if os.environ.get("FINHUB_SKIP_WARMUP") != "1":
        market.warmup()
    yield
    market.worker().stop()


app = FastAPI(title="FinHub backend", version=__version__, lifespan=lifespan)

# The UI is served from the Tauri webview or the Vite dev server; both are local origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "python": platform.python_version(),
        "platform": platform.platform(terse=True),
    }


@app.get("/engines")
def list_engines(refresh: bool = False) -> list[dict]:
    return [asdict(s) for s in engines.statuses(refresh=refresh)]


@app.get("/examples/receipt")
def receipt_example() -> dict:
    """A worked example of a receipt, built from fixed illustrative inputs (not live data)."""
    from finhub_backend.receipts import Quantity, Source, Unit, add

    dividend_yield = Quantity(
        value=0.99,
        unit=Unit.PERCENT,
        label="Dividend yield (as reported)",
        source=Source(provider="example input", detail="data providers often report this in percent"),
    )
    buyback_yield = Quantity(
        value=0.025,
        unit=Unit.FRACTION,
        label="Buyback yield",
        source=Source(provider="example input"),
    )
    total = add(
        "Shareholder yield",
        dividend_yield.to(Unit.FRACTION).model_copy(update={"label": "Dividend yield (converted to fraction)"}),
        buyback_yield,
    )
    return {
        "note": (
            "Illustration with fixed inputs, not live data. Click a row to open its receipt. Adding the "
            "percent value directly to the fraction would raise an error instead of silently returning 101.5%."
        ),
        "receipt": total.receipt(),
    }


# --------------------------------------------------------------------------------------------------
# Market data
# --------------------------------------------------------------------------------------------------

def _market(call, *args):
    try:
        return call(*args)
    except market.MarketDataError as exc:
        # 502: an upstream data source failed. The body carries every attempt for the UI to show.
        return JSONResponse(status_code=502, content={"error": str(exc), "attempts": exc.attempts})


def _check(symbol: str) -> str:
    import re

    if not re.fullmatch(r"[A-Za-z0-9.\-^=]{1,15}", symbol):
        raise HTTPException(status_code=422, detail="invalid symbol")
    return symbol.upper()


@app.get("/market/quote/{symbol}")
def market_quote(symbol: str):
    return _market(market.quote, _check(symbol))


@app.get("/market/history/{symbol}")
def market_history(symbol: str, range: str = Query("1Y", pattern="^(1M|3M|6M|1Y|5Y|MAX)$")):
    return _market(market.history, _check(symbol), range)


@app.get("/market/profile/{symbol}")
def market_profile(symbol: str):
    return _market(market.profile, _check(symbol))


@app.get("/market/news/{symbol}")
def market_news(symbol: str, limit: int = Query(20, ge=1, le=50)):
    return _market(market.news, _check(symbol), limit)


@app.get("/market/sources")
def market_sources() -> list[dict]:
    return market.source_health()


DEFAULT_PORT = 8765


def run() -> None:
    import uvicorn

    from finhub_backend import watchdog

    watchdog.start()
    port = int(os.environ.get("FINHUB_BACKEND_PORT", DEFAULT_PORT))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()
