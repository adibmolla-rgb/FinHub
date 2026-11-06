"""Install an engine's environment with uv, in the background, with progress the UI can poll.

uv comes from FINHUB_UV (the copy bundled with the desktop app) or PATH. Engine sources may be
read-only (inside an installed app), so the environment goes wherever engines.engine_env() says.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from finhub_backend import engines, market

# Matches the UI's check for a missing engine (Ticker.tsx), which then points the user at SYS.
_HOLD_REASON = "engine not installed yet: setup is still running"


@dataclass
class InstallState:
    engine: str
    state: str = "idle"  # idle | running | done | failed
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    log: deque = field(default_factory=lambda: deque(maxlen=200))

    def public(self) -> dict:
        return {
            "engine": self.engine,
            "state": self.state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "log_tail": list(self.log)[-12:],
        }


_states: dict[str, InstallState] = {}
_lock = threading.Lock()


def uv_path() -> str | None:
    return os.environ.get("FINHUB_UV") or shutil.which("uv")


def state(engine_id: str) -> InstallState:
    with _lock:
        return _states.setdefault(engine_id, InstallState(engine_id))


def install(engine_id: str) -> InstallState:
    """Start installing an engine unless it is already being installed. Returns immediately."""
    if engine_id not in {e.id for e in engines.ENGINES}:
        raise KeyError(engine_id)
    st = state(engine_id)
    with _lock:
        if st.state == "running":
            return st
        st.state, st.error, st.started_at, st.finished_at = "running", None, time.time(), None
        st.log.clear()
    if engine_id == "openbb":  # the only engine with a long-lived worker
        market.worker().hold(_HOLD_REASON)
    threading.Thread(target=_run, args=(st,), daemon=True, name=f"install-{engine_id}").start()
    return st


def _run(st: InstallState) -> None:
    try:
        synced = _sync(st)
    finally:
        # Files are in place, so the worker may start now. OpenBB's first import (the check below) takes
        # minutes, and market data shouldn't wait for it.
        if st.engine == "openbb":
            market.worker().release()
    if not synced:
        return
    st.log.append("Checking the engine imports (the first import can take a few minutes)…")
    engines.statuses(refresh=True)
    st.state, st.finished_at = "done", time.time()


def _sync(st: InstallState) -> bool:
    """Run uv sync. On failure, record why on the state and return False."""
    uv = uv_path()
    if not uv:
        st.state, st.error, st.finished_at = "failed", "uv not found (set FINHUB_UV or install uv)", time.time()
        return False
    project = engines.engines_dir() / st.engine
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(engines.engine_env(st.engine))}
    cmd = [uv, "sync", "--frozen", "--no-dev", "--project", str(project)]
    st.log.append("$ " + " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            **engines.NO_WINDOW,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                st.log.append(line)
        code = proc.wait()
    except OSError as exc:
        st.state, st.error, st.finished_at = "failed", f"could not run uv: {exc}", time.time()
        return False
    if code != 0:
        st.state, st.error, st.finished_at = "failed", f"uv sync exited with {code}", time.time()
        return False
    return True
