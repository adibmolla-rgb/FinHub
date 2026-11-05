// Command bar: everything in FinHub can be driven from the keyboard.

export type PanelId = 'SYS' | 'HELP' | 'RCPT' | 'LOG'

export type CommandResult =
  | { kind: 'open'; panel: PanelId; message: string }
  | { kind: 'clear'; message: string }
  | { kind: 'refresh'; message: string }
  | { kind: 'error'; message: string }

export const COMMANDS: { name: string; usage: string; description: string; status: 'ready' | 'planned' }[] = [
  { name: 'HELP', usage: 'HELP', description: 'List every command', status: 'ready' },
  { name: 'SYS', usage: 'SYS', description: 'Backend and engine status', status: 'ready' },
  { name: 'RCPT', usage: 'RCPT', description: 'How a number’s receipt works', status: 'ready' },
  { name: 'REFRESH', usage: 'REFRESH', description: 'Re-check backend and engines', status: 'ready' },
  { name: 'CLEAR', usage: 'CLEAR', description: 'Clear the activity log', status: 'ready' },
  { name: '<TICKER>', usage: 'AAPL', description: 'Quote, chart and fundamentals for a ticker', status: 'planned' },
  { name: 'ASK', usage: 'ASK is NVDA momentum still working after costs?', description: 'Reasoning agent with a visible plan, data and code', status: 'planned' },
  { name: 'BT', usage: 'BT SPY sma 20 50', description: 'Backtest with costs and validation warnings', status: 'planned' },
  { name: 'DEBATE', usage: 'DEBATE TSLA', description: 'Bull vs bear agent committee', status: 'planned' },
  { name: 'SIM', usage: 'SIM start', description: 'Simulated exchange with trading bots', status: 'planned' },
]

const PANELS: PanelId[] = ['SYS', 'HELP', 'RCPT', 'LOG']

export function runCommand(input: string): CommandResult {
  const text = input.trim()
  if (!text) return { kind: 'error', message: 'Type a command, or HELP to list them.' }
  const [head] = text.split(/\s+/)
  const word = head.toUpperCase()

  if ((PANELS as string[]).includes(word)) {
    return { kind: 'open', panel: word as PanelId, message: `Opened ${word}` }
  }
  if (word === 'CLEAR') return { kind: 'clear', message: 'Log cleared' }
  if (word === 'REFRESH') return { kind: 'refresh', message: 'Re-checking backend and engines…' }

  const planned = COMMANDS.find((c) => c.status === 'planned' && c.name === word)
  if (planned) return { kind: 'error', message: `${word} is planned but not built yet: ${planned.description}.` }
  if (/^[A-Z.\-^]{1,10}$/.test(word)) {
    return { kind: 'error', message: `Ticker views arrive with the data engine (next step). Got “${word}”.` }
  }
  return { kind: 'error', message: `Unknown command “${head}”. Type HELP.` }
}
