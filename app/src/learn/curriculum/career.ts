import type { Track } from '../types'

export const career: Track = {
  id: 'career',
  title: 'Getting into the industry',
  description: 'What interviews test, projects worth building, competitions, and a 12-month plan from zero.',
  access: 'free',
  lessons: [
    {
      id: 'career-interviews',
      title: 'What interviews actually test',
      minutes: 25,
      summary: 'Online assessments, mental maths, probability, coding, and the conversation.',
      body: `
Quant hiring is unusually test-driven. The good news: tests can be practised.

## The usual stages

1. **Application**: CV with grades, projects, competitions.
2. **Online assessment**: timed tests. Trading firms: mental arithmetic, number sequences, probability.
   Developer roles: coding problems (HackerRank/Codility style).
3. **Phone / video interviews**: probability puzzles, expected value, statistics, coding, your projects.
4. **Final round / superday**: several interviews in a row, sometimes a **trading game** (market making
   with other candidates), system design for developers, and behavioural questions.

## By role

| Role | Practise |
|---|---|
| Trader | Mental maths (speed!), probability puzzles, expected value, betting and market-making games |
| Researcher | Probability, statistics, regression, ML, a research project you can defend in depth |
| Developer | Data structures and algorithms, C++/Python, systems (memory, concurrency), design |
| Risk / strats | Statistics, derivatives pricing, stochastic calculus, numerical methods |

## Mental maths

Trading firms test arithmetic under time pressure. Practise daily, ten minutes:
- [Zetamac](https://arithmetic.zetamac.com) (default settings: a two-minute round). Scores of roughly 40–60+ are commonly quoted as targets;
  check what candidates for your target firms report.
- Fractions ↔ percentages, quick multiplication (e.g. 47 × 23), estimating square roots.

## Talking through problems

Interviewers care how you think. Say your assumptions, start simple, check edge cases, sanity-check
answers ("is a probability above 1? then I made a mistake"). Saying "I'm not sure, but here's how I'd
check" beats guessing confidently.

## Your projects

Expect to be asked about every line on your CV. Know your project's numbers, its weaknesses, and what you'd
do differently. "My strategy stopped working after costs, and here's why" is a strong answer.
`,
      quiz: [
        { q: 'For a quant trader role, which daily practice does this lesson recommend?', options: ['Reading annual reports', 'Timed mental arithmetic', 'Learning HTML', 'Memorising tickers'], answer: 1, why: 'Trading firms screen on fast, accurate arithmetic; it improves quickly with daily practice.' },
      ],
      resources: [
        { title: 'Zetamac arithmetic game', url: 'https://arithmetic.zetamac.com', free: true },
        { title: 'Xinfeng Zhou, A Practical Guide to Quantitative Finance Interviews', url: 'https://www.google.com/search?q=Practical+Guide+to+Quantitative+Finance+Interviews', note: 'The standard question bank' },
        { title: 'Timothy Crack, Heard on the Street', url: 'https://www.google.com/search?q=Heard+on+the+Street+Crack', note: 'Classic interview questions' },
        { title: 'Jane Street puzzles (monthly)', url: 'https://www.janestreet.com/puzzles/', free: true },
      ],
    },
    {
      id: 'career-projects',
      title: 'Projects that count',
      minutes: 25,
      summary: 'Four projects interviewers respect, and how to make them non-trivial.',
      body: `
Two deep projects you can defend for twenty minutes beat ten tutorial repos.

| Project | Shows | Makes it serious |
|---|---|---|
| **Backtester with real validation** | Software design + statistical judgement | Next-bar fills, costs, walk-forward, trial count, honest negative results |
| **Order book / market-making simulator (C++)** | Systems skill, microstructure | Price-time matching, tests, measured throughput, a market-making agent with P&L split into spread vs adverse selection |
| **Options pricer** | Numerical methods, derivatives | Tree, Black–Scholes and Monte Carlo agreeing; Greeks; implied vol from real quotes |
| **Replication of a published anomaly** | Research method | Broad universe, costs, sub-periods, multiple-testing adjustment |

FinHub contains working versions of all four ideas. Use them to understand what "good" looks like, then
build your own from scratch. You learn by building, and interviewers will ask about your code, not FinHub's.

## Make it presentable

- GitHub with a clear README: question, method, results (tables/charts), limitations.
- Tests for the maths.
- A short write-up or blog post of what you learned, including what failed.

## Avoid

- "Predicting stock prices with an LSTM" with an impressive accuracy number.
- Live-trading bots with real money as a learning project.
- Results you can't explain or reproduce.
`,
      quiz: [
        { q: 'Which project description is most convincing?', options: ['“Built an AI that predicts the S&P with 87% accuracy”', '“Built a backtester with costs and walk-forward validation; momentum’s Sharpe fell from 0.9 to 0.3 after costs”', '“Made 15 trading bots”', '“Followed a YouTube tutorial”'], answer: 1, why: 'Specific, honest, validated results show judgement. Spectacular accuracy claims suggest look-ahead or overfitting.' },
      ],
      tryIt: [{ command: 'BACKTEST SPY sma 50 200', label: 'See a validated backtest: BACKTEST' }],
    },
    {
      id: 'career-competitions',
      title: 'Competitions, networking and applications',
      minutes: 20,
      summary: 'Where to get evidence and how to get noticed.',
      body: `
## Competitions

- **[IMC Prosperity](https://prosperity.imc.com)**: an algorithmic trading competition run by IMC, usually
  yearly, in teams. Thousands of entrants; a strong placement is real evidence, and taking part teaches a
  lot either way.
- **Kaggle**: data science competitions. Valuable only with a strong placement or a serious write-up.
- **Programming contests** (Codeforces, ICPC): excellent for developer roles and online assessments.
- **Jane Street's monthly puzzles**: practice, and a conversation topic.

## Early programmes

Many firms run **insight days / spring weeks** for first-year university students and **internships**
for penultimate-year students. Applications often open the summer or autumn before. Internships are the
main route into graduate jobs, so apply broadly and early.

## Networking

- Alumni from your university at target firms are your warmest contacts. A short, specific message
  ("I built X, I'm curious how your team approaches Y") works better than asking for a job.
- University finance, trading and quant societies run events with firms.
- Post write-ups of your projects; they give people a reason to talk to you.

## Applying

- Apply to a range: top trading firms, hedge funds, bank quant and technology teams, asset managers,
  exchanges and data companies. Don't put all your applications into ten firms.
- Tailor the top of your CV to the role (trading vs research vs development).
`,
      quiz: [
        { q: 'For most firms, what is the main route into a graduate quant role?', options: ['Cold emailing the CEO', 'A penultimate-year internship', 'Posting on social media', 'Buying a course certificate'], answer: 1, why: 'Internships convert into graduate offers at many firms; applications open months in advance.' },
      ],
      resources: [{ title: 'IMC Prosperity', url: 'https://prosperity.imc.com', free: true }],
    },
    {
      id: 'career-plan',
      title: 'A 12-month plan from zero',
      minutes: 15,
      summary: 'Month by month, at 8–12 hours a week.',
      body: `
A realistic plan if you're starting with no quant background. Adjust the pace to your time.

| Months | Maths | Coding | Quant and markets | Output |
|---|---|---|---|---|
| **1–2** | Algebra refresher; probability basics (Stat 110 first lectures) | Python basics; daily small exercises | This course: Start here + Markets | A notebook computing returns, volatility and drawdowns for 5 stocks |
| **3–4** | Probability: distributions, conditional probability, expected value; daily puzzles | NumPy, pandas, plotting; first LeetCode easies | Backtesting lesson; FinHub BACKTEST experiments | **Project 1**: your own backtester with costs and next-bar fills |
| **5–6** | Statistics: estimation, testing, regression | Tests, Git, a clean GitHub | Portfolios and risk; factors | Project 1 with walk-forward and an honest write-up |
| **7–8** | Linear algebra (MIT 18.06) | Data structures and algorithms: 100+ problems | Options; FinHub OPT | **Project 2**: options pricer (tree + Black–Scholes + Monte Carlo) or a factor replication |
| **9–10** | Calculus and optimisation; random walks | C++ basics (if aiming at dev/trading) | Microstructure; FinHub SIM | **Project 3 (dev/trading)**: order book in C++ |
| **11–12** | Interview puzzle books; mental maths daily | Timed online assessments | Applications; competitions | CV, applications, mock interviews |

## Every day (15 minutes)

- 10 minutes of [Zetamac](https://arithmetic.zetamac.com).
- One probability puzzle or one coding problem.

## How you'll know you're ready

- You can explain your projects' results and weaknesses without notes.
- You solve most easy and many medium coding problems in time.
- Probability puzzles feel like patterns you've seen before.

> Mark this lesson complete and come back to it monthly: tick off what you've done and adjust the plan.
`,
      quiz: [
        { q: 'Which habit does this plan ask you to keep every day?', options: ['Reading market news for an hour', 'Ten minutes of mental arithmetic plus one puzzle or coding problem', 'Day trading', 'Watching lectures at 2× speed'], answer: 1, why: 'Small daily practice compounds and builds exactly the skills that interviews screen for.' },
      ],
    },
  ],
}
