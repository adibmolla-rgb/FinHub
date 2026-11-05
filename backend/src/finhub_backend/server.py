"""HTTP API the terminal UI talks to. Runs locally on 127.0.0.1 only."""

from __future__ import annotations

import os
import platform
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from finhub_backend import __version__, engines

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm the engine cache in the background so the first /engines call is fast.
    threading.Thread(target=engines.statuses, daemon=True).start()
    yield


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


DEFAULT_PORT = 8765


def run() -> None:
    import uvicorn

    from finhub_backend import watchdog

    watchdog.start()
    port = int(os.environ.get("FINHUB_BACKEND_PORT", DEFAULT_PORT))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()
