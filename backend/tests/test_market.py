import sys
import textwrap

import pytest
from fastapi.testclient import TestClient

from finhub_backend import market
from finhub_backend.server import app
from finhub_backend.worker_client import EngineWorker, WorkerError

# Test fixture shaped like the worker's quote result. Values are arbitrary test numbers.
QUOTE_RESULT = {
    "provider": "cboe",
    "provider_name": "Cboe (via OpenBB)",
    "fetched_at": "2026-11-05T14:30:00+00:00",
    "attempts": [
        {"provider": "yahoo", "ok": False, "error": "ConnectionError: blocked", "ms": 12},
        {"provider": "cboe", "ok": True, "error": None, "ms": 80},
    ],
    "data": {
        "symbol": "TEST",
        "currency": "USD",
        "exchange": "XNAS",
        "fields": {
            "price": {"value": 110.0, "field": "last_price"},
            "previous_close": {"value": 100.0, "field": "prev_close"},
            "year_high": {"value": 125.0, "field": "year_high"},
            "volume": {"value": 1_000_000, "field": "volume"},
        },
    },
}


def test_change_is_computed_by_finhub_with_full_receipt():
    q = market.build_quote(QUOTE_RESULT)
    v = q["values"]
    assert v["change"]["value"] == pytest.approx(10.0)
    assert v["change_pct"]["unit"] == "fraction"
    assert v["change_pct"]["value"] == pytest.approx(0.10)
    assert v["change_pct"]["formula"] == "Change ÷ Previous close"
    # The receipt reaches all the way down to the provider fields.
    price_receipt = v["change_pct"]["inputs"][0]["inputs"][0]
    assert price_receipt["source"]["provider"] == "Cboe (via OpenBB)"
    assert price_receipt["source"]["detail"] == "last_price"
    assert v["from_high_pct"]["value"] == pytest.approx(110 / 125 - 1)
    assert v["volume"]["unit"] == "shares" and v["volume"]["currency"] is None
    assert q["fallback_used"] is True


def test_missing_previous_close_means_no_change_rather_than_a_guess():
    result = {**QUOTE_RESULT, "data": {**QUOTE_RESULT["data"], "fields": {"price": {"value": 5.0, "field": "p"}}}}
    v = market.build_quote(result)["values"]
    assert "change" not in v and "change_pct" not in v


