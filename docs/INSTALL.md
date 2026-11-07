# Installing FinHub

FinHub installs like any desktop app. You do **not** need Python, Node or anything else: on first
launch it downloads and sets up its own private copy of everything it needs.

- [1. Download](#1-download)
- [2. Install](#2-install)
- [The security warning](#the-security-warning)
- [3. First launch](#3-first-launch)
- [4. Optional: AI agent](#4-optional-ai-agent)
- [Where FinHub keeps its files](#where-finhub-keeps-its-files)
- [Troubleshooting](#troubleshooting)
- [Updating and uninstalling](#updating-and-uninstalling)
- [Building from source](#building-from-source)

## 1. Download

**From a release (easiest, when one is published):**
[github.com/adibmolla-rgb/FinHub/releases](https://github.com/adibmolla-rgb/FinHub/releases)

**From the latest build (always available, needs a GitHub login):**

1. Open [Actions → CI](https://github.com/adibmolla-rgb/FinHub/actions/workflows/ci.yml).
2. Click the newest run with a green tick.
3. Scroll to **Artifacts** and download the zip for your system:

| System | Artifact | File inside |
|---|---|---|
| Windows 10/11 (64-bit) | `finhub-windows-latest` | `FinHub_0.4.0_x64-setup.exe` (or `FinHub_0.4.0_x64_en-US.msi`) |
| macOS on Apple Silicon (M1–M4) | `finhub-macos-latest` | `FinHub_0.4.0_aarch64.dmg` |
| Linux (Debian/Ubuntu, others via AppImage) | `finhub-ubuntu-22.04` | `FinHub_0.4.0_amd64.deb` or `FinHub_0.4.0_amd64.AppImage` |

Intel Macs are not built yet ([build from source](#building-from-source) works).

## 2. Install

- **Windows:** unzip, run `FinHub_…_x64-setup.exe`, follow the installer.
- **macOS:** unzip, open the `.dmg`, drag **FinHub** to **Applications**.
- **Linux (.deb):** `sudo apt install ./FinHub_0.4.0_amd64.deb`, then run `finhub` or open it from your apps menu.
- **Linux (AppImage):** `chmod +x FinHub_0.4.0_amd64.AppImage` and run it.

## The security warning

FinHub is not code-signed yet (signing certificates cost money and must be in the publisher's name),
so the first time you open it:

- **Windows:** "Windows protected your PC" → click **More info** → **Run anyway**.
- **macOS:** if it says FinHub "is damaged" or "can't be opened because Apple cannot check it", open
  Terminal and run:

  ```bash
  xattr -cr /Applications/FinHub.app
  ```

  then open FinHub again. (This removes the "downloaded from the internet" flag; it does not change
  the app.)

## 3. First launch

The first launch takes **a few minutes**; later launches take about a second. A banner at the top
shows what it is doing:

1. **"Setting up FinHub's Python environment"**: downloads a private Python and FinHub's backend
   (about 1–2 minutes).
2. **"Installing the market-data engine (OpenBB)"**: a few hundred MB, once (a few minutes). Market
   data commands work as soon as it finishes; progress is visible in `SYS`.

Then try:

```
AAPL
FA AAPL
MACRO US
BACKTEST SPY sma 20 50
```

Type `HELP` for every command. Click any example in the HELP panel to run it.

## 4. Optional: AI agent

`ASK`, `BT` and `DEBATE` use an AI model of your choice:

1. Type `AI`.
2. Pick **Claude (Anthropic)** or **OpenAI** and paste an API key, or pick **Ollama** to run a model
   locally for free (install [Ollama](https://ollama.com), then run `ollama pull qwen2.5:7b`).
3. Save, then try `ASK what drove NVDA over the last 3 months?`

The first agent command offers to install the agent engine (Vibe-Trading, a few hundred MB). Your key
is stored only in your FinHub data folder and sent only to the provider you chose.

To use FinHub *from* Claude instead, see [AI_ASSISTANTS.md](AI_ASSISTANTS.md).

## Where FinHub keeps its files

| System | Folder |
|---|---|
| Windows | `%LOCALAPPDATA%\app.finhub.terminal` |
| macOS | `~/Library/Application Support/app.finhub.terminal` |
| Linux | `~/.local/share/app.finhub.terminal` |

Inside: `envs/` (its private Python environments), `logs/` (start here if something goes wrong),
`agent-settings.json`, `watchlist.json`, `alerts.json`, `portfolio.json`, and `vibe-trading/` (saved agent runs).

## Troubleshooting

| Symptom | What to do |
|---|---|
| Banner says "FinHub could not start its backend" | Open `logs/backend-setup.err.log` and `logs/backend.err.log`. Usually a network problem during first setup: check your connection and restart FinHub. |
| "Couldn't load the quote" with a table of providers | Each row is a provider FinHub tried and why it failed. All failing usually means no internet or a firewall/proxy. One failing is normal: FinHub falls back automatically. |
| "The market-data engine isn't installed yet" | Wait for the install banner to finish, or open `SYS` → **Install** next to OpenBB. |
| `SYS` shows OpenBB "probe timed out" | Its very first import can take minutes on a slow disk. Type `REFRESH`. |
| AI agent: "rejected the API key" | Type `AI` and paste the key again. |
| AI agent with Ollama: "couldn't reach" | Make sure Ollama is running and the model is pulled. |
| Port 8765 already in use | Another FinHub (or another program) is using it. Close it and restart FinHub. |
| Anything else | Open an issue with the files from `logs/`. |

To start completely fresh, quit FinHub and delete the data folder (you will lose your watchlist,
alerts, portfolio, AI settings and saved agent runs).

## Updating and uninstalling

- **Update:** install the newer version over the old one. Your data folder is kept.
- **Uninstall:** Windows: Settings → Apps → FinHub → Uninstall. macOS: drag FinHub from Applications
  to the Bin. Linux: `sudo apt remove fin-hub`. Then delete the data folder above if you want to
  remove everything.

## Building from source

Requirements: [uv](https://docs.astral.sh/uv/), Node 20+ with [pnpm](https://pnpm.io), Rust, and on
Linux the [Tauri system libraries](https://v2.tauri.app/start/prerequisites/).

```bash
git clone https://github.com/adibmolla-rgb/FinHub.git
cd FinHub/backend && uv sync && cd ..
cd engines/openbb && uv sync && cd ../..          # market data (~220 packages)
cd engines/vibe-trading && uv sync && cd ../..    # AI agent (optional, ~190 packages)
cd app && pnpm install
pnpm tauri dev      # run the desktop app in development
pnpm tauri build    # build installers for this system
```

To use a browser instead of the desktop window: `uv run finhub-backend` in `backend/`, `pnpm dev` in
`app/`, then open http://127.0.0.1:1420.
