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
        "Sharpe ratio, finhub_portfolio_risk for VaR/ES and correlations, and finhub_price_option for "
        "option values and Greeks. Results include where each number came from and warnings; report "
        "those warnings to the user rather than hiding them. This is research, not financial advice."
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
def finhub_watchlist() -> dict:
    """The user's FinHub watchlist tickers."""
    return _call("GET", "/watchlist")


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
