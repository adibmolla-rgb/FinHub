import type { Track } from '../types'

export const methods: Track = {
  id: 'methods',
  title: 'Quant methods',
  description: 'The core techniques: research without self-deception, portfolios and risk, factors, options, market making, ML.',
  access: 'free',
  lessons: [
    {
      id: 'methods-backtesting',
      title: 'Backtesting without fooling yourself',
      minutes: 35,
      summary: 'The seven ways backtests lie, and the fixes.',
      body: `
Most backtests that look great are wrong. Interviewers know this, and the fastest way to impress them is
to show you know it too.

## The seven ways backtests lie

| Problem | What happens | Fix |
|---|---|---|
| **Look-ahead bias** | Using information you didn't have yet (today's close to trade at today's close; revised data) | Trade on the next bar; use point-in-time data; test that signals don't change when you cut off the future |
| **Survivorship bias** | Testing only on companies that still exist; the bankrupt ones are missing | Use a universe that includes delisted stocks |
| **Ignoring costs** | Commission, spread, slippage and impact | Charge them on every trade; compare before/after |
| **Overfitting** | Tuning until the past looks perfect | Few parameters; out-of-sample tests; walk-forward |
| **Multiple testing** | Trying many ideas and keeping the best | Count trials; deflated Sharpe; hold-out data |
| **Unrealistic fills** | Assuming you trade at mid, in any size | Model the spread and size limits |
| **Regime dependence** | A strategy that only worked in one period | Test across decades and market conditions |

## Walk-forward testing

Split time into blocks. For each block, choose parameters using **only earlier data**, then record how
they do in the block. Stitch the out-of-sample blocks together: that's the result you'd actually have
had. If it's far worse than the full-sample result, you overfitted.

## The deflated Sharpe ratio

If you tried N strategy variants, the best Sharpe you'd expect **from pure luck** rises with N. The
deflated Sharpe ratio (Bailey & López de Prado) estimates the probability that your best result beats
that luck threshold, also accounting for fat tails and skew. Below ~95%: treat it as luck.

## A research process that works

1. Write the hypothesis and *why* it should work (a mechanism), before testing.
2. Decide the test, data and costs in advance.
3. Run it once; record every variant you try.
4. Validate out of sample. Report failures too.

> A modest strategy validated properly beats a "3.0 Sharpe" ML model nobody can explain. FinHub's
> BACKTEST runs the causality check, walk-forward test, deflated Sharpe and parameter map for you.
`,
      quiz: [
        { q: 'Testing a strategy only on today’s S&P 500 members over 20 years introduces…', options: ['Look-ahead bias only', 'Survivorship bias', 'Lower volatility', 'No bias'], answer: 1, why: 'Companies that failed or were removed are missing, so the universe is biased towards winners (it also uses today’s membership, a form of look-ahead).' },
        { q: 'Walk-forward out-of-sample Sharpe is 0.2; full-sample Sharpe is 1.1. Most likely…', options: ['The strategy is excellent', 'Parameters were overfitted', 'Costs were too low', 'Data is missing'], answer: 1, why: 'Parameters chosen with hindsight look great on the data they were fitted to and much worse on unseen data.' },
      ],
      tryIt: [{ command: 'BACKTEST QQQ momentum 126', label: 'Validate a momentum strategy: BACKTEST' }],
      resources: [{ title: 'Marcos López de Prado, Advances in Financial Machine Learning', url: 'https://www.google.com/search?q=Advances+in+Financial+Machine+Learning', note: 'Chapters on backtest overfitting' }],
    },
    {
      id: 'methods-portfolios',
      title: 'Portfolios and risk',
      minutes: 35,
      summary: 'Diversification, mean–variance, VaR and expected shortfall, estimation error.',
      body: `
## Diversification

Portfolio variance is w'Σw (see the linear algebra lesson). Combining assets that don't move together
lowers risk without necessarily lowering return. That's the only "free lunch" in finance.

## Mean–variance optimisation (Markowitz)

Choose weights to get the most expected return for a given risk:

- **Minimum-variance portfolio**: the least risky mix, ignoring returns.
- **Maximum-Sharpe (tangency) portfolio**: the best return per unit of risk.

**The catch:** the optimiser needs expected returns, and those are estimated very poorly (see the
statistics lesson). It then puts big bets on whichever assets happened to do well in the sample.
Practitioners shrink estimates, add constraints, or use risk-based methods (minimum variance, risk
parity). Always look at how much the "optimal" weights change when you resample the data.

## Measuring risk

- **Volatility**: typical size of moves.
- **Value at Risk (VaR)** at 99%: a one-day loss you should exceed only 1 day in 100. Three ways to
  compute it: **historical** (the 1% worst past day), **parametric** (assume a normal distribution),
  **Monte Carlo** (simulate).
- **Expected Shortfall (ES)**: the *average* loss on those worst days. It sees how bad the tail is;
  VaR doesn't. Regulators increasingly prefer ES.
- **Backtesting VaR (Kupiec test)**: did breaches happen about as often as promised? Too many means the
  model understates risk.
- **Risk contribution**: a holding's share of total risk. A 10% position in a volatile, correlated asset
  can be 30% of the risk.

> Run RISK on a portfolio. Then add a volatile stock with a small weight and watch its share of risk.
`,
      quiz: [
        { q: 'Expected Shortfall at 99% is…', options: ['The best day in 100', 'The average loss on the worst 1% of days', 'Always smaller than VaR', 'The volatility'], answer: 1, why: 'ES averages the tail beyond VaR, so it’s at least as large as VaR and reflects how bad bad days get.' },
        { q: 'Why are max-Sharpe weights often unstable?', options: ['Computers are imprecise', 'Expected returns are estimated with huge error, and the optimiser amplifies it', 'Volatility is unknowable', 'Correlations are always zero'], answer: 1, why: 'Small changes in noisy return estimates swing the optimum. Bootstrap error bars make this visible.' },
      ],
      tryIt: [{ command: 'RISK SPY 60 TLT 30 GLD 10', label: 'Analyse a portfolio: RISK' }],
    },
    {
      id: 'methods-factors',
      title: 'Factors and anomalies',
      minutes: 30,
      summary: 'Momentum, value, size, quality, and how to test a published idea.',
      body: `
A **factor** is a characteristic that has historically explained (and sometimes predicted) returns across
many assets.

| Factor | Idea | Typical measure |
|---|---|---|
| **Market (beta)** | Exposure to the overall market | Regression on the index |
| **Size** | Small companies vs large | Market cap |
| **Value** | Cheap vs expensive companies | Book-to-price, earnings yield |
| **Momentum** | Recent winners keep winning for a while | 12-month return excluding the last month |
| **Quality / profitability** | Profitable, stable firms | Gross profit / assets, ROE |
| **Low volatility** | Calm stocks have done surprisingly well per unit of risk | Past volatility |

**Time-series momentum** (in FinHub's BACKTEST) asks whether an asset's own past return predicts its
future; **cross-sectional momentum** ranks many assets against each other.

## Replicating a published result

A great learning project: pick a famous anomaly, rebuild it on a broad universe, then ask:
- Does it survive **costs**?
- Does it hold in **different periods** (before and after it was published)?
- How strong is it after a **multiple-testing** adjustment?

Many published anomalies weaken after publication, which is itself an interesting result.

## Why factors might work

- **Risk**: you're paid for bearing a risk others avoid.
- **Behaviour**: investors under- or over-react.
- **Constraints**: some investors can't hold certain assets.
Knowing *why* helps you judge whether an effect should persist.
`,
      quiz: [
        { q: 'Cross-sectional momentum buys…', options: ['Assets that fell most', 'Assets with the best recent returns relative to others', 'The cheapest assets', 'Random assets'], answer: 1, why: 'It ranks assets by recent performance and buys the winners (often shorting the losers).' },
      ],
      tryIt: [{ command: 'BACKTEST SPY momentum 252', label: 'Test time-series momentum: BACKTEST' }],
    },
    {
      id: 'methods-options-pricing',
      title: 'Option pricing in depth',
      minutes: 40,
      summary: 'Binomial trees, Black–Scholes, Monte Carlo, Greeks and implied volatility.',
      body: `
## Three ways to price the same option

1. **Binomial tree**: let the price go up or down each small step with "risk-neutral" probabilities,
   compute payoffs at the end, then discount back step by step. Handles early exercise (American options).
2. **Black–Scholes formula**: the limit of the tree with infinitely many steps, for European options:
   C = S·N(d₁) − K·e^(−rT)·N(d₂), with N the normal CDF.
3. **Monte Carlo**: simulate many price paths, average the discounted payoffs. Flexible for complex products;
   report the **standard error** so you know how accurate it is.

If all three agree, your code is probably right. That's exactly what OPT shows you.

## Implied volatility

Every input except volatility is observable. So traders run the formula **backwards**: given the market
price, which volatility produces it? That's **implied volatility**, the market's price of future
uncertainty. Options are quoted in it.

## The volatility smile

If Black–Scholes were exactly right, implied volatility would be the same for every strike. In reality,
out-of-the-money puts usually have higher implied volatility (a "skew" or "smile"): the market prices
crashes as more likely than a normal distribution would. Modelling the smile is a big part of
derivatives quant work.

## Hedging and the Greeks

A market maker who sells an option **delta-hedges** by holding delta shares, so small moves cancel. They
remain exposed to **gamma** (delta changing) and **vega** (volatility changing). Option trading is largely
trading volatility.

> Exercise: in OPT, set a market price and read off implied volatility. Then change it by 0.50 and see how
> much implied volatility moves (that ratio is 1/vega).
`,
      quiz: [
        { q: 'Implied volatility is…', options: ['Historical volatility of the stock', 'The volatility that makes the model price equal the market price', 'Always 20%', 'The option’s delta'], answer: 1, why: 'It’s backed out of the market price by inverting the pricing formula.' },
        { q: 'Which method handles early exercise of an American option most naturally?', options: ['Black–Scholes formula', 'Binomial tree', 'Linear regression', 'None of them'], answer: 1, why: 'At each node of the tree you can compare exercising now with continuing.' },
      ],
      tryIt: [{ command: 'OPT', label: 'Price, Greeks and implied vol: OPT' }],
      resources: [
        { title: 'John Hull, Options, Futures, and Other Derivatives', url: 'https://www.google.com/search?q=Hull+Options+Futures+and+Other+Derivatives', note: 'The standard textbook' },
        { title: 'Sheldon Natenberg, Option Volatility and Pricing', url: 'https://www.google.com/search?q=Natenberg+Option+Volatility+and+Pricing', note: 'How option traders think' },
      ],
    },
    {
      id: 'methods-microstructure',
      title: 'Market making and microstructure',
      minutes: 30,
      summary: 'Quoting, inventory, adverse selection, and how prices absorb information.',
      body: `
**Market microstructure** studies how trading actually happens: order books, who trades, and how
information gets into prices.

## A market maker's decisions

1. **Where to quote**: around a fair-value estimate, which they update from trades and order flow.
2. **How wide**: wide enough to cover adverse selection and inventory risk, narrow enough to win trades.
3. **How to skew**: with inventory, shift quotes to unload it.

A famous model (Avellaneda–Stoikov, 2008) formalises this: quote around a **reservation price** that
moves away from mid as inventory grows, with a spread that widens with volatility and risk aversion.

## How information enters prices

When an informed trader buys, the market maker loses on that trade but learns something: buying
pressure suggests the price should be higher. The **Kyle model** shows prices moving in proportion to
net order flow. FinHub's simulated market maker does exactly this: it learns from trade prices and
signed order flow, which is why prices converge to the hidden true value after a shock.

## Practise it

Market-making games are common in trading interviews. In SIM:
1. Make markets by resting orders near the bid and offer; flatten regularly.
2. Watch the **spread earned** vs **after trade** split in your P&L.
3. Press **Bad news**: notice how being on the wrong side of informed flow hurts.
`,
      quiz: [
        { q: 'Why does a market maker widen its spread when volatility rises?', options: ['To trade more', 'Greater risk of adverse selection and inventory losses', 'Exchanges require it', 'It always does at noon'], answer: 1, why: 'More uncertainty means larger possible losses on inventory and a higher chance the counterparty knows more.' },
      ],
      tryIt: [{ command: 'SIM', label: 'Make markets against bots: SIM' }],
      resources: [{ title: 'Larry Harris, Trading and Exchanges', url: 'https://www.google.com/search?q=Larry+Harris+Trading+and+Exchanges', note: 'Market microstructure for practitioners' }],
    },
    {
      id: 'methods-ml',
      title: 'Machine learning in finance: the honest version',
      minutes: 30,
      summary: 'Where ML helps, where it fails, and how to avoid leaking the future.',
      body: `
Machine learning is powerful, but financial data is small, noisy and changing, which is the worst setting
for flexible models.

## Why "predict tomorrow's price with an LSTM" usually fails

- **Low signal-to-noise**: daily returns are mostly noise; a model fits the noise.
- **Few independent samples**: 20 years of daily data is only ~5,000 points, heavily overlapping.
- **Non-stationarity**: relationships change as markets adapt.
- **Leakage**: random train/test splits put future data in training; overlapping labels leak too.

## Doing it properly

- Use **time-ordered splits** (train on the past, test on the future), never random shuffles.
- Add **embargo** gaps between train and test when labels overlap in time.
- Start with **simple baselines** (linear regression, logistic regression). If a complex model can't beat
  them out of sample, it isn't adding anything.
- Evaluate the **trading result after costs**, not just accuracy.
- Track every experiment (multiple testing applies to ML too).

## Where ML genuinely helps

- Combining many weak signals; ranking stocks cross-sectionally.
- Text: news and filings (with careful timestamps).
- Execution: predicting short-term volume or impact.
- Risk: detecting regime changes.

> Interviewers are wary of projects that "predict stock prices with deep learning". A careful, honest
> study with proper validation, even with a negative result, impresses far more.
`,
      quiz: [
        { q: 'Why not randomly shuffle data into train and test sets for a trading model?', options: ['It’s slower', 'Future information leaks into training', 'It reduces accuracy on purpose', 'Libraries don’t allow it'], answer: 1, why: 'Shuffling lets the model learn from data that comes after the test points, which can’t happen in real trading.' },
      ],
      resources: [{ title: 'fast.ai Practical Deep Learning (free)', url: 'https://course.fast.ai', free: true }],
    },
  ],
}
