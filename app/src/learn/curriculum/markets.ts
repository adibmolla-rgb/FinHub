import type { Track } from '../types'

export const markets: Track = {
  id: 'markets',
  title: 'Markets and trading',
  description: 'What is traded, how prices form, returns and risk, costs, options, company and macro basics.',
  access: 'free',
  lessons: [
    {
      id: 'markets-basics',
      title: 'What a market is',
      minutes: 12,
      summary: 'Assets, exchanges, and who trades and why.',
      body: `
A **market** is a place where buyers and sellers agree a price. Today almost all of it happens on
computers.

## What gets traded

| Asset | What you own | Example |
|---|---|---|
| **Stocks (equities)** | A slice of a company | Apple (AAPL) |
| **Bonds** | A loan to a government or company that pays interest | US 10-year Treasury |
| **Currencies (FX)** | One currency against another | EUR/USD |
| **Commodities** | Physical goods, usually via futures | Oil, gold, wheat |
| **Derivatives** | A contract whose value depends on something else | Options, futures, swaps |
| **Funds / ETFs** | A basket of other assets in one ticker | SPY (the S&P 500) |

An **index** (like the S&P 500, written ^GSPC) is a number summarising a basket of stocks. You can't
buy an index directly, but you can buy an ETF that tracks it.

## Who trades, and why

- **Investors** (pension funds, individuals) buy to hold for years.
- **Hedgers** trade to reduce a risk they already have (an airline buying oil futures).
- **Speculators** trade to profit from price moves.
- **Market makers** stand ready to buy *and* sell, earning a small gap between the two prices.
- **Arbitrageurs** profit when the same thing has two prices in two places, which pushes prices back
  into line.

Prices come from all of them interacting. If more people want to buy than sell at the current price,
the price rises until enough sellers appear.

## Exchanges and tickers

Shares trade on **exchanges** (NYSE, Nasdaq, London Stock Exchange…), each identified by a **ticker**:
AAPL, MSFT, SHEL.L (Shell in London). FinHub uses Yahoo's ticker style.

> Market prices are not "the truth". They are the current balance of everyone's views, needs and
> mistakes. Much of quant finance is about when, and how much, that balance is predictable.
`,
      quiz: [
        {
          q: 'A bond is…',
          options: ['A share of a company', 'A loan that pays interest', 'An option to buy a stock', 'A currency'],
          answer: 1,
          why: 'Buying a bond lends money to the issuer, who pays interest and returns the principal at maturity.',
        },
        {
          q: 'An airline buying oil futures to lock in fuel costs is mainly…',
          options: ['Speculating', 'Hedging', 'Market making', 'Arbitraging'],
          answer: 1,
          why: 'It already has exposure to oil prices through its business; the futures reduce that risk.',
        },
      ],
      tryIt: [{ command: 'SPY', label: 'Look at an ETF: SPY' }, { command: '^GSPC', label: 'Look at an index: ^GSPC' }],
    },
    {
      id: 'markets-order-book',
      title: 'How prices form: the order book',
      minutes: 15,
      summary: 'Bids, asks, the spread, market and limit orders, matching.',
      body: `
On an exchange, every share price you see comes from an **order book**: a list of everyone currently
willing to buy or sell, and at what price.

~~~
        SELLERS (asks)
        100.03   500 shares
        100.02   200 shares   <- best ask: the cheapest seller
      ---------------------
        100.00   300 shares   <- best bid: the highest buyer
         99.99   800 shares
        BUYERS (bids)
~~~

- The **bid** is the best price someone will pay; the **ask** (or offer) is the best price someone will sell at.
- The **spread** is the gap: here 100.02 − 100.00 = 0.02. The **mid** price is halfway: 100.01.

## Two kinds of order

- A **market order** says "trade now at whatever price is available". Buying 100 shares at market here
  fills at 100.02. You pay the spread, but you are certain to trade.
- A **limit order** says "trade only at this price or better". A buy limit at 100.00 joins the bid
  queue and waits. You might get a better price, but you might never trade.

## Matching

The exchange's **matching engine** pairs orders by **price, then time**: the best price trades first,
and among equal prices, whoever arrived first. That's why speed matters to some firms: being first in
the queue at a price is valuable.

Buying a lot at once "walks the book": after the 200 shares at 100.02 are gone, you pay 100.03 for the
next 500. This is **market impact**, and it's why big investors split orders up.

> The best way to understand an order book is to trade in one. FinHub's simulator gives you a live
> book with bots on the other side.
`,
      quiz: [
        {
          q: 'Best bid 50.10, best ask 50.14. What is the spread and the mid?',
          options: ['0.04 and 50.12', '0.04 and 50.14', '0.14 and 50.10', '0.02 and 50.12'],
          answer: 0,
          why: 'Spread = 50.14 − 50.10 = 0.04. Mid = (50.10 + 50.14) / 2 = 50.12.',
        },
        {
          q: 'You must sell immediately, whatever happens. Which order?',
          options: ['Limit order above the ask', 'Market order', 'Limit order at the bid minus 1', 'No order'],
          answer: 1,
          why: 'A market order trades now against the best available bid. Certainty of execution costs you the spread.',
        },
        {
          q: 'Two buy orders at the same price. Which fills first?',
          options: ['The larger one', 'The one that arrived first', 'A random one', 'Both equally'],
          answer: 1,
          why: 'Price-time priority: at equal prices, earlier orders fill first.',
        },
      ],
      tryIt: [{ command: 'SIM', label: 'Trade in a live order book: SIM' }],
    },
    {
      id: 'markets-market-making',
      title: 'Market makers, liquidity and adverse selection',
      minutes: 15,
      summary: 'How market makers earn the spread, and who they lose it to.',
      body: `
A **market maker** keeps both a bid and an ask in the market all the time, ready to trade with anyone.
If they buy at 100.00 and later sell at 100.02, they earn the spread. Do that millions of times and it
adds up. This provides **liquidity**: other people can trade instantly.

## The two risks

1. **Inventory risk.** After buying from a seller, the market maker holds shares. If the price falls
   before they can sell, they lose. So they **skew** their quotes: with too many shares, they lower
   both bid and ask to encourage buyers and discourage sellers.
2. **Adverse selection.** Some traders know something the market maker doesn't (news, a big order
   coming). They trade exactly when the quote is wrong. The market maker earns the spread from
   uninformed traders and **loses it to informed ones**.

A market maker profits only if what they earn from the uninformed beats what they lose to the
informed. That's why spreads **widen** in uncertain times: the chance of facing someone who knows more
goes up.

## Splitting your P&L

Each trade has two parts:

- **Spread earned**: how much better than mid you traded (positive if you bought below mid or sold above it).
- **What happened afterwards**: did the price move with you or against you? Persistently against you
  means you are being picked off: adverse selection.

FinHub's SIM shows exactly this split for your own trades.

> Firms like Optiver, IMC and Jane Street are, at heart, very sophisticated market makers. Their
> interviews often include market-making games for exactly this reason.
`,
      quiz: [
        {
          q: 'A market maker has bought a lot of shares and wants to reduce inventory. They should…',
          options: ['Raise both quotes', 'Lower both quotes', 'Widen only the bid', 'Stop quoting forever'],
          answer: 1,
          why: 'Lower quotes make their offer more attractive to buyers and their bid less attractive to sellers, so inventory falls.',
        },
        {
          q: 'Adverse selection means…',
          options: ['Choosing the wrong stock', 'Trading against people who know more, exactly when your quote is wrong', 'Paying high commissions', 'The spread being too narrow'],
          answer: 1,
          why: 'Informed traders choose when to trade with you, so on average those trades go against you.',
        },
      ],
      tryIt: [{ command: 'SIM', label: 'Try to beat the market maker: SIM' }, { command: 'ARENA', label: 'Watch the arena: ARENA' }],
    },
    {
      id: 'markets-returns-risk',
      title: 'Returns, compounding and risk',
      minutes: 20,
      summary: 'Simple and log returns, volatility, drawdown, the Sharpe ratio.',
      body: `
## Returns

The **return** over a period is how much you made as a fraction of what you started with:

~~~
return = (price_end − price_start) / price_start
~~~

From 100 to 110 is a return of 0.10 (10%). FinHub stores returns as **fractions** (0.10), not
percentages (10), to avoid mixing them up.

**Returns compound.** +10% then −10% is not zero: 100 → 110 → 99, a loss of 1%. To combine returns
over time, multiply growth factors: (1 + 0.10) × (1 − 0.10) − 1 = −0.01.

**Log returns**, ln(price_end / price_start), add up over time instead of multiplying, which makes
some maths easier. For small moves they are almost equal to simple returns.

## Annualising

Daily numbers are scaled to a year with about **252 trading days**:

- Average return: daily mean × 252.
- **Volatility** (standard deviation of returns): daily volatility × √252. Volatility grows with the
  *square root* of time, because random ups and downs partly cancel.

## Measuring risk

- **Volatility**: how much returns typically swing. 20% a year is roughly a typical single stock;
  a broad index is often around 15%.
- **Maximum drawdown**: the worst fall from a peak to a later low. It's what investors actually feel.
- **Value at Risk (VaR)**: a loss you should only exceed on, say, 1 day in 100.

## Return per unit of risk: the Sharpe ratio

~~~
Sharpe = (average return − risk-free rate) / volatility      (both annualised)
~~~

A Sharpe of 0.5 is typical for a stock index over the long run; 1 is good; above 2 for a simple
daily strategy is so rare that you should suspect a bug or overfitting first.

> Worked example: a strategy earns 0.04% a day on average with 1% daily volatility. Annual return ≈
> 0.0004 × 252 = 10.1%. Annual volatility ≈ 0.01 × √252 = 15.9%. Sharpe ≈ 0.101 / 0.159 ≈ 0.63.
`,
      quiz: [
        {
          q: 'A price goes 100 → 120 → 90. What is the total return?',
          options: ['+10%', '−10%', '−5%', '0%'],
          answer: 1,
          why: '(90 − 100) / 100 = −0.10. The +20% and −25% steps compound: 1.2 × 0.75 = 0.9.',
        },
        {
          q: 'Daily volatility is 2%. Roughly what is annual volatility?',
          options: ['2% × 252 ≈ 504%', '2% × √252 ≈ 32%', '2% × 12 = 24%', '2%'],
          answer: 1,
          why: 'Volatility scales with the square root of time: 0.02 × √252 ≈ 0.02 × 15.87 ≈ 0.317.',
        },
        {
          q: 'A backtest of a simple daily strategy shows a Sharpe ratio of 3.5. Your first thought should be…',
          options: ['Invest everything', 'Check for bugs, look-ahead bias and overfitting', 'Sharpe doesn’t matter', 'Raise leverage'],
          answer: 1,
          why: 'Results that good are extremely rare. Most often they come from a data error, trading on information you wouldn’t have had, or testing many variants until one looked lucky.',
        },
      ],
      tryIt: [{ command: 'CMP SPY QQQ TLT', label: 'Compare volatility and Sharpe: CMP' }],
    },
    {
      id: 'markets-costs-short-leverage',
      title: 'Long, short, leverage and costs',
      minutes: 12,
      summary: 'Betting on falls, borrowing to invest, and what trading really costs.',
      body: `
## Long and short

- **Long**: you own it; you make money if it rises.
- **Short**: you borrow shares, sell them, and buy them back later. You profit if the price falls. Your
  loss is unlimited in theory (the price can keep rising), and you pay to borrow the shares.

## Leverage

**Leverage** means controlling more than your capital, by borrowing or using derivatives. With 2×
leverage, a 10% move becomes a 20% gain or loss. It multiplies skill and mistakes equally, and it can
force you out at the worst moment if losses trigger a margin call.

## What trading really costs

| Cost | What it is |
|---|---|
| **Commission** | A fee per trade |
| **Spread** | Buying at the ask and selling at the bid costs the spread on every round trip |
| **Slippage** | The price moves between deciding and trading |
| **Market impact** | Your own order pushes the price against you; grows with size |
| **Borrow cost** | Fees for shorting |

Costs are measured in **basis points**: 1 bp = 0.01% = 0.0001. A strategy that trades every day and
pays 10 bp per trade pays about 252 × 0.001 ≈ 25% a year in costs. Most strategies that look great
before costs vanish after them.

> Rule: never trust a backtest that ignores costs. FinHub's BACKTEST shows results before and after
> costs side by side so you can see the damage.
`,
      quiz: [
        {
          q: 'How many basis points is 0.25%?',
          options: ['2.5', '25', '250', '0.25'],
          answer: 1,
          why: '1 bp = 0.01%, so 0.25% = 25 bp.',
        },
        {
          q: 'With 3× leverage, the asset falls 10%. Your capital falls about…',
          options: ['10%', '30%', '3%', '0%'],
          answer: 1,
          why: 'Leverage multiplies the move: 3 × 10% = 30% (ignoring financing costs).',
        },
      ],
      tryIt: [{ command: 'BACKTEST SPY sma 20 50', label: 'See costs in a backtest: BACKTEST' }],
    },
    {
      id: 'markets-options',
      title: 'Options: calls, puts and payoffs',
      minutes: 20,
      summary: 'The right to buy or sell at a fixed price, and why that is worth something.',
      body: `
An **option** is a contract giving the right, but not the obligation, to trade something at a fixed
price (the **strike**) on or before a date (the **expiry**).

- A **call** is the right to **buy** at the strike. It pays off when the price ends **above** the strike.
- A **put** is the right to **sell** at the strike. It pays off when the price ends **below** the strike.

## Payoff at expiry

~~~
call payoff = max(price − strike, 0)
put payoff  = max(strike − price, 0)
~~~

Example: a call with strike 100. At expiry the stock is 120, so the payoff is 20. At 90 you simply
don't exercise: payoff 0. Your loss is limited to what you paid for the option (the **premium**), but
the upside is open. That asymmetry is why options cost money.

## What makes an option worth more?

- **Further in the money** (stock well above a call's strike): more intrinsic value.
- **More time** to expiry: more chance of a big move.
- **Higher volatility**: bigger possible moves. Because losses are capped, extra volatility helps
  the holder. Volatility is the key input that traders actually argue about.
- Interest rates and dividends matter a little.

## Pricing in one idea

You can combine shares and cash so that, over a short time, they behave exactly like the option. If
the option traded at any other price, there would be risk-free profit (**arbitrage**). That idea gives
the famous **Black–Scholes** formula. You'll meet it properly in the quant methods track.

## Strategies

Combining options shapes your payoff: a **spread** caps both gain and loss; a **straddle** (call +
put at the same strike) profits from a big move in either direction; an **iron condor** profits if
nothing much happens.

> Open OPT, pick a strategy, and drag the inputs around. Watch the payoff and price change. It is the
> fastest way to build intuition.
`,
      quiz: [
        {
          q: 'Strike 50 put; at expiry the stock is 42. The payoff is…',
          options: ['0', '8', '42', '−8'],
          answer: 1,
          why: 'Put payoff = max(strike − price, 0) = max(50 − 42, 0) = 8.',
        },
        {
          q: 'All else equal, higher volatility makes a call option…',
          options: ['Cheaper', 'More expensive', 'Worthless', 'Unaffected'],
          answer: 1,
          why: 'Bigger possible moves raise the chance of a large payoff while the loss stays capped at the premium.',
        },
      ],
      tryIt: [{ command: 'OPT', label: 'Open the options lab: OPT' }],
    },
    {
      id: 'markets-company-numbers',
      title: 'Reading a company’s numbers',
      minutes: 15,
      summary: 'Income statement, balance sheet, cash flow, and a few ratios.',
      body: `
Public companies publish three main statements, usually quarterly and yearly.

| Statement | Answers | Key lines |
|---|---|---|
| **Income statement** | Did it make money over the period? | Revenue, gross profit, operating income, net income |
| **Balance sheet** | What does it own and owe at a moment? | Assets, liabilities, shareholders' equity |
| **Cash flow statement** | Where did cash actually come from and go? | Operating cash flow, capital expenditure, free cash flow |

Profit and cash differ: a company can report profit while running out of cash (customers haven't paid
yet), or the reverse.

## Ratios that matter

- **Gross margin** = gross profit ÷ revenue: how much is left after the direct cost of what it sells.
- **Operating / net margin**: profit after running costs / after everything.
- **Revenue growth**: this period vs the same period a year before.
- **Return on equity (ROE)** = net income ÷ shareholders' equity: profit generated per unit of owners' capital.
- **Debt to equity**: how much of the company is funded by borrowing.
- **Free cash flow** = operating cash flow − capital expenditure: cash the business generates after investing.
- **P/E ratio** = price per share ÷ earnings per share: how many years of current earnings the market price represents.

## Where quants use this

Quant equity strategies turn these numbers into **factors** (value, quality, profitability…) and test
whether they predict returns across thousands of companies. Data quality matters enormously: you must
use the numbers **as they were known at the time**, not later corrected versions, or your test cheats.

> In FA, click any ratio: the receipt shows exactly which line item and period fed it.
`,
      quiz: [
        {
          q: 'Revenue 500, gross profit 200. Gross margin is…',
          options: ['2.5', '40%', '60%', '200'],
          answer: 1,
          why: 'Gross margin = 200 / 500 = 0.40 = 40%.',
        },
        {
          q: 'Which statement shows what a company owns and owes at a single date?',
          options: ['Income statement', 'Balance sheet', 'Cash flow statement', 'Annual report cover'],
          answer: 1,
          why: 'The balance sheet is a snapshot; the other two cover a period.',
        },
      ],
      tryIt: [{ command: 'FA AAPL', label: 'Read Apple’s statements: FA AAPL' }],
    },
    {
      id: 'markets-macro',
      title: 'Macro: rates, inflation and the economy',
      minutes: 12,
      summary: 'Why interest rates and inflation move every market.',
      body: `
**Macroeconomics** is the economy as a whole. A few numbers move almost every asset:

- **Inflation** (often CPI, year on year): how fast prices rise. High inflation erodes the value of
  future cash, hurting bonds especially.
- **Interest rates**: central banks (the Fed, the Bank of England, the ECB) set short-term rates to
  steer inflation and growth. Long-term rates (like the 10-year government bond yield) reflect
  expected future short rates plus a premium for risk.
- **Unemployment** and **GDP growth**: how strong the economy is.

## How they connect to prices

- **Rates up → bond prices down.** A bond's fixed payments are worth less when new bonds pay more.
- **Rates up → stock valuations down**, especially for companies whose profits are far in the future
  (future cash is discounted more heavily).
- **Surprises matter, not levels.** Markets price in what they expect; prices move when the news
  differs from expectations.

## Discounting

£100 in a year is worth less than £100 today, because you could invest today's money. At a 5% rate:
present value = 100 / 1.05 ≈ 95.24. This one idea underlies bond pricing, company valuation and
option pricing.

> MACRO shows inflation, unemployment and interest rates by country from the OECD.
`,
      quiz: [
        {
          q: 'Interest rates rise unexpectedly. Existing bond prices typically…',
          options: ['Rise', 'Fall', 'Stay the same', 'Double'],
          answer: 1,
          why: 'Their fixed payments are now less attractive than new bonds’, so their price falls until their yield matches.',
        },
        {
          q: 'At a 10% rate, the present value of 110 received in one year is…',
          options: ['121', '110', '100', '99'],
          answer: 2,
          why: '110 / 1.10 = 100.',
        },
      ],
      tryIt: [{ command: 'MACRO US', label: 'US macro data: MACRO US' }],
    },
  ],
}
