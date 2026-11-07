"""FinHub as an MCP server, so AI agents (Claude Desktop, Claude Code, Vibe-Trading, ...) can use it.

Run as `finhub-mcp` over stdio. Data, backtest and risk tools call the FinHub app running on this
computer (it must be open), so agents get the same data sources, receipts and validation warnings as
the app. Option pricing is computed locally and works even when the app is closed.

Every tool is read-only: nothing here places orders, spends money or changes files.
"""

from __future__ import annotations

import os
from typing import Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from finhub_backend import options

BACKEND = os.environ.get("FINHUB_BACKEND_URL", "http://127.0.0.1:8765")
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

server = MCPServer(
    name="finhub",
    title="FinHub",
    instructions=(
        "FinHub is a market research terminal. Use finhub_quote and finhub_history for prices, "
        "finhub_backtest to test a trading rule with costs, next-bar fills, walk-forward and a deflated "
        "Sharpe ratio, finhub_portfolio_risk for VaR/ES and correlations, finhub_price_option for "
        "option values and Greeks, finhub_fundamentals for statements and ratios, finhub_macro for OECD "
        "macro series, finhub_screen to filter a universe of stocks, finhub_ownership for insider trades, holders "
        "and short interest, finhub_options_chain for a live chain, finhub_calendar for earnings and economic "
        "events, finhub_filings for SEC filings, finhub_etf_holdings for an ETF's largest holdings and "
        "finhub_yield_curve for US Treasury yields, and finhub_portfolio for the user's own recorded holdings. Fractions are fractions: 0.05 = 5%. Results include where each number came from and warnings; report "
        "those warnings to the user rather than hiding them. The finhub_arena_* tools trade in a SIMULATED "
        "market with bots (no real money) for practice and experiments. This is research, not financial advice."
    ),
)


