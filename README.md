# FinHub

**An open-source market research terminal for your desktop.** One keyboard-driven app for market
data, fundamentals, macro data, a stock screener, a backtester, portfolio risk, an options lab, price
alerts, an AI research agent, and a simulated exchange where you and AI agents trade against bots.
Every number can show you where it came from. A built-in course (`LEARN`) teaches quantitative finance
from zero, with each lesson linked to the tool that demonstrates it.

Free, open source (Apache 2.0), no account. Windows, macOS and Linux.

![Agent arena](docs/screenshot-arena.png)

## Quick links

| I want to… | Read |
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
  built-in simulators (`SIM`, `ARENA`).
- **Not financial advice.** Analytics and AI answers are research tools; check them.
- **Not a Bloomberg replacement.** Data comes from free public providers (Yahoo Finance, Cboe, Nasdaq,
  TMX, SEC filings, OECD). Quotes can be delayed, coverage outside US large caps is thinner, and
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
| `SCREEN` | Filter large caps / your watchlist / any tickers by price, day move, size, 52-week range, sector |
| `CMP AAPL MSFT NVDA` | Performance, volatility, Sharpe, drawdown and correlation, side by side |
| `BACKTEST SPY sma 20 50` | A backtest with costs, look-ahead check, walk-forward, deflated Sharpe and a parameter map |
| `RISK SPY 60 TLT 30 GLD 10` | VaR and expected shortfall three ways, a VaR backtest, correlations, optimal weights |
| `OPT AAPL` | Option prices three ways, Greeks, implied volatility, strategy builder with payoffs |
| `ALERT AAPL > 200` · `ALERT NVDA -5%` | Price and day-move alerts with desktop notifications |
| `ASK …` · `BT …` · `DEBATE TSLA` | AI research agent with a live trace of every tool it uses (`NOTES` keeps them) |
| `SIM` · `ARENA` | Trade against bots · a shared market where AI agents trade too |
| `W NVDA` · `MCP` · `AI` · `HELP` | Watchlist · connect AI assistants · pick the AI provider · all commands |

Full reference and walkthroughs: [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

![Options lab](docs/screenshot-options.png)

## Install (short version)

1. Download the installer for your system: from the latest
   [release](https://github.com/adibmolla-rgb/FinHub/releases), or from the latest green
   [CI run](https://github.com/adibmolla-rgb/FinHub/actions/workflows/ci.yml) → **Artifacts**
   (`finhub-windows-latest`, `finhub-macos-latest`, `finhub-ubuntu-22.04`).
2. Run it. Windows: *More info → Run anyway*. macOS: see the [install guide](docs/INSTALL.md#the-security-warning).
3. First launch takes a few minutes (it downloads its own Python and data engine, once).

Details, troubleshooting and uninstalling: [docs/INSTALL.md](docs/INSTALL.md).

## Use it from Claude

FinHub is an MCP server with 15 tools (quotes, history, fundamentals, macro, screener, backtests,
portfolio risk, option pricing, alerts, watchlist, and trading in the simulated arena). Type `MCP` in
the app for the exact setup line for your computer, or see [docs/AI_ASSISTANTS.md](docs/AI_ASSISTANTS.md).
Claude Code opened in this repository connects automatically via [.mcp.json](.mcp.json).

## Status: what has and hasn't been verified

FinHub v0.4 was built in a sandbox that blocks finance websites and AI providers. Be clear about
what that means:

| Area | Status |
|---|---|
| Analytics maths (backtester, risk, options, indicators, simulator, receipts) | ✅ 124 automated tests, many against textbook and reference values |
| App, backend and engines on Windows, macOS, Linux | ✅ Built and tested in CI on all three on every change |
| Installer on a clean machine | ✅ Linux `.deb` installed and run as a fresh user (self-setup, data-engine install, clean shutdown). Windows/macOS installers build in CI but were not hand-installed |
| MCP server | ✅ Tested end to end over stdio, including an agent trading in the arena |
| Live market data, fundamentals, macro, screener against real providers | ⚠️ **Not yet seen working live.** Provider fallback, error reporting and every screen are tested with recorded or synthetic data |
| AI agent answering with a real API key | ⚠️ Requests verified to reach Anthropic's API (rejected only for a placeholder key) |

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
(Apache 2.0) as separate engines, and draws charts with
[TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts) (Apache 2.0). See
[NOTICE](NOTICE). Market data is subject to each provider's terms; FinHub is for personal research.
FinHub is not affiliated with any of these projects, or with Bloomberg, Fincept or Finnhub.
