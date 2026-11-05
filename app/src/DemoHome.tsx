import { DOWNLOAD_URL } from './demo'
import { Panel } from './components'

export function DemoHome({ onRun }: { onRun: (command: string) => void }) {
  return (
    <main className="grid grid--single">
      <Panel code="FINHUB" title="FinHub web demo" className="grid__single">
        <div className="stack demo">
          <p>
            FinHub is an open-source market research terminal for your desktop. This web demo runs the parts that need no
            server, entirely in your browser:
          </p>
          <ul>
            <li><button className="link" onClick={() => onRun('LEARN')}>LEARN</button>: a free course that teaches quantitative finance from zero. What quants do, how markets and trading work, the maths, Python and C++, backtesting, risk and options, and how to get a job in the industry, with quizzes and links into the tools below.</li>
            <li><button className="link" onClick={() => onRun('OPT')}>OPT</button>: options lab. Black–Scholes, binomial tree and Monte Carlo side by side, Greeks, implied volatility and a strategy builder with payoff diagrams.</li>
            <li><button className="link" onClick={() => onRun('SIM')}>SIM</button>: a simulated exchange. Trade against a market maker, noise, momentum, mean-reversion and informed bots; trigger news, a flash crash or a liquidity drain; see your profit split into spread earned and adverse selection.</li>
          </ul>
          <p>
            The desktop app adds live market data with a receipt behind every number, fundamentals, macro data, a backtester
            with look-ahead checks, walk-forward testing and the deflated Sharpe ratio, portfolio risk, a screener, alerts,
            an AI research agent, and an arena where AI agents trade through MCP.
          </p>
          <p><a className="btn btn--buy demo__cta" href={DOWNLOAD_URL} target="_blank" rel="noreferrer">Download FinHub for Windows, macOS or Linux</a></p>
          <p className="muted small">Free and open source (Apache 2.0). No account needed.</p>
        </div>
      </Panel>
    </main>
  )
}
