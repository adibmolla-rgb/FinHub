import json
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from finhub_backend import agent, market, paper
from finhub_backend.server import app

ACCOUNT = "a" * 32


def new_york(day: str, hour: int, minute: int = 0) -> datetime:
    return datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:00").replace(tzinfo=paper.NEW_YORK).astimezone(UTC)


@pytest.mark.parametrize(
    "placed, fills",
    [
        (new_york("2026-11-04", 10), "2026-11-04"),  # Wednesday, market open: today's close is still ahead
        (new_york("2026-11-04", 15, 59), "2026-11-04"),
        (new_york("2026-11-04", 16), "2026-11-05"),  # the close has happened, so the price is known
        (new_york("2026-11-04", 23), "2026-11-05"),
        (new_york("2026-11-06", 17), "2026-11-09"),  # Friday evening goes to Monday
        (new_york("2026-11-07", 12), "2026-11-09"),  # Saturday
        (new_york("2026-11-08", 12), "2026-11-09"),  # Sunday
        (new_york("2026-11-09", 8), "2026-11-09"),  # before Monday's open
        (new_york("2026-07-01", 15, 30), "2026-07-01"),  # summer time
    ],
)
def test_an_order_always_fills_at_a_close_still_ahead(placed, fills):
    assert paper.fill_day(placed).isoformat() == fills


def test_fill_day_uses_new_york_time_not_the_computers():
    # 20:30 in London on a Wednesday in November is 15:30 in New York, before the close.
    assert paper.fill_day(datetime(2026, 11, 4, 20, 30, tzinfo=UTC)) == date(2026, 11, 4)
    # 21:30 in London is 16:30 in New York, after it.
    assert paper.fill_day(datetime(2026, 11, 4, 21, 30, tzinfo=UTC)) == date(2026, 11, 5)


@pytest.mark.parametrize(
    "now, settled",
    [
        (new_york("2026-11-04", 16, 29), "2026-11-03"),
        (new_york("2026-11-04", 16, 30), "2026-11-04"),
        (new_york("2026-11-07", 12), "2026-11-06"),  # Saturday
        (new_york("2026-11-09", 9), "2026-11-06"),  # Monday morning
    ],
)
def test_latest_settled_day(now, settled):
    assert paper.latest_settled_day(now).isoformat() == settled


class Ledger:
    """Stands in for Vibe-Trading's ledger, including its habit of filling at the close of whatever day it's given."""

    def __init__(self, start_on="2026-11-02"):
        self.account = {
            "id": ACCOUNT, "label": "Test", "market": "us", "currency": "USD", "created_at": "2026-11-02T00:00:00+00:00", "start_on": start_on,
            "last_date": None, "revision": 0, "initial_state": {"cash": 1000.0, "positions": []}, "account_state": {"cash": 1000.0, "positions": []},
        }
        self.history = []
        self.calls = []  # (day, orders)
        self.holidays = set()
        self.not_ready = set()

    def __call__(self, method, path, timeout=120.0, **kwargs):
        if path == "/api/paper-accounts" and method == "GET":
            return [self.account]
        if path.endswith("/history"):
            return self.history
        if method == "GET":
            return json.loads(json.dumps(self.account))
        body = kwargs["json"]
        assert body["expected_revision"] == self.account["revision"], "stale revision"
        day = body["to_date"]
        self.calls.append((day, body["orders"]))
        if day in self.not_ready:
            return {"account": self.account, "committed": False, "result": {"code": "PAPER_DATA_NOT_READY", "message": "no bar yet"}}
        if day in self.holidays:
            return {"account": self.account, "committed": False, "result": {"nav_series": [], "fills": []}}
        self.account.update(last_date=day, revision=self.account["revision"] + 1)
        step = {"fills": [], "rejected_orders": [], "nav_series": [{"date": day, "nav": 1000.0}], "data_provenance": {"source": "test"}}
        self.history.append(step)
        return {"account": json.loads(json.dumps(self.account)), "committed": True, "result": step}


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    fake = Ledger()
    monkeypatch.setattr(agent, "call_engine", fake)
    monkeypatch.setattr(market, "quote", lambda s: {"currency": "USD", "values": {"price": {"value": 100.0, "unit": "currency", "currency": "USD", "label": "Last price"}}})
    return fake


def order(symbol="AAPL", side="buy", quantity=1.0, fill_day="2026-11-04", id="o" * 12):
    return {"id": id, "account_id": ACCOUNT, "symbol": symbol, "side": side, "quantity": quantity, "placed_at": "2026-11-03T22:00:00+00:00", "fill_day": fill_day}