FAKE_WORKER = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        req = json.loads(line)
        if req["method"] == "quote":
            print(json.dumps({"id": req["id"], "ok": False, "error": "no provider could serve quote",
                              "attempts": [{"provider": "yahoo", "ok": False, "error": "blocked", "ms": 1}]}), flush=True)
        else:
            print(json.dumps({"id": req["id"], "ok": True, "result": {"echo": req["method"]}}), flush=True)
    """
)


@pytest.fixture
def fake_worker(tmp_path):
    script = tmp_path / "worker.py"
    script.write_text(FAKE_WORKER)
    from pathlib import Path

    w = EngineWorker(Path(sys.executable), script)
    market.set_worker(w)
    yield w
    w.stop()
    market.set_worker(None)


def test_worker_client_round_trip_and_errors(fake_worker):
    assert fake_worker.call("ping") == {"echo": "ping"}
    with pytest.raises(WorkerError) as err:
        fake_worker.call("quote", {"symbol": "X"})
    assert err.value.attempts[0]["provider"] == "yahoo"


def test_worker_restarts_after_it_dies(fake_worker):
    fake_worker.call("ping")
    fake_worker._proc.kill()
    fake_worker._proc.wait()
    assert fake_worker.call("ping") == {"echo": "ping"}


def test_endpoint_returns_502_with_attempts_and_records_health(fake_worker):
    client = TestClient(app)
    res = client.get("/market/quote/AAPL")
    assert res.status_code == 502
    assert res.json()["attempts"][0]["provider"] == "yahoo"
    health = {h["provider"]: h for h in client.get("/market/sources").json()}
    assert health["yahoo"]["status"] == "failing"


def test_bad_symbols_are_rejected():
    client = TestClient(app)
    assert client.get("/market/quote/rm%20-rf").status_code == 422


BARS_WORKER = textwrap.dedent(
    """
    import json, sys, math
    for line in sys.stdin:
        req = json.loads(line)
        if req["method"] == "history":
            # Synthetic test series: a sine wave around 100 with a slow upward drift.
            bars = [{"time": f"2015-01-01+{i}", "open": 0, "high": 0, "low": 0,
                     "close": 100 * (1 + 0.0003 * i) * (1 + 0.05 * math.sin(i / 15)), "volume": 0} for i in range(1600)]
            print(json.dumps({"id": req["id"], "ok": True, "result": {
                "provider": "test", "provider_name": "SYNTHETIC", "fetched_at": "2026-11-05T00:00:00+00:00",
                "attempts": [{"provider": "test", "ok": True, "error": None, "ms": 1}],
                "data": {"symbol": "TEST", "interval": "1d", "adjusted": req["params"].get("adjusted", False), "bars": bars}}}), flush=True)
    """
)


def test_backtest_endpoint_requests_adjusted_prices_and_reports_provenance(tmp_path):
    from pathlib import Path

    script = tmp_path / "worker.py"
    script.write_text(BARS_WORKER)
    w = EngineWorker(Path(sys.executable), script)
    market.set_worker(w)
    try:
        res = TestClient(app).post("/backtest", json={"symbol": "TEST", "strategy": "sma", "params": {"fast": 10, "slow": 50}})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["data"]["adjusted"] is True and body["data"]["provider"] == "SYNTHETIC"
        assert body["causality_check"] is True
        assert body["walk_forward"]["available"] is True
        assert set(body["metrics"]) == {"strategy", "strategy_before_costs", "buy_hold"}
        assert len(body["curve"]) > 100
    finally:
        w.stop()
        market.set_worker(None)


MULTI_WORKER = textwrap.dedent(
    """
    import json, sys, random
    for line in sys.stdin:
        req = json.loads(line)
        sym = req["params"]["symbol"]
        rnd = random.Random(sym)  # a different synthetic series per ticker
        price, bars = 100.0, []
        start = 0 if sym != "SHORT" else 1500  # SHORT has less history: tests date alignment
        for i in range(start, 1600):
            price *= 1 + rnd.gauss(0.0003, 0.01)
            bars.append({"time": f"day{i:05d}", "open": 0, "high": 0, "low": 0, "close": price, "volume": 0})
        print(json.dumps({"id": req["id"], "ok": True, "result": {
            "provider": "test", "provider_name": "SYNTHETIC", "fetched_at": "2026-11-05T00:00:00+00:00",
            "attempts": [], "data": {"symbol": sym, "interval": "1d", "adjusted": True, "bars": bars}}}), flush=True)
    """
)


@pytest.fixture
def multi_worker(tmp_path):
    from pathlib import Path

    script = tmp_path / "worker.py"
    script.write_text(MULTI_WORKER)
    w = EngineWorker(Path(sys.executable), script)
    market.set_worker(w)
    yield w
    w.stop()
    market.set_worker(None)


def test_risk_endpoint_aligns_dates_and_reports_sources(multi_worker):
    client = TestClient(app)
    res = client.post("/risk", json={"holdings": [{"symbol": "AAA", "weight": 60}, {"symbol": "BBB", "weight": 40}], "confidence": 0.95})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["weights"] == pytest.approx([0.6, 0.4])
    assert {d["symbol"] for d in body["data"]} == {"AAA", "BBB"}
    assert body["var_backtest"]["available"]
    # A holding with only 100 days of history limits the shared window.
    res = client.post("/risk", json={"holdings": [{"symbol": "AAA", "weight": 1}, {"symbol": "SHORT", "weight": 1}]})
    assert res.json()["period"]["days"] == 99
    assert client.post("/risk", json={"holdings": [{"symbol": "AAA", "weight": 1}, {"symbol": "AAA", "weight": 1}]}).status_code == 422
