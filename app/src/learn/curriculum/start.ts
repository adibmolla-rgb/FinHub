import type { Track } from '../types'

export const start: Track = {
  id: 'start',
  title: 'Start here',
  description: 'What quant finance is, the jobs inside it, and how to use this course.',
  access: 'free',
  lessons: [
    {
      id: 'start-what-is-quant',
      title: 'What is quant finance?',
      minutes: 10,
      summary: 'Using maths, statistics and code to make financial decisions.',
      body: `
**Quantitative finance** ("quant") is using mathematics, statistics and computer code to make financial
decisions that are too many, too fast or too complicated to make by gut feeling.

A useful way to see the whole field is as four questions. Every quant job specialises in one or two:

| Question | Example | Who owns it |
|---|---|---|
| **What is this worth?** | The fair price of an option on Apple shares | Derivatives quants, traders |
| **What will it probably do?** | Will this stock beat its sector next week? | Quant researchers |
| **How should I trade it?** | Buy £50m of shares without pushing the price up | Execution quants, quant developers |
| **How badly could it go wrong?** | The loss on a bad day, 1 in 100 | Risk quants |

## Why maths, statistics and code?

- **Prices are uncertain**, so you need **probability** to describe what might happen.
- **Data is noisy**, so you need **statistics** to tell a real pattern from luck. This is the hardest
  and most important skill in the field.
- **Markets are electronic and fast.** Most trading is done by programs, so ideas only matter once they
  are **code** that runs correctly on real data.
- **Finance** tells you which questions are worth asking and what the rules are (fees, short-selling,
  liquidity).

Remove any one of these and it fails: a brilliant model with a bug loses money; perfect code with a
fake pattern also loses money, just more slowly.

## How quant differs from "normal" finance

- A traditional stock picker studies a few companies deeply and uses judgement.
- A quant studies **many** things at once with data and models, and treats judgement as something to
  **test**.
- Investment banking (mergers, raising money for companies) uses almost no statistics; it is a
  different career, even though it sits in the same banks.

## What a quant actually does all day

Mostly: get data, clean it, form a hypothesis, test it carefully, find out it doesn't work (most ideas
don't), fix bugs, and occasionally find something small but real. It is closer to science than to
the trading floors in films.

> You don't need to be a genius. You need solid probability and statistics, real coding ability, and the
> discipline not to fool yourself. All three can be learned, and this course shows you how.
`,
      quiz: [
        {
          q: 'Which skill is described as the hardest and most important in quant finance?',
          options: ['Predicting the news', 'Telling a real pattern from luck (statistics)', 'Speed-reading financial reports', 'Knowing every company'],
          answer: 1,
          why: 'Data is noisy and it is easy to find patterns that are pure chance. Statistics, and the discipline to use it honestly, separates real edges from luck.',
        },
        {
          q: '"What is the loss on a bad day, 1 in 100?" is a question for which kind of quant?',
          options: ['Risk', 'Execution', 'Derivatives pricing', 'None, it is accounting'],
          answer: 0,
          why: 'Measuring how badly things could go wrong is risk management. In FinHub, RISK answers exactly this with Value at Risk.',
        },
      ],
      tryIt: [{ command: 'RISK SPY 60 TLT 40', label: 'See a risk quant’s tools: RISK' }],
    },
    {
      id: 'start-jobs',
      title: 'The jobs: who does what',
      minutes: 15,
      summary: 'Trader, researcher, developer, risk, strats, asset management.',
      body: `
"Quant" is at least six different jobs. They hire on different evidence, so know which you are aiming at.

| Role | What they do | What interviews test | Typical background |
|---|---|---|---|
| **Quant trader** | Prices and trades in real time; manages risk on the fly | Probability puzzles, mental maths, expected value, games | Strong maths/CS/physics/engineering graduates |
| **Quant researcher** | Finds predictive signals in data with statistics and ML | Statistics, probability, ML, research projects | Often Master's or PhD in a quantitative subject |
| **Quant developer** | Builds the trading and research systems | Coding (C++/Python), data structures and algorithms, systems | Computer science graduates |
| **Risk / model validation** | Measures risk; checks that models are right | Statistics, finance, regulation | Maths, statistics, finance; often a Master's |
| **Strats / derivatives quant** (banks) | Prices complex products, builds pricing libraries | Stochastic calculus, numerical methods, coding | Maths/physics; often Master's or PhD |
| **Quant asset management** | Builds systematic portfolios (factors, risk) | Statistics, portfolio theory, coding | Mixed; Master's common |

## Where they work

- **Proprietary trading firms** trade their own money, often as market makers. Examples: Jane Street,
  Optiver, IMC, Citadel Securities, Hudson River Trading, Jump Trading, SIG.
- **Hedge funds** manage investors' money with systematic strategies. Examples: Two Sigma, D. E. Shaw,
  Renaissance Technologies, G-Research, Man Group, Citadel.
- **Investment banks** have quant teams in trading, pricing and risk ("strats", "QR").
- **Asset managers** run systematic and factor funds.
- **Exchanges, data and fintech companies** need quant developers and data scientists too.

## Which is realistic for you?

- **From a Computer Science degree:** quant developer is the most direct route; trading is possible if
  you get very good at probability and mental maths; research usually wants a further degree.
- **From maths, physics or statistics:** trading and research are natural; learn to code properly.
- **From economics or finance:** risk, quant asset management and data roles are realistic; build up
  maths and coding.

> Pick a target role early (you can change later). It decides what you should practise: puzzles and
> mental maths for trading, coding and algorithms for development, statistics and research for research.
`,
      quiz: [
        {
          q: 'Which role mostly tests coding, data structures and algorithms?',
          options: ['Quant trader', 'Quant developer', 'Model validation', 'Strats'],
          answer: 1,
          why: 'Quant developers build the systems. Their interviews look like strong software-engineering interviews, often with C++ and performance questions.',
        },
        {
          q: 'A proprietary trading firm…',
          options: ['Advises companies on mergers', 'Trades its own money', 'Only manages pension funds', 'Is a type of exchange'],
          answer: 1,
          why: 'Prop firms trade their own capital, often as market makers. Hedge funds trade investors’ money.',
        },
      ],
    },
    {
      id: 'start-roadmap',
      title: 'Your roadmap through this course',
      minutes: 8,
      summary: 'What to learn, in what order, and how long it takes.',
      body: `
This course goes in the order that works best from zero. Each lesson ends with a short quiz and,
where possible, a **Try it** button that opens the matching FinHub tool so you can see the idea working.

## The order

1. **Markets and trading** (this course's next track): what you are modelling. About a week.
2. **Maths**: probability first, then statistics, linear algebra, calculus. The biggest block: 2–4 months
   alongside everything else.
3. **Coding**: Python straight away, in parallel with the maths. C++ later if you aim at development or
   trading firms.
4. **Quant methods**: backtesting, portfolios, options, market making. Uses the maths and code.
5. **Getting in**: projects, competitions, interview practice, applications.

## How much time?

Starting from nothing, about **8–12 hours a week for a year** gets you to the point where you can
build serious projects and pass early interview rounds for junior roles. More time, faster. A
12-month plan is in the last track.

## How to study

- **Do, don't just read.** After each maths topic, solve problems. After each coding lesson, write code.
- **Use FinHub as your lab.** Every concept here has a tool you can try: change the inputs and watch
  what happens.
- **Practise a little every day.** Ten minutes of mental arithmetic or probability puzzles daily beats
  three hours once a week.
- **Keep a log** of what you learned and built. It becomes your CV and your interview stories.

> Mark lessons complete as you go; your progress is saved on this computer.
`,
      quiz: [
        {
          q: 'What does this course suggest learning first in maths?',
          options: ['Stochastic calculus', 'Probability', 'Measure theory', 'Differential geometry'],
          answer: 1,
          why: 'Probability is tested in almost every quant interview and underpins everything else. Advanced topics only make sense once probability is solid.',
        },
      ],
    },
  ],
}
