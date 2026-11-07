# Changelog

## Unreleased

**New**
- `LEARN` (also `COURSE`): a quant finance course from zero, in the app and the web demo. 37 lessons in
  six tracks (start here, markets and trading, maths, coding, quant methods, getting into the industry),
  quizzes with explanations, try-it buttons that run FinHub commands, resources, and progress saved
  locally. Tracks carry an `access` flag (`free`/`premium`) for future paid courses; no payments yet.

- `FIND`: search about 70,000 stocks and ETFs by name, business, country, sector and size, with FinanceDatabase. `SCREEN` now takes a list of tickers.
- `VOL`: GARCH volatility forecasts with arch, checked each month against a simple guess.
- `BOND`: value a bond with QuantLib: yield, durations, convexity and value on the Treasury curve.
- `MOOD`, `QLIB` and `AGENTS`: finBERT, Microsoft Qlib and TradingAgents as optional engines, installed from `SYS`. `QLIB` and
  `AGENTS` run in the background and are saved, and both stop if FinHub closes.
- `LEARN`: links to Machine Learning for Algorithmic Trading, Financial Models Numerical Methods and more, with try-it buttons for the new commands.
- `READ`: read SEC filings inside FinHub, section by section, and search them, with edgartools.
- `OPTIM`: test ways of choosing weights out of sample against your own, with skfolio.
- `REPORT`: performance reports with QuantStats, for a ticker, a backtest or a paper account.
- `ALPHA`: analyse one signal in depth with Alphalens: prediction by holding period, returns across five groups of stocks,
  and turnover.
- `PAPER`: practice trading with real prices and fake money, on Vibe-Trading's paper ledger. Orders fill at the
  first close still ahead, so nothing can fill at a price you've already seen. No AI provider needed.
- `ALPHA`: Vibe-Trading's library of published signals, 281 of which run on US stocks, with tests on the S&P 500 that run in the background and
  are saved. Results carry their survivorship warning. No AI provider needed.
- `FACTORS`: Fama-French factor returns for 8 regions, from Kenneth French's Data Library.
- `COT`: CFTC Commitments of Traders, as an overview of 34 major markets or for one market.
- `FED`: Fed funds rate and target, SOFR, money supply, inflation expectations and an approximate real rate.
- `SWARM`: Vibe-Trading's 30 teams of AI agents, with live progress for each agent. Nothing starts until you
  press Start team.
- Eight new MCP tools: `finhub_factors`, `finhub_cot`, `finhub_fed`, `finhub_paper_accounts`, `finhub_alpha_library`,
  `finhub_optimise`, `finhub_performance_report` and `finhub_read_filing`.
- `PORT`: your own record of buys, sells and splits, valued at live prices, with first-in, first-out cost
  basis, profit, weights and a button that opens `RISK` with your weights. It can't place orders.
- Six research panels, built on data the OpenBB engine already installs, each with an MCP tool:
  `OWN` (insider trades, institutional holders, short interest), `CHAIN` (live options chain and volatility
  smile), `CAL` (earnings and economic calendars), `FILINGS` (SEC filings), `ETF` (largest holdings) and
  `CURVE` (US Treasury yield curve and spreads).
- Vibe-Trading updated to 0.1.19. Installed engines now update themselves when a new FinHub release pins a newer
  version.
- `ALPHA`, `CAL`, `CHAIN`, `COT`, `CURVE`, `ETF`, `FACTORS`, `FED`, `FILINGS`, `OPTIM`, `OWN`, `PAPER`, `PORT`, `READ`, `REPORT`
  and `SWARM` are now commands, so tickers with those names
  open with `EQ`, for example `EQ CAL`.

**Fixed**
- The top-bar clock overflowed the screen on phones (web demo).
- AI assistants using FinHub's tools only saw "Error executing tool" when one failed, not the reason, including
  when FinHub simply wasn't open.
- On Windows, `ASK`, `BT` and `DEBATE` never started: the agent hung while loading, then gave up with "the agent
  did not start within 180s".
- Installing a new version over an old one could keep running the old backend, because `uv` only looked at
  `pyproject.toml`'s modified time and builds preserve it. New features then failed with "not found".
- `SYS` and the status bar called a working data source "failing" after you asked for a ticker, date or country
  it doesn't have. These now show as "no data", and "failing" means a real error.
- CPI inflation in `MACRO` showed as 0.036 instead of 3.60%.
- The `finhub_screen` MCP tool ignored `symbols` unless `universe` was also set to `custom`, and screened the
  large caps instead.
- Links did nothing in the desktop app on Windows, including news headlines and company websites. They now
  open in your default browser.
- The first market-data request after launch could hang on Windows until another request arrived, because
  OpenBB runs `git` as it loads and `git` blocked on the data worker's request pipe. The app's polling hid
  this; a lone request, such as one from an AI assistant over MCP, timed out.
- On first launch, Yahoo could fail for the whole session with `module 'yfinance' has no attribute 'Ticker'`,
  leaving quotes on the Cboe fallback until a restart. The data worker no longer runs while its engine is
  being installed.

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
