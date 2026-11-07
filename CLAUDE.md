# CLAUDE.md: working on FinHub

Guidance for Claude Code (and people) changing this repository. For *using* FinHub from Claude, see
[docs/AI_ASSISTANTS.md](docs/AI_ASSISTANTS.md).

## What this is

FinHub is a desktop market research terminal: a Tauri 2 app (Rust shell + React/TypeScript UI) that
starts a local Python backend (FastAPI on `127.0.0.1:8765`), which in turn drives third-party engines
in their own Python environments. Core promise: every number has a **receipt** (unit, provider,
provider field, time, formula, inputs), and analytics are built to resist self-deception (next-bar
fills, look-ahead checks, walk-forward, deflated Sharpe, bootstrap error bars).

## Architecture

```
app/                           Tauri 2 + React 19 + TypeScript (Vite)
  src-tauri/src/lib.rs         Shell: first-launch Python setup with bundled uv (finhub-uv), starts and
                               stops the backend, exposes `backend_phase` to the UI. Debug builds use
                               the repo checkout; release builds use bundled sources in resources/python.
  scripts/stage-python.mjs     Copies backend + engine sources and uv into src-tauri/ before a build.
  src/App.tsx                  Workspaces, command dispatch, polling (health, engines, sources, alerts).
  src/commands.ts              Command parser + COMMANDS table (drives HELP and suggestions).
  src/api.ts                   Typed client for every backend endpoint; formatValue() renders receipts.
  src/Research.tsx             The six research panels.
  src/Portfolio.tsx            PORT.
  src/links.ts                 Sends external links to the browser; the webview drops them otherwise.
  src/quant/                   options.ts, indicators.ts, compare.ts (pure maths, unit-tested) and screens.
  src/sim/                     SIM: engine.ts (order book), market.ts (bots), Sim.tsx; Arena.tsx (ARENA UI).
  src/demo.ts                  Web-demo mode flags (pnpm build:web).
  src/learn/                   LEARN course: types.ts, parse.ts + markdown.tsx (Markdown subset), Learn.tsx,
                               curriculum/*.ts (one Track per file), index.ts (TRACKS order).
backend/src/finhub_backend/
  server.py                    All HTTP endpoints. Lifespan starts engine probes, data warm-up, alerts loop.
  receipts.py                  Quantity/Unit/Source. Unit-safe arithmetic; AS_REPORTED never converts.
  engines.py, installer.py     Engine registry, probes and installs (uv sync into app-data envs).
  worker_client.py             JSON-lines client for the long-lived data worker subprocess.
  market.py                    Quotes/history/profile/news → receipts; provider attempts and health.
  backtest.py, risk.py         numpy analytics (see the rules below).
  fundamentals.py, macro.py    Statement ratios and OECD series with receipts.
  portfolio.py                 PORT: the trade ledger, FIFO cost basis and valuation.
  research.py                  OWN, CHAIN, CAL, FILINGS, ETF and CURVE: raw rows to summaries with receipts.
  screener.py, alerts.py       Screener over an explicit universe; one-shot alerts + background loop.
  sim.py                       Python port of the simulator: the shared ARENA market.
  agent.py, store.py           Vibe-Trading agent process + settings; watchlist and saved agent runs.
  mcp_server.py                finhub-mcp (MCP SDK 2.x, stdio). Tools call the HTTP API.
engines/openbb/                Isolated env (OpenBB + Apache-licensed extensions + yfinance)
  worker.py, providers.py      Data worker: provider chains, JSON lines over stdin/stdout.
engines/vibe-trading/          Isolated env (Vibe-Trading[anthropic]); serve.py runs its API server.
```

Why engines are isolated: OpenBB 5 needs `fastmcp>=4`, Vibe-Trading needs `fastmcp<4`, and
Vibe-Trading installs generic top-level modules (`src`, `cli`). The backend never imports an engine;
it runs them as subprocesses that exit when their stdin closes.

## Commands

```bash
# Backend
cd backend && uv sync && uv run pytest -q            # 141 tests
uv run finhub-backend                                 # API on 127.0.0.1:8765
uv run finhub-mcp                                     # MCP server (stdio)

# Data worker
cd engines/openbb && uv sync && uv run pytest -q      # 36 tests (network-free)

# App
cd app && pnpm install
pnpm test        # vitest: 85 tests (maths, parser, course content, file-name clash check)
pnpm lint
pnpm build       # tsc + vite (also what CI's tauri build runs first)
pnpm build:web   # static web demo into dist-web/
pnpm tauri dev   # desktop app in development (needs the backend env synced)
```

**Before every commit run:** `uv run pytest -q` (backend), `pnpm test && pnpm lint && pnpm build`
(app). Running tests without `pnpm build` has let type errors through before.

CI (`.github/workflows/ci.yml`) runs backend tests, engine installs and desktop builds on Windows,
macOS and Linux, plus the web demo build. `release.yml` attaches installers to a published GitHub
Release; `pages.yml` (manual) publishes the web demo.

