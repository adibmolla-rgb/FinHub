# FinHub

**An open-source market research terminal for your desktop.** One keyboard-driven app for market
data, fundamentals, macro data, a stock screener, a backtester, portfolio risk, an options lab, price
alerts, an AI research agent, and a simulated exchange where you and AI agents trade against bots.
Every number can show you where it came from. A built-in course (`LEARN`) teaches quantitative finance
from zero, with each lesson linked to the tool that demonstrates it.

Free, open source (Apache 2.0), no account. Windows, macOS and Linux.

![Agent arena](docs/screenshot-arena.png)

## Quick links

| I want toâ€¦ | Read |
|---|---|
| Install it | [docs/INSTALL.md](docs/INSTALL.md) |
| Learn quant finance from scratch | Type `LEARN` in the app (or the web demo) |
| Learn every command, with walkthroughs | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) |
| Use FinHub from Claude Desktop, Claude Code or another AI assistant | [docs/AI_ASSISTANTS.md](docs/AI_ASSISTANTS.md) |
| Work on the code (people or Claude Code) | [CLAUDE.md](CLAUDE.md) |
| See what changed | [CHANGELOG.md](CHANGELOG.md) |

## What FinHub is

- **A research workstation.** Look things up, test ideas and measure risk, all from one command bar.
- **Honest about its numbers.** Click any number to see its *receipt*: which data provider it came
  from, the provider's own field name, the reporting period, when it was fetched, and for computed
  values the formula and inputs. Values in different units (percent vs fraction) cannot be mixed
  without an explicit conversion.
- **Hard to fool yourself with.** The backtester trades on the *next* bar, charges costs at every
  fill, checks itself for look-ahead bias, runs walk-forward tests, reports a deflated Sharpe ratio
  for the number of parameter combinations tried, and warns when a result looks too good. Optimal
  portfolio weights come with error bars.
