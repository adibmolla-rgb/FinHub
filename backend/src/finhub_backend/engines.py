"""Engine registry: which third-party engines are installed and usable.

Each engine lives in its own isolated Python environment under ``engines/<id>/.venv`` because engines
pin conflicting dependencies (OpenBB 5 needs fastmcp>=4, Vibe-Trading needs fastmcp<4). The backend
never imports an engine directly; it probes the engine's own interpreter in a subprocess. If an engine
is missing or broken, FinHub still starts and shows that engine as unavailable with the reason.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class EngineSpec:
    id: str
    name: str
    role: str
    module: str  # import name
    distribution: str  # pip package name
    license: str
    homepage: str


ENGINES: tuple[EngineSpec, ...] = (
    EngineSpec(
        id="openbb",
        name="OpenBB",
        role="Market, fundamental, macro and news data",
        module="openbb",
        distribution="openbb",
        license="Apache-2.0",
        homepage="https://github.com/openbq-org/OpenBB",
    ),
    EngineSpec(
        id="vibe-trading",
        name="Vibe-Trading",
        role="Reasoning agent, backtests, options lab, agent debates",
        module="api_server",  # the package installs generic top-level modules (src, cli, backtest)
        distribution="vibe-trading-ai",
        license="MIT",
        homepage="https://github.com/HKUDS/Vibe-Trading",
    ),
)


def engines_dir() -> Path:
    override = os.environ.get("FINHUB_ENGINES_DIR")
    if override:
        return Path(override)
    # backend/src/finhub_backend/engines.py -> repo root / engines
    return Path(__file__).resolve().parents[3] / "engines"


def engine_env(engine_id: str) -> Path:
    """Where an engine's virtual environment lives.

    In development it is ``engines/<id>/.venv``. Installed apps keep engine sources read-only inside the
    app bundle, so they set FINHUB_ENGINE_ENVS_DIR to a writable folder in the user's app data.
    """
    envs = os.environ.get("FINHUB_ENGINE_ENVS_DIR")
    return Path(envs) / engine_id if envs else engines_dir() / engine_id / ".venv"


def engine_python(engine_id: str) -> Path:
    return engine_env(engine_id) / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


# On Windows, a console program started from a window-less parent opens its own console window.
NO_WINDOW = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


@dataclass(frozen=True)
class EngineStatus:
    id: str
    name: str
    role: str
    license: str
    homepage: str
    available: bool
    version: str | None
    reason: str | None


_PROBE = """
import importlib, importlib.metadata, json, sys
dist, mod = sys.argv[1], sys.argv[2]
out = {"version": None, "error": None}
try:
    out["version"] = importlib.metadata.version(dist)
    importlib.import_module(mod)
except Exception as exc:
    out["error"] = repr(exc)
print(json.dumps(out))
"""


def check(spec: EngineSpec, timeout: float = 900.0) -> EngineStatus:
    # Generous timeout: OpenBB builds its command index on the very first import, which takes minutes.
    base = {k: v for k, v in asdict(spec).items() if k in {"id", "name", "role", "license", "homepage"}}
    python = engine_python(spec.id)
    if not python.exists():
        return EngineStatus(**base, available=False, version=None, reason="not installed")
    try:
        proc = subprocess.run(
            [str(python), "-I", "-c", _PROBE, spec.distribution, spec.module],
            capture_output=True,
            text=True,
            timeout=timeout,
            **NO_WINDOW,
        )
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return EngineStatus(**base, available=False, version=None, reason=f"probe timed out after {timeout:.0f}s")
    except (json.JSONDecodeError, IndexError):
        return EngineStatus(**base, available=False, version=None, reason=f"probe failed: {proc.stderr[-300:]}")
    if result["error"]:
        return EngineStatus(**base, available=False, version=result["version"], reason=f"import failed: {result['error']}")
    return EngineStatus(**base, available=True, version=result["version"], reason=None)


_cache: list[EngineStatus] | None = None
_cache_lock = threading.Lock()


def statuses(refresh: bool = False) -> list[EngineStatus]:
    """Probe all engines in parallel. Results are cached because some engines (OpenBB) take tens of
    seconds to import; pass refresh=True to re-probe."""
    global _cache
    with _cache_lock:
        if _cache is None or refresh:
            with ThreadPoolExecutor(max_workers=len(ENGINES)) as pool:
                _cache = list(pool.map(check, ENGINES))
        return list(_cache)
