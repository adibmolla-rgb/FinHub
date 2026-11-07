// Command bar: everything in FinHub can be driven from the keyboard.

import { RANGES, type AlertKind, type AskKind, type PortfolioSide, type Range } from './api'
import type { ResearchView } from './Research'

export type PanelId = 'SYS' | 'HELP' | 'WATCH' | 'LOG'

export type PortfolioEntry = { symbol: string; side: PortfolioSide; quantity: number; price?: number; fees?: number; date?: string }

export type CommandResult =
  | { kind: 'open'; panel: PanelId; message: string }
  | { kind: 'ticker'; symbol: string; range?: Range; message: string }
  | { kind: 'range'; range: Range; message: string }
  | { kind: 'home'; message: string }
  | { kind: 'agent'; ask: AskKind; text: string; message: string }
  | { kind: 'ai'; message: string }
  | { kind: 'sim'; message: string }
  | { kind: 'opt'; symbol?: string; message: string }
  | { kind: 'watch'; add?: string; remove?: string; message: string }
  | { kind: 'notes'; message: string }
  | { kind: 'rcpt'; message: string }
  | { kind: 'mcp'; message: string }
  | { kind: 'fa'; symbol: string; message: string }
  | { kind: 'cmp'; symbols: string[]; message: string }
  | { kind: 'arena'; message: string }
  | { kind: 'learn'; message: string }
  | { kind: 'macro'; country: string; message: string }
  | { kind: 'research'; view: ResearchView; message: string }
  | { kind: 'portfolio'; add?: PortfolioEntry; message: string }
  | { kind: 'screen'; message: string }
  | { kind: 'alerts'; add?: { symbol: string; kind: AlertKind; threshold: number }; message: string }
  | { kind: 'risk'; holdings: { symbol: string; weight: number }[]; message: string }
  | { kind: 'backtest'; symbol?: string; strategy?: string; params?: number[]; message: string }
  | { kind: 'clear'; message: string }
  | { kind: 'refresh'; message: string }
  | { kind: 'error'; message: string }

