import json

from fastapi.testclient import TestClient

from finhub_backend import store
from finhub_backend.server import app


def test_watchlist_defaults_dedupes_and_validates(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    assert client.get("/watchlist").json()["symbols"] == store.DEFAULT_WATCHLIST
    assert client.put("/watchlist", json={"symbols": ["aapl", "AAPL", " msft "]}).json()["symbols"] == ["AAPL", "MSFT"]
    assert client.get("/watchlist").json()["symbols"] == ["AAPL", "MSFT"]
    assert client.put("/watchlist", json={"symbols": ["../etc"]}).status_code == 422


def _session(root, sid, title, status, answer=None, trace=()):
    d = root / "vibe-trading" / "sessions" / sid
    (d / "attempts" / "a1").mkdir(parents=True)
    (d / "session.json").write_text(json.dumps({"session_id": sid, "title": title, "created_at": f"2026-11-0{sid[-1]}T00:00:00", "last_attempt_id": "a1"}))
    (d / "attempts" / "a1" / "attempt.json").write_text(json.dumps({"status": status, "error": None if status == "completed" else "boom"}))
    msgs = [{"role": "user", "content": "question"}] + ([{"role": "assistant", "content": answer}] if answer else [])
    (d / "messages.jsonl").write_text("\n".join(json.dumps(m) for m in msgs))
    (d / "trace.jsonl").write_text("\n".join(json.dumps(t) for t in trace))


def test_notes_list_and_detail_rebuild_the_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    _session(tmp_path, "s1", "BT: SPY sma", "completed", "Sharpe 0.4 after costs", [
        {"type": "tool_call", "tool": "get_prices", "call_id": "c1", "args": {"symbol": "SPY"}},
        {"type": "tool_result", "tool": "get_prices", "call_id": "c1", "status": "ok", "preview": "1258 rows"},
    ])
    _session(tmp_path, "s2", "ASK: why?", "failed")
    client = TestClient(app)
    notes = client.get("/notes").json()
    assert [n["id"] for n in notes] == ["s2", "s1"]  # newest first
    assert notes[1]["kind"] == "bt" and notes[1]["preview"].startswith("Sharpe")
    assert notes[0]["status"] == "failed" and notes[0]["error"] == "boom"
    detail = client.get("/notes/s1").json()
    assert detail["steps"] == [{"id": "c1", "tool": "get_prices", "args": {"symbol": "SPY"}, "status": "ok", "preview": "1258 rows"}]
    assert client.get("/notes/..%2Fx").status_code in (404, 422)
    assert client.get("/notes/nope").status_code == 404
