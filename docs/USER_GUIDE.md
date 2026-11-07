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
| `FACTORS` | `FACTORS`, `FACTORS EUROPE`, `FACTORS US 10` | Fama-French factor returns from Kenneth French's Data Library: market, size, value, profitability, investment and momentum, with each one's latest month, last 12 months, average a year, volatility and t-statistic. Regions: `US NA EUROPE JAPAN ASIA DEVELOPED EXUS EMERGING`. Monthly data. These are paper portfolios before trading costs. |
| `COT` | `COT`, `COT GOLD`, `COT S&P 500`, `COT MICRO BITCOIN` | CFTC Commitments of Traders. With no market, an overview of 34 major markets. With one, net positions for large speculators, small speculators and commercials, their share of open interest, and a score against their own recent range. Reported weekly, so it isn't today's position. A search can match several contracts: check the name at the top. |
| `FED` | `FED` | Effective federal funds rate and target range, SOFR, M1 and M2 with M2's yearly growth, professional forecasters' inflation expectations, and an approximate real rate. |
| `OWN` | `OWN AAPL` | Insider trades from SEC Form 4, the largest institutional holders from 13F filings, and short interest with days to cover. Insider totals count only open-market or private trades in common stock over the last 90 days: grants, option exercises, gifts and tax withholding are listed but not counted. 13F and short interest data lag, so check their dates. |
| `CHAIN` | `CHAIN AAPL`, `CHAIN AAPL 2027-01-15` | Live options chain for one expiration (by default the first a week or more out; pick another from the menu), a volatility smile, at-the-money implied vol and put/call ratios. Shows strikes within 25% of the price unless you choose **All strikes**. Quotes can be delayed. |
| `CAL` | `CAL`, `CAL 14` | Earnings and economic events for the next 7 days, or 1 to 31. Filter earnings by name or your watchlist, and events by country. Economic figures are shown exactly as published. |
| `FILINGS` | `FILINGS AAPL` | A US-listed company's latest SEC filings, filterable by form, with links to each document. |
| `ETF` | `ETF SPY` | An ETF's largest holdings and their weights. This is only part of the fund: the panel says how much of it the listed holdings cover. |
| `CURVE` | `CURVE` | US Treasury par yields by maturity, compared with a month and a year earlier, and the 10-year minus 2-year and 10-year minus 3-month spreads. A negative spread means the curve is inverted. |
| `CMP` | `CMP AAPL MSFT NVDA` | 2 to 8 tickers on one growth-of-1 chart (dividend-adjusted), with return, CAGR, volatility, Sharpe, max drawdown and correlations. |
| `FIND` | `FIND`, `FIND battery` | Search about 70,000 stocks and ETFs worldwide by name, ticker or what the business does, and filter by country, sector and size, using FinanceDatabase. It's a reference list, so sizes and descriptions can be out of date. The list downloads the first time, and again when a newer one is out. Sends results to `SCREEN` for live numbers. |
| `SCREEN` | `SCREEN`, `SCREEN AAPL MSFT` | Filter a universe (built-in ~60 large caps, your watchlist, or tickers you type) by price, day change, market cap, distance from the 52-week high/low, and sector. Click a column to sort. |
| `W` | `W NVDA`, `W -NVDA` | Add to / remove from the watchlist on the home screen. |
| `ALERT` | `ALERT AAPL > 200`, `ALERT AAPL < 150`, `ALERT NVDA +5%`, `ALERT NVDA -5%` | One-shot alerts on a price level or the day's move. Checked every 2 minutes while FinHub is open; you get a banner and a desktop notification. `ALERTS` lists them. |

Commands take priority over tickers of the same name. To open a company whose ticker is also a command, use `EQ`: `EQ CAL` opens Caleres.

Chart indicators: toggle `SMA20 SMA50 SMA200 EMA20 BB RSI` on the chart toolbar (remembered).

### Analysis