export const COMMANDS: { name: string; usage: string; description: string; status: 'ready' | 'planned' }[] = [
  { name: 'LEARN', usage: 'LEARN', description: 'Course: learn quant finance from zero (markets, maths, coding, methods, getting a job)', status: 'ready' },
  { name: '<TICKER>', usage: 'AAPL', description: 'Quote, chart, profile and news for a ticker', status: 'ready' },
  { name: 'EQ', usage: 'EQ MSFT 5Y', description: 'Same, with a chart range (1M 3M 6M 1Y 5Y MAX)', status: 'ready' },
  { name: 'MACRO', usage: 'MACRO GB', description: 'OECD inflation, unemployment, interest rates and GDP for a country (default US)', status: 'ready' },
  { name: 'PORT', usage: 'PORT BUY AAPL 10 150', description: 'Your own holdings at live prices: cost basis, profit and weights (also SELL and SPLIT)', status: 'ready' },
  { name: 'OWN', usage: 'OWN AAPL', description: 'Insider trades, largest institutional holders and short interest', status: 'ready' },
  { name: 'CHAIN', usage: 'CHAIN AAPL', description: 'Live options chain and volatility smile; add a date for one expiration', status: 'ready' },
  { name: 'CAL', usage: 'CAL 14', description: 'Upcoming earnings and economic events (next 7 days, or up to 31)', status: 'ready' },
  { name: 'FILINGS', usage: 'FILINGS AAPL', description: 'Latest SEC filings with links to the documents', status: 'ready' },
  { name: 'ETF', usage: 'ETF SPY', description: 'An ETF’s largest holdings and their weights', status: 'ready' },
  { name: 'CURVE', usage: 'CURVE', description: 'US Treasury yield curve, with spreads and comparisons a month and a year back', status: 'ready' },
  { name: 'SCREEN', usage: 'SCREEN', description: 'Screen large caps, your watchlist or any tickers by price, move, size and 52-week range', status: 'ready' },
  { name: 'CMP', usage: 'CMP AAPL MSFT NVDA', description: 'Compare performance, risk and correlation of up to 8 tickers', status: 'ready' },
  { name: 'FA', usage: 'FA AAPL', description: 'Financial statements and key ratios, each ratio with a receipt', status: 'ready' },
  { name: 'RANGE', usage: '6M', description: 'Change the chart range of the open ticker', status: 'ready' },
  { name: 'HOME', usage: 'HOME', description: 'Back to the home workspace', status: 'ready' },
  { name: 'SYS', usage: 'SYS', description: 'Backend, engines and data-source health', status: 'ready' },
  { name: 'RCPT', usage: 'RCPT', description: 'How a number’s receipt works', status: 'ready' },
  { name: 'ALERT', usage: 'ALERT AAPL > 200', description: 'Price alert (> or < a price, or +5% / -5% day move); ALERTS lists them', status: 'ready' },
  { name: 'W', usage: 'W NVDA  ·  W -NVDA', description: 'Add to / remove from the watchlist on the home screen', status: 'ready' },
  { name: 'NOTES', usage: 'NOTES', description: 'Past ASK / BT / DEBATE runs with answers and traces', status: 'ready' },
  { name: 'REFRESH', usage: 'REFRESH', description: 'Reload the current view and re-check engines', status: 'ready' },
  { name: 'CLEAR', usage: 'CLEAR', description: 'Clear the activity log', status: 'ready' },
  { name: 'HELP', usage: 'HELP', description: 'List every command', status: 'ready' },
  { name: 'ASK', usage: 'ASK is NVDA momentum still working after costs?', description: 'Reasoning agent with a visible trace of every tool it uses', status: 'ready' },
  { name: 'BT', usage: 'BT SPY 20/50 day moving-average crossover', description: 'Agent backtest with costs, buy-and-hold comparison and validation warnings', status: 'ready' },
  { name: 'DEBATE', usage: 'DEBATE TSLA', description: 'Bull case, bear case and a neutral judge', status: 'ready' },
  { name: 'MCP', usage: 'MCP', description: 'Use FinHub from Claude Desktop, Claude Code or other AI assistants', status: 'ready' },
  { name: 'AI', usage: 'AI', description: 'Choose the AI provider (Claude, OpenAI or local Ollama) and key', status: 'ready' },
  { name: 'BACKTEST', usage: 'BACKTEST SPY sma 20 50', description: 'FinHub backtester: costs, next-bar fills, walk-forward, deflated Sharpe (also momentum 126, meanrev 20 2)', status: 'ready' },
  { name: 'RISK', usage: 'RISK SPY 60 TLT 30 GLD 10', description: 'Portfolio VaR/ES three ways, VaR backtest, correlations, risk contributions, optimal weights', status: 'ready' },
  { name: 'OPT', usage: 'OPT AAPL', description: 'Options lab: price three ways, Greeks, implied vol, strategy payoffs', status: 'ready' },
  { name: 'ARENA', usage: 'ARENA', description: 'Shared simulated market where AI agents trade (via MCP); watch or join', status: 'ready' },
  { name: 'SIM', usage: 'SIM', description: 'Simulated exchange: trade against bots, trigger news and crashes', status: 'ready' },
]

const PANELS: PanelId[] = ['SYS', 'HELP', 'LOG'] // WATCH is handled by the W command (it takes arguments)
const RESERVED = new Set(['HOME', 'CLEAR', 'REFRESH', 'EQ', 'RANGE', 'AI', 'SETTINGS', 'SIM', 'OPT', 'BACKTEST', 'RISK', 'W', 'WATCH', 'NOTES', 'RCPT', 'MCP', 'FA', 'CMP', 'ARENA', 'LEARN', 'COURSE', 'MACRO', 'ALERT', 'ALERTS', 'SCREEN', ...PANELS, ...COMMANDS.map((c) => c.name)])
const SYMBOL = /^\^?[A-Z0-9][A-Z0-9.\-^=]{0,14}$/ // a leading ^ marks an index, e.g. ^GSPC

