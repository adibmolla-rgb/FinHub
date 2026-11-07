"""HTTP API the terminal UI talks to. Runs locally on 127.0.0.1 only."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict

import httpx
from fastapi import FastAPI, HTTPException, Path as PathParam, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware

from finhub_backend import __version__, agent, alerts, alpha, backtest, jobs, engines, fundamentals, installer, lab, macro, market, paper, portfolio, research, risk, screener, sim, store

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Warm the engine cache in the background so the first /engines call is fast.
    def startup() -> None:
        statuses = {s.id: s for s in engines.statuses()}
        # Installed apps set FINHUB_AUTO_INSTALL so the data engine sets itself up on first launch, and
        # engines already installed follow the versions this release pins.
        auto = os.environ.get("FINHUB_AUTO_INSTALL") == "1"
        stale = [e.id for e in engines.ENGINES if auto and statuses[e.id].available and installer.out_of_date(e.id)]
        if auto and not statuses["openbb"].available:
            installer.install("openbb")
        for engine_id in stale:
            installer.install(engine_id)
        if os.environ.get("FINHUB_SKIP_WARMUP") != "1" and statuses["openbb"].available and "openbb" not in stale:
            market.warmup()

    threading.Thread(target=startup, daemon=True, name="startup").start()
    if os.environ.get("FINHUB_SKIP_WARMUP") != "1":
        alerts.start_background(market.quote)
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


@app.get("/mcp/config")
def mcp_config() -> dict:
    """How to connect an MCP client (e.g. Claude Desktop) to FinHub on this computer."""
    import sys
    from pathlib import Path

    exe = Path(sys.executable).parent / ("finhub-mcp.exe" if sys.platform == "win32" else "finhub-mcp")
    return {
        "command": str(exe),
        "exists": exe.exists(),
        "claude_desktop": {"mcpServers": {"finhub": {"command": str(exe)}}},
        "claude_code": f'claude mcp add finhub -- "{exe}"',
    }


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
def market_history(symbol: str, range: str = Query("1Y", pattern="^(1M|3M|6M|1Y|5Y|MAX)$"), adjusted: bool = False):
    return _market(market.history, _check(symbol), range, adjusted)


@app.get("/market/profile/{symbol}")
def market_profile(symbol: str):
    return _market(market.profile, _check(symbol))


@app.get("/market/news/{symbol}")
def market_news(symbol: str, limit: int = Query(20, ge=1, le=50)):
    return _market(market.news, _check(symbol), limit)


@app.get("/market/fundamentals/{symbol}")
def market_fundamentals(symbol: str, period: str = Query("annual", pattern="^(annual|quarter)$")):
    return _market(fundamentals.fundamentals, _check(symbol), period)


@app.get("/macro/{country}")
def macro_dashboard(country: str, years: int = Query(10, ge=1, le=40)):
    try:
        return _market(macro.dashboard, country, years)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class PortfolioTransaction(BaseModel):
    symbol: str
    side: str
    quantity: float
    price: float | None = None
    fees: float = 0.0
    date: str | None = None


@app.get("/portfolio")
def portfolio_report() -> dict:
    try:
        return portfolio.report()
    except portfolio.LedgerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/portfolio/transactions")
def portfolio_add(t: PortfolioTransaction) -> dict:
    try:
        return portfolio.add(t.symbol, t.side, t.quantity, t.price, t.fees, t.date)
    except portfolio.LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/portfolio/transactions/{transaction_id}")
def portfolio_remove(transaction_id: str) -> dict:
    try:
        if not portfolio.remove(transaction_id):
            raise HTTPException(status_code=404, detail="no such transaction")
    except portfolio.LedgerError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"deleted": transaction_id}


@app.get("/research/ownership/{symbol}")
def research_ownership(symbol: str):
    return _market(research.ownership, _check(symbol))


@app.get("/research/options/{symbol}")
def research_options(symbol: str, expiration: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    return _market(research.options_chain, _check(symbol), expiration)


@app.get("/research/calendar")
def research_calendar(
    days: int = Query(7, ge=1, le=31),
    symbols: str | None = Query(None, max_length=500),
    limit: int | None = Query(None, ge=1, le=5000),
):
    wanted = [_check(s) for s in symbols.split(",") if s] if symbols else None
    return _market(research.calendar, days, wanted, limit)


@app.get("/research/filings/{symbol}")
def research_filings(symbol: str):
    return _market(research.filings, _check(symbol))


@app.get("/research/etf/{symbol}")
def research_etf(symbol: str):
    return _market(research.etf_holdings, _check(symbol))


@app.get("/research/curve")
def research_curve():
    return _market(research.yield_curve)


@app.get("/research/factors")
def research_factors(region: str = Query("US", pattern="^[A-Za-z]{2,12}$"), years: int = Query(30, ge=1, le=70)):
    try:
        return _market(research.factors, region, years)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/research/cot")
def research_cot(market_name: str | None = Query(None, alias="market", max_length=60, pattern=r"^[A-Za-z0-9&/.,()$%+#:_\- ]+$")):
    return _market(research.cot, market_name)


@app.get("/research/fed")
def research_fed():
    return _market(research.fed)


class SecIdentityIn(BaseModel):
    name: str = Field(max_length=200)
    email: str = Field(max_length=300)


@app.get("/settings/sec-identity")
def sec_identity_status() -> dict:
    return {"configured": store.get_sec_identity() is not None}


@app.put("/settings/sec-identity")
def sec_identity_save(body: SecIdentityIn) -> dict:
    try:
        store.set_sec_identity(body.name, body.email)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"configured": True}


@app.get("/research/read")
def research_read(
    symbol: str | None = Query(None, max_length=15),
    form: str = Query("10-K", pattern=r"^[0-9A-Za-z/\- ]{1,12}$"),
    accession: str | None = Query(None, pattern=r"^\d{10}-\d{2}-\d{6}$"),
):
    if not accession and not symbol:
        raise HTTPException(status_code=422, detail="give a ticker or an accession number")
    try:
        return _market(research.read_filing, _check(symbol) if symbol and not accession else None, form.upper(), accession)
    except research.IdentityNeeded as exc:
        return JSONResponse(status_code=428, content={"error": str(exc)})


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
    result.pop("daily")  # thousands of numbers the chart doesn't need
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
# Agent arena: a shared simulated market that AI agents (via MCP) and the user can trade in
# --------------------------------------------------------------------------------------------------


class SimOrder(BaseModel):
    name: str
    side: str
    qty: int
    price: float | None = None


class SimSteps(BaseModel):
    steps: int = Field(1, ge=1, le=2000)


class SimScenario(BaseModel):
    scenario: str


class SimReset(BaseModel):
    seed: int = Field(42, ge=0, le=2**31)


class SimName(BaseModel):
    name: str


@app.get("/sim/state")
def sim_state(history: int = Query(300, ge=1, le=4000), reveal: bool = False) -> dict:
    return sim.arena().state(history, reveal)


@app.post("/sim/order")
def sim_order(o: SimOrder) -> dict:
    try:
        return sim.arena().order(o.name, o.side, o.qty, o.price)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/sim/cancel")
def sim_cancel(n: SimName) -> dict:
    return {"cancelled": sim.arena().cancel_all(n.name)}


@app.get("/sim/account/{name}")
def sim_account(name: str) -> dict:
    return sim.arena().account_view(name)


@app.post("/sim/advance")
def sim_advance(s: SimSteps) -> dict:
    a = sim.arena()
    a.tick(s.steps)
    return {"step": a.book.step}


@app.post("/sim/scenario")
def sim_scenario(s: SimScenario) -> dict:
    try:
        return {"event": sim.arena().trigger(s.scenario)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/sim/reset")
def sim_reset(r: SimReset) -> dict:
    return {"step": sim.reset_arena(r.seed).book.step}


# --------------------------------------------------------------------------------------------------
# Screener
# --------------------------------------------------------------------------------------------------


class ScreenRequest(BaseModel):
    universe: str = "large_caps"
    symbols: list[str] | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_change: float | None = None
    max_change: float | None = None
    min_market_cap: float | None = None
    max_from_high: float | None = None
    min_from_low: float | None = None
    sectors: list[str] = Field(default_factory=list)


@app.post("/screen")
def run_screen(req: ScreenRequest) -> dict:
    f = screener.Filters(
        req.min_price, req.max_price, req.min_change, req.max_change, req.min_market_cap,
        req.max_from_high, req.min_from_low, tuple(req.sectors),
    )
    try:
        return screener.screen(req.universe, f, req.symbols)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/screen/universes")
def screen_universes() -> dict:
    return {"large_caps": screener.LARGE_CAPS, "sectors": sorted(set(screener.LARGE_CAPS.values()))}


# --------------------------------------------------------------------------------------------------
# Price alerts
# --------------------------------------------------------------------------------------------------


class AlertIn(BaseModel):
    symbol: str
    kind: str
    threshold: float


@app.get("/alerts")
def list_alerts() -> dict:
    return alerts.listing()


@app.post("/alerts")
def add_alert(a: AlertIn) -> dict:
    try:
        return alerts.add(a.symbol, a.kind, a.threshold)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str) -> dict:
    if not alerts.remove(alert_id):
        raise HTTPException(status_code=404, detail="alert not found")
    return {"deleted": alert_id}


@app.post("/alerts/check")
def check_alerts() -> dict:
    """Check now instead of waiting for the background check (every 2 minutes)."""
    return {"fired": alerts.check(market.quote)}


# --------------------------------------------------------------------------------------------------
# Watchlist and saved research
# --------------------------------------------------------------------------------------------------


class WatchlistUpdate(BaseModel):
    symbols: list[str] = Field(max_length=store.MAX_WATCHLIST)


@app.get("/watchlist")
def get_watchlist() -> dict:
    return {"symbols": store.get_watchlist()}


@app.put("/watchlist")
def put_watchlist(update: WatchlistUpdate) -> dict:
    try:
        return {"symbols": store.set_watchlist(update.symbols)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/watchlist/quotes")
def watchlist_quotes() -> list[dict]:
    """Quote every watchlist ticker in parallel; a failure for one ticker doesn't fail the rest."""
    from concurrent.futures import ThreadPoolExecutor

    symbols = store.get_watchlist()

    def one(sym: str) -> dict:
        try:
            return {"symbol": sym, "ok": True, "quote": market.quote(sym)}
        except market.MarketDataError as exc:
            return {"symbol": sym, "ok": False, "error": str(exc)}

    if not symbols:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(symbols))) as pool:
        return list(pool.map(one, symbols))


