import pytest
from fastapi.testclient import TestClient

from finhub_backend import alerts
from finhub_backend.server import app


def q(price, change):
    return {"provider_name": "Test", "values": {"price": {"value": price}, "change_pct": {"value": change}}}


def test_alerts_fire_once_and_record_events(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    up = alerts.add("aapl", "above", 200)
    mv = alerts.add("NVDA", "move_down", 0.05)
    alerts.add("MSFT", "below", 100)
    quotes = {"AAPL": q(201.5, 0.01), "NVDA": q(90, -0.06), "MSFT": q(400, 0.0)}
    fired = alerts.check(lambda s: quotes[s])
    assert {e["alert_id"] for e in fired} == {up["id"], mv["id"]}
    assert "now 201.5" in next(e["text"] for e in fired if e["alert_id"] == up["id"])
    assert alerts.check(lambda s: quotes[s]) == []  # one-shot
    state = alerts.listing()
    assert [a["active"] for a in state["alerts"]] == [False, False, True]
    assert len(state["events"]) == 2


def test_failed_quote_never_fires(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    alerts.add("AAPL", "below", 1000)

    def boom(_):
        raise RuntimeError("network down")

    assert alerts.check(boom) == []
    assert alerts.listing()["alerts"][0]["active"] is True


def test_validation(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    for args in [("../x", "above", 1), ("AAPL", "sideways", 1), ("AAPL", "above", -5), ("AAPL", "move_up", 5)]:
        with pytest.raises(ValueError):
            alerts.add(*args)


def test_endpoints(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    c = TestClient(app)
    a = c.post("/alerts", json={"symbol": "spy", "kind": "above", "threshold": 600}).json()
    assert a["description"] == "SPY: price rises to or above 600"
    assert c.post("/alerts", json={"symbol": "spy", "kind": "nope", "threshold": 1}).status_code == 422
    assert len(c.get("/alerts").json()["alerts"]) == 1
    assert c.delete(f"/alerts/{a['id']}").status_code == 200
    assert c.delete(f"/alerts/{a['id']}").status_code == 404
