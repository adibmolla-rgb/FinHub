"""Install an engine's environment with uv, in the background, with progress the UI can poll.

uv comes from FINHUB_UV (the copy bundled with the desktop app) or PATH. Engine sources may be
read-only (inside an installed app), so the environment goes wherever engines.engine_env() says.
"""

from __future__ import annotations

import hashlib
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


def _lock_hash(engine_id: str) -> str | None:
    lock = engines.engines_dir() / engine_id / "uv.lock"
    return hashlib.sha256(lock.read_bytes()).hexdigest() if lock.exists() else None


def _marker(engine_id: str):
    return engines.engine_env(engine_id) / ".finhub-lock"


def out_of_date(engine_id: str) -> bool:
    """True when an installed engine was last synced from a different uv.lock, as after an app upgrade."""
    marker = _marker(engine_id)
    current = _lock_hash(engine_id)
    if current is None or not engines.engine_python(engine_id).exists():
        return False
    return not marker.exists() or marker.read_text(encoding="utf-8").strip() != current


def _record_lock(st: InstallState) -> None:
    """Remember which lock this install came from. Failing only means one more sync at the next launch."""
    current = _lock_hash(st.engine)
    try:
        if current:
            _marker(st.engine).write_text(current, encoding="utf-8")
    except OSError as exc:
        st.log.append(f"Couldn't record the installed version: {exc}")


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
    if engine_id == "openbb":
        market.worker().hold(_HOLD_REASON)
    elif engine_id == "vibe-trading":
        from finhub_backend import agent

        agent.server.stop()  # new runs are refused until the state above leaves "running"
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
    _record_lock(st)
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
    pinned = project / ".python-version"
    if pinned.exists():  # a UV_PYTHON on this computer would otherwise win, and Qlib can't use a newer Python
        env["UV_PYTHON"] = pinned.read_text(encoding="utf-8").strip()
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
