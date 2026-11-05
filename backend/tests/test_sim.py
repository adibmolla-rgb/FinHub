"""The Python simulator must behave like the app's: exact accounting, reproducibility, price discovery."""

import pytest
from fastapi.testclient import TestClient

from finhub_backend import sim
from finhub_backend.server import app


def test_order_book_price_time_priority():
    b = sim.OrderBook()
    b.limit("a", "sell", 101, 50)
    b.limit("b", "sell", 100, 30)
    b.limit("c", "sell", 100, 30)
    b.limit("x", "buy", 101, 70)
    assert [(t.seller, t.price, t.qty) for t in b.trades] == [("b", 100, 30), ("c", 100, 30), ("a", 101, 10)]


def test_cash_and_shares_are_conserved():
    m = sim.Market(7)
    for i in range(500):
        m.tick()
        if i == 100:
            m.trigger("crash")
        if i % 50 == 0:
            m.order("claude", "buy", 50)
    assert sum(a.position for a in m.book.accounts.values()) == 0
    assert sum(a.cash for a in m.book.accounts.values()) == 0


def test_reproducible_from_seed():
    def run():
        m = sim.Market(123)
        m.tick(300)
        return [h["mid"] for h in m.history]

    assert run() == run()


@pytest.mark.parametrize("scenario", ["crash", "news-up", "news-down", "drain"])
def test_price_returns_to_true_value_after_shocks(scenario):
    for seed in range(1, 6):
        m = sim.Market(seed)
        m.tick(200)
        m.trigger(scenario)
        m.tick(600)
        last = m.history[-1]
        assert abs(last["mid"] - last["value"]) / last["value"] < 0.03, (scenario, seed)


def test_participant_orders_and_validation():
    m = sim.Market(3)
    m.tick(20)
    out = m.order("agent-1", "buy", 100)
    assert out["filled"] == 100 and out["account"]["position"] == 100
    rest = m.order("agent-1", "sell", 10, price=500.0)  # far above the market: rests
    assert rest["resting"]["remaining"] == 10
    assert m.cancel_all("agent-1") == 1
    for bad in [("maker", "buy", 1, None), ("ok", "hold", 1, None), ("ok", "buy", 0, None), ("bad name!", "buy", 1, None)]:
        with pytest.raises(ValueError):
            m.order(*bad)


def test_arena_endpoints_hide_true_value_unless_asked():
    client = TestClient(app)
    client.post("/sim/reset", json={"seed": 5})
    st = client.get("/sim/state").json()
    assert st["step"] == 50 and "value" not in st["history"][-1]
    assert "value" in client.get("/sim/state?reveal=true").json()["history"][-1]
    r = client.post("/sim/order", json={"name": "tester", "side": "buy", "qty": 10}).json()
    assert r["filled"] == 10
    assert client.post("/sim/advance", json={"steps": 25}).json()["step"] == 75
    assert any(row["name"] == "tester" for row in client.get("/sim/state").json()["leaderboard"])
    assert client.post("/sim/order", json={"name": "maker", "side": "buy", "qty": 10}).status_code == 422