- **Open to AI.** It has its own AI research agent with a visible step-by-step trace, and it is an
  [MCP](https://modelcontextprotocol.io) server, so Claude and other assistants can use its tools.
- **Self-installing.** The installer needs nothing else; on first launch it sets up its own private
  Python and data engine.

## What FinHub is not

- **Not a broker.** It cannot place real orders or touch real money. The only trading is in the
  built-in simulators (`SIM`, `ARENA`) and paper accounts (`PAPER`).
- **Not financial advice.** Analytics and AI answers are research tools; check them.
- **Not a Bloomberg replacement.** Data comes from free public providers (Yahoo Finance, Cboe, Nasdaq,
  TMX, SEC filings, OECD, the US Treasury, the Federal Reserve, the CFTC, the Kenneth French Data Library). Quotes can be delayed, coverage outside US large caps is thinner, and
  providers change or break without notice. FinHub falls back to the next provider and tells you when
  it does.
- **Not a full-market screener.** No free source offers one, so `SCREEN` covers a built-in list of
  ~60 large caps, your watchlist, or tickers you type.
- **Not code-signed yet.** Windows and macOS show a warning the first time you open it
  ([how to get past it](docs/INSTALL.md#the-security-warning)).
- **Not a hosted website.** It runs on your computer. A small web demo (course, options lab and
  simulator) can be built and published separately.

## What it does

| Command | What you get |
|---|---|
| `LEARN` | A course from zero: what quant is, markets and trading, the maths, Python/C++/SQL, quant methods, and how to get hired, with quizzes and a 12-month plan |
| `AAPL` | Quote, candlestick chart (SMA, EMA, Bollinger, RSI), company profile and news |
| `FA AAPL` | Income statement, balance sheet, cash flow and key ratios |
| `MACRO GB` | OECD inflation, unemployment, interest rates and real GDP for a country |
| `PORT BUY AAPL 10 150` | Your own record of trades, valued at live prices: cost basis, profit, weights, and one click to `RISK`. It can't place orders |
| `PAPER BUY AAPL 10` | Practice trading with real prices and fake money. Orders fill at the next close, so you can't trade on a price you've already seen |
| `ALPHA` | A library of 281 published signals for US stocks. Read how they work and test which still predict the S&P 500 |
| `OPTIM SPY 60 TLT 30 GLD 10` | Test ways of choosing weights on data they haven't seen, against your own |
| `REPORT AAPL` | A performance report: Sharpe, drawdowns, returns by month, and alpha and beta against a benchmark |
| `OWN AAPL` | Insider trades, largest institutional holders and short interest |
| `CHAIN AAPL` | Live options chain with a volatility smile, at-the-money implied vol and put/call ratios |
| `CAL` | Upcoming earnings and economic events |
| `FILINGS AAPL` | Latest SEC filings with links to the documents |
| `READ AAPL 10-Q` | Read a filing inside FinHub, section by section, and search it |
| `ETF SPY` | An ETF's largest holdings and their weights |
| `CURVE` | US Treasury yield curve, with spreads and comparisons a month and a year back |
| `FACTORS` | Fama-French factor returns (market, size, value, profitability, investment, momentum) for 8 regions, with t-statistics |
| `COT GOLD` | CFTC Commitments of Traders: how speculators and hedgers are positioned, for 34 major markets or any contract |
| `FED` | Fed funds rate and target, SOFR, money supply, inflation expectations and an approximate real rate |
| `SCREEN` | Filter large caps / your watchlist / any tickers by price, day move, size, 52-week range, sector |
| `FIND battery` | Search about 70,000 stocks and ETFs worldwide by name, business, country, sector and size |
| `VOL SPY` | Forecast volatility with a GARCH model, and check whether it beat a simple guess |
| `BOND 4.5 10` | Value a bond: yield, durations, convexity and its value on today's Treasury curve |
| `MOOD AAPL` | Read the tone of the latest headlines with finBERT, on your computer (optional install) |
| `QLIB` | Train Microsoft Qlib's machine learning workflow on large caps and test it on later years (optional install) |
| `AGENTS TSLA` | TradingAgents: AI analysts, researchers, a trader and a risk team write up one stock (optional install, needs an AI provider) |
| `CMP AAPL MSFT NVDA` | Performance, volatility, Sharpe, drawdown and correlation, side by side |
| `BACKTEST SPY sma 20 50` | A backtest with costs, look-ahead check, walk-forward, deflated Sharpe and a parameter map |
| `RISK SPY 60 TLT 30 GLD 10` | VaR and expected shortfall three ways, a VaR backtest, correlations, optimal weights |
| `OPT AAPL` | Option prices three ways, Greeks, implied volatility, strategy builder with payoffs |
| `ALERT AAPL > 200` Â· `ALERT NVDA -5%` | Price and day-move alerts with desktop notifications |
| `ASK â€¦` Â· `BT â€¦` Â· `DEBATE TSLA` | AI research agent with a live trace of every tool it uses (`NOTES` keeps them) |
| `SWARM` | A team of AI agents works on a question together, choosing from 30 teams such as an investment committee or a risk committee |
| `SIM` Â· `ARENA` | Trade against bots Â· a shared market where AI agents trade too |
| `W NVDA` Â· `MCP` Â· `AI` Â· `HELP` | Watchlist Â· connect AI assistants Â· pick the AI provider Â· all commands |

Full reference and walkthroughs: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

![Options lab](docs/screenshot-options.png)

## Install (short version)

1. Download the installer for your system: from the latest
   [release](https://github.com/adibmolla-rgb/FinHub/releases), or from the latest green
   [CI run](https://github.com/adibmolla-rgb/FinHub/actions/workflows/ci.yml) â†’ **Artifacts**
   (`finhub-windows-latest`, `finhub-macos-latest`, `finhub-ubuntu-22.04`).
2. Run it. Windows: *More info â†’ Run anyway*. macOS: see the [install guide](docs/INSTALL.md#the-security-warning).
3. First launch takes a few minutes (it downloads its own Python and data engine, once).

Details, troubleshooting and uninstalling: [docs/INSTALL.md](docs/INSTALL.md).

## Use it from Claude

FinHub is an MCP server with 34 tools (quotes, history, fundamentals, macro, ownership, options chains,
calendars, filings, ETF holdings, the yield curve, factors, futures positioning, Federal Reserve data, your recorded holdings, screener, backtests,
portfolio risk, option pricing, alerts, watchlist, and trading in the simulated arena). Type `MCP` in
the app for the exact setup line for your computer, or see [docs/AI_ASSISTANTS.md](docs/AI_ASSISTANTS.md).
Claude Code opened in this repository connects automatically via [.mcp.json](.mcp.json).

## Status: what has and hasn't been verified

FinHub v0.4 was built in a sandbox that blocks finance websites and AI providers. Be clear about
what that means:

| Area | Status |
|---|---|
| Analytics maths (backtester, risk, options, indicators, simulator, receipts) | âœ… 457 automated tests across the app, backend and data engine, many against textbook and reference values |
| App, backend and engines on Windows, macOS, Linux | âœ… Built and tested in CI on all three on every change |
| Installer on a clean machine | âœ… Linux `.deb` installed and run as a fresh user (self-setup, data-engine install, clean shutdown). Windows installer installed and opened by hand in November 2026. The macOS installer builds in CI but was not hand-installed |
| MCP server | âœ… Tested end to end over stdio, including an agent trading in the arena |
| Live market data, fundamentals, macro and research panels against real providers | âœ… Seen working on Windows in November 2026. Free providers can still change or break without notice |
| Screener against real providers | âœ… Seen working on Windows in November 2026 (61 of 61 large caps quoted) |
| AI agent answering with a real API key | âš ï¸ Requests verified to reach Anthropic's API (rejected only for a placeholder key) |

If something fails against live data, the error panels name each provider tried and why it failed,
and the logs are in your FinHub data folder ([where](docs/INSTALL.md#where-finhub-keeps-its-files)).
Please open an issue with them.

## How it fits together

```
app/                    Desktop app: Tauri 2 (Rust) shell + React/TypeScript interface
backend/                Local API (FastAPI on 127.0.0.1:8765) and the finhub-mcp server
engines/openbb/         Isolated Python env: OpenBB + yfinance, and FinHub's data worker
engines/vibe-trading/   Isolated Python env: the Vibe-Trading AI research agent
```

More in [CLAUDE.md](CLAUDE.md#architecture).

## Credits and licence

Apache 2.0. FinHub runs [OpenBB](https://github.com/openbq-org/OpenBB) (Apache 2.0),
[Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) (MIT) and [yfinance](https://github.com/ranaroussi/yfinance)
(Apache 2.0) as separate engines, uses [skfolio](https://github.com/skfolio/skfolio) (BSD), [QuantStats](https://github.com/ranaroussi/quantstats) (Apache 2.0) and
[Alphalens](https://github.com/stefan-jansen/alphalens-reloaded) (Apache 2.0) inside the agent engine, and
[edgartools](https://github.com/dgunning/edgartools) (MIT) inside the data engine, and draws charts with
[TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) (Apache 2.0). See
[NOTICE](NOTICE). Market data is subject to each provider's terms; FinHub is for personal research.
FinHub is not affiliated with any of these projects, or with Bloomberg, Fincept or Finnhub.
