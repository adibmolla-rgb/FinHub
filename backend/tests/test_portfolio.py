import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from finhub_backend import market, portfolio
from finhub_backend.server import app
from finhub_backend.worker_client import WorkerError


@pytest.fixture(autouse=True)
def data_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    return tmp_path


def tx(side, quantity, price=0.0, day="2026-01-01", symbol="AAPL", fees=0.0):
    return {"id": f"{symbol}{side}{quantity}{day}", "symbol": symbol, "side": side, "quantity": quantity, "price": price, "fees": fees, "date": day}


def receipt(label, value, unit="currency", currency="USD"):
    return {"label": label, "value": value, "unit": unit, "currency": currency, "source": {"provider": "Test", "fetched_at": "2026-11-05T00:00:00+00:00", "detail": None}, "formula": None, "inputs": []}


def quote(price, change=1.0, currency="USD"):
    return {"currency": currency, "provider_name": "Test", "fallback_used": False, "values": {"price": receipt("Last price", price, currency=currency), "change": receipt("Change", change, currency=currency)}}


# --- cost basis ---------------------------------------------------------------------------------


def test_sales_use_the_oldest_shares_first():
    books = portfolio.replay([tx("buy", 10, 100, "2026-01-01"), tx("buy", 10, 200, "2026-02-01"), tx("sell", 15, 300, "2026-03-01")])
    book = books["AAPL"]
    assert book["realized"] == pytest.approx(10 * (300 - 100) + 5 * (300 - 200))
    assert [list(lot) for lot in book["lots"]] == [[5, 200]]


def test_fees_raise_cost_and_lower_proceeds():
    book = portfolio.replay([tx("buy", 10, 100, "2026-01-01", fees=10), tx("sell", 10, 110, "2026-02-01", fees=5)])["AAPL"]
    assert book["realized"] == pytest.approx(10 * (110 - 101) - 5)
    assert not book["lots"]


def test_order_is_by_trade_date_not_entry_date():
    book = portfolio.replay([tx("sell", 5, 150, "2026-03-01"), tx("buy", 10, 100, "2026-01-01")])["AAPL"]
    assert book["realized"] == pytest.approx(5 * 50)


def test_splits_keep_cost_and_profit_unchanged():
    book = portfolio.replay([tx("buy", 10, 100, "2026-01-01"), tx("split", 4, 0, "2026-02-01"), tx("sell", 40, 30, "2026-03-01")])["AAPL"]
    assert book["realized"] == pytest.approx(40 * (30 - 25))
    assert not book["lots"]
    reverse = portfolio.replay([tx("buy", 10, 100, "2026-01-01"), tx("split", 0.5, 0, "2026-02-01")])["AAPL"]
    assert [list(lot) for lot in reverse["lots"]] == [[5, 200]]


def test_fractional_sales_leave_no_dust():
    book = portfolio.replay([tx("buy", 0.3, 100), tx("sell", 0.1, 100, "2026-02-01"), tx("sell", 0.2, 100, "2026-03-01")])["AAPL"]
    assert not book["lots"]


# --- the ledger file ----------------------------------------------------------------------------


def test_transactions_survive_a_restart():
    saved = portfolio.add("aapl", "buy", 10, 100.0, 1.0, "2026-01-01")
    assert saved["symbol"] == "AAPL"
    assert portfolio.load() == [saved]


def test_cant_sell_more_than_held_even_when_back_dated():
    portfolio.add("AAPL", "buy", 10, 100.0, day="2026-06-01")
    with pytest.raises(portfolio.LedgerError, match="can't sell"):
        portfolio.add("AAPL", "sell", 11, 100.0, day="2026-07-01")
    with pytest.raises(portfolio.LedgerError, match="can't sell"):
        portfolio.add("AAPL", "sell", 5, 100.0, day="2026-05-01")  # before the shares were bought
    assert len(portfolio.load()) == 1


def test_cant_delete_a_buy_that_a_sale_depends_on():
    buy = portfolio.add("AAPL", "buy", 10, 100.0, day="2026-01-01")
    sell = portfolio.add("AAPL", "sell", 10, 100.0, day="2026-02-01")
    with pytest.raises(portfolio.LedgerError, match="nothing to sell"):
        portfolio.remove(buy["id"])
    assert portfolio.remove(sell["id"]) is True
    assert portfolio.remove(buy["id"]) is True
    assert portfolio.remove("missing") is False
    assert portfolio.load() == []