| Command | Example | What it does |
|---|---|---|
| `BACKTEST` | `BACKTEST SPY sma 20 50`, `BACKTEST QQQ momentum 126`, `BACKTEST GLD meanrev 20 2` | FinHub's backtester. See [Testing a strategy](#testing-a-strategy-properly). |
| `PORT` | `PORT`, `PORT BUY AAPL 10 150`, `PORT SELL AAPL 5 180 2026-03-01 fee=1.50`, `PORT SPLIT NVDA 10` | Your own record of trades, valued at live prices. See [Tracking your portfolio](#tracking-your-portfolio). |
| `READ` | `READ AAPL`, `READ AAPL 10-Q`, `READ AAPL DEF 14A` | Read a company's latest filing of that form inside FinHub, section by section, and search it. `FILINGS` has a **Read** button for any filing. The first time, it asks for the name and email the SEC requires automated tools to declare. These stay on your computer and go only to the SEC. |
| `OPTIM` | `OPTIM SPY 60 TLT 30 GLD 10`, `OPTIM SPY 60 TLT 40 5Y` | Test ways of choosing weights on data they haven't seen. See [Testing weights out of sample](#testing-weights-out-of-sample). |
| `REPORT` | `REPORT AAPL`, `REPORT AAPL QQQ`, `REPORT AAPL QQQ MAX` | A performance report: return, volatility, Sharpe, Sortino, drawdowns, tail risk, returns by month, and alpha and beta against a benchmark (SPY unless you name one). `BACKTEST` and `PAPER` have a **Performance report** button too. Needs the agent engine, but no AI provider. |
| `PAPER` | `PAPER`, `PAPER BUY AAPL 10`, `PAPER SELL AAPL 5` | Practice trading with real prices and fake money. See [Paper trading](#paper-trading). |
| `ALPHA` | `ALPHA`, `ALPHA momentum` | A library of 281 published signals for US stocks, and tests of them on the S&P 500. See [Testing published signals](#testing-published-signals). |
| `VOL` | `VOL SPY` | Volatility forecasts for 1, 5 and 21 days from a GARCH(1,1) model with fat tails, using arch. Each month for up to three years it's refitted on the past only and compared with what happened, and with simply assuming the last month carries on. When a shock barely fades, no long-run level is shown, because the formula becomes unreliable. |
| `BOND` | `BOND 4.5 10`, `BOND 4.5 10 97` | Coupon in percent, years, and optionally a price per 100, using QuantLib. Gives yield to maturity, modified and Macaulay duration, convexity, DV01, and the next payments. Without a price, it's valued on today's Treasury curve. Coupons are twice a year. |
| `MOOD` | `MOOD AAPL` | The tone of the latest headlines (positive, neutral or negative) with finBERT, on your computer. Optional: install it in `SYS` (about 1.1 GB), and the first run downloads the model (about 420 MB). It reads tone only, and can be fooled by a headline about something else, so don't treat it as a trading signal. The model is licensed for non-commercial use. |
| `QLIB` | `QLIB` | Microsoft Qlib's workflow on the built-in large caps: 158 price and volume features, a LightGBM model, a final test on the last three years. Optional: install it in `SYS` (about 800 MB). Runs in the background and is saved. Today's large caps are survivors, which flatters the result, and it says so. Press Start to run it. |
| `RISK` | `RISK SPY 60 TLT 30 GLD 10` | Portfolio risk (ticker then weight; weights are normalised). See [Measuring portfolio risk](#measuring-portfolio-risk). |
| `OPT` | `OPT`, `OPT AAPL` | Options lab; with a ticker it starts from the live price. See [Pricing options](#pricing-options-and-strategies). |

### AI

| Command | Example | What it does |
|---|---|---|
| `AGENTS` | `AGENTS`, `AGENTS TSLA` | TradingAgents: market, news and fundamentals analysts, a bull and bear debate, a trader and a risk team write up one stock, using the provider set with `AI`. Optional: install it in `SYS` (about 200 MB). It never starts until you press Start, since it uses far more of your provider than `ASK`, and closing FinHub stops it. It writes a report and can't place orders. The text is AI-written, so its figures have no receipts. |
| `SWARM` | `SWARM`, `SWARM investment_committee TSLA` | A team of AI agents works on a question together. See [Teams of agents](#teams-of-agents). |
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

### Testing weights out of sample

`OPTIM` asks whether a way of choosing weights holds up on data it hasn't seen, which `RISK`'s optimal weights can't tell you. It needs the agent engine from `SYS`, but no AI provider.

Each method chooses weights using the past year and holds them for the next quarter, over and over. Only the held quarters count. Your own weights are tested over the same days, so you can see whether any method beat them. Open it from `RISK` with **Test these weights out of sample**, or type `OPTIM SPY 60 TLT 30 GLD 10`.

Results are before trading costs and shift with the period, so a small lead means little. Maximum Sharpe can't be tested over a stretch where every asset had a negative expected return, and FinHub says so when that happens.

### Paper trading

`PAPER` is practice with real prices and fake money. It has no broker connection. It's different from `SIM`, which is a made-up market, and `PORT`, which records trades you made elsewhere.

1. Install the agent engine from `SYS`. Paper trading runs on it, but it doesn't need an AI provider.
2. Type `PAPER` and create an account with some starting cash.
3. Place an order in the panel. `PAPER BUY AAPL 10` fills in the form, and **Place order** sends it.
4. Come back later. Opening the account fills any orders that are due and values it.

Orders fill at the closing price of the first session still ahead when you place them: today's close during US trading hours, otherwise the next session's. So you can't buy at a price you've already seen. They settle from half an hour after the close.

For now, accounts are US stocks in whole shares, using market orders. Commission follows a typical US broker, at $0.0049 a share with a $0.99 minimum. A sale of more than you hold, or a purchase you can't afford, is refused and shown under **Trades**. Accounts can't be deleted yet.

### Testing published signals

`ALPHA` lists 281 published ways of predicting US stock returns, from academic papers to industry libraries. It doesn't use your AI provider.

1. Type `ALPHA`, or `ALPHA momentum` for one theme. Click **Details** to read how a signal works.
2. Tick at least two signals and click **Compare** for a full table. **Test the whole library** reports how many signals still work and the best five.
3. For a deeper look at one signal, click **Details**, then **Analyse this signal in depth**. It shows how the signal does over 1, 5 and 21 days, how returns climb across five groups of stocks, and how much of the portfolio it would trade.
4. A test downloads about 500 stocks and usually takes 5 to 10 minutes the first time for each period. You can leave the screen, and the result is saved under **Saved tests**. Closing FinHub stops a running test.

IC is the correlation between a signal's ranking of stocks and their next returns. IR is the average IC divided by how much it varies. They measure prediction before trading costs, not profit.

Read the warning on every result. The test uses today's S&P 500 members, so companies that collapsed and left the index are missing, and results look better than they really were. Some academic signals are price-only stand-ins for the original, as their notes say.

### Teams of agents

`SWARM` runs one of Vibe-Trading's 30 teams: several AI agents with different jobs, such as a bull researcher, a bear researcher, a risk reviewer and a portfolio manager, who pass their work along and finish with one report.

1. Set up `AI` first, and install the agent engine from `SYS`.
2. Type `SWARM`, pick a team and answer its questions. `SWARM investment_committee TSLA` picks the team and fills in the first answer.
3. Click **Start team**. Nothing runs before that, because a team uses far more of your AI provider than `ASK`. On a paid key it costs more, and on a small local model it can take a very long time or fail.
4. Watch each agent's progress, and read the report at the end. You can leave and come back from **Recent runs**, but closing FinHub stops a running team.

Check what a team tells you: it's AI-written research, not advice.

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
- Your watchlist, alerts, portfolio, paper accounts, signal tests, AI settings and agent history live in your FinHub data folder
  ([where](INSTALL.md#where-finhub-keeps-its-files)).
- If a panel shows "Couldn't load…", the table under it lists every provider tried and why it failed.
