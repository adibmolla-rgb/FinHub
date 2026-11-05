import { useEffect, useState } from 'react'
import { BACKEND_URL } from './api'

type Config = { command: string; exists: boolean; claude_desktop: unknown; claude_code: string }

function Copy({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      className="chip"
      onClick={() => navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500) }, () => {})}
    >
      {done ? 'Copied' : 'Copy'}
    </button>
  )
}

/** Shows how to plug FinHub into Claude Desktop, Claude Code or any MCP client on this computer. */
export function McpPanel() {
  const [cfg, setCfg] = useState<Config | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    fetch(`${BACKEND_URL}/mcp/config`).then((r) => r.json()).then(setCfg, (e) => setErr(String(e)))
  }, [])
  if (err) return <p className="bad">{err}</p>
  if (!cfg) return <p className="muted">Loading…</p>
  const desktop = JSON.stringify(cfg.claude_desktop, null, 2)
  return (
    <div className="stack">
      <p>
        FinHub can be used as a tool by AI assistants through the Model Context Protocol (MCP). They get quotes and history,
        FinHub’s backtester (with its look-ahead check, walk-forward and deflated Sharpe), portfolio risk and option pricing,
        including FinHub’s data sources and warnings. Every tool is read-only.
      </p>
      <h3 className="subhead">Claude Desktop</h3>
      <p className="muted small">Settings → Developer → Edit Config, add this to <code>claude_desktop_config.json</code>, then restart Claude Desktop:</p>
      <div className="codebox"><pre>{desktop}</pre><Copy text={desktop} /></div>
      <h3 className="subhead">Claude Code</h3>
      <div className="codebox"><pre>{cfg.claude_code}</pre><Copy text={cfg.claude_code} /></div>
      <h3 className="subhead">Any other MCP client</h3>
      <p className="muted small">Run this program over stdio: <code>{cfg.command}</code> {cfg.exists ? <span className="ok">(found)</span> : <span className="warn">(not found yet: it appears after FinHub finishes its first-launch setup)</span>}</p>
      <p className="muted small">Keep FinHub open while the assistant uses it: data, backtest and risk tools run through the app. Option pricing works even when FinHub is closed.</p>
    </div>
  )
}
