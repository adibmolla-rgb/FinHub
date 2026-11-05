# Changelog

## 0.4.0

**New**
- `FA`: financial statements (annual/quarterly) and key ratios with receipts naming provider fields and periods.
- `MACRO`: OECD inflation, unemployment, interest rates and real GDP; units taken from provider metadata.
- `SCREEN`: screener over ~60 large caps, the watchlist, or typed tickers.
- `CMP`: compare up to 8 tickers (adjusted prices, correlations).
- `BACKTEST`: FinHub's backtester with next-bar fills, costs, a causality (look-ahead) check, walk-forward
  testing, deflated Sharpe ratio, parameter sensitivity map, warnings and CSV export.
- `RISK`: VaR/ES three ways, Kupiec VaR backtest, risk contributions, correlations, min-variance and
  max-Sharpe weights with bootstrap error bars.
- `OPT`: options lab: Black–Scholes, binomial (American) and Monte Carlo side by side, Greeks, implied
  volatility, strategy builder with payoff diagrams.
- `ALERT` / `ALERTS`: price and day-move alerts with desktop notifications.
- `ARENA`: shared simulated market for AI agents; MCP tools to trade in it.
- MCP server `finhub-mcp` with 15 tools; `MCP` command shows setup.
- Chart indicators (SMA 20/50/200, EMA 20, Bollinger, RSI), watchlist (`W`), research history (`NOTES`),
  command suggestions, panel focus mode, copy-as-CSV, saved command history.
- Web demo build (options lab and simulator in a browser) and a Pages publishing workflow.
- Docs: install guide, user guide, AI assistants guide, CLAUDE.md.

**Fixed**
- Windows/macOS builds broken by module names differing only by case (now tested).
- Index tickers such as `^GSPC` were rejected by the command bar and watchlist.
- Command errors were invisible on screens without an activity log (now shown as a banner).

## 0.3.0

- Self-installing desktop app: bundled uv sets up a private Python on first launch; data engine
  installs automatically; no console windows on Windows; backend stops with the app.
- AI research agent (`ASK`, `BT`, `DEBATE`) on Vibe-Trading with a live reasoning trace; `AI` settings.
- `SIM`: market simulator with five bot strategies and news/crash/drain scenarios.
- Fixed: Claude 5-family models rejected non-default temperature; fast agent failures were not shown.

## 0.2.0

- Market data: quote, chart, profile and news with receipts and provider fallback (Yahoo → Cboe →
  Nasdaq → TMX); data-source health in `SYS`.
- Fixed: concurrent OpenBB calls broke its asyncio locks; misleading Yahoo errors.

## 0.1.0

- Foundation: Tauri shell, local backend, engine registry for OpenBB and Vibe-Trading in isolated
  environments, receipts with unit-safe arithmetic, command bar.