## Rules that prevent real bugs (each one has bitten this project)

1. **Units.** Store fractions (0.05 = 5%), never percent. Build values as `Quantity` with a `Unit`; never
   add values with different units. Compute changes and ratios from raw inputs rather than trusting
   provider percentages. If a provider doesn't declare a unit, use `Unit.AS_REPORTED` and never convert.
   OpenBB marks normalised percents with `x-frontend_multiply: 100` and spells the unit key both
   `x-unit_measurement` and `x-unit_measurment`.
2. **No module names that differ only by case or `.ts`/`.tsx`** (e.g. `options.ts` + `Options.tsx`).
   They collide on Windows/macOS and break the build there while passing on Linux. `src/names.test.ts`
   and a CI step enforce this.
3. **Next-bar fills.** In `backtest.simulate`, the position over return r[i] is `target[i-1]`. Costs are
   charged multiplicatively at the fill: `(1 - cost) * (1 + gross) - 1`.
4. **OpenBB calls run on one thread** (`on_obb_thread`): its provider locks are bound to an event loop.
5. **Simulator market maker** learns fair value from trade prices and signed order flow; it must not
   anchor on the last mid (its own skewed quotes → runaway drift). Track trades by id, not index (the
   trade log is trimmed). Keep ticks (ints) and display prices separate.
6. **Child processes on Windows** need `CREATE_NO_WINDOW` (`engines.NO_WINDOW`, `hidden()` in lib.rs).
7. **Claude 5-family models** reject non-default temperature; `agent.agent_env` sets 1 for them.
8. **Licences.** Only depend on Apache/MIT/BSD code. OpenBB's yfinance extension is AGPL: use the
   `yfinance` library directly. Never copy code from FinceptTerminal (AGPL, trademark).
9. **Missing data fails closed.** A failed quote never fires an alert; a screener row missing a
   filtered field is excluded; a ratio with a missing input is omitted; nothing is guessed.
10. **Never fake data in the UI.** Tests and screenshots may use synthetic data, clearly labelled.
11. **No worker during an engine install.** A package folder without its `__init__.py` yet imports as an
    empty namespace package, and that process keeps it for life. `installer` holds the worker during `uv sync`.
12. **The worker's child processes must not inherit its request pipe.** On Windows they hang while the worker
    blocks reading it, and OpenBB runs `git` as it loads. Test engine changes with a lone request as well as
    in the app, whose polling hides this kind of hang.
13. **Providers can answer a different question in the same shape.** Asked for a stock's ETF holdings, Nasdaq
    returns the funds that hold it. Check live output for wrong inputs too, not just right ones. Try the
    popular tickers as well: OpenBB's Cboe reader works on AAPL but crashes on SPY, TSLA and NVDA.
14. **Test upgrades, not just fresh installs.** `uv sync` decides whether to reinstall the backend from
    `tool.uv.cache-keys`, and Windows file copies keep modified times. Without the source in those keys, an
    upgrade leaves the old backend running behind the new UI.

## Adding things

- **A command:** add a `CommandResult` variant and a `COMMANDS` row in `commands.ts`, handle it in
  `App.tsx` (`submit` switch + workspace render), add parser tests in `src/sim/engine.test.ts`, and add
  it to `docs/USER_GUIDE.md`.
- **A course or lesson:** write a `Track` in `app/src/learn/curriculum/` and list it in `learn/index.ts`.
  Lesson bodies are a Markdown subset in template strings: use `~~~` code fences and escape inline
  backticks. Every `tryIt` command must parse (`learn.test.ts` checks this, plus quiz answer indexes,
  unique ids and https links). `access: 'premium'` only shows a badge; there is no access control or
  payment yet, so don't put paid content in the open-source repo.
- **A data source:** add a fetcher in `engines/openbb/providers.py`, register it in `CHAINS`/`FETCHERS`,
  return raw values with the provider field name, and build receipts in the backend.
- **An MCP tool:** add a function in `mcp_server.py` calling the HTTP API, with an accurate
  `ToolAnnotations` (read-only unless it changes state), extend `tests/test_mcp.py`, and document it in
  `docs/AI_ASSISTANTS.md`.
- **A backend dependency:** add it to `backend/pyproject.toml` and run `uv sync` (commits the lock).
  Installed apps sync with `--frozen`, so the lock must be committed.

## Data and environment notes

- Data sources (no keys): Yahoo via yfinance; Cboe, Nasdaq, TMX, FINRA, SEC, OECD via OpenBB.
- App data folder: `FINHUB_DATA_DIR` (set by the shell to the OS app-data dir; `~/.finhub` in dev).
- `FINHUB_SKIP_WARMUP=1` disables background warm-up and the alerts loop (tests set it).
- Vibe-Trading reads `LANGCHAIN_PROVIDER`, `LANGCHAIN_MODEL_NAME`, provider keys and `VIBE_TRADING_HOME`.