function asRange(word: string | undefined): Range | undefined {
  const w = word?.toUpperCase()
  return (RANGES as readonly string[]).includes(w ?? '') ? (w as Range) : undefined
}

export function runCommand(input: string): CommandResult {
  const text = input.trim()
  if (!text) return { kind: 'error', message: 'Type a command, or HELP to list them.' }
  const words = text.split(/\s+/)
  const word = words[0].toUpperCase()

  if ((PANELS as string[]).includes(word)) return { kind: 'open', panel: word as PanelId, message: `Opened ${word}` }
  if (word === 'HOME') return { kind: 'home', message: 'Home workspace' }
  if (word === 'CLEAR') return { kind: 'clear', message: 'Log cleared' }
  if (word === 'REFRESH') return { kind: 'refresh', message: 'Reloading…' }

  const bareRange = asRange(word)
  if (bareRange) return { kind: 'range', range: bareRange, message: `Chart range ${bareRange}` }
  if (word === 'RANGE') {
    const r = asRange(words[1])
    return r ? { kind: 'range', range: r, message: `Chart range ${r}` } : { kind: 'error', message: `RANGE needs one of ${RANGES.join(' ')}` }
  }

  if (word === 'EQ') {
    const sym = words[1]?.toUpperCase()
    if (!sym || !SYMBOL.test(sym)) return { kind: 'error', message: 'EQ needs a ticker, e.g. EQ AAPL' }
    return { kind: 'ticker', symbol: sym, range: asRange(words[2]), message: `Loading ${sym}…` }
  }

  if (word === 'SIM') return { kind: 'sim', message: 'Market simulator' }
  if (word === 'NOTES') return { kind: 'notes', message: 'Research history' }
  if (word === 'ARENA') return { kind: 'arena', message: 'Agent arena' }
  if (word === 'LEARN' || word === 'COURSE') return { kind: 'learn', message: 'Learn quant finance' }
  if (word === 'ALERTS') return { kind: 'alerts', message: 'Alerts' }
  if (word === 'SCREEN') return { kind: 'screen', message: 'Screener' }
  if (word === 'ALERT') {
    const m = text.match(/^ALERT\s+([A-Za-z0-9.\-^=]{1,15})\s*(>|<|\+|-)\s*([0-9]*\.?[0-9]+)\s*(%)?\s*$/i)
    if (!m) return { kind: 'error', message: 'Usage: ALERT AAPL > 200, ALERT AAPL < 150, ALERT NVDA +5% or ALERT NVDA -5%' }
    const [, sym, op, num, pctSign] = m
    const value = parseFloat(num)
    const isMove = op === '+' || op === '-'
    if (isMove && !pctSign) return { kind: 'error', message: 'Day-move alerts need a %, e.g. ALERT NVDA +5%' }
    if (!isMove && pctSign) return { kind: 'error', message: 'Use > or < with a price, or +/- with a %' }
    const kind: AlertKind = op === '>' ? 'above' : op === '<' ? 'below' : op === '+' ? 'move_up' : 'move_down'
    const threshold = isMove ? value / 100 : value
    return { kind: 'alerts', add: { symbol: sym.toUpperCase(), kind, threshold }, message: `Alert: ${sym.toUpperCase()} ${op}${num}${pctSign ?? ''}` }
  }
  if (word === 'MACRO') {
    const country = words.slice(1).join(' ') || 'US'
    if (!/^[A-Za-z _-]{2,40}$/.test(country)) return { kind: 'error', message: 'Usage: MACRO GB (or MACRO united kingdom)' }
    return { kind: 'macro', country, message: `Macro: ${country}` }
  }
  if (word === 'PORT') {
    if (words.length === 1) return { kind: 'portfolio', message: 'Portfolio' }
    const usage = 'Usage: PORT BUY AAPL 10 150, PORT SELL AAPL 5 180 (then optionally a date and fee=1.50), or PORT SPLIT NVDA 10'
    const side = words[1].toLowerCase()
    const sym = words[2]?.toUpperCase()
    const quantity = Number(words[3])
    if (!['buy', 'sell', 'split'].includes(side) || !sym || !SYMBOL.test(sym) || !(quantity > 0) || !Number.isFinite(quantity)) return { kind: 'error', message: usage }
    const entry: PortfolioEntry = { symbol: sym, side: side as PortfolioSide, quantity }
    let rest = words.slice(4)
    if (side !== 'split') {
      entry.price = Number(rest[0])
      if (rest[0] === undefined || !(entry.price >= 0) || !Number.isFinite(entry.price)) return { kind: 'error', message: usage }
      rest = rest.slice(1)
    }
    for (const word of rest) {
      const fee = word.match(/^fee=([0-9]*\.?[0-9]+)$/i)
      if (/^\d{4}-\d{2}-\d{2}$/.test(word) && !entry.date) entry.date = word
      else if (fee && side !== 'split' && entry.fees === undefined) entry.fees = Number(fee[1])
      else return { kind: 'error', message: usage }
    }
    const what = side === 'split' ? `split ${sym} ${quantity}-for-1` : `${side} ${quantity} ${sym} at ${entry.price}`
    return { kind: 'portfolio', add: entry, message: `Recorded: ${what}` }
  }
  if (word === 'OWN' || word === 'FILINGS' || word === 'ETF') {
    const sym = words[1]?.toUpperCase()
    if (!sym || !SYMBOL.test(sym)) return { kind: 'error', message: `Usage: ${word} ${word === 'ETF' ? 'SPY' : 'AAPL'}` }
    const view = word === 'OWN' ? 'own' : word === 'ETF' ? 'etf' : 'filings'
    return { kind: 'research', view: { view, symbol: sym }, message: `${word} ${sym}` }
  }
  if (word === 'CHAIN') {
    const sym = words[1]?.toUpperCase()
    const expiration = words[2]
    if (!sym || !SYMBOL.test(sym) || (expiration && !/^\d{4}-\d{2}-\d{2}$/.test(expiration))) return { kind: 'error', message: 'Usage: CHAIN AAPL or CHAIN AAPL 2027-01-15' }
    return { kind: 'research', view: { view: 'chain', symbol: sym, expiration }, message: `Options chain for ${sym}` }
  }
  if (word === 'CAL') {
    const days = words[1] === undefined ? 7 : Number(words[1])
    if (!Number.isInteger(days) || days < 1 || days > 31) return { kind: 'error', message: 'Usage: CAL or CAL 14 (1 to 31 days ahead)' }
    return { kind: 'research', view: { view: 'cal', days }, message: `Calendar: next ${days} days` }
  }
  if (word === 'CURVE') return { kind: 'research', view: { view: 'curve' }, message: 'US Treasury yield curve' }
  if (word === 'RCPT') return { kind: 'rcpt', message: 'Receipts' }
  if (word === 'MCP') return { kind: 'mcp', message: 'Connect AI assistants' }
  if (word === 'CMP') {
    const syms = [...new Set(words.slice(1).map((w) => w.toUpperCase()))]
    if (syms.length < 2 || syms.length > 8 || !syms.every((x) => SYMBOL.test(x))) return { kind: 'error', message: 'Usage: CMP AAPL MSFT NVDA (2 to 8 tickers)' }
    return { kind: 'cmp', symbols: syms, message: `Compare ${syms.join(', ')}` }
  }
  if (word === 'FA') {
    const sym = words[1]?.toUpperCase()
    if (!sym || !SYMBOL.test(sym)) return { kind: 'error', message: 'Usage: FA AAPL' }
    return { kind: 'fa', symbol: sym, message: `Fundamentals for ${sym}` }
  }
  if (word === 'W' || word === 'WATCH') {
    const arg = words[1]?.toUpperCase()
    if (!arg) return { kind: 'watch', message: 'Watchlist' }
    const remove = arg.startsWith('-')
    const sym = remove ? arg.slice(1) : arg
    if (!SYMBOL.test(sym)) return { kind: 'error', message: 'Usage: W NVDA to add, W -NVDA to remove' }
    return remove ? { kind: 'watch', remove: sym, message: `Removed ${sym} from the watchlist` } : { kind: 'watch', add: sym, message: `Added ${sym} to the watchlist` }
  }
  if (word === 'RISK') {
    const rest = words.slice(1)
    const holdings: { symbol: string; weight: number }[] = []
    for (let i = 0; i < rest.length; i += 2) {
      const sym = rest[i].toUpperCase()
      const w = parseFloat(rest[i + 1])
      if (!SYMBOL.test(sym) || !(w > 0)) return { kind: 'error', message: 'Usage: RISK SPY 60 TLT 30 GLD 10 (ticker then weight)' }
      holdings.push({ symbol: sym, weight: w })
    }
    return { kind: 'risk', holdings, message: holdings.length ? `Risk: ${holdings.map((h) => h.symbol).join(', ')}` : 'Portfolio risk' }
  }
  if (word === 'BACKTEST') {
    const sym = words[1]?.toUpperCase()
    if (sym && !SYMBOL.test(sym)) return { kind: 'error', message: 'Usage: BACKTEST SPY sma 20 50' }
    const strategy = words[2]?.toLowerCase()
    if (strategy && !['sma', 'momentum', 'meanrev'].includes(strategy)) return { kind: 'error', message: 'Strategies: sma, momentum, meanrev' }
    const params = words.slice(3).map(Number)
    return { kind: 'backtest', symbol: sym, strategy, params, message: sym ? `Backtest ${sym}` : 'Backtester' }
  }
  if (word === 'OPT') {
    const sym = words[1]?.toUpperCase()
    if (sym && !SYMBOL.test(sym)) return { kind: 'error', message: 'OPT takes an optional ticker, e.g. OPT AAPL' }
    return { kind: 'opt', symbol: sym, message: sym ? `Options lab for ${sym}` : 'Options lab' }
  }
  if (word === 'AI' || word === 'SETTINGS') return { kind: 'ai', message: 'AI settings' }
  if (word === 'ASK' || word === 'BT' || word === 'DEBATE') {
    const rest = text.slice(words[0].length).trim()
    if (!rest) return { kind: 'error', message: `${word} needs something to work on, e.g. ${COMMANDS.find((c) => c.name === word)?.usage}` }
    return { kind: 'agent', ask: word.toLowerCase() as AskKind, text: rest, message: `${word}: ${rest}` }
  }

  const planned = COMMANDS.find((c) => c.status === 'planned' && c.name === word)
  if (planned) return { kind: 'error', message: `${word} is planned but not built yet: ${planned.description}.` }

  if (SYMBOL.test(word) && !RESERVED.has(word)) {
    return { kind: 'ticker', symbol: word, range: asRange(words[1]), message: `Loading ${word}…` }
  }
  return { kind: 'error', message: `Unknown command “${words[0]}”. Type HELP.` }
}

/** Commands matching what has been typed so far (by name), for the suggestion list under the bar. */
export function suggest(input: string, limit = 6): typeof COMMANDS {
  const word = input.trim().split(/\s+/)[0]?.toUpperCase() ?? ''
  if (!word || input.includes(' ')) return []
  const ready = COMMANDS.filter((c) => c.status === 'ready' && !c.name.startsWith('<'))
  const starts = ready.filter((c) => c.name.startsWith(word))
  const contains = ready.filter((c) => !c.name.startsWith(word) && c.description.toUpperCase().includes(word) && word.length >= 3)
  return [...starts, ...contains].slice(0, limit)
}
