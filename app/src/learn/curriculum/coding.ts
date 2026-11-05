import type { Track } from '../types'

export const coding: Track = {
  id: 'coding',
  title: 'Coding',
  description: 'Python from zero to a real backtest, then algorithms, C++, SQL and good engineering habits.',
  access: 'free',
  lessons: [
    {
      id: 'coding-setup',
      title: 'Which languages, and getting set up',
      minutes: 20,
      summary: 'Python first, C++ later, SQL alongside. Install everything.',
      body: `
## Which languages, and why

| Language | Used for | When to learn |
|---|---|---|
| **Python** | Research, data analysis, backtests, machine learning, prototypes | Now. It's the common language of quant research |
| **C++** | Fast trading systems, pricing libraries, anything latency-sensitive | After Python, if you aim at quant dev or trading firms |
| **SQL** | Pulling data out of databases | Alongside Python; a few weeks is enough |
| Others | Some firms use Java, C#, OCaml (Jane Street), Rust, kdb+/q | Firms teach their own stack; don't start here |

## Install Python

1. Install **Python 3.12+** from [python.org](https://www.python.org/downloads/) (tick "Add to PATH" on Windows).
2. Install an editor: [VS Code](https://code.visualstudio.com/) with the Python extension.
3. Make a project folder and a **virtual environment** so each project has its own packages:

~~~bash
mkdir quant-practice && cd quant-practice
python -m venv .venv
# Windows: .venv\\Scripts\\activate      macOS/Linux: source .venv/bin/activate
pip install numpy pandas matplotlib jupyter yfinance
~~~

4. Start a notebook with \`jupyter notebook\` (great for exploring) or write \`.py\` files (better for real code).

## How to learn to code (honestly)

- **Type the examples yourself**; don't copy-paste. Then change them and see what breaks.
- **Read error messages** from the bottom up. They usually tell you the line and the problem.
- **Build small things** you care about: a returns calculator, a chart of your favourite stock.
- AI assistants are great for explaining errors and concepts. Make sure you can write the code
  without them, because interviews and online assessments don't allow help.
`,
      quiz: [
        { q: 'For a quant developer at a trading firm, which language matters most after Python?', options: ['HTML', 'C++', 'Excel VBA', 'PHP'], answer: 1, why: 'Low-latency trading systems are mostly C++; quant developer interviews often include it.' },
        { q: 'Why use a virtual environment?', options: ['To make Python faster', 'So each project has its own isolated packages', 'It is required for Jupyter', 'To hide code from others'], answer: 1, why: 'Different projects need different package versions; isolation prevents conflicts (FinHub does the same with its engines).' },
      ],
      resources: [
        { title: 'Official Python tutorial', url: 'https://docs.python.org/3/tutorial/', free: true },
        { title: 'Automate the Boring Stuff with Python (free online)', url: 'https://automatetheboringstuff.com', free: true },
      ],
    },
    {
      id: 'coding-python-basics',
      title: 'Python basics',
      minutes: 60,
      summary: 'Variables, types, lists, dictionaries, loops, functions.',
      body: `
Open a Python file or notebook and type each example.

## Values, variables and types

~~~python
price = 101.25          # float (decimal number)
shares = 100            # int (whole number)
ticker = "AAPL"         # str (text)
is_open = True          # bool (True/False)
value = price * shares  # 10125.0
print(f"{ticker}: {shares} shares worth {value:,.2f}")
~~~

## Lists and dictionaries

~~~python
closes = [100.0, 102.0, 101.0, 105.0]   # a list: ordered, indexable from 0
print(closes[0], closes[-1])            # first and last: 100.0 105.0
closes.append(104.0)

portfolio = {"AAPL": 0.6, "MSFT": 0.4}  # a dict: key -> value
portfolio["NVDA"] = 0.0
print(portfolio["AAPL"])
~~~

## Loops and conditions

~~~python
returns = []
for i in range(1, len(closes)):
    r = closes[i] / closes[i - 1] - 1
    returns.append(r)
    if r < -0.01:
        print(f"Day {i}: big drop {r:.2%}")
~~~

## Functions

~~~python
def total_return(prices):
    """Fractional return from the first to the last price."""
    return prices[-1] / prices[0] - 1

def annualised_volatility(daily_returns):
    n = len(daily_returns)
    mean = sum(daily_returns) / n
    var = sum((r - mean) ** 2 for r in daily_returns) / (n - 1)
    return var ** 0.5 * 252 ** 0.5

print(total_return(closes))
~~~

Writing volatility by hand once is worth it; afterwards you'll use numpy.

## Exercises

1. Write \`max_drawdown(prices)\` that returns the worst peak-to-trough fall as a fraction.
   (Track the running peak in a loop.)
2. Write \`compound(returns)\` that turns a list of daily returns into a total return.
3. Simulate 1,000 coin flips with \`import random\` and \`random.random() < 0.5\`; check about half are heads.
`,
      quiz: [
        { q: 'In Python, closes[-1] is…', options: ['An error', 'The last element', 'The first element', 'The list reversed'], answer: 1, why: 'Negative indices count from the end; −1 is the last element.' },
        { q: 'Which data structure maps tickers to weights?', options: ['list', 'dict', 'str', 'bool'], answer: 1, why: 'A dictionary maps keys (tickers) to values (weights).' },
      ],
      resources: [
        { title: 'Official Python tutorial', url: 'https://docs.python.org/3/tutorial/', free: true },
        { title: 'Project Euler (maths + code problems)', url: 'https://projecteuler.net', free: true },
      ],
    },
    {
      id: 'coding-numpy-pandas',
      title: 'NumPy and pandas: working with data',
      minutes: 60,
      summary: 'Arrays, vectorised maths, DataFrames, real prices.',
      body: `
Loops are slow and verbose for data. **NumPy** does maths on whole arrays at once; **pandas** adds
labelled tables (DataFrames) with dates.

## NumPy

~~~python
import numpy as np

prices = np.array([100.0, 102.0, 101.0, 105.0, 104.0])
returns = prices[1:] / prices[:-1] - 1        # all returns at once, no loop
print(returns.mean(), returns.std(ddof=1))
print(returns.std(ddof=1) * np.sqrt(252))     # annualised volatility

rng = np.random.default_rng(42)
simulated = rng.normal(0.0004, 0.01, size=(1000, 252))  # 1,000 simulated years of daily returns
final = np.prod(1 + simulated, axis=1)                  # growth of 1 in each year
print(np.percentile(final, [5, 50, 95]))
~~~

## pandas with real data

~~~python
import pandas as pd
import yfinance as yf

close = yf.download(["SPY", "TLT"], start="2015-01-01", auto_adjust=True)["Close"]
returns = close.pct_change().dropna()

print(returns.describe())                 # summary statistics
print(returns.corr())                     # correlation matrix
print(returns.std() * np.sqrt(252))       # annualised volatility per asset

rolling_vol = returns["SPY"].rolling(63).std() * np.sqrt(252)   # 3-month rolling volatility
rolling_vol.plot(title="SPY rolling volatility")
~~~

\`auto_adjust=True\` adjusts for splits and dividends. Use adjusted prices for returns, or a stock split
looks like a crash.

## Key pandas ideas

- **Index by date**: \`close.loc["2020-03"]\` selects March 2020.
- **Vectorised operations**: \`close / close.shift(1) - 1\` is the same as \`pct_change()\`.
- **shift(1)** moves data one row later. This is how you avoid using tomorrow's information today
  (next lesson).
- **Missing data**: \`dropna()\`, \`fillna()\`. Always check what's missing and why.
`,
      quiz: [
        { q: 'Why prefer prices[1:] / prices[:-1] − 1 over a Python loop?', options: ['It gives different answers', 'It is vectorised: shorter and much faster', 'Loops are not allowed in NumPy', 'It handles text'], answer: 1, why: 'NumPy runs the arithmetic in optimised compiled code over the whole array.' },
        { q: 'Why use split- and dividend-adjusted prices for returns?', options: ['They are prettier', 'Unadjusted prices show fake drops on split days', 'They are always higher', 'Exchanges require it'], answer: 1, why: 'A 4-for-1 split cuts the share price by 75% with no loss to holders; unadjusted data records it as a crash.' },
      ],
      tryIt: [{ command: 'CMP SPY TLT GLD', label: 'Compare the numbers with FinHub: CMP' }],
      resources: [
        { title: 'Wes McKinney, Python for Data Analysis, 3rd ed. (free online)', url: 'https://wesmckinney.com/book/', free: true },
        { title: 'NumPy: absolute beginners guide', url: 'https://numpy.org/doc/stable/user/absolute_beginners.html', free: true },
      ],
    },
    {
      id: 'coding-first-backtest',
      title: 'Your first backtest, done honestly',
      minutes: 60,
      summary: 'A moving-average strategy in pandas: timing, costs, and comparison.',
      body: `
A **backtest** asks: if I had followed this rule in the past, what would have happened? It's easy to
write one that lies. Here's one that doesn't.

## Step 1: the signal

~~~python
import numpy as np
import yfinance as yf

close = yf.download("SPY", start="2005-01-01", auto_adjust=True)["Close"].squeeze()
fast = close.rolling(50).mean()
slow = close.rolling(200).mean()
signal = (fast > slow).astype(float)   # 1 = want to be long, decided at each day's close
~~~

## Step 2: timing (where most backtests cheat)

\`signal\` on day t uses day t's closing price. You can't trade at a price you only learn when it's
already gone. So the earliest you can act is the **next** close, and the first return you earn is the
one after that:

~~~python
ret = close.pct_change()               # ret on day t = close(t) / close(t-1) - 1
position = signal.shift(2)             # decided at close t, traded at close t+1, earns ret from t+2
# signal.shift(1) would mean trading at the same close you used to decide: look-ahead bias
~~~

## Step 3: costs

~~~python
cost_per_trade = 0.0010                # 10 basis points: commission + slippage
turnover = position.diff().abs().fillna(0)
strategy = position * ret - turnover * cost_per_trade
buy_hold = ret
~~~

## Step 4: compare honestly

~~~python
def summary(r):
    r = r.dropna()
    years = len(r) / 252
    growth = (1 + r).prod()
    vol = r.std() * np.sqrt(252)
    sharpe = r.mean() * 252 / vol
    wealth = (1 + r).cumprod()
    max_dd = (wealth / wealth.cummax() - 1).min()
    return dict(CAGR=growth ** (1 / years) - 1, vol=vol, sharpe=sharpe, max_dd=max_dd)

print("strategy ", summary(strategy))
print("buy&hold", summary(buy_hold))
~~~

## What you'll probably find

The strategy often has **lower drawdowns** but **lower returns** than buy-and-hold, and a similar or
worse Sharpe after costs. That's a real, useful finding. Now:

1. Try 10 different window pairs. Notice how tempting it is to keep the best one. That's overfitting.
2. Split the data: pick windows on 2005–2014 only, then test them on 2015–today.
3. Run the same thing in FinHub's BACKTEST and compare your numbers: it applies the same timing rule,
   plus walk-forward testing and a deflated Sharpe ratio.
`,
      quiz: [
        { q: 'Your signal uses today’s close. Using position = signal.shift(1) on close-to-close returns means…', options: ['A realistic next-day trade', 'Trading at the very close you used to decide: look-ahead bias', 'Ignoring costs', 'Shorting'], answer: 1, why: 'shift(1) earns tomorrow’s return from today’s close, so you’d have to trade at the price that produced the signal.' },
        { q: 'You try 50 parameter pairs and report the best. The reported Sharpe is…', options: ['Unbiased', 'Probably too high', 'Probably too low', 'Exactly right if costs are included'], answer: 1, why: 'Picking the best of many noisy results inflates it (selection bias). Test it on data you didn’t use to choose it.' },
      ],
      tryIt: [{ command: 'BACKTEST SPY sma 50 200', label: 'Check your numbers: BACKTEST SPY sma 50 200' }],
      resources: [{ title: 'Ernest Chan, Quantitative Trading (book)', url: 'https://www.google.com/search?q=Ernest+Chan+Quantitative+Trading', note: 'Practical introduction to building strategies' }],
    },
    {
      id: 'coding-algorithms',
      title: 'Data structures and algorithms',
      minutes: 45,
      summary: 'Big-O, the core structures, and how to practise for coding interviews.',
      body: `
Nearly every quant developer and many trader/researcher interviews include coding problems. They test
whether you can pick the right **data structure** and reason about speed.

## Big-O: how cost grows

| Big-O | Meaning | Example |
|---|---|---|
| O(1) | Constant | Dictionary lookup |
| O(log n) | Halves each step | Binary search in sorted data |
| O(n) | One pass | Summing a list |
| O(n log n) | Sorting | \`sorted(prices)\` |
| O(n²) | Every pair | Naive pair comparison |

## Structures to know cold

- **Array/list**: fast index, slow insert in the middle.
- **Hash map (dict) / hash set**: O(1) average lookup. The answer to "have I seen this before?"
- **Stack and queue**: last-in-first-out / first-in-first-out.
- **Heap (priority queue)**: always know the smallest/largest quickly. An order book's best bid is a heap problem.
- **Binary search** on sorted data.
- **Trees and graphs**: traversal (BFS/DFS).

## A classic, two ways

"Find two prices in a list that sum to a target."

~~~python
def two_sum_slow(xs, target):              # O(n^2): check every pair
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            if xs[i] + xs[j] == target:
                return i, j

def two_sum_fast(xs, target):              # O(n): remember what we've seen
    seen = {}
    for i, x in enumerate(xs):
        if target - x in seen:
            return seen[target - x], i
        seen[x] = i
~~~

## How to practise

- Do problems on [LeetCode](https://leetcode.com): start with easy array/hash-map problems, then
  medium. 150–250 well-understood problems is a common target before applications.
- Talk through your approach out loud, state the complexity, test edge cases (empty input, one element).
- Timed online assessments (HackerRank, Codility) are usually the first filter. Practise under time.
`,
      quiz: [
        { q: 'Average cost of looking up a key in a Python dict?', options: ['O(n)', 'O(log n)', 'O(1)', 'O(n²)'], answer: 2, why: 'Hash maps give constant-time lookup on average.' },
        { q: 'Which structure always gives you the highest bid quickly as orders arrive and leave?', options: ['Unsorted list', 'Heap / priority queue (or sorted map)', 'Stack', 'String'], answer: 1, why: 'A heap keeps the best element at the top in O(log n) per update; real order books often use sorted maps of price levels.' },
      ],
      resources: [
        { title: 'LeetCode', url: 'https://leetcode.com', free: true },
        { title: 'NeetCode roadmap (curated problem list)', url: 'https://neetcode.io/roadmap', free: true },
      ],
    },
    {
      id: 'coding-cpp',
      title: 'C++ essentials',
      minutes: 60,
      summary: 'Compiled, typed and fast: the basics, and an order book in C++.',
      body: `
C++ is used where speed matters: trading engines, pricing libraries. It's harder than Python because
you control memory and types, but that control is the point.

## Setup

Install a compiler (g++ or clang; on Windows, Visual Studio Community or MSYS2), then:

~~~bash
g++ -std=c++20 -O2 -Wall main.cpp -o main && ./main
~~~

## The basics

~~~cpp
#include <iostream>
#include <vector>
#include <string>

struct Order {
    int id;
    std::string side;   // "buy" or "sell"
    double price;
    int qty;
};

double notional(const Order& o) {          // pass by const reference: no copy
    return o.price * o.qty;
}

int main() {
    std::vector<Order> orders = {{1, "buy", 100.0, 10}, {2, "sell", 100.5, 5}};
    for (const auto& o : orders) {
        std::cout << o.id << " " << o.side << " " << notional(o) << "\\n";
    }
}
~~~

Key ideas: **static types** (the compiler checks them), **compiled** (turned into machine code ahead of
time), **references** (\`const Order&\` avoids copying), **the standard library** (\`std::vector\`,
\`std::map\`, \`std::unordered_map\`).

## Memory, the modern way

- Prefer values and standard containers. If you need heap objects, use \`std::unique_ptr\` /
  \`std::make_unique\`; avoid raw \`new\`/\`delete\`.
- **RAII**: resources are released automatically when objects go out of scope.

## A first project: an order book

Keep bids in \`std::map<double, std::deque<Order>, std::greater<double>>\` (highest price first) and
asks in \`std::map<double, std::deque<Order>>\` (lowest first). Implement add, cancel and matching with
price-time priority. Then write tests and measure how many orders per second it handles. This is the
classic quant-developer portfolio project; FinHub's SIM engine follows the same rules.
`,
      quiz: [
        { q: 'Why pass const Order& rather than Order?', options: ['It’s required syntax', 'Avoids copying the object and prevents changing it', 'Makes it a pointer you must delete', 'Makes the function faster to compile'], answer: 1, why: 'A const reference reads the original without a copy and the compiler stops you modifying it.' },
        { q: 'Modern C++ prefers which for owning heap memory?', options: ['Raw new/delete', 'std::unique_ptr', 'malloc', 'Global variables'], answer: 1, why: 'Smart pointers free memory automatically (RAII), preventing leaks.' },
      ],
      tryIt: [{ command: 'SIM', label: 'See an order book in action: SIM' }],
      resources: [
        { title: 'learncpp.com (free, thorough)', url: 'https://www.learncpp.com', free: true },
        { title: 'C++ reference', url: 'https://en.cppreference.com', free: true },
      ],
    },
    {
      id: 'coding-sql',
      title: 'SQL for market data',
      minutes: 30,
      summary: 'Query, filter, aggregate, and compute returns in a database.',
      body: `
Most firms keep data in databases. **SQL** gets it out. A few weeks of practice is enough for interviews.

Imagine a table \`prices(date, ticker, close)\`.

~~~sql
-- Latest close for each ticker
SELECT ticker, MAX(date) AS last_date
FROM prices
GROUP BY ticker;

-- Average close per ticker in 2024
SELECT ticker, AVG(close) AS avg_close
FROM prices
WHERE date BETWEEN '2024-01-01' AND '2024-12-31'
GROUP BY ticker
ORDER BY avg_close DESC;

-- Daily returns with a window function
SELECT date, ticker,
       close / LAG(close) OVER (PARTITION BY ticker ORDER BY date) - 1 AS daily_return
FROM prices;
~~~

Know: SELECT, WHERE, GROUP BY, HAVING, ORDER BY, JOIN (inner/left), and window functions (LAG, ROW_NUMBER,
running sums). Practise on a free interactive site, then load your own price data into SQLite with
pandas (\`df.to_sql\`).
`,
      quiz: [
        { q: 'Which clause filters groups after aggregation?', options: ['WHERE', 'HAVING', 'ORDER BY', 'LIMIT'], answer: 1, why: 'WHERE filters rows before grouping; HAVING filters groups after aggregates are computed.' },
      ],
      resources: [{ title: 'SQLBolt (interactive lessons)', url: 'https://sqlbolt.com', free: true }],
    },
    {
      id: 'coding-engineering',
      title: 'Git, testing and good habits',
      minutes: 30,
      summary: 'Version control, tests and readable code: what turns scripts into evidence.',
      body: `
Employers judge projects by whether they look like real engineering.

## Git and GitHub

~~~bash
git init
git add .
git commit -m "Moving-average backtest with costs"
git remote add origin https://github.com/YOU/quant-practice.git
git push -u origin main
~~~

Commit small, meaningful steps with clear messages. Put projects on GitHub with a README explaining what,
why, how to run, and **what you found** (including what didn't work).

## Tests

~~~python
# test_metrics.py   (run with: pip install pytest && pytest)
from metrics import total_return

def test_total_return():
    assert abs(total_return([100, 110]) - 0.10) < 1e-12

def test_flat():
    assert total_return([50, 50]) == 0
~~~

Test the maths against cases you can work out by hand. FinHub's own code is tested against textbook
values for exactly this reason.

## Habits

- Names that say what things are (\`annual_vol\`, not \`x2\`).
- Functions that do one thing.
- Never hard-code results; make every number reproducible from code and data.
- Record every experiment, including failures; it is your evidence against overfitting.
`,
      quiz: [
        { q: 'What makes a GitHub project most convincing to a quant employer?', options: ['Many small tutorial repos', 'A clear README, tests and honest findings', 'Lots of stars', 'Using the newest framework'], answer: 1, why: 'Depth, correctness and honest reporting beat breadth. Interviewers will ask about every claim.' },
      ],
      resources: [{ title: 'Pro Git (free book)', url: 'https://git-scm.com/book/en/v2', free: true }],
    },
  ],
}