@app.get("/notes")
def list_notes() -> list[dict]:
    return store.list_notes()


@app.get("/notes/{note_id}")
def get_note(note_id: str) -> dict:
    note = store.get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="note not found")
    return note


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
    import numpy as np

    symbols = [h.symbol.upper() for h in req.holdings]
    if len(set(symbols)) != len(symbols):
        raise HTTPException(status_code=422, detail="each ticker can appear only once")
    try:
        common, rows, origins = market.aligned_closes(symbols, req.range)
    except market.MarketDataError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "attempts": exc.attempts})
    if len(common) < 61:
        raise HTTPException(status_code=422, detail=f"only {len(common)} trading days shared by all holdings; need at least 61")
    closes = np.array(rows, dtype=float)
    returns = closes[1:] / closes[:-1] - 1
    try:
        result = risk.analyse(symbols, [h.weight for h in req.holdings], common[1:], returns, req.confidence, req.value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["data"] = [{"symbol": s, **origins[s]} for s in symbols]
    if not all(o["adjusted"] for o in origins.values()):
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


# --------------------------------------------------------------------------------------------------
# Swarm: Vibe-Trading's teams of agents
# --------------------------------------------------------------------------------------------------


class SwarmStart(BaseModel):
    preset: str = Field(pattern=r"^[a-z0-9_]{1,60}$")
    variables: dict[str, str] = Field(default_factory=dict)


# One team at a time: teams are expensive, and rapid clicks or a retrying client shouldn't each start one.
_swarm_start = asyncio.Lock()


async def _swarm(method: str, path: str, **kwargs):
    import anyio

    try:
        await anyio.to_thread.run_sync(agent.server.ensure)
    except agent.AgentNotReady as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    try:
        res = await _agent_request(method, path, **kwargs)
        body = res.json()
    except (httpx.HTTPError, ValueError) as exc:
        return JSONResponse(status_code=502, content={"error": f"agent request failed: {exc}"})
    if res.status_code >= 400:
        detail = body.get("detail") if isinstance(body, dict) else None
        return JSONResponse(status_code=res.status_code, content={"error": str(detail or body)})
    return body


def _run_id(run_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", run_id):
        raise HTTPException(status_code=422, detail="invalid run id")
    return run_id


@app.get("/agent/swarm/presets")
async def swarm_presets():
    return await _swarm("GET", "/swarm/presets")


@app.get("/agent/swarm/runs")
async def swarm_runs(limit: int = Query(20, ge=1, le=100)):
    return await _swarm("GET", "/swarm/runs", params={"limit": limit})


@app.post("/agent/swarm/runs")
async def swarm_start(req: SwarmStart):
    variables = {k: v.strip() for k, v in req.variables.items() if v.strip()}
    if any(len(v) > 500 for v in variables.values()):
        raise HTTPException(status_code=422, detail="a value is too long")
    # The agent starts a team even with its questions unanswered, which would spend the provider's credit on nothing.
    presets = await _swarm("GET", "/swarm/presets")
    if isinstance(presets, JSONResponse):
        return presets
    preset = next((p for p in presets if p.get("name") == req.preset), None)
    if preset is None:
        return JSONResponse(status_code=404, content={"error": f"no team called {req.preset}"})
    missing = [v["name"] for v in preset.get("variables", []) if v.get("required") and v["name"] not in variables]
    if missing:
        return JSONResponse(status_code=422, content={"error": f"this team needs: {', '.join(missing)}"})
    async with _swarm_start:
        runs = await _swarm("GET", "/swarm/runs", params={"limit": 20})
        if isinstance(runs, JSONResponse):
            return runs
        if any(r.get("status") not in ("completed", "failed", "cancelled") and not r.get("is_stale") for r in runs):
            return JSONResponse(status_code=409, content={"error": "a team is already running; wait for it to finish or cancel it first"})
        return await _swarm("POST", "/swarm/runs", json={"preset_name": req.preset, "user_vars": variables})


@app.get("/agent/swarm/runs/{run_id}")
async def swarm_run(run_id: str):
    return await _swarm("GET", f"/swarm/runs/{_run_id(run_id)}")


@app.post("/agent/swarm/runs/{run_id}/cancel")
async def swarm_cancel(run_id: str):
    return await _swarm("POST", f"/swarm/runs/{_run_id(run_id)}/cancel")


# --------------------------------------------------------------------------------------------------
# Paper trading and the signal library: Vibe-Trading features that need no AI model
# --------------------------------------------------------------------------------------------------


def _engine(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except agent.AgentNotReady as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})
    except (paper.PaperError, alpha.AlphaError, agent.EngineError, lab.LabError, jobs.JobError) as exc:
        return JSONResponse(status_code=exc.status, content={"error": str(exc)})
    except market.MarketDataError as exc:
        return JSONResponse(status_code=502, content={"error": str(exc), "attempts": exc.attempts})


_PAPER_ID = r"^[a-f0-9]{8,64}$"


class PaperAccountIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    cash: float = Field(allow_inf_nan=False)


class PaperOrderIn(BaseModel):
    symbol: str = Field(max_length=20)
    side: str
    quantity: float = Field(allow_inf_nan=False)


@app.get("/paper/accounts")
def paper_accounts():
    return _engine(paper.accounts)


@app.post("/paper/accounts")
def paper_create(body: PaperAccountIn):
    return _engine(paper.create, body.label, body.cash)


@app.get("/paper/accounts/{account_id}")
def paper_account(account_id: str = PathParam(pattern=_PAPER_ID)):
    return _engine(paper.view, account_id)


@app.post("/paper/accounts/{account_id}/orders")
def paper_place(body: PaperOrderIn, account_id: str = PathParam(pattern=_PAPER_ID)):
    return _engine(paper.place, account_id, body.symbol, body.side, body.quantity)


@app.delete("/paper/orders/{order_id}")
def paper_cancel(order_id: str = PathParam(pattern=_PAPER_ID)):
    def cancel() -> dict:
        if not paper.cancel(order_id):
            raise paper.PaperError("no such order; it may already have filled", status=404)
        return {"cancelled": order_id}

    return _engine(cancel)


class AlphaCompareIn(BaseModel):
    alpha_ids: list[str] = Field(max_length=50)
    period: str = Field(max_length=9)


class AlphaBenchIn(BaseModel):
    zoo: str = Field(max_length=20)
    period: str = Field(max_length=9)


@app.get("/alpha/library")
def alpha_library(zoo: str | None = Query(None, max_length=20), theme: str | None = Query(None, max_length=30)):
    return _engine(alpha.library, zoo, theme)


@app.get("/alpha/library/{alpha_id}")
def alpha_detail(alpha_id: str):
    return _engine(alpha.detail, alpha_id)


@app.get("/alpha/runs")
def alpha_runs():
    return alpha.runs()


@app.post("/alpha/compare")
def alpha_compare(body: AlphaCompareIn):
    return _engine(alpha.start_compare, body.alpha_ids, body.period)


@app.post("/alpha/bench")
def alpha_bench(body: AlphaBenchIn):
    return _engine(alpha.start_bench, body.zoo, body.period)


class AlphaFactorIn(BaseModel):
    alpha_id: str = Field(max_length=80)
    period: str = Field(max_length=9)


@app.post("/alpha/factor")
def alpha_factor(body: AlphaFactorIn):
    return _engine(alpha.start_factor, body.alpha_id, body.period)


@app.get("/alpha/runs/{run_id}")
def alpha_run(run_id: str):
    def one() -> dict:
        found = alpha.run(run_id)
        if found is None:
            raise alpha.AlphaError("no such test", status=404)
        return found

    return _engine(one)


# --------------------------------------------------------------------------------------------------
# OPTIM and REPORT: skfolio and QuantStats, in the agent engine's environment
# --------------------------------------------------------------------------------------------------


class OptimIn(BaseModel):
    holdings: list[Holding] = Field(min_length=2, max_length=25)
    range: str = Field("MAX", pattern="^(5Y|MAX)$")


class ReportIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    benchmark: str | None = Field(None, pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    range: str = Field("5Y", pattern="^(1Y|5Y|MAX)$")


class SeriesReportIn(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    dates: list[str]
    equity: list[float]
    benchmark_equity: list[float] | None = None
    benchmark_label: str | None = Field(None, max_length=120)


class VolatilityIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")
    range: str = Field("MAX", pattern="^(5Y|MAX)$")


class BondIn(BaseModel):
    coupon: float = Field(allow_inf_nan=False)
    years: float = Field(allow_inf_nan=False)
    price: float | None = Field(None, allow_inf_nan=False)


class SymbolIn(BaseModel):
    symbol: str = Field(pattern=r"^[A-Za-z0-9.\-^=]{1,15}$")


@app.post("/lab/volatility")
def lab_volatility(body: VolatilityIn):
    return _engine(lab.volatility, body.symbol, body.range)


@app.post("/lab/bond")
def lab_bond(body: BondIn):
    def value() -> dict:
        curve, detail = None, None
        try:  # Valuing it on the curve is a bonus: without a curve, a given price is still enough.
            today = research.yield_curve()
            if today["unit_kind"] == "fraction":
                curve = [{"years": t["years"], "rate": t["latest"]["value"]} for t in today["tenors"] if t["years"] >= 0.25]
                detail = f"Treasury par yields of {today['date']} from {today['provider_name']}"
        except market.MarketDataError:
            pass
        return lab.bond(body.coupon, body.years, body.price, curve, detail)

    return _engine(value)


@app.post("/lab/mood")
def lab_mood(body: SymbolIn):
    return _engine(lab.mood, body.symbol)


@app.get("/find")
def find(
    kind: str = Query("equities", pattern="^(equities|etfs)$"),
    query: str = Query("", max_length=80),
    country: str | None = Query(None, max_length=60),
    sector: str | None = Query(None, max_length=60),
    market_cap: str | None = Query(None, max_length=20),
    limit: int = Query(200, ge=1, le=1000),
):
    def search() -> dict:
        res = market._fetch("find_symbols", {"kind": kind, "query": query, "country": country, "sector": sector, "market_cap": market_cap, "limit": limit})
        return {**res["data"], **market._meta(res)}

    return _engine(search)


@app.get("/find/options")
def find_options():
    def options() -> dict:
        return market._fetch("find_options", {})["data"]

    return _engine(options)


def _agents_work(symbol: str, date: str) -> dict:
    settings = agent.load_settings()
    public = settings.public()
    if not public["configured"]:
        raise agent.AgentNotReady("no AI provider configured; set one with the AI command")
    key_env = agent.PROVIDERS[settings.provider]["key_env"]
    extra = {key_env: settings.api_key} if key_env and settings.api_key else None
    request = {"symbol": symbol, "date": date, "provider": settings.provider, "model": public["model"], "ollama_url": settings.ollama_url, "home": str(agent.data_dir() / "tradingagents")}
    try:
        return lab.run("analyse", request, timeout=7200.0, engine="tradingagents", extra_env=extra)
    except lab.LabError as exc:
        # Its message names OpenAI whichever provider is in use, because Ollama is reached through the same kind of client.
        if settings.provider == "ollama" and "connection" in str(exc).lower():
            raise lab.LabError(f"couldn't reach Ollama at {settings.ollama_url}. Is it running, with {public['model']} pulled?", status=503) from exc
        raise


QLIB_BARS = 252 * 16


def _qlib_work() -> dict:
    from concurrent.futures import ThreadPoolExecutor

    def fetch(symbol: str):
        try:
            return symbol, market.history(symbol, "MAX", adjusted=True)
        except market.MarketDataError:
            return symbol, None

    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(fetch, list(screener.LARGE_CAPS)))
    panels = {}
    for symbol, history in fetched:
        if history and history["adjusted"] and len(history["bars"]) > 2500:
            bars = history["bars"][-QLIB_BARS:]  # enough to learn from, without needing many gigabytes of memory
            panels[symbol] = {"dates": [str(b["time"])[:10] for b in bars], **{f: [b.get(f) for b in bars] for f in ("open", "high", "low", "close", "volume")}}
    if len(panels) < 20:
        raise lab.LabError(f"only {len(panels)} large caps had at least 10 years of adjusted prices; it needs 20", status=502)
    left_out = sorted(set(screener.LARGE_CAPS) - set(panels))
    provider = next(h["provider_name"] for _, h in fetched if h)
    return {**lab.qlib_receipts(lab.run("train", {"panels": panels}, timeout=7200.0, engine="qlib"), provider), "left_out": left_out}


@app.post("/jobs/agents")
def jobs_agents(body: SymbolIn):
    from datetime import UTC, datetime

    symbol = body.symbol.upper()
    day = paper.latest_settled_day(datetime.now(UTC)).isoformat()
    return _engine(jobs.start, "agents", {"symbol": symbol, "date": day}, lambda: _agents_work(symbol, day))


@app.post("/jobs/qlib")
def jobs_qlib():
    return _engine(jobs.start, "qlib", {}, _qlib_work)


@app.get("/jobs")
def jobs_list(kind: str = Query(pattern="^(agents|qlib)$")):
    return jobs.listing(kind)


@app.get("/jobs/{run_id}")
def jobs_get(run_id: str):
    found = jobs.get(run_id)
    if found is None:
        return JSONResponse(status_code=404, content={"error": "no such run"})
    return found


@app.post("/lab/optimise")
def lab_optimise(body: OptimIn):
    return _engine(lab.optimise, [h.model_dump() for h in body.holdings], body.range)


@app.post("/lab/report")
def lab_report(body: ReportIn):
    return _engine(lab.report_symbol, body.symbol, body.benchmark, body.range)


@app.post("/lab/report/backtest")
def lab_report_backtest(req: BacktestRequest):
    def report() -> dict:
        hist = market.history(req.symbol.upper(), req.range, adjusted=True)
        bars = hist["bars"]
        try:
            result = backtest.run_backtest([str(b["time"]) for b in bars], [b["close"] for b in bars], req.strategy, req.params, req.cost_bps, req.slippage_bps, req.allow_short, adjusted=bool(hist["adjusted"]))
        except ValueError as exc:
            raise lab.LabError(str(exc)) from exc
        daily = result["daily"]
        symbol = hist["symbol"]
        return lab.report_returns(f"{symbol} {result['label']}", daily["dates"], daily["strategy"], daily["buy_hold"], f"{symbol} buy and hold", f"daily returns after costs, prices from {hist['provider_name']}")

    return _engine(report)


@app.post("/lab/report/series")
def lab_report_series(body: SeriesReportIn):
    return _engine(lab.report_series, body.label, body.dates, body.equity, body.benchmark_equity, body.benchmark_label)


DEFAULT_PORT = 8765


def run() -> None:
    import uvicorn

    from finhub_backend import watchdog

    watchdog.start()
    port = int(os.environ.get("FINHUB_BACKEND_PORT", DEFAULT_PORT))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()
