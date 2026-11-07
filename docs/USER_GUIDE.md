# FinHub user guide

Everything in FinHub runs from the **command bar** at the top. Press `Ctrl+K` (`Cmd+K` on a Mac) or `/`
to jump to it, type a command, press Enter.

- Start typing and suggestions appear; **Tab** completes the first one.
- **↑ / ↓** walk your command history (kept between sessions).
- Click any underlined number to open its **receipt** (see [Receipts](#receipts)).
- Double-click a panel's title bar (or press ⤢) to **maximise** it; **Esc** restores.
- On the home screen, click any example in the HELP panel to run it.

Contents: [Commands](#command-reference) · [Receipts](#receipts) · [Walkthroughs](#walkthroughs) ·
[Data sources](#data-sources) · [Tips](#tips)

## Command reference

### Markets

| Command | Example | What it does |
|---|---|---|
| *ticker* | `AAPL` | Quote strip, candlestick chart with volume, company profile and news. Tickers follow Yahoo conventions: `BRK-B`, `^GSPC` (S&P 500 index), `EURUSD=X`, `BTC-USD`, `SHEL.L` (London). |
| `EQ` | `EQ MSFT 5Y` | Same, choosing the chart range: `1M 3M 6M 1Y 5Y MAX`. |
| *range* | `6M` | Change the open chart's range. |
| `FA` | `FA AAPL` | Income statement, balance sheet, cash flow (annual or quarterly), and key ratios: margins, revenue growth, ROE, ROA, debt/equity, free cash flow. |
| `MACRO` | `MACRO GB` | OECD CPI inflation, unemployment, short and long interest rates, and real GDP, with 10-year charts. Countries by code (`US GB JP DE FR CA IT AU KR MX ES NL CH SE NO NZ IE PL TR BR ZA IN CN`) or name (`MACRO united kingdom`). |
| `OWN` | `OWN AAPL` | Insider trades from SEC Form 4, the largest institutional holders from 13F filings, and short interest with days to cover. Insider totals count only open-market or private trades in common stock over the last 90 days: grants, option exercises, gifts and tax withholding are listed but not counted. 13F and short interest data lag, so check their dates. |
| `CHAIN` | `CHAIN AAPL`, `CHAIN AAPL 2027-01-15` | Live options chain for one expiration (by default the first a week or more out; pick another from the menu), a volatility smile, at-the-money implied vol and put/call ratios. Shows strikes within 25% of the price unless you choose **All strikes**. Quotes can be delayed. |
| `CAL` | `CAL`, `CAL 14` | Earnings and economic events for the next 7 days, or 1 to 31. Filter earnings by name or your watchlist, and events by country. Economic figures are shown exactly as published. |
| `FILINGS` | `FILINGS AAPL` | A US-listed company's latest SEC filings, filterable by form, with links to each document. |
| `ETF` | `ETF SPY` | An ETF's largest holdings and their weights. This is only part of the fund: the panel says how much of it the listed holdings cover. |
| `CURVE` | `CURVE` | US Treasury par yields by maturity, compared with a month and a year earlier, and the 10-year minus 2-year and 10-year minus 3-month spreads. A negative spread means the curve is inverted. |
| `CMP` | `CMP AAPL MSFT NVDA` | 2 to 8 tickers on one growth-of-1 chart (dividend-adjusted), with return, CAGR, volatility, Sharpe, max drawdown and correlations. |
| `SCREEN` | `SCREEN` | Filter a universe (built-in ~60 large caps, your watchlist, or tickers you type) by price, day change, market cap, distance from the 52-week high/low, and sector. Click a column to sort. |
| `W` | `W NVDA`, `W -NVDA` | Add to / remove from the watchlist on the home screen. |
| `ALERT` | `ALERT AAPL > 200`, `ALERT AAPL < 150`, `ALERT NVDA +5%`, `ALERT NVDA -5%` | One-shot alerts on a price level or the day's move. Checked every 2 minutes while FinHub is open; you get a banner and a desktop notification. `ALERTS` lists them. |

Commands take priority over tickers of the same name. To open a company whose ticker is also a command, use `EQ`: `EQ CAL` opens Caleres.

Chart indicators: toggle `SMA20 SMA50 SMA200 EMA20 BB RSI` on the chart toolbar (remembered).

### Analysis

| Command | Example | What it does |
|---|---|---|
| `BACKTEST` | `BACKTEST SPY sma 20 50`, `BACKTEST QQQ momentum 126`, `BACKTEST GLD meanrev 20 2` | FinHub's backtester. See [Testing a strategy](#testing-a-strategy-properly). |
| `PORT` | `PORT`, `PORT BUY AAPL 10 150`, `PORT SELL AAPL 5 180 2026-03-01 fee=1.50`, `PORT SPLIT NVDA 10` | Your own record of trades, valued at live prices. See [Tracking your portfolio](#tracking-your-portfolio). |
| `RISK` | `RISK SPY 60 TLT 30 GLD 10` | Portfolio risk (ticker then weight; weights are normalised). See [Measuring portfolio risk](#measuring-portfolio-risk). |
| `OPT` | `OPT`, `OPT AAPL` | Options lab; with a ticker it starts from the live price. See [Pricing options](#pricing-options-and-strategies). |

### AI

| Command | Example | What it does |
|---|---|---|
| `AI` | `AI` | Choose the agent's model: Claude, OpenAI (API key) or Ollama (free, local). |
| `ASK` | `ASK is NVDA momentum still working after costs?` | Research question. The **trace** panel shows every tool the agent uses (data fetches, code, backtests) with inputs and results; the answer streams in beside it. |
| `BT` | `BT SPY 20/50 day moving-average crossover` | The agent writes and runs a backtest, instructed to use next-bar fills, costs and a buy-and-hold comparison. Use `BACKTEST` for FinHub's own checked engine. |
| `DEBATE` | `DEBATE TSLA` | Bull case, bear case and a neutral judge. |
| `NOTES` | `NOTES` | Every past `ASK`/`BT`/`DEBATE` run: answer, prompt, tool trace, and **Run again**. |
| `MCP` | `MCP` | The exact setup for using FinHub from Claude Desktop / Claude Code ([guide](AI_ASSISTANTS.md)). |

### Simulators

| Command | What it does |
|---|---|
| `SIM` | Your own market against five bots. Keys: **B** buy, **S** sell, **F** flatten, **Space** pause. Buttons trigger good/bad news, a flash crash or a liquidity drain; **Reveal true value** shows what the informed bot knows. |
| `ARENA` | One shared market that AI agents trade in through MCP. Watch the leaderboard, run the clock, trigger events, or trade alongside them. |

### App

| Command | What it does |
|---|---|
| `LEARN` | The course: learn quant finance from zero (see [Learning quant finance](#learning-quant-finance)). Also `COURSE`. |
| `HOME` | Home screen: system status, watchlist, commands, activity log. |
| `SYS` | Backend, engines (install buttons) and data-source health. |
| `RCPT` | A worked example of a receipt. |
| `REFRESH` | Reload the current view and re-check engines. |
| `CLEAR` | Clear the activity log. |
| `HELP` | Every command. |

## Learning quant finance

`LEARN` opens a self-paced course for complete beginners: 37 lessons in six tracks, roughly 18 hours of
reading plus practice.

1. **Start here**: what quantitative finance is, the jobs (trader, researcher, developer, risk), and how to
   use the course.
2. **Markets and trading**: what is traded, the order book, market makers, returns and risk, shorting and
   leverage, options, company accounts, macro.
3. **The maths**: from logs and sums through probability, distributions, statistics, linear algebra,
   calculus, regression and random walks to Black–Scholes.
4. **Coding**: Python from first principles, NumPy and pandas, an honest first backtest, algorithms, C++,
   SQL, Git and testing.
5. **Quant methods**: backtesting without fooling yourself, portfolios and risk, factors, option pricing,
   market making, machine learning done carefully.
6. **Getting into the industry**: what interviews test, projects worth building, competitions and
   applications, and a 12-month plan from zero.

Each lesson has a short quiz with explanations, buttons that run the matching FinHub command (for example
`BACKTEST SPY sma 50 200` in the backtesting lesson), and links to free courses and standard books.
Progress (✓) is saved on this computer only. In the web demo, lessons whose tools need live data mark
their buttons "desktop app".

The course is education, not financial advice.

## Receipts

Most numbers in FinHub are buttons. Clicking one opens a panel showing:

- **unit**: `fraction` (0.05 means 5%), `currency`, `shares`, `ratio`, or `as_reported` (the provider
  did not declare a unit, so FinHub shows the number exactly as given and never converts it);
- **source**: the provider (e.g. "Yahoo Finance (yfinance)", "SEC filings (via OpenBB)") and the
  provider's own field name and period, e.g. `Total Revenue · period ending 2025-09-30`;
- **time** fetched;
- for computed values, the **formula** and its **inputs**, each with its own receipt.

FinHub computes changes, percentage changes and ratios itself from raw inputs, because providers
disagree on whether "1.5" means 1.5% or 150%.

## Walkthroughs

### Researching a company

1. `AAPL`: price, chart, profile, news. Turn on `SMA50` and `RSI` on the chart.
2. `FA AAPL`: margins, growth, returns, debt. Click a ratio to see exactly which line items fed it.
3. `CMP AAPL MSFT GOOGL`: how it has done against peers, and how correlated they are.
4. `OPT AAPL`: what the options market's volatility implies (enter an option's market price to get
   its implied volatility).
5. `ASK what are the main risks in Apple's latest results?` (needs `AI` set up).

### Testing a strategy properly

`BACKTEST SPY sma 20 50` (moving-average crossover), `momentum 126` (time-series momentum, lookback in
days) or `meanrev 20 2` (z-score mean reversion: lookback, entry z). Choose **MAX** history for the
walk-forward test. Read the **"Can you trust this result?"** panel first:

- **No look-ahead**: the signals were recomputed on truncated history and matched.
- **Next-bar fills**: a signal from today's close trades at tomorrow's close.
- **Costs**: commission + slippage in basis points (1 bp = 0.01%) at every trade. Compare the
  *Strategy* and *Before costs* columns.
- **Walk-forward**: parameters chosen on past data only, then tested on the next period. Out-of-sample
  far worse than full-sample means overfitting.
- **Deflated Sharpe**: the probability the edge is real after accounting for how many parameter
  combinations were tried. Below 95% means the result is consistent with luck.
- **Parameter map**: Sharpe for every combination. A broad green area suggests a robust effect; one
  bright cell among red suggests luck.

Then compare with buy-and-hold. Most simple strategies don't beat it after costs; FinHub is built
to show you that rather than hide it. **Copy metrics** / **Copy equity curve** paste into Excel.

### Measuring portfolio risk

`RISK SPY 60 TLT 30 GLD 10`, choose 95% or 99% confidence:

- **VaR**: on 1 day in 100 (at 99%) expect to lose at least this much. **Expected shortfall**: the
  average loss on those days. Shown three ways (historical, normal, Monte Carlo); big differences
  between them mean fat tails.
- **VaR backtest (Kupiec)**: would rolling VaR have been breached about as often as it should have?
- **Share of risk**: a holding can be 10% of the money and 40% of the risk.
- **Alternative weights**: minimum-variance and maximum-Sharpe portfolios with **±** error bars from
  resampling history. Large ± means the "optimal" weights are mostly noise.

### Tracking your portfolio

`PORT` is a record you keep yourself. It has no broker connection and can't place orders.

1. Add a trade from the form in the panel, or type it: `PORT BUY AAPL 10 150`. Add a date and fees if you
   want them: `PORT SELL AAPL 5 180 2026-03-01 fee=1.50`.
2. Enter prices in the currency the ticker is quoted in. London tickers are often quoted in pence.
3. When a company splits its shares, record it yourself: `PORT SPLIT NVDA 10` for a 10-for-1 split, or
   `PORT SPLIT XYZ 0.5` for a 1-for-2 reverse split. FinHub doesn't detect splits, and profit would be wrong
   without this.
4. Click **Measure risk** to open `RISK` with your current weights.

How the numbers work:

- Cost basis is first-in, first-out, with fees included. Trades are worked through in date order, so you can
  enter old ones in any order. A sale of more than you held on that date is refused.
- Dividends aren't recorded, so returns are price returns.
- If a holding has no live price, value and cost totals are left out until it does, because a smaller total
  would look complete.
- Each currency has its own totals. They're never converted or added together.

Your trades are stored only on this computer, in `portfolio.json` in your FinHub data folder. If that file
is damaged, FinHub says so and won't change it.

### Pricing options and strategies

`OPT` (or `OPT AAPL`). Enter spot, strike, days, volatility, rate and dividend yield as you'd write
them (25 for 25%). The price is computed three independent ways (Black–Scholes, a binomial tree and
Monte Carlo) and FinHub checks they agree. Tick **American** for early exercise. Greeks are per 1.00
of spot, per volatility point, per day and per rate point. In **Strategy builder**, pick a preset
(spreads, straddle, iron condor, butterfly…) or edit legs; the chart shows profit at expiry and
halfway there, with break-evens.

### Practising market making

`SIM`. Try to make money by buying near the bid and selling near the offer. Your P&L splits into
**Spread** (what you earned by trading better than mid) and **After trade** (how the price moved
after you traded; persistently negative means better-informed traders are picking you off: adverse
selection). Press **Good news** and watch the informed bot move the price before the market maker
catches up.

### Letting an AI agent trade

Connect Claude ([guide](AI_ASSISTANTS.md)), open `ARENA` in FinHub, and ask Claude: *"Use FinHub's
arena: look at the order book and recent trades, then try to make money over 200 steps. Trade as
'claude'. Explain each decision."* Its trades appear on the leaderboard and tape.

## Data sources

| Data | Providers, in order (first that answers wins) |
|---|---|
| Quotes, daily history | Yahoo → Cboe → Nasdaq → TMX |
| Company profile | Yahoo → Nasdaq → TMX → FINRA |
| News | Yahoo → Nasdaq → TMX |
| Financial statements | Yahoo → SEC filings → Nasdaq → TMX |
| Macro | OECD |
| Insider trades | SEC filings → Nasdaq |
| Institutional holders | Nasdaq |
| Short interest | Nasdaq → FINRA |
| Options chains | Cboe's delayed feed → Cboe via OpenBB → Nasdaq |
| Earnings and economic calendars | Nasdaq |
| SEC filings | SEC |
| ETF holdings | Nasdaq |
| Treasury yields | US Treasury → Federal Reserve |

Every panel says which provider served it and whether a fallback was needed; `SYS` tracks each
provider's recent successes and failures. Backtests, risk and comparisons use prices adjusted for
splits and dividends; the ticker chart shows prices as traded. Insider totals only appear when the data
comes from SEC filings, and implied volatility only when the provider supplies it in a declared unit.

## Tips

- Everything works from the keyboard; the mouse is optional.
- **Copy CSV** buttons appear on backtests, statements, comparisons and the screener.
- Your watchlist, alerts, portfolio, AI settings and agent history live in your FinHub data folder
  ([where](INSTALL.md#where-finhub-keeps-its-files)).
- If a panel shows "Couldn't load…", the table under it lists every provider tried and why it failed.
