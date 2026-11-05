# Using FinHub from Claude and other AI assistants

FinHub is an [MCP](https://modelcontextprotocol.io) server. Once connected, Claude Desktop, Claude
Code or any MCP client can call FinHub's tools: look up prices, fundamentals and macro data, screen
stocks, run checked backtests, measure portfolio risk, price options, manage alerts, and trade in a
simulated market. Answers carry FinHub's receipts and warnings.

- [How it works](#how-it-works)
- [Connect Claude Desktop](#connect-claude-desktop)
- [Connect Claude Code](#connect-claude-code)
- [Other MCP clients](#other-mcp-clients)
- [Tools](#tools)
- [Example prompts](#example-prompts)
- [The arena: AI agents trading](#the-arena-ai-agents-trading)
- [Safety and limits](#safety-and-limits)
- [Troubleshooting](#troubleshooting)

## How it works

```
Claude Desktop / Claude Code ──stdio──> finhub-mcp ──HTTP──> FinHub app (backend on 127.0.0.1:8765)
```

`finhub-mcp` is a small program installed with FinHub. Data, backtest, risk, screener, alert and
arena tools go through the **running FinHub app**, so keep FinHub open while Claude uses them.
`finhub_price_option` is computed locally and works even when FinHub is closed.

## Connect Claude Desktop

1. Open FinHub (after its first-launch setup has finished) and type `MCP`. It shows the exact path to
   `finhub-mcp` on your computer and a ready-made config. Typical paths:

   | System | `finhub-mcp` |
   |---|---|
   | Windows | `%LOCALAPPDATA%\app.finhub.terminal\envs\backend\Scripts\finhub-mcp.exe` |
   | macOS | `~/Library/Application Support/app.finhub.terminal/envs/backend/bin/finhub-mcp` |
   | Linux | `~/.local/share/app.finhub.terminal/envs/backend/bin/finhub-mcp` |

2. In Claude Desktop: **Settings → Developer → Edit Config**, and add FinHub to
   `claude_desktop_config.json` (use the full path FinHub showed you; on Windows, double the
   backslashes in JSON):

   ```json
   {
     "mcpServers": {
       "finhub": {
         "command": "C:\\Users\\YOU\\AppData\\Local\\app.finhub.terminal\\envs\\backend\\Scripts\\finhub-mcp.exe"
       }
     }
   }
   ```

3. Restart Claude Desktop. FinHub's tools appear in the tools menu. Try: *"Use FinHub to get the
   latest quote for MSFT."*

## Connect Claude Code

From any folder, with the path FinHub's `MCP` command shows:

```bash
claude mcp add finhub -- "/path/to/finhub-mcp"
```

**Working inside this repository?** It already contains [.mcp.json](../.mcp.json), which runs
`finhub-mcp` from the source checkout with `uv`. Claude Code offers to enable it when you open the
repo. Start the backend first (`uv run finhub-backend` in `backend/`, or run the app).

## Other MCP clients

Run the `finhub-mcp` executable over **stdio** (no arguments). Optional environment variable:
`FINHUB_BACKEND_URL` (default `http://127.0.0.1:8765`).

## Tools

All values follow one rule: **fractions are fractions** (0.05 = 5%) unless a field says otherwise.

### Market data and research (read-only)

| Tool | Arguments | Returns |
|---|---|---|
| `finhub_quote` | `symbol` | Price, change, % change, volume, market cap, 52-week range; each value with unit, source, provider field, formula |
| `finhub_history` | `symbol`, `range` (`1M`…`MAX`), `adjusted` (default true) | Daily closes (thinned to ≤1300 points) with provider and adjustment flag |
| `finhub_fundamentals` | `symbol`, `period` (`annual`/`quarter`) | Three statements + key ratios with receipts |
| `finhub_macro` | `country` (code or name) | OECD CPI, unemployment, interest rates, real GDP; `unit_kind` = `fraction` or `as_reported` (quote verbatim) |
| `finhub_screen` | `universe` (`large_caps`/`watchlist`/`custom`), `symbols`, `min_price`, `max_price`, `min_change`, `max_change`, `min_market_cap`, `max_from_high`, `min_from_low`, `sectors` | Matching tickers; tickers without quotes listed under `failed` |
| `finhub_watchlist` | – | The user's watchlist |
| `finhub_alerts` | – | The user's alerts and recent alert events |

### Analysis (read-only)

| Tool | Arguments | Returns |
|---|---|---|
| `finhub_backtest` | `symbol`, `strategy` (`sma`/`momentum`/`meanrev`), `params` (`{fast, slow}` / `{lookback}` / `{lookback, entry_z}`), `cost_bps`, `slippage_bps`, `range`, `allow_short` | Metrics vs buy-and-hold (before/after costs), causality check, walk-forward folds and parameter surface, deflated Sharpe, **warnings**, sampled equity curve |
| `finhub_portfolio_risk` | `holdings` (`{ticker: weight}`), `confidence`, `range`, `value` | VaR/ES three ways, Kupiec backtest, volatility, drawdown, worst periods, correlations, risk contributions, min-variance and max-Sharpe weights with bootstrap error bars, **warnings** |
| `finhub_price_option` | `option_type`, `spot`, `strike`, `days_to_expiry`, `volatility`, `rate`, `dividend_yield`, `market_price` (optional) | European (Black–Scholes) and American (binomial) prices, Greeks, implied volatility. Works offline |

### Actions (change state, never touch money)

| Tool | Arguments | Effect |
|---|---|---|
| `finhub_add_alert` | `symbol`, `kind` (`above`/`below`/`move_up`/`move_down`), `threshold` | Creates a one-shot alert in the user's app (desktop notification when it fires). Move thresholds are fractions |
| `finhub_arena_state` | `name` (optional) | **Simulated** market: order book, trades, mid history, leaderboard, events, your account |
| `finhub_arena_order` | `name`, `side`, `qty`, `price` (optional: limit order) | Places a **simulated** order under your participant name |
| `finhub_arena_cancel` | `name` | Cancels your **simulated** resting orders |
| `finhub_arena_advance` | `steps` (1–2000) | Moves the **simulated** clock; bots trade each step |

## Example prompts

- *"Use FinHub to compare AAPL, MSFT and GOOGL fundamentals. Show margins and ROE, and tell me which
  provider fields each ratio came from."*
- *"Backtest a 50/200 moving-average crossover on SPY with FinHub using MAX history. Is the deflated
  Sharpe above 95%? Summarise the warnings."*
- *"Try momentum lookbacks on QQQ with finhub_backtest and look at the parameter surface. Is there a
  robust plateau or a lone spike?"*
- *"What's the 99% one-day VaR of 60% SPY, 30% TLT, 10% GLD? Which holding contributes most risk?"*
- *"Screen the large caps for stocks within 5% of their 52-week high that are up today."*
- *"What's inflation and unemployment doing in the UK according to FinHub's macro data?"*
- *"Price a 3-month at-the-money put on AAPL at 30% volatility and give me the Greeks."*
- *"Set a FinHub alert if NVDA falls 5% in a day."*

## The arena: AI agents trading

`ARENA` in FinHub is one shared simulated market. Bots trade in it: a market maker, noise traders,
momentum, mean reversion, and an informed trader who knows the hidden "true value". AI agents join
under their own names through the `finhub_arena_*` tools and appear on the leaderboard. You can
watch, run the clock, trigger news or a crash, and trade yourself.

A good prompt for Claude:

> Use FinHub's arena tools and trade as "claude". First read the state: the book, the spread, recent
> trades. Then try to make money over about 200 steps by trading and advancing the clock in small
> increments. Before each order, explain your reasoning. At the end, report your P&L and what you
> learned about the market maker and the informed trader.

Ideas for experiments:
- Several AI assistants under different names: who earns the spread, who gets picked off?
- Trigger **Bad news** in FinHub mid-session and see how the agent reacts.
- Ask the agent to make markets (resting limit orders on both sides) instead of taking liquidity.

## Safety and limits

- Market, research and analysis tools are **read-only** (marked `readOnlyHint` for clients).
- `finhub_add_alert` writes to the user's alert list; agents should only add alerts the user asked for.
- Arena tools only ever change the **simulation**. FinHub has no broker connection and cannot place
  real orders.
- Everything runs on the user's computer (`127.0.0.1`); the MCP server does not listen on a network
  port.
- Data limits are the app's: free providers, possibly delayed, fallback reported. Results are research,
  not financial advice; tools return warnings and agents should relay them.

## Troubleshooting

| Problem | Fix |
|---|---|
| "FinHub isn't running on this computer" | Open the FinHub app, wait for "backend online", try again |
| Tools don't appear in Claude Desktop | Check the path in `claude_desktop_config.json` (type `MCP` in FinHub to copy it), restart Claude Desktop |
| `finhub-mcp` not found | FinHub creates it during first-launch setup; open FinHub once and let it finish |
| "no provider could serve…" | The data providers couldn't be reached; the message lists each one and why |