@pytest.mark.parametrize("args", [
    ("../etc", "buy", 1, 1.0), ("AAPL", "short", 1, 1.0), ("AAPL", "buy", 0, 1.0), ("AAPL", "buy", -1, 1.0),
    ("AAPL", "buy", float("nan"), 1.0), ("AAPL", "buy", float("inf"), 1.0), ("AAPL", "buy", 1, -1.0), ("AAPL", "buy", 1, None),
    ("AAPL", "buy", 1, float("nan")), ("AAPL", "split", 1, None), ("AAPL", "split", 0, None),
])
def test_bad_transactions_are_refused(args):
    with pytest.raises(portfolio.LedgerError):
        portfolio.add(*args)
    assert portfolio.load() == []


def test_absurdly_large_numbers_are_refused():
    for kwargs in ({"quantity": 1e308, "price": 1.0}, {"quantity": 1.0, "price": 1e308}, {"quantity": 1.0, "price": 1.0, "fees": 1e308}):
        with pytest.raises(portfolio.LedgerError, match="too large"):
            portfolio.add("AAPL", "buy", **kwargs)


def test_bad_fees_and_dates_are_refused():
    tomorrow = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    for kwargs in ({"fees": -1.0}, {"fees": float("nan")}, {"day": "soon"}, {"day": tomorrow}):
        with pytest.raises(portfolio.LedgerError):
            portfolio.add("AAPL", "buy", 1, 1.0, **kwargs)


def test_a_damaged_ledger_is_never_overwritten(data_folder):
    path = data_folder / "portfolio.json"
    for damaged in ("{not json", '{"transactions": 5}', '{"other": []}', json.dumps({"transactions": [tx("sell", 1, 1)]})):
        path.write_text(damaged, encoding="utf-8")
        with pytest.raises(portfolio.LedgerError, match="damaged"):
            portfolio.add("AAPL", "buy", 1, 1.0)
        assert path.read_text(encoding="utf-8") == damaged


# --- valuation ----------------------------------------------------------------------------------


def test_position_value_profit_and_weights():
    out = portfolio.value(
        [tx("buy", 10, 100, symbol="AAPL"), tx("buy", 5, 200, symbol="MSFT")],
        {"AAPL": quote(150, change=2), "MSFT": quote(100, change=-1)},
    )
    aapl, msft = out["positions"]
    assert aapl["value"]["value"] == 1500 and aapl["unrealized"]["value"] == 500
    assert aapl["unrealized_pct"]["unit"] == "fraction" and aapl["unrealized_pct"]["value"] == pytest.approx(0.5)
    assert aapl["day_change"]["value"] == 20
    assert aapl["weight"]["value"] == pytest.approx(0.75) and msft["weight"]["value"] == pytest.approx(0.25)
    total = out["totals"][0]
    assert total["complete"] and total["value"]["value"] == 2000 and total["cost_basis"]["value"] == 2000
    assert total["unrealized"]["value"] == 0 and total["day_change"]["value"] == 15
    assert out["risk_holdings"] == [{"symbol": "AAPL", "weight": 75.0}, {"symbol": "MSFT", "weight": 25.0}]
    assert {i["label"] for i in aapl["value"]["inputs"]} == {"AAPL shares held", "Last price"}


def test_a_missing_price_removes_totals_instead_of_understating_them():
    out = portfolio.value([tx("buy", 10, 100, symbol="AAPL"), tx("buy", 5, 200, symbol="MSFT")], {"AAPL": quote(150)})
    total = out["totals"][0]
    assert not total["complete"] and total["missing"] == ["MSFT"]
    assert total["currency"] == "USD"  # MSFT might be in USD too, so even this total can't claim to be whole
    assert "value" not in total and "cost_basis" not in total and "unrealized" not in total and "day_change" not in total
    assert len(out["totals"]) == 1
    assert not any("more than one currency" in w for w in out["warnings"])  # one known currency, one unknown
    assert out["risk_holdings"] is None
    assert any("MSFT" in w for w in out["warnings"])
    msft = next(p for p in out["positions"] if p["symbol"] == "MSFT")
    assert "value" not in msft and msft["cost_basis"]["value"] == 1000


def test_currencies_are_never_added_together():
    out = portfolio.value(
        [tx("buy", 10, 100, symbol="AAPL"), tx("buy", 10, 100, symbol="SHEL.L")],
        {"AAPL": quote(150), "SHEL.L": quote(2500, currency="GBp")},
    )
    assert {t["currency"]: t["value"]["value"] for t in out["totals"]} == {"USD": 1500, "GBp": 25000}
    assert out["risk_holdings"] is None
    assert any("more than one currency" in w for w in out["warnings"])
    assert all(p["weight"]["value"] == 1 for p in out["positions"])


