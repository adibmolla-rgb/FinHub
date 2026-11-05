from fastapi.testclient import TestClient

from finhub_backend.server import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["version"]


def test_engines_report_without_crashing_when_missing(tmp_path, monkeypatch):
    # Point at an empty engines folder: every engine must report "not installed", not crash.
    monkeypatch.setenv("FINHUB_ENGINES_DIR", str(tmp_path))
    engines = client.get("/engines?refresh=true").json()
    ids = {e["id"] for e in engines}
    assert {"openbb", "vibe-trading"} <= ids
    for e in engines:
        assert isinstance(e["available"], bool)
        assert e["available"] is False
        assert e["reason"] == "not installed"


def test_receipt_example_converts_units_before_adding():
    body = client.get("/examples/receipt").json()
    receipt = body["receipt"]
    assert receipt["unit"] == "fraction"
    assert abs(receipt["value"] - 0.0349) < 1e-9
    assert len(receipt["inputs"]) == 2


def test_watchdog_detects_dead_process():
    import subprocess
    import sys

    from finhub_backend.watchdog import _alive

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert _alive(proc.pid) is False
    import os

    assert _alive(os.getpid()) is True
