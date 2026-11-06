import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from finhub_backend import engines, installer, market
from finhub_backend.worker_client import EngineWorker, WorkerUnavailable

# Stands in for engines/openbb/worker.py: imports a package on each request, as providers._yf() does.
WORKER = """
import json, sys
for line in sys.stdin:
    request = json.loads(line)
    import halfpkg
    result = {"has_ticker": hasattr(halfpkg, "Ticker")}
    print(json.dumps({"id": request["id"], "ok": True, "result": result}), flush=True)
"""


@pytest.fixture(autouse=True)
def fresh_worker():
    # installer.install() touches the shared worker; don't leak one pointing at a test's temp folder.
    market.set_worker(None)
    yield
    market.worker().stop()
    market.set_worker(None)


@pytest.fixture
def half_installed(tmp_path):
    """A worker whose package folder exists but has no __init__.py yet, as uv leaves it mid-install."""
    (tmp_path / "halfpkg").mkdir()
    script = tmp_path / "worker.py"
    script.write_text(WORKER)
    worker = EngineWorker(Path(sys.executable), script)
    market.set_worker(worker)
    return worker


def _wait_until_finished(st: installer.InstallState) -> None:
    deadline = time.time() + 30
    while st.state == "running" and time.time() < deadline:
        time.sleep(0.02)
    assert st.state != "running", st.public()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_install_creates_env_outside_source_dir(tmp_path, monkeypatch):
    # A tiny stand-in project in place of the real engine: same install path, no downloads.
    src = tmp_path / "engines" / "openbb"
    src.mkdir(parents=True)
    (src / "pyproject.toml").write_text(
        '[project]\nname = "stand-in"\nversion = "0"\nrequires-python = ">=3.12"\ndependencies = []\n'
        "[tool.uv]\npackage = false\n"
    )
    subprocess.run(["uv", "lock", "--project", str(src)], check=True, capture_output=True)
    monkeypatch.setenv("FINHUB_ENGINES_DIR", str(tmp_path / "engines"))
    monkeypatch.setenv("FINHUB_ENGINE_ENVS_DIR", str(tmp_path / "envs"))

    st = installer.install("openbb")
    deadline = time.time() + 120
    while st.state == "running" and time.time() < deadline:
        time.sleep(0.2)

    assert st.state == "done", st.public()
    assert engines.engine_python("openbb").exists()
    assert str(engines.engine_python("openbb")).startswith(str(tmp_path / "envs"))
    assert not (src / ".venv").exists()  # the (possibly read-only) source folder is untouched


def test_unknown_engine_is_rejected():
    with pytest.raises(KeyError):
        installer.install("nope")


def test_worker_that_imported_a_half_install_is_replaced(half_installed, tmp_path, monkeypatch):
    # The first-launch bug: a worker started mid-install imports the folder as an empty namespace package
    # and keeps it for life, so Yahoo fails with "no attribute 'Ticker'" until FinHub restarts.
    assert half_installed.call("quote") == {"has_ticker": False}
    seen = {}

    def fake_sync(st):
        try:
            half_installed.call("quote")
        except WorkerUnavailable as exc:
            seen["during_sync"] = str(exc)
        (tmp_path / "halfpkg" / "__init__.py").write_text("class Ticker: ...")
        return True

    monkeypatch.setattr(installer, "_sync", fake_sync)
    monkeypatch.setattr(engines, "statuses", lambda refresh=False: [])
    st = installer.install("openbb")
    _wait_until_finished(st)

    assert st.state == "done", st.public()
    assert "engine not installed" in seen["during_sync"]  # Ticker.tsx matches this to point at SYS
    assert half_installed.call("quote") == {"has_ticker": True}


def test_failed_install_lets_the_worker_start_again(half_installed, monkeypatch):
    def fake_sync(st):
        st.state, st.error, st.finished_at = "failed", "uv sync exited with 1", time.time()
        return False

    monkeypatch.setattr(installer, "_sync", fake_sync)
    _wait_until_finished(installer.install("openbb"))

    assert installer.state("openbb").state == "failed"
    assert half_installed.call("quote") == {"has_ticker": False}


def test_installing_another_engine_leaves_the_data_worker_running(half_installed, monkeypatch):
    half_installed.call("quote")
    monkeypatch.setattr(installer, "_sync", lambda st: True)
    monkeypatch.setattr(engines, "statuses", lambda refresh=False: [])
    _wait_until_finished(installer.install("vibe-trading"))

    assert half_installed.running


def test_held_worker_reports_a_market_data_error(half_installed):
    half_installed.hold("engine not installed yet: setup is still running")
    with pytest.raises(market.MarketDataError, match="engine not installed"):
        market.quote("AAPL")
