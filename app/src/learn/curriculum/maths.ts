import type { Track } from '../types'

export const maths: Track = {
  id: 'maths',
  title: 'The maths',
  description: 'Exactly the maths quants use, from algebra to random walks, with interview-style practice.',
  access: 'free',
  lessons: [
    {
      id: 'maths-foundations',
      title: 'Foundations: functions, exp, log and sums',
      minutes: 20,
      summary: 'The algebra every later topic leans on.',
      body: `
If school maths feels rusty, start here. Everything later uses these.

## Exponentials and logarithms

- Growth compounds: £100 growing 5% a year for n years becomes 100 × 1.05ⁿ.
- With continuous compounding at rate r: amount = A × e^(r·t), where e ≈ 2.71828.
- The **natural log** ln undoes e: ln(e^x) = x. Rules you'll use constantly:
  ln(a·b) = ln a + ln b, ln(a/b) = ln a − ln b, ln(aⁿ) = n·ln a.
- That's why **log returns add up**: ln(P₂/P₀) = ln(P₂/P₁) + ln(P₁/P₀).

## Sums

The Greek Σ means "add up". Σᵢ xᵢ over i = 1…n is x₁ + x₂ + … + xₙ. The **mean** is (1/n) Σ xᵢ.
A **geometric series**: 1 + q + q² + … = 1 / (1 − q) when |q| < 1. It appears in discounting and in
"expected number of tries" puzzles.

## Functions and graphs

Be comfortable reading y = f(x): what happens as x grows, where the curve is steepest, where it's
flat. Sketching a function before computing anything is a habit interviewers like.

## Practice

1. Price goes 100 → 105 → 99.75. Compute both simple returns and both log returns; check the log
   returns add to ln(99.75/100).
2. What is 1 + 1/2 + 1/4 + 1/8 + …?
3. Solve 1.07ⁿ = 2 for n (how long to double at 7%?). Answer: n = ln 2 / ln 1.07 ≈ 10.2 years.
`,
      quiz: [
        { q: 'ln(a·b) equals…', options: ['ln a · ln b', 'ln a + ln b', 'ln(a) / ln(b)', 'a · ln b'], answer: 1, why: 'Logs turn multiplication into addition, which is why log returns add over time.' },
        { q: '1 + 1/3 + 1/9 + 1/27 + … =', options: ['1.5', '2', '3', 'Infinite'], answer: 0, why: 'Geometric series with q = 1/3: 1 / (1 − 1/3) = 1.5.' },
      ],
      resources: [
        { title: 'Khan Academy: Algebra and precalculus', url: 'https://www.khanacademy.org/math/algebra2', free: true },
        { title: '3Blue1Brown: Essence of calculus (for intuition)', url: 'https://www.3blue1brown.com/topics/calculus', free: true },
      ],
    },
    {
      id: 'maths-probability',
      title: 'Probability: the most important topic',
      minutes: 40,
      summary: 'Events, conditional probability, Bayes, expected value, and puzzles.',
      body: `
Probability is tested in nearly every quant interview and underlies every model. Invest the most time here.

## Basics

- A probability is between 0 and 1. P(not A) = 1 − P(A).
- **Independent** events: P(A and B) = P(A) × P(B). Two fair coin flips both heads: ½ × ½ = ¼.
- **Either**: P(A or B) = P(A) + P(B) − P(A and B).
- **Counting**: number of ways to choose k from n is "n choose k" = n! / (k!(n − k)!).

## Conditional probability and Bayes

P(A | B) means "probability of A given B happened" = P(A and B) / P(B).

**Bayes' rule** flips it: P(A | B) = P(B | A) × P(A) / P(B).

> Classic: 1% of people have a disease. A test catches 90% of cases but also flags 5% of healthy
> people. You test positive. Chance you're ill? P(+) = 0.01×0.9 + 0.99×0.05 = 0.0585, so
> P(ill | +) = 0.009 / 0.0585 ≈ 15%. Most positives are false because healthy people are so common.
> This exact reasoning separates real trading signals from noise.

## Expected value

The **expected value** is the probability-weighted average outcome: E[X] = Σ x · P(x).

- A fair die: E = (1+2+3+4+5+6)/6 = 3.5.
- A bet paying £10 with probability 0.3 and costing £3: EV = 0.3×10 − 3 = £0 (fair).
- **Linearity**: E[X + Y] = E[X] + E[Y] always, even if X and Y are dependent. This solves many puzzles.

Traders think in expected value all day: take bets with positive EV, size them so a bad run can't
ruin you.

## Interview-style puzzles

1. Expected number of rolls of a die to get a six? Each roll succeeds with p = 1/6, so the answer is
   1/p = **6**.
2. Two children; at least one is a boy. Probability both are boys? Outcomes BB, BG, GB equally likely
   → **1/3**.
3. You flip a coin until heads. You win 2ⁿ where n is the flip count. Fair price? The EV is infinite
   (the St Petersburg paradox), which is why risk and bankroll matter, not just EV.
4. Expected number of fixed points when shuffling n cards? By linearity: n × (1/n) = **1**.

## How to get good

Work through a proper course (Harvard's Stat 110 is free and excellent) and do problems daily. Speed
comes from having seen many patterns.
`,
      quiz: [
        { q: 'Roll two fair dice. Probability the total is 7?', options: ['1/12', '1/6', '1/36', '7/36'], answer: 1, why: '6 of the 36 equally likely outcomes sum to 7: (1,6),(2,5),…,(6,1). 6/36 = 1/6.' },
        { q: 'A game: win £20 with probability 1/4, otherwise win nothing. It costs £4 to play. EV per play?', options: ['+£1', '−£1', '+£5', '£0'], answer: 0, why: 'EV = ¼ × 20 − 4 = 5 − 4 = +£1.' },
        { q: 'Expected number of coin flips to see the first head?', options: ['1', '1.5', '2', '4'], answer: 2, why: 'Geometric distribution with p = ½: expected tries = 1/p = 2.' },
      ],
      resources: [
        { title: 'Harvard Stat 110 (Blitzstein): lectures, notes and book', url: 'https://stat110.net', note: 'The best single resource; free', free: true },
        { title: 'Xinfeng Zhou, A Practical Guide to Quantitative Finance Interviews', url: 'https://www.google.com/search?q=Practical+Guide+to+Quantitative+Finance+Interviews', note: 'The standard interview puzzle book' },
      ],
    },
    {
      id: 'maths-distributions',
      title: 'Random variables and distributions',
      minutes: 30,
      summary: 'Mean, variance, the normal distribution, and why markets have fat tails.',
      body: `
A **random variable** is a number decided by chance: tomorrow's return, a die roll.

## Mean and variance

- **Mean** μ = E[X]: the centre.
- **Variance** σ² = E[(X − μ)²]: the average squared distance from the mean. **Standard deviation** σ is
  its square root, in the same units as X. In finance σ of returns is **volatility**.
- Var(aX) = a² Var(X). For **independent** X and Y, Var(X + Y) = Var(X) + Var(Y). That's why
  volatility over n days grows like √n.

## Distributions you need

| Distribution | Describes | Key facts |
|---|---|---|
| **Bernoulli / Binomial** | Successes in n yes/no trials | Mean np, variance np(1−p) |
| **Geometric** | Tries until first success | Mean 1/p |
| **Poisson** | Count of rare events in a period | Mean = variance = λ |
| **Uniform** | Equally likely over a range | |
| **Normal (Gaussian)** | Sums of many small effects | 68% within 1σ, 95% within ~2σ (1.96), 99.7% within 3σ |
| **Lognormal** | Prices (log returns normal) | Never negative |

## The Central Limit Theorem

Add up many independent random effects and the total is approximately **normal**, whatever each effect
looks like. That's why the normal distribution is everywhere, and why averages are predictable even when
single outcomes aren't.

## Fat tails: where finance breaks the textbook

Real daily returns have **fat tails**: extreme days happen far more often than a normal distribution
says. A "5-sigma" day should almost never happen under a normal model, yet markets produce them every
few years. Kurtosis measures this (3 for a normal; often much higher for returns).

> Practical rule: models that assume normal returns underestimate crash risk. FinHub's RISK compares a
> normal-based VaR with historical VaR and warns you when tails are fat.
`,
      quiz: [
        { q: 'If daily returns are independent with σ = 1%, what is σ over 4 days?', options: ['4%', '2%', '1%', '16%'], answer: 1, why: 'Variances add: 4 × (1%)², so σ = √4 × 1% = 2%.' },
        { q: 'About what fraction of a normal distribution lies within 2 standard deviations of the mean?', options: ['50%', '68%', '95%', '99.9%'], answer: 2, why: 'Roughly 95% (exactly 95% at 1.96σ).' },
      ],
      tryIt: [{ command: 'RISK SPY 100', label: 'See fat tails in real data: RISK' }],
      resources: [{ title: 'Harvard Stat 110', url: 'https://stat110.net', free: true }],
    },
    {
      id: 'maths-statistics',
      title: 'Statistics: telling signal from noise',
      minutes: 40,
      summary: 'Estimation, standard error, hypothesis tests, and the multiple-testing trap.',
      body: `
Probability goes from a model to data ("if the coin is fair, how often will I see 7 heads?"). Statistics
goes backwards, from data to a model ("I saw 7 heads; is the coin fair?").

## Estimates have error

The sample mean of n observations has a **standard error** of σ / √n. More data shrinks uncertainty,
but slowly: 4× the data halves the error.

> In finance this is brutal. Stock returns have a mean of maybe 0.04% a day and a σ of 1%. With 10
> years (2,520 days), the standard error of the mean is 1% / √2520 ≈ 0.02%, half the thing you're
> trying to measure. Expected returns are very hard to estimate; volatility is much easier.

## Hypothesis tests and p-values

- Start with a **null hypothesis** ("this strategy has no edge").
- Compute how surprising your result would be if the null were true: the **p-value**.
- A small p-value (say < 0.05) means "this would be rare by luck alone". It does **not** mean the
  probability the strategy works.

A **t-statistic** = estimate / standard error. Roughly, |t| > 2 is "significant at 5%".

## The multiple-testing trap (the big one)

Test 20 random strategies at the 5% level and you expect **one** to look significant by pure luck. Try
1,000 parameter combinations and the best will look brilliant. This is the most common way people fool
themselves in quant finance.

Fixes:
- Count every variant you try, and demand more evidence when you've tried many (e.g. the **deflated
  Sharpe ratio**, which adjusts for the number of trials).
- Keep data you never look at until the very end (an **out-of-sample** test).
- **Walk-forward** testing: choose parameters on the past, test on the following period, repeat.

## Correlation is not causation

Two series can move together because of a third factor, or by coincidence. With thousands of
financial series, coincidences are guaranteed.
`,
      quiz: [
        { q: 'To halve the standard error of a mean, you need about how much more data?', options: ['2×', '4×', '10×', '√2×'], answer: 1, why: 'Standard error = σ/√n, so halving it requires √n to double, i.e. n × 4.' },
        { q: 'You test 100 strategies with no real edge at the 5% significance level. How many look significant by chance, on average?', options: ['0', 'About 1', 'About 5', 'About 50'], answer: 2, why: 'Each has a 5% false-positive chance: 100 × 0.05 = 5.' },
        { q: 'A p-value of 0.03 means…', options: ['97% chance the strategy works', 'A result this extreme would happen 3% of the time if there were no edge', 'The strategy returns 3%', 'The test is 3% wrong'], answer: 1, why: 'The p-value is computed assuming the null hypothesis is true. It is not the probability the hypothesis is true.' },
      ],
      tryIt: [{ command: 'BACKTEST SPY sma 20 50', label: 'See the deflated Sharpe and walk-forward: BACKTEST' }],
      resources: [
        { title: 'Harvard Stat 110 (probability foundations)', url: 'https://stat110.net', free: true },
        { title: 'Marcos López de Prado, Advances in Financial Machine Learning', url: 'https://www.google.com/search?q=Advances+in+Financial+Machine+Learning', note: 'Backtest overfitting and the deflated Sharpe ratio; advanced' },
      ],
    },
    {
      id: 'maths-linear-algebra',
      title: 'Linear algebra for portfolios',
      minutes: 35,
      summary: 'Vectors, matrices, covariance, and portfolio variance w’Σw.',
      body: `
Linear algebra is the language of portfolios and of machine learning.

## Vectors and matrices

- A **vector** is a list of numbers: portfolio weights w = (0.6, 0.3, 0.1).
- The **dot product** a·b = Σ aᵢbᵢ. Portfolio return = w · r (weights times asset returns).
- A **matrix** is a grid of numbers; multiplying a matrix by a vector combines its rows with the vector.
- The **transpose** w' (or wᵀ) turns a column into a row.

## Covariance and correlation

- **Covariance** between two assets: do they move together? Positive: up together. Negative: one up, one down.
- **Correlation** = covariance / (σ₁σ₂), always between −1 and +1.
- The **covariance matrix** Σ holds every variance (diagonal) and covariance (off-diagonal).

## Portfolio variance: the key formula

~~~
portfolio variance = w' Σ w
~~~

For two assets: σ²ₚ = w₁²σ₁² + w₂²σ₂² + 2w₁w₂ρσ₁σ₂. If correlation ρ is low, the cross term is small
and the portfolio is **less risky than its parts**. That's diversification, in one line of maths.

> Worked example: two assets, each σ = 20%, weights 50/50. With ρ = 1: σₚ = 20%. With ρ = 0: σₚ =
> √(0.25×0.04 + 0.25×0.04) = √0.02 ≈ 14.1%. With ρ = −1: 0%.

## Beyond

- **Solving linear systems** and **matrix inverses** give optimal portfolios (Σ⁻¹μ is proportional to the
  maximum-Sharpe portfolio when unconstrained).
- **Eigenvalues and eigenvectors** find the main directions of variation (PCA), e.g. the "market factor".
- **Regression** is linear algebra: β = (X'X)⁻¹X'y.
`,
      quiz: [
        { q: 'Two assets with σ = 10% each, correlation 0, held 50/50. Portfolio volatility?', options: ['10%', '7.1%', '5%', '0%'], answer: 1, why: 'σ² = 0.25×0.01 + 0.25×0.01 = 0.005, σ ≈ 0.0707.' },
        { q: 'Correlation must lie between…', options: ['0 and 1', '−1 and 1', '0 and ∞', '−∞ and ∞'], answer: 1, why: 'Correlation is covariance scaled by both standard deviations, so it’s bounded by −1 and +1.' },
      ],
      tryIt: [{ command: 'RISK SPY 60 TLT 30 GLD 10', label: 'Correlations and risk contributions: RISK' }],
      resources: [
        { title: 'MIT 18.06 Linear Algebra (Gilbert Strang)', url: 'https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/', free: true },
        { title: '3Blue1Brown: Essence of linear algebra', url: 'https://www.3blue1brown.com/topics/linear-algebra', free: true },
      ],
    },
    {
      id: 'maths-calculus',
      title: 'Calculus and optimisation',
      minutes: 30,
      summary: 'Derivatives, Greeks, gradients, and finding the best answer.',
      body: `
## Derivatives (the calculus kind)

The **derivative** f'(x) is the slope: how fast f changes when x changes a little. Rules: d/dx xⁿ = nxⁿ⁻¹,
d/dx eˣ = eˣ, d/dx ln x = 1/x, plus the product and chain rules.

In finance, sensitivities are derivatives. The option **Greeks** are exactly this:

| Greek | Derivative of option price with respect to |
|---|---|
| **Delta** | the underlying price |
| **Gamma** | delta with respect to price (second derivative) |
| **Vega** | volatility |
| **Theta** | time |
| **Rho** | interest rate |

A **Taylor expansion** says a small change Δx moves f by about f'(x)Δx + ½f''(x)Δx². For options:
P&L ≈ delta × move + ½ × gamma × move². That's how option traders think about risk.

## Integrals

An **integral** adds up infinitely many small pieces: the area under a curve. Probability densities
integrate to 1; expected values are integrals.

## Optimisation

To find the best x, look where the derivative is zero (and check it's a maximum, not a minimum). With
many variables you follow the **gradient**, the direction of steepest increase. **Constraints** (weights
must add to 1, no short selling) are handled with Lagrange multipliers or by projecting back onto the
allowed set, which is what FinHub's optimiser does.

> Caution: an optimiser happily exploits estimation errors. Feed it noisy expected returns and it
> builds extreme portfolios. RISK shows bootstrap error bars on its optimal weights for this reason.
`,
      quiz: [
        { q: 'd/dx of x³ is…', options: ['x²', '3x²', '3x³', 'x⁴/4'], answer: 1, why: 'Power rule: d/dx xⁿ = n xⁿ⁻¹.' },
        { q: 'An option’s delta is 0.6. The stock rises £1. The option rises roughly…', options: ['£1', '£0.60', '£0.06', '£6'], answer: 1, why: 'Delta is the first derivative: change ≈ delta × move = 0.6 × 1.' },
      ],
      tryIt: [{ command: 'OPT', label: 'See Greeks change as you move inputs: OPT' }],
      resources: [
        { title: '3Blue1Brown: Essence of calculus', url: 'https://www.3blue1brown.com/topics/calculus', free: true },
        { title: 'Khan Academy: Calculus', url: 'https://www.khanacademy.org/math/calculus-1', free: true },
      ],
    },
    {
      id: 'maths-regression',
      title: 'Regression and correlation',
      minutes: 25,
      summary: 'Fitting lines, beta, R², and the pitfalls.',
      body: `
**Linear regression** fits y ≈ α + βx by choosing α and β to minimise the sum of squared errors.

## In finance

- Regress a stock's returns on the market's returns: **β (beta)** is how much the stock moves per 1% market
  move; **α (alpha)** is the return not explained by the market. "Finding alpha" means finding returns
  the market (or other factors) doesn't explain.
- With several x's (multiple regression) you measure exposure to many **factors** at once: market, size,
  value, momentum.

## Reading results

- **R²**: the fraction of y's variation explained. In return prediction, an R² of 1% can be valuable;
  anything high is suspicious.
- **t-statistic of β**: is the relationship distinguishable from zero? (See the statistics lesson and
  remember multiple testing.)

## Pitfalls

- **Look-ahead**: using x values you wouldn't have known at the time you trade.
- **Non-stationarity**: relationships change over time; a beta from 2010 may not hold today.
- **Outliers**: one crash day can dominate a fit.
- **Overfitting**: more variables always improve the fit in-sample and usually hurt out-of-sample.

## Practice

Compute by hand for x = (1, 2, 3), y = (2, 4, 7): β = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)² = 2.5, α = ȳ − βx̄ = −0.67.
Then do it in Python with numpy.polyfit and check.
`,
      quiz: [
        { q: 'A stock has β = 1.5. The market falls 2%. Expected move from the market alone?', options: ['−1.5%', '−3%', '−2%', '+3%'], answer: 1, why: 'β × market move = 1.5 × −2% = −3%.' },
        { q: 'Adding more explanatory variables to a regression always…', options: ['Improves out-of-sample accuracy', 'Increases (or keeps) in-sample R²', 'Removes look-ahead bias', 'Reduces beta'], answer: 1, why: 'In-sample fit can only improve; out-of-sample usually gets worse beyond a point (overfitting).' },
      ],
      resources: [{ title: 'Wes McKinney, Python for Data Analysis (free online)', url: 'https://wesmckinney.com/book/', free: true }],
    },
    {
      id: 'maths-stochastic',
      title: 'Random walks, Brownian motion and Black–Scholes',
      minutes: 35,
      summary: 'How prices are modelled as random processes.',
      body: `
## Random walks

Flip a coin each step: +1 for heads, −1 for tails. Your position is a **random walk**. After n steps its
expected value is 0 and its standard deviation is √n. Prices behave a bit like this: unpredictable
steps whose spread grows with √time.

## Brownian motion

Make the steps tiny and frequent and you get **Brownian motion** W(t): continuous, random, with
W(t) ~ Normal(0, t). It's the building block of continuous-time finance.

## Geometric Brownian motion (GBM)

Prices can't go negative and moves scale with the price, so the standard model is

~~~
dS = μ S dt + σ S dW
~~~

meaning: over a tiny time dt, the price drifts by μS dt and jiggles randomly with size σS√dt. Under
GBM, log returns are normal and prices are lognormal.

## Black–Scholes in one paragraph

Hold Δ shares against one option, with Δ chosen so small price moves cancel. That combination is
**riskless** over a short time, so it must earn the risk-free rate, otherwise there's free money. That
argument gives a formula for the option price that depends on volatility but **not** on the stock's
expected return μ. The resulting formula is what OPT computes, and its binomial-tree and Monte Carlo
versions agree with it.

## Itô's lemma (the one new rule)

In ordinary calculus, small squared changes vanish. With Brownian motion, (dW)² behaves like dt, so a
second-order term survives. **Itô's lemma** is the chain rule with that extra term. You need it for
derivatives pricing roles; learn probability and statistics thoroughly first.

> Simulation builds intuition faster than proofs: in Python, generate thousands of GBM paths with numpy
> and watch the distribution of final prices.
`,
      quiz: [
        { q: 'A symmetric ±1 random walk after 100 steps has standard deviation…', options: ['100', '10', '50', '1'], answer: 1, why: '√n = √100 = 10.' },
        { q: 'In the Black–Scholes model, the option price does NOT depend on…', options: ['Volatility', 'The stock’s expected return μ', 'The strike', 'Time to expiry'], answer: 1, why: 'Hedging removes μ: the price is the same whatever investors expect the stock to return.' },
      ],
      tryIt: [{ command: 'OPT', label: 'Three pricing methods side by side: OPT' }],
      resources: [
        { title: 'MIT 18.S096 Topics in Mathematics with Applications in Finance', url: 'https://ocw.mit.edu/courses/18-s096-topics-in-mathematics-with-applications-in-finance-fall-2013/', free: true },
        { title: 'Steven Shreve, Stochastic Calculus for Finance I (discrete) and II', url: 'https://www.google.com/search?q=Shreve+Stochastic+Calculus+for+Finance', note: 'For derivatives roles; after probability' },
      ],
    },
  ],
}
