# Engines

Each folder is an isolated Python environment for one third-party engine. They are kept apart on
purpose: engines pin conflicting versions of shared libraries (OpenBB 5 needs `fastmcp>=4`,
Vibe-Trading needs `fastmcp<4`), and Vibe-Trading installs generic top-level modules (`src`, `cli`,
`backtest`) that would collide with other packages in a shared environment.

The backend never imports an engine. It talks to each one as a separate process, so a missing or
broken engine shows up as "unavailable" in the SYS panel instead of crashing FinHub.

Install an engine:

```bash
cd engines/openbb && uv sync
cd engines/vibe-trading && uv sync
```
