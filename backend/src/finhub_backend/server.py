"""HTTP API the terminal UI talks to. Runs locally on 127.0.0.1 only."""

from __future__ import annotations

import json
import os
import platform
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from finhub_backend import __version__, agent, backtest, engines, installer, market, risk

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm the engine cache in the background so the first /engines call is fast.
    def startup() -> None:
        statuses = {s.id: s for s in engines.statuses()}
        # Installed apps set FINHUB_AUTO_INSTALL so the data engine sets itself up on first launch.
        if os.environ.get("FINHUB_AUTO_INSTALL") == "1" and not statuses["openbb"].available:
            installer.install("openbb")
        elif os.environ.get("FINHUB_SKIP_WARMUP") != "1" and statuses["openbb"].available:
            market.warmup()

    threading.Thread(target=startup, daemon=True, name="startup").start()
    yield
    market.worker().stop()
    agent.server.stop()


app = FastAPI(title="FinHub backend", version=__version__, lifespan=lifespan)

# The UI is served from the Tauri webview or the Vite dev server; both are local origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_methods=["*"],
    expose_headers=["*"],
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


@app.post("/engines/{engine_id}/install")
def install_engine(engine_id: str) -> dict:
    try:
        return installer.install(engine_id).public()
    except KeyError:
        raise HTTPException(status_code=404, detail="unknown engine") from None


@app.get("/engines/{engine_id}/install")
def install_status(engine_id: str) -> dict:
    if engine_id not in {e.id for e in engines.ENGINES}:
        raise HTTPException(status_code=404, detail="unknown engine")
    return installer.state(engine_id).public()


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


# --------------------------------------------------------------------------------------------------
# Backtester
# --------------------------------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    strategy: str = "sma"
    params: dict[str, float] = Field(default_factory=dict)
    range: str = Field("5Y", pattern="^(1Y|5Y|MAX)$")
    cost_bps: float = Field(5.0, ge=0, le=500)
    slippage_bps: float = Field(5.0, ge=0, le=500)
    allow_short: bool = False


@app.get("/backtest/strategies")
def backtest_strategies() -> list[dict]:
    return backtest.describe()