class FinHubUnavailable(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(base_url=BACKEND, timeout=240)


def _call(method: str, path: str, **kwargs) -> dict | list:
    try:
        with _client() as c:
            res = c.request(method, path, **kwargs)
    except httpx.ConnectError as exc:
        raise FinHubUnavailable("FinHub isn't running on this computer. Open the FinHub app, then try again.") from exc
    try:
        body = res.json()
    except ValueError:
        body = {"error": res.text[:500]}
    if res.status_code >= 400:
        detail = body.get("error") or body.get("detail") if isinstance(body, dict) else body
        tried = body.get("attempts") if isinstance(body, dict) else None
        msg = f"FinHub error ({res.status_code}): {detail}"
        if tried:
            msg += " | providers tried: " + "; ".join(f"{a['provider']}: {a.get('error') or 'ok'}" for a in tried)
        raise RuntimeError(msg)
    return body


def _flatten_receipt(r: dict) -> dict:
    out = {"value": r["value"], "unit": r["unit"], "source": r["source"]["provider"]}
    if r.get("currency"):
        out["currency"] = r["currency"]
    if r["source"].get("detail"):
        out["field"] = r["source"]["detail"]
    if r.get("formula"):
        out["formula"] = r["formula"]
    return out


@server.tool(annotations=READ_ONLY)
def finhub_quote(symbol: str) -> dict:
    """Latest quote for a ticker (e.g. AAPL, SPY, BTC-USD): price, change, % change (as a fraction),
    volume, market cap and 52-week range, each with its data source. Change values are computed by
    FinHub from price and previous close."""
    q = _call("GET", f"/market/quote/{symbol.upper()}")
    return {
        "symbol": q["symbol"],
        "currency": q["currency"],
        "provider": q["provider_name"],
        "fetched_at": q["fetched_at"],
        "fallback_used": q["fallback_used"],
        "values": {k: _flatten_receipt(v) for k, v in q["values"].items()},
    }


@server.tool(annotations=READ_ONLY)
def finhub_history(symbol: str, range: Literal["1M", "3M", "6M", "1Y", "5Y", "MAX"] = "1Y", adjusted: bool = True) -> dict:
    """Daily closing prices for a ticker. adjusted=True adjusts for splits and dividends (use it for
    returns and backtests). Long ranges are thinned to at most ~1300 points."""
    h = _call("GET", f"/market/history/{symbol.upper()}", params={"range": range, "adjusted": adjusted})
    bars = h["bars"]
    step = max(1, len(bars) // 1300)
    return {
        "symbol": h["symbol"],
        "provider": h["provider_name"],
        "adjusted": h["adjusted"],
        "fetched_at": h["fetched_at"],
        "points": [{"date": str(b["time"]), "close": round(b["close"], 4)} for b in bars[::step]],
    }


@server.tool(annotations=READ_ONLY)
def finhub_backtest(
    symbol: str,
    strategy: Literal["sma", "momentum", "meanrev"] = "sma",
    params: dict[str, float] | None = None,
    cost_bps: float = 5,
    slippage_bps: float = 5,
    range: Literal["1Y", "5Y", "MAX"] = "MAX",
    allow_short: bool = False,
) -> dict:
    """Backtest a simple rule on adjusted daily prices with FinHub's validation. Strategies and params:
    sma {fast, slow} moving-average crossover; momentum {lookback} time-series momentum; meanrev
    {lookback, entry_z} z-score mean reversion. Returns metrics vs buy-and-hold (before and after
    costs), a look-ahead (causality) check, walk-forward out-of-sample results, the deflated Sharpe
    ratio for the number of parameter combinations tried, and warnings. Always relay the warnings."""
    res = _call(
        "POST",
        "/backtest",
        json={"symbol": symbol, "strategy": strategy, "params": params or {}, "range": range,
              "cost_bps": cost_bps, "slippage_bps": slippage_bps, "allow_short": allow_short},
    )
    curve = res.pop("curve", [])
    step = max(1, len(curve) // 40)
    res["equity_curve_sample"] = [{"date": c["time"], "strategy": round(c["strategy"], 4), "buy_hold": round(c["buy_hold"], 4)} for c in curve[::step]]
    return res


@server.tool(annotations=READ_ONLY)
def finhub_portfolio_risk(holdings: dict[str, float], confidence: float = 0.99, range: Literal["1Y", "5Y", "MAX"] = "5Y", value: float = 10_000) -> dict:
    """Risk of a portfolio given as {ticker: weight} (weights are normalised). Returns one-day VaR and
    expected shortfall (historical, normal and Monte Carlo), a Kupiec backtest of VaR, volatility,
    drawdown, worst periods, correlations, risk contributions, and long-only minimum-variance and
    maximum-Sharpe weights with bootstrap error bars. Losses are positive fractions (0.02 = 2%)."""
    res = _call(
        "POST",
        "/risk",
        json={"holdings": [{"symbol": s, "weight": w} for s, w in holdings.items()], "confidence": confidence, "range": range, "value": value},
    )
    res.pop("histogram", None)
    return res


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def finhub_price_option(
    option_type: Literal["call", "put"],
    spot: float,
    strike: float,
    days_to_expiry: float,
    volatility: float,
    rate: float = 0.04,
    dividend_yield: float = 0.0,
    market_price: float | None = None,
) -> dict:
    """Price a European option (Black–Scholes) and its American version (binomial tree), with Greeks.
    volatility, rate and dividend_yield are FRACTIONS (25% -> 0.25). If market_price is given, also
    returns the implied volatility (None if the price breaks no-arbitrage bounds). Works offline."""
    T = days_to_expiry / 365
    args = (option_type, spot, strike, T, rate, dividend_yield)
    out = {
        "inputs": {"type": option_type, "spot": spot, "strike": strike, "years": T, "volatility": volatility, "rate": rate, "dividend_yield": dividend_yield},
        "european_black_scholes": options.black_scholes(*args, volatility),
        "american_binomial_400": options.binomial(*args, volatility, american=True),
        "greeks": options.greeks(*args, volatility),
    }
    if market_price is not None:
        out["implied_volatility"] = options.implied_vol(market_price, *args)
    return out


@server.tool(annotations=READ_ONLY)
def finhub_fundamentals(symbol: str, period: Literal["annual", "quarter"] = "annual") -> dict:
    """Income statement, balance sheet and cash flow (up to 8 periods) plus key ratios (margins,
    revenue growth, ROE, ROA, debt/equity, free cash flow). Ratios are computed by FinHub only when
    every input exists; each ratio's receipt names the provider field and period it used."""
    return _call("GET", f"/market/fundamentals/{symbol.upper()}", params={"period": period})


@server.tool(annotations=READ_ONLY)
def finhub_macro(country: str = "US") -> dict:
    """OECD macro series for a country (code like US, GB, JP, DE or a name like united_kingdom): CPI
    inflation, unemployment, short and long interest rates, real GDP. unit_kind 'fraction' means
    0.042 = 4.2%; 'as_reported' means the provider did not declare a unit: quote it verbatim with
    the given unit text, never convert it."""
    return _call("GET", f"/macro/{country}")


@server.tool(annotations=READ_ONLY)
def finhub_portfolio() -> dict:
    """The user's own recorded holdings at live prices: shares, FIFO cost basis, value, profit, weights
    and totals per currency. These are personal figures, so only fetch them when the user asks about their
    portfolio. A total is missing when a holding has no live price (see warnings); currencies are never
    added together. Dividends aren't recorded, so returns are price returns. Trades are entered in the app."""
    return _call("GET", "/portfolio")


@server.tool(annotations=READ_ONLY)
def finhub_ownership(symbol: str) -> dict:
    """Insider trades (SEC Form 4), largest institutional holders (13F) and short interest for a
    ticker. Insider totals count open-market or private trades in common stock only; grants, exercises,
    gifts and tax withholding are excluded. Check each row's dates: 13F and short data lag. Sections that
    failed are named under errors."""
    return _call("GET", f"/research/ownership/{symbol}")


@server.tool(annotations=READ_ONLY)
def finhub_options_chain(symbol: str, expiration: str | None = None) -> dict:
    """One expiration of a ticker's live options chain (YYYY-MM-DD; default: the first a week or more
    out), plus at-the-money implied vol and put/call ratios. All expirations are listed. Implied vol is a
    fraction (0.25 = 25%) and null when the provider didn't declare its unit. Quotes can be delayed."""
    return _call("GET", f"/research/options/{symbol}", params={"expiration": expiration} if expiration else None)


@server.tool(annotations=READ_ONLY)
def finhub_calendar(days: int = 7, symbols: list[str] | None = None, limit: int = 100) -> dict:
    """Upcoming earnings and economic events for the next 1 to 31 days. Earnings are listed by date
    then market cap; pass symbols to filter them, and limit caps how many come back. Economic figures stay
    as the provider's text, and event times have no stated time zone. EPS is as reported."""
    params: dict = {"days": days, "limit": limit}
    if symbols:
        params["symbols"] = ",".join(symbols)
    return _call("GET", "/research/calendar", params=params)


@server.tool(annotations=READ_ONLY)
def finhub_filings(symbol: str) -> dict:
    """A US-listed company's latest SEC filings, with form type, date, accession number and a link to
    each document."""
    return _call("GET", f"/research/filings/{symbol}")


@server.tool(annotations=READ_ONLY)
def finhub_etf_holdings(symbol: str) -> dict:
    """An ETF's largest holdings and their weights. This is only part of the fund: `listed` says how
    many holdings the provider published and `listed_weight` how much of the fund they cover."""
    return _call("GET", f"/research/etf/{symbol}")


@server.tool(annotations=READ_ONLY)
def finhub_yield_curve() -> dict:
    """US Treasury par yields by maturity for the latest day, the same curve about a month and a year
    earlier, and the 10y-2y and 10y-3m spreads in basis points. unit_kind 'fraction' means 0.042 = 4.2%;
    'as_reported' means the provider declared no unit: quote it verbatim."""
    return _call("GET", "/research/curve")


@server.tool(annotations=READ_ONLY)
def finhub_screen(
    universe: Literal["large_caps", "watchlist", "custom"] = "large_caps",
    symbols: list[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_change: float | None = None,
    max_change: float | None = None,
    min_market_cap: float | None = None,
    max_from_high: float | None = None,
    min_from_low: float | None = None,
    sectors: list[str] | None = None,
) -> dict:
    """Screen ~60 large caps across all 11 GICS sectors, the watchlist, or custom tickers (1-100).
    Changes and distances are FRACTIONS: min_change=0.02 means up at least 2% today; max_from_high=0.05
    means within 5% of the 52-week high; min_from_low=0.2 means at least 20% above the 52-week low.
    min_market_cap is in currency units (1e11 = 100bn). Tickers lacking data for a set filter are
    excluded; tickers with no quote are listed under 'failed'. Passing symbols screens those tickers."""
    if symbols and universe == "large_caps":
        universe = "custom"
    body = {k: v for k, v in locals().items() if v is not None}
    body.setdefault("sectors", [])
    res = _call("POST", "/screen", json=body)
    for row in res.get("matches", []):
        row.pop("receipts", None)
    return res


@server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def finhub_add_alert(symbol: str, kind: Literal["above", "below", "move_up", "move_down"], threshold: float) -> dict:
    """Create a one-shot price alert in the user's FinHub app (they get a desktop notification when
    it fires). above/below take a price; move_up/move_down take the day's move as a FRACTION
    (0.05 = 5%). Only create alerts the user asked for."""
    return _call("POST", "/alerts", json={"symbol": symbol, "kind": kind, "threshold": threshold})


@server.tool(annotations=READ_ONLY)
def finhub_alerts() -> dict:
    """The user's FinHub price alerts (active and triggered) and recent alert events."""
    return _call("GET", "/alerts")


@server.tool(annotations=READ_ONLY)
def finhub_watchlist() -> dict:
    """The user's FinHub watchlist tickers."""
    return _call("GET", "/watchlist")


# --------------------------------------------------------------------------------------------------
# Agent arena: a SIMULATED market. No real money, no real orders. Shared with the app's ARENA screen.
# --------------------------------------------------------------------------------------------------

SIMULATED = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)


@server.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def finhub_arena_state(name: str | None = None) -> dict:
    """SIMULATED market (no real money). Order book depth, recent trades, mid-price history, the
    leaderboard of bots and agents, recent news events, and (if name is given) your own account. The
    true value is hidden; the informed bot knows it. Bots: market maker, noise, momentum, mean
    reversion, informed. Use finhub_arena_order to trade and finhub_arena_advance to move time."""
    st = _call("GET", "/sim/state", params={"history": 60})
    if name:
        st["your_account"] = _call("GET", f"/sim/account/{name}")
    return st


@server.tool(annotations=SIMULATED)
def finhub_arena_order(name: str, side: Literal["buy", "sell"], qty: int, price: float | None = None) -> dict:
    """SIMULATED market (no real money). Place an order under your participant name (letters, digits,
    _ or -). Without price it is a market order; with price it is a limit order that rests if not
    filled. Returns fills, average price, any resting order and your account (position, cash, P&L
    marked to mid)."""
    body = {"name": name, "side": side, "qty": qty}
    if price is not None:
        body["price"] = price
    return _call("POST", "/sim/order", json=body)


@server.tool(annotations=SIMULATED)
def finhub_arena_cancel(name: str) -> dict:
    """SIMULATED market. Cancel all your resting orders."""
    return _call("POST", "/sim/cancel", json={"name": name})


@server.tool(annotations=SIMULATED)
def finhub_arena_advance(steps: int = 10) -> dict:
    """SIMULATED market. Advance the clock by 1-2000 steps; the bots trade each step. Prices and the
    hidden true value move as time passes, so check finhub_arena_state again afterwards."""
    return _call("POST", "/sim/advance", json={"steps": steps})


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