def test_an_order_placed_after_the_close_cant_fill_at_that_close(ledger, monkeypatch):
    monkeypatch.setattr(paper, "_now", lambda: new_york("2026-11-04", 17))
    placed = paper.place(ACCOUNT, "aapl", "buy", 2)
    assert placed["fill_day"] == "2026-11-05"
    paper.settle(ACCOUNT, new_york("2026-11-04", 17))  # 4 Nov has closed, but this order must not use it
    assert all(orders == [] for _, orders in ledger.calls)
    assert paper._load() == [placed]
    paper.settle(ACCOUNT, new_york("2026-11-05", 17))
    assert ledger.calls[-1] == ("2026-11-05", [{"symbol": "AAPL.US", "side": "buy", "qty": 2.0}])
    assert paper._load() == []


def test_an_order_waits_until_its_close_can_settle(ledger):
    paper._save([order(fill_day="2026-11-04")])
    paper.settle(ACCOUNT, new_york("2026-11-04", 16, 29))
    assert all(orders == [] for _, orders in ledger.calls)
    assert len(paper._load()) == 1


def test_orders_settle_day_by_day_then_the_account_is_valued(ledger):
    paper._save([order(id="a" * 12, fill_day="2026-11-03"), order(id="b" * 12, symbol="MSFT", fill_day="2026-11-04")])
    assert paper.settle(ACCOUNT, new_york("2026-11-06", 17)) is None
    assert [(day, [o["symbol"] for o in orders]) for day, orders in ledger.calls] == [("2026-11-03", ["AAPL.US"]), ("2026-11-04", ["MSFT.US"]), ("2026-11-06", [])]
    assert paper._load() == []


def test_an_order_due_on_a_holiday_moves_to_the_next_session(ledger):
    ledger.holidays = {"2026-11-03"}
    paper._save([order(fill_day="2026-11-03")])
    assert paper.settle(ACCOUNT, new_york("2026-11-06", 17)) is None
    assert ledger.calls[:2] == [("2026-11-03", [{"symbol": "AAPL.US", "side": "buy", "qty": 1.0}]), ("2026-11-04", [{"symbol": "AAPL.US", "side": "buy", "qty": 1.0}])]
    assert paper._load() == []


def test_a_settled_order_fills_no_earlier_than_the_ledger_allows(ledger):
    ledger.account["last_date"] = "2026-11-05"
    paper._save([order(fill_day="2026-11-03")])
    paper.settle(ACCOUNT, new_york("2026-11-06", 17))
    assert ledger.calls[0][0] == "2026-11-06"


def test_when_data_isnt_ready_nothing_is_lost(ledger):
    ledger.not_ready = {"2026-11-04"}
    paper._save([order(fill_day="2026-11-04")])
    note = paper.settle(ACCOUNT, new_york("2026-11-06", 17))
    assert "AAPL" in note and "no bar yet" in note
    assert len(paper._load()) == 1
    assert ledger.account["last_date"] is None


def test_other_accounts_orders_are_left_alone(ledger):
    other = {**order(id="c" * 12, fill_day="2026-11-03"), "account_id": "b" * 32}
    paper._save([other])
    paper.settle(ACCOUNT, new_york("2026-11-06", 17))
    assert paper._load() == [other]


@pytest.mark.parametrize(
    "symbol, side, quantity, message",
    [
        ("<b>", "buy", 1, "US ticker"),
        ("AAPL", "short", 1, "buy or sell"),
        ("AAPL", "buy", 0, "whole number"),
        ("AAPL", "buy", -1, "whole number"),
        ("AAPL", "buy", 1.5, "whole number"),
        ("AAPL", "buy", 1e12, "whole number"),
    ],
)
def test_bad_orders_are_refused(ledger, symbol, side, quantity, message):
    with pytest.raises(paper.PaperError, match=message):
        paper.place(ACCOUNT, symbol, side, quantity)
    assert paper._load() == []


def test_tickers_that_cant_be_priced_or_arent_usd_are_refused_up_front(ledger, monkeypatch):
    def no_quote(symbol):
        raise market.MarketDataError("down", [])

    monkeypatch.setattr(market, "quote", no_quote)
    with pytest.raises(paper.PaperError, match="no quote"):
        paper.place(ACCOUNT, "ZZZZ", "buy", 1)
    monkeypatch.setattr(market, "quote", lambda s: {"currency": "GBp"})
    with pytest.raises(paper.PaperError, match="US stocks"):
        paper.place(ACCOUNT, "VOD", "buy", 1)
    assert paper._load() == []


def test_a_suffix_from_the_ledger_is_accepted_once():
    assert paper.clean_symbol(" brk-b ") == "BRK-B"
    assert paper.clean_symbol("AAPL.US") == "AAPL"