@app.post("/backtest")
def run_backtest_endpoint(req: BacktestRequest):
    try:
        hist = market.history(req.symbol.upper(), req.range, adjusted=True)
    except market.MarketDataError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "attempts": exc.attempts})
    bars = hist["bars"]
    try:
        result = backtest.run_backtest(
            [str(b["time"]) for b in bars],
            [b["close"] for b in bars],
            req.strategy,
            req.params,
            req.cost_bps,
            req.slippage_bps,
            req.allow_short,
            adjusted=bool(hist["adjusted"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["symbol"] = hist["symbol"]
    result["data"] = {
        "provider": hist["provider_name"],
        "fetched_at": hist["fetched_at"],
        "adjusted": hist["adjusted"],
        "attempts": hist["attempts"],
        "bars": len(bars),
    }
    return result


# --------------------------------------------------------------------------------------------------
# Portfolio risk
# --------------------------------------------------------------------------------------------------


class Holding(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    weight: float = Field(gt=0)


class RiskRequest(BaseModel):
    holdings: list[Holding] = Field(min_length=1, max_length=25)
    range: str = Field("5Y", pattern="^(1Y|5Y|MAX)$")
    confidence: float = Field(0.99, ge=0.9, le=0.999)
    value: float = Field(10_000, gt=0)


@app.post("/risk")
def portfolio_risk(req: RiskRequest):
    from concurrent.futures import ThreadPoolExecutor

    import numpy as np

    symbols = [h.symbol.upper() for h in req.holdings]
    if len(set(symbols)) != len(symbols):
        raise HTTPException(status_code=422, detail="each ticker can appear only once")

    def fetch(sym: str):
        try:
            return sym, market.history(sym, req.range, adjusted=True), None
        except market.MarketDataError as exc:
            return sym, None, exc

    with ThreadPoolExecutor(max_workers=min(6, len(symbols))) as pool:
        fetched = list(pool.map(fetch, symbols))
    failed = [(s, e) for s, h, e in fetched if e is not None]
    if failed:
        sym, exc = failed[0]
        return JSONResponse(
            status_code=502,
            content={"error": f"couldn't load {', '.join(s for s, _ in failed)}: {exc}", "attempts": exc.attempts},
        )

    # Align on the dates every holding traded.
    series = {s: {str(b["time"]): b["close"] for b in h["bars"]} for s, h, _ in fetched}
    common = sorted(set.intersection(*(set(v) for v in series.values())))
    if len(common) < 61:
        raise HTTPException(status_code=422, detail=f"only {len(common)} trading days shared by all holdings; need at least 61")
    closes = np.array([[series[s][d] for s in symbols] for d in common], dtype=float)
    returns = closes[1:] / closes[:-1] - 1
    try:
        result = risk.analyse(symbols, [h.weight for h in req.holdings], common[1:], returns, req.confidence, req.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["data"] = [
        {"symbol": s, "provider": h["provider_name"], "fetched_at": h["fetched_at"], "adjusted": h["adjusted"], "bars": len(h["bars"])}
        for s, h, _ in fetched
    ]
    if not all(h["adjusted"] for _, h, _ in fetched):
        result["warnings"].append("Some prices are not adjusted for splits and dividends; a split shows up as a fake loss.")
    return result


# --------------------------------------------------------------------------------------------------
# Reasoning agent (Vibe-Trading)
# --------------------------------------------------------------------------------------------------


class AgentSettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None  # omit to keep the stored key; "" to clear it
    ollama_url: str | None = None


class AskRequest(BaseModel):
    kind: str = Field("ask", pattern="^(ask|bt|debate)$")
    text: str = Field(min_length=1, max_length=4000)


@app.get("/agent/settings")
def get_agent_settings() -> dict:
    return agent.load_settings().public()


@app.put("/agent/settings")
def put_agent_settings(update: AgentSettingsUpdate) -> dict:
    try:
        return agent.save_settings(update.model_dump(exclude_unset=True)).public()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/agent/status")
def agent_status() -> dict:
    return {**agent.server.status(), "settings": agent.load_settings().public()}


async def _agent_request(method: str, path: str, **kwargs) -> httpx.Response:
    async with httpx.AsyncClient(base_url=agent.AGENT_URL, timeout=60) as client:
        return await client.request(method, path, **kwargs)


@app.post("/agent/ask")
async def agent_ask(req: AskRequest):
    import anyio

    try:
        await anyio.to_thread.run_sync(agent.server.ensure)
    except agent.AgentNotReady as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    prompt = agent.build_prompt(req.kind, req.text)
    title = f"{req.kind.upper()}: {req.text}"[:80]
    try:
        created = await _agent_request("POST", "/sessions", json={"title": title})
        created.raise_for_status()
        session_id = created.json()["session_id"]
        sent = await _agent_request("POST", f"/sessions/{session_id}/messages", json={"content": prompt})
        sent.raise_for_status()
    except httpx.HTTPError as exc:
        return JSONResponse(status_code=502, content={"error": f"agent request failed: {exc}"})
    return {"session_id": session_id, "prompt": prompt, "kind": req.kind, "text": req.text}


@app.get("/agent/sessions/{session_id}/events")
async def agent_events(session_id: str):
    """Relay the agent's server-sent events (plan, tool calls, results, answer text) to the UI."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", session_id):
        raise HTTPException(status_code=422, detail="invalid session id")

    async def relay():
        try:
            async with httpx.AsyncClient(base_url=agent.AGENT_URL, timeout=None) as client:
                async with client.stream("GET", f"/sessions/{session_id}/events", params={"replay": "active"}) as res:
                    async for chunk in res.aiter_raw():
                        yield chunk
        except httpx.HTTPError as exc:
            yield f"event: relay.error\ndata: {json.dumps({'error': str(exc)})}\n\n".encode()

    return StreamingResponse(relay(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/agent/sessions/{session_id}/state")
async def agent_session_state(session_id: str):
    """Status of the session's latest run, including the error if it failed."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", session_id):
        raise HTTPException(status_code=422, detail="invalid session id")
    try:
        res = await _agent_request("GET", f"/sessions/{session_id}")
        session = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    attempt_id = session.get("last_attempt_id")
    attempt = agent.attempt_state(session_id, attempt_id) if attempt_id else None
    return {"session_status": session.get("status"), "attempt": attempt}


@app.get("/agent/sessions/{session_id}/messages")
async def agent_messages(session_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", session_id):
        raise HTTPException(status_code=422, detail="invalid session id")
    try:
        res = await _agent_request("GET", f"/sessions/{session_id}/messages")
        return JSONResponse(status_code=res.status_code, content=res.json())
    except (httpx.HTTPError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})


@app.post("/agent/sessions/{session_id}/cancel")
async def agent_cancel(session_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", session_id):
        raise HTTPException(status_code=422, detail="invalid session id")
    try:
        res = await _agent_request("POST", f"/sessions/{session_id}/cancel")
        return res.json()
    except httpx.HTTPError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})


DEFAULT_PORT = 8765


def run() -> None:
    import uvicorn

    from finhub_backend import watchdog

    watchdog.start()
    port = int(os.environ.get("FINHUB_BACKEND_PORT", DEFAULT_PORT))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()
