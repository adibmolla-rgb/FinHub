// Command bar: everything in FinHub can be driven from the keyboard.

import { RANGES, type AskKind, type Range } from './api'

export type PanelId = 'SYS' | 'HELP' | 'RCPT' | 'LOG'

export type CommandResult =
  | { kind: 'open'; panel: PanelId; message: string }
  | { kind: 'ticker'; symbol: string; range?: Range; message: string }
  | { kind: 'range'; range: Range; message: string }
  | { kind: 'home'; message: string }
  | { kind: 'agent'; ask: AskKind; text: string; message: string }
  | { kind: 'ai'; message: string }
  | { kind: 'sim'; message: string }
  | { kind: 'clear'; message: string }
  | { kind: 'refresh'; message: string }
  | { kind: 'error'; message: string }

export const COMMANDS: { name: string; usage: string; description: string; status: 'ready' | 'planned' }[] = [
  { name: '<TICKER>', usage: 'AAPL', description: 'Quote, chart, profile and news for a ticker', status: 'ready' },
  { name: 'EQ', usage: 'EQ MSFT 5Y', description: 'Same, with a chart range (1M 3M 6M 1Y 5Y MAX)', status: 'ready' },
  { name: 'RANGE', usage: '6M', description: 'Change the chart range of the open ticker', status: 'ready' },
  { name: 'HOME', usage: 'HOME', description: 'Back to the home workspace', status: 'ready' },
  { name: 'SYS', usage: 'SYS', description: 'Backend, engines and data-source health', status: 'ready' },
  { name: 'RCPT', usage: 'RCPT', description: 'How a number’s receipt works', status: 'ready' },
  { name: 'REFRESH', usage: 'REFRESH', description: 'Reload the current view and re-check engines', status: 'ready' },
  { name: 'CLEAR', usage: 'CLEAR', description: 'Clear the activity log', status: 'ready' },
  { name: 'HELP', usage: 'HELP', description: 'List every command', status: 'ready' },
  { name: 'ASK', usage: 'ASK is NVDA momentum still working after costs?', description: 'Reasoning agent with a visible trace of every tool it uses', status: 'ready' },
  { name: 'BT', usage: 'BT SPY 20/50 day moving-average crossover', description: 'Agent backtest with costs, buy-and-hold comparison and validation warnings', status: 'ready' },
  { name: 'DEBATE', usage: 'DEBATE TSLA', description: 'Bull case, bear case and a neutral judge', status: 'ready' },
  { name: 'AI', usage: 'AI', description: 'Choose the AI provider (Claude, OpenAI or local Ollama) and key', status: 'ready' },
  { name: 'SIM', usage: 'SIM', description: 'Simulated exchange: trade against bots, trigger news and crashes', status: 'ready' },
]

const PANELS: PanelId[] = ['SYS', 'HELP', 'RCPT', 'LOG']
const RESERVED = new Set(['HOME', 'CLEAR', 'REFRESH', 'EQ', 'RANGE', 'AI', 'SETTINGS', 'SIM', ...PANELS, ...COMMANDS.map((c) => c.name)])
const SYMBOL = /^[A-Z0-9][A-Z0-9.\-^=]{0,14}$/

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