def test_closed_positions_keep_realised_profit():
    out = portfolio.value([tx("buy", 10, 100), tx("sell", 10, 130, "2026-02-01")], {"AAPL": quote(150)})
    assert out["positions"] == []
    assert out["closed"][0]["realized"]["value"] == 300
    assert out["totals"][0]["realized"]["value"] == 300
    assert out["risk_holdings"] is None


def test_gifted_shares_have_no_return_percentage():
    out = portfolio.value([tx("buy", 10, 0)], {"AAPL": quote(150)})
    assert "unrealized_pct" not in out["positions"][0] and "unrealized_pct" not in out["totals"][0]
    assert out["positions"][0]["unrealized"]["value"] == 1500


def test_missing_day_change_only_removes_the_day_total():
    q = quote(150)
    del q["values"]["change"]
    total = portfolio.value([tx("buy", 10, 100)], {"AAPL": q})["totals"][0]
    assert total["value"]["value"] == 1500 and "day_change" not in total


def test_an_empty_ledger_reports_nothing():
    out = portfolio.value([], {})
    assert out["positions"] == [] and out["totals"] == [] and out["risk_holdings"] is None


# --- routes -------------------------------------------------------------------------------------


class Worker:
    def call(self, kind, params=None, timeout=90):
        if params["symbol"] == "DEAD":
            raise WorkerError("no provider could serve quote", [])
        return {"data": {"symbol": params["symbol"], "currency": "USD", "exchange": "X", "fields": {"price": {"value": 150.0, "field": "price"}, "previous_close": {"value": 149.0, "field": "prev"}}},
                "attempts": [{"provider": "t", "ok": True, "error": None, "ms": 1}], "provider": "t", "provider_name": "Test", "fetched_at": "2026-11-05T00:00:00+00:00"}

    def stop(self):
        pass


client = TestClient(app)


@pytest.fixture
def worker():
    market.set_worker(Worker())
    yield
    market.set_worker(None)


def test_routes_add_value_and_delete(worker):
    res = client.post("/portfolio/transactions", json={"symbol": "aapl", "side": "buy", "quantity": 10, "price": 100, "date": "2026-01-01"})
    assert res.status_code == 200
    client.post("/portfolio/transactions", json={"symbol": "DEAD", "side": "buy", "quantity": 1, "price": 5, "date": "2026-01-01"})
    body = client.get("/portfolio").json()
    aapl = next(p for p in body["positions"] if p["symbol"] == "AAPL")
    assert aapl["value"]["value"] == 1500 and aapl["day_change"]["value"] == 10
    assert any("DEAD" in w for w in body["warnings"])
    assert client.delete(f"/portfolio/transactions/{res.json()['id']}").status_code == 200
    assert client.delete("/portfolio/transactions/nope").status_code == 404


def test_routes_explain_refusals(worker):
    res = client.post("/portfolio/transactions", json={"symbol": "AAPL", "side": "sell", "quantity": 1, "price": 1})
    assert res.status_code == 422 and "can't sell" in res.json()["detail"]
    buy = client.post("/portfolio/transactions", json={"symbol": "AAPL", "side": "buy", "quantity": 1, "price": 1, "date": "2026-01-01"}).json()
    client.post("/portfolio/transactions", json={"symbol": "AAPL", "side": "sell", "quantity": 1, "price": 1, "date": "2026-01-02"})
    res = client.delete(f"/portfolio/transactions/{buy['id']}")
    assert res.status_code == 422 and "nothing to sell" in res.json()["detail"]


def test_damaged_ledger_is_reported_not_hidden(worker, data_folder):
    (data_folder / "portfolio.json").write_text("{broken", encoding="utf-8")
    res = client.get("/portfolio")
    assert res.status_code == 500 and "damaged" in res.json()["detail"]


def test_trade_dates_follow_this_computers_calendar_not_utc(data_folder, monkeypatch):
    # The form offers the local date. East of UTC, that is often already tomorrow in UTC terms.
    monkeypatch.setattr(portfolio, "_today", lambda: date(2026, 11, 8))
    assert portfolio.add("AAPL", "buy", 1, 100, day="2026-11-08")["date"] == "2026-11-08"
    assert portfolio.add("AAPL", "buy", 1, 100)["date"] == "2026-11-08"
    with pytest.raises(portfolio.LedgerError, match="future"):
        portfolio.add("AAPL", "buy", 1, 100, day="2026-11-09")
