# FinHub

An open-source market research terminal that runs as a desktop app (and later as a website). It
brings a data platform, an AI reasoning agent, analytics and a simulated exchange together in one
keyboard-driven workspace, and it shows where every number comes from.

> Status: **v0.1, foundation.** The app shell, backend, engine management and receipts layer work.
> Market data, the reasoning agent, analytics panels and the simulator are the next milestones.

![FinHub v0.1](docs/screenshot.png)

## Why

Open-source terminals tend to fail in the same ways: they won't install, they need an account, their
data sources break silently, their numbers are sometimes wrong with nothing to catch it, and their AI
agents are black boxes. FinHub is built around fixing those:

| Problem | FinHub's answer |
|---|---|
| Install and launch failures | Every engine runs in its own isolated environment; a broken engine is reported, not fatal. Installers are built and tested in CI on macOS, Windows and Linux. |
| Forced accounts | None. Bring your own data and LLM keys. |
| Silently wrong numbers | **Receipts.** Every value carries its unit, source, fetch time and formula. Values in different units (percent vs fraction) cannot be added without an explicit conversion. |
| Black-box AI | The agent's plan, data, code and validation are shown step by step and saved. *(planned)* |

## How it fits together

```
app/                    Desktop app: Tauri 2 shell + React/TypeScript interface
  src-tauri/            Starts the backend on launch, stops it on exit
backend/                Local API (FastAPI, 127.0.0.1:8765): receipts, engine registry
engines/openbb/         Isolated env: OpenBB (market, fundamental, macro, news data)
engines/vibe-trading/   Isolated env: Vibe-Trading (reasoning agent, backtests, options, debates)
```

The backend never imports an engine. Engines pin conflicting dependencies (OpenBB 5 needs
`fastmcp>=4`, Vibe-Trading needs `fastmcp<4`), so each lives in its own environment and runs as a
separate process. If the app is closed, crashes or is force-quit, the backend shuts itself down.

## Run it

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+ with pnpm, Rust, and on Linux the
[Tauri system libraries](https://v2.tauri.app/start/prerequisites/).

```bash
cd backend && uv sync && cd ..
cd engines/openbb && uv sync && cd ../..          # optional, ~220 packages
cd engines/vibe-trading && uv sync && cd ../..    # optional, ~190 packages
cd app && pnpm install && pnpm tauri dev
```

To work on the interface in a browser instead: run `uv run finhub-backend` in `backend/` and
`pnpm dev` in `app/`, then open http://127.0.0.1:1420.

Keyboard: `Ctrl/Cmd+K` or `/` focuses the command bar, `↑`/`↓` walk command history. Type `HELP`.

## Roadmap

1. **Foundation** ✅ App shell, self-starting backend, engine registry, receipts, CI.
2. **Data and charts.** OpenBB behind the receipts layer; ticker, chart, fundamentals and news panels; data-source health and fallback.
3. **Reasoning agent.** Vibe-Trading embedded; `ASK`, `BT` and `DEBATE` with a visible plan, data, code and validation; saved research notes.
4. **Analytics panels.** Options, portfolio risk, screener, valuation.
5. **Market simulator.** Our own exchange (order book, matching engine) with trading bots, plus an MCP server so outside AI agents can trade in it.
6. **Polish.** Dockable layouts, a self-managed Python runtime so users install nothing else, signed installers, a web demo.

## Licence

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for third-party credits.