def test_share_classes_are_spelled_the_way_the_ledger_knows_them(ledger):
    # Sent as BRK-B.US, the ledger says unknown_symbol and refuses the order.
    assert paper.to_ledger("BRK-B") == "BRK.B.US"
    assert paper.from_ledger("BRK.B.US") == "BRK-B"
    assert paper.from_ledger(paper.to_ledger("AAPL")) == "AAPL"
    paper._save([order(symbol="BRK-B")])
    paper.settle(ACCOUNT, new_york("2026-11-04", 17))
    assert ledger.calls[0][1][0]["symbol"] == "BRK.B.US"


def test_a_damaged_orders_file_is_reported_and_kept(ledger):
    paper._path().write_text("{ not json", encoding="utf-8")
    with pytest.raises(paper.PaperError, match="damaged") as caught:
        paper.place(ACCOUNT, "AAPL", "buy", 1)
    assert caught.value.status == 500
    assert paper._path().read_text(encoding="utf-8") == "{ not json"


def test_cancel(ledger):
    paper._save([order()])
    assert paper.cancel("nope") is False
    assert paper.cancel("o" * 12) is True
    assert paper._load() == []


def test_figures_and_a_position_with_no_price():
    account = {
        "id": ACCOUNT, "label": "T", "currency": "USD", "created_at": "2026-11-02", "start_on": "2026-11-02", "last_date": "2026-11-03",
        "initial_state": {"cash": 1000.0, "positions": []},
        "account_state": {"cash": 500.0, "positions": [{"symbol": "AAPL.US", "qty": 2.0, "avg_cost": 100.0}, {"symbol": "ZZZ.US", "qty": 1.0, "avg_cost": 300.0}]},
    }
    history = [
        {"nav_series": [{"date": "2026-11-02", "nav": 1000.0}], "fills": [], "rejected_orders": [], "data_provenance": {"source": "unavailable"}},
        {
            "nav_series": [{"date": "2026-11-03", "nav": 1100.0}],
            "fills": [{"trade_date": "2026-11-03", "symbol": "AAPL.US", "side": "buy", "qty": 2.0, "price": 100.0, "fee": 0.99}],
            "rejected_orders": [{"trade_date": "2026-11-03", "symbol": "TSLA.US", "side": "buy", "qty": 99.0, "detail": "buy cost exceeds cash"}],
            "data_provenance": {"source": "sina"},
        },
    ]
    out = paper.account_view(account, history, [], {"AAPL": {"value": 150.0, "unit": "currency", "currency": "USD", "label": "Last price"}})
    assert out["value"]["value"] == 1100
    assert out["profit"]["value"] == 100
    assert out["return"]["value"] == pytest.approx(0.1)
    assert out["fees"]["value"] == pytest.approx(0.99)
    assert "sina" in out["value"]["source"]["detail"]
    assert out["nav"] == [["2026-11-02", 1000.0], ["2026-11-03", 1100.0]]
    aapl, zzz = out["positions"]
    assert (aapl["symbol"], aapl["value"], aapl["profit"]) == ("AAPL", 300.0, 100.0)
    assert (zzz["price"], zzz["value"], zzz["profit"]) == (None, None, None)  # no price, no guess
    assert out["rejected"][0]["reason"] == "buy cost exceeds cash"


def test_a_new_account_shows_no_value_until_a_close_settles():
    account = {"id": ACCOUNT, "label": "T", "currency": "USD", "created_at": "x", "start_on": "2026-11-09", "last_date": None, "initial_state": {"cash": 1000.0, "positions": []}, "account_state": {"cash": 1000.0, "positions": []}}
    out = paper.account_view(account, [], [], {})
    assert "value" not in out and "return" not in out
    assert out["cash"]["value"] == 1000


def test_routes(ledger, monkeypatch):
    monkeypatch.setattr(paper, "_now", lambda: new_york("2026-11-04", 17))
    client = TestClient(app)
    assert client.get("/paper/accounts").json()[0]["pending"] == 0
    placed = client.post(f"/paper/accounts/{ACCOUNT}/orders", json={"symbol": "AAPL", "side": "buy", "quantity": 1})
    assert placed.status_code == 200 and placed.json()["fill_day"] == "2026-11-05"
    assert client.get("/paper/accounts").json()[0]["pending"] == 1
    assert client.post(f"/paper/accounts/{ACCOUNT}/orders", json={"symbol": "AAPL", "side": "buy", "quantity": 0.5}).status_code == 422
    assert client.get("/paper/accounts/not-an-id").status_code == 422
    assert client.delete(f"/paper/orders/{placed.json()['id']}").status_code == 200
    assert client.delete(f"/paper/orders/{placed.json()['id']}").status_code == 404


def test_routes_explain_when_the_engine_isnt_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))

    def missing(*args, **kwargs):
        raise agent.AgentNotReady("the reasoning-agent engine (Vibe-Trading) is not installed; install it from SYS")

    monkeypatch.setattr(agent, "call_engine", missing)
    res = TestClient(app).get("/paper/accounts")
    assert res.status_code == 503 and "install it from SYS" in res.json()["error"]
