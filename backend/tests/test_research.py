from datetime import date

import pytest
from fastapi.testclient import TestClient

from finhub_backend import market, research
from finhub_backend.server import app
from finhub_backend.worker_client import WorkerError

META = {"provider_name": "Test provider", "fetched_at": "2026-11-05T00:00:00+00:00"}
TODAY = date(2026, 11, 6)


def insider(**kw):
    return {
        "date": "2026-11-03", "direction": "Disposition", "security": "Common Stock", "shares": 100.0, "price": 300.0,
        "type": "Open market or private sale of non-derivative or derivative security", "plan_10b5_1": False, **kw,
    }


def test_insider_totals_count_only_real_trades():
    rows = [
        insider(shares=100.0, price=300.0, plan_10b5_1=True),
        insider(shares=300.0, price=310.0),
        insider(direction="Acquisition", shares=50.0, price=290.0, type="Open market or private purchase of security"),
        # None of these is a decision to buy or sell at a price.
        insider(type="Grant, award or other acquisition pursuant to Rule 16b-3(d)", direction="Acquisition", price=0.0),
        insider(type="Payment of exercise price or tax liability by delivering or withholding securities"),
        insider(type="Bona fide gift", price=0.0),
        insider(security="Restricted Stock Unit"),
        insider(date="2026-07-01"),  # older than 90 days
    ]
    out = research.insider_summary(rows, META, TODAY)
    assert out["trades"] == 3
    assert out["sold_shares"]["value"] == 400
    assert out["sold_value"]["value"] == pytest.approx(100 * 300 + 300 * 310)
    assert out["bought_shares"]["value"] == 50
    assert out["bought_value"]["value"] == pytest.approx(50 * 290)
    assert out["sold_on_plan"]["unit"] == "fraction" and out["sold_on_plan"]["value"] == pytest.approx(0.25)


def test_no_insider_totals_when_the_provider_cant_separate_real_trades():
    rows = [{"date": "2026-11-03", "direction": None, "type": "Automatic Sell", "shares": 100.0, "price": 300.0}]
    assert research.insider_summary(rows, META, TODAY) is None


def test_no_plan_share_without_sales():
    assert "sold_on_plan" not in research.insider_summary([insider(direction="Acquisition")], META, TODAY)


def test_short_summary_is_computed_from_raw_counts():
    rows = [{"date": "2026-09-30", "short": 90.0, "previous": 80.0, "avg_volume": 10.0}, {"date": "2026-10-15", "short": 120.0, "previous": 100.0, "avg_volume": 40.0}]
    out = research.short_summary(rows, META)
    assert out["date"] == "2026-10-15"
    assert out["change"]["unit"] == "fraction" and out["change"]["value"] == pytest.approx(0.2)
    assert out["days_to_cover"]["value"] == pytest.approx(3.0)
    assert out["short"]["unit"] == "shares"


def test_short_summary_omits_what_it_cant_compute():
    out = research.short_summary([{"date": "2026-10-15", "short": 120.0, "previous": 0.0, "avg_volume": None}], META)
    assert "change" not in out and "days_to_cover" not in out


def contract(strike, kind, bid=1.0, ask=2.0, iv=0.3, volume=10.0, oi=100.0):
    return {"strike": strike, "type": kind, "bid": bid, "ask": ask, "last": 1.5, "volume": volume, "open_interest": oi, "iv": iv, "delta": 0.5}


def chain(contracts, iv_unit="fraction", spot=100.0):
    return {
        "symbol": "AAPL", "expiration": "2026-12-18", "expirations": ["2026-12-18"], "iv_unit": iv_unit,
        "underlying": {"value": spot, "field": "underlying_price"} if spot else None, "contracts": contracts,
    }


def test_chain_summary_pairs_calls_and_puts():
    out = research.options_view(chain([
        contract(95, "call", iv=0.40, volume=10, oi=100), contract(95, "put", iv=0.42, volume=20, oi=300),
        contract(100, "call", iv=0.30, volume=30, oi=100), contract(100, "put", iv=0.32, volume=60, oi=300),
    ]), META)
    assert [r["strike"] for r in out["rows"]] == [95, 100]
    assert out["rows"][1]["call"]["mid"] == pytest.approx(1.5)
    assert out["summary"]["atm_iv"]["value"] == pytest.approx(0.31)  # the strike at the price, not its neighbour
    assert out["summary"]["put_call_volume"]["value"] == pytest.approx(2.0)
    assert out["summary"]["put_call_oi"]["value"] == pytest.approx(3.0)


def test_chain_ignores_implied_vol_without_a_two_sided_quote():
    out = research.options_view(chain([contract(100, "call", bid=0.0, iv=9.9), contract(105, "call", iv=0.3)]), META)
    assert out["summary"]["atm_iv"]["value"] == pytest.approx(0.3)  # 105 is the nearest strike actually quoted
    assert out["rows"][0]["call"]["mid"] is None
    assert [p["strike"] for p in out["smile"]] == [105]


def test_chain_shows_no_implied_vol_when_its_unit_is_undeclared():
    out = research.options_view(chain([contract(100, "call", iv=30.0), contract(100, "put", iv=31.0)], iv_unit="as_reported"), META)
    assert "atm_iv" not in out["summary"] and out["smile"] == []
    assert out["rows"][0]["call"]["iv"] is None


def test_chain_has_no_put_call_ratio_without_calls():
    out = research.options_view(chain([contract(100, "put")]), META)
    assert "put_call_volume" not in out["summary"]


def treasury(*curves, kind="percent"):
    return {"unit_kind": kind, "unit": "percent, as published", "curves": list(curves)}


def curve(day, y3m=4.0, y2=4.5, y10=4.25):
    return {"date": day, "points": [{"tenor": "3 Mo", "years": 3 / 12, "value": y3m}, {"tenor": "2 Yr", "years": 2.0, "value": y2}, {"tenor": "10 Yr", "years": 10.0, "value": y10}]}


def test_curve_converts_percent_and_finds_inversion():
    out = research.curve_view(treasury(curve("2025-11-03", y10=5.0), curve("2026-10-05", y10=4.1), curve("2026-11-05")), META)
    assert out["unit_kind"] == "fraction"
    ten = out["tenors"][-1]
    assert ten["latest"]["unit"] == "fraction" and ten["latest"]["value"] == pytest.approx(0.0425)
    assert ten["month_ago"] == pytest.approx(0.041) and ten["year_ago"] == pytest.approx(0.05)
    assert out["month_ago_date"] == "2026-10-05" and out["year_ago_date"] == "2025-11-03"
    spread = out["spreads"]["10y_2y"]
    assert spread["unit"] == "bp" and spread["value"] == pytest.approx(-25)
    assert out["spreads"]["10y_3m"]["value"] == pytest.approx(25)
    assert len(spread["inputs"]) == 2


def test_curve_never_converts_an_undeclared_unit():
    out = research.curve_view(treasury(curve("2026-11-05"), kind="as_reported"), META)
    assert out["unit_kind"] == "as_reported" and out["spreads"] == {}
    assert out["tenors"][-1]["latest"]["unit"] == "as_reported" and out["tenors"][-1]["latest"]["value"] == 4.25


def test_curve_without_history_leaves_comparisons_empty():
    out = research.curve_view(treasury(curve("2026-11-05")), META)
    assert out["month_ago_date"] is None and out["tenors"][0]["month_ago"] is None


def test_etf_weights_and_listed_share():
    data = {"symbol": "SPY", "weight_kind": "fraction", "rows": [{"symbol": "AAPL", "name": "Apple", "weight": 0.07}, {"symbol": "MSFT", "name": "Microsoft", "weight": 0.06}]}
    out = research.etf_view(data, META)
    assert out["listed"] == 2 and out["listed_weight"]["value"] == pytest.approx(0.13)
    assert out["rows"][0]["weight"]["source"]["detail"] == "weight"


def test_etf_with_undeclared_weights_stays_as_reported():
    data = {"symbol": "SPY", "weight_kind": "as_reported", "rows": [{"symbol": "AAPL", "name": "Apple", "weight": 7.0}]}
    out = research.etf_view(data, META)
    assert out["rows"][0]["weight"]["unit"] == "as_reported" and "listed_weight" not in out


class FakeWorker:
    """Answers worker calls from a table; anything missing fails as a provider would."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def call(self, kind, params=None, timeout=90):
        self.calls.append((kind, params))
        if kind not in self.answers:
            raise WorkerError(f"no provider could serve {kind}", [{"provider": "test", "ok": False, "error": "down", "ms": 1}])
        return {"data": self.answers[kind], "attempts": [{"provider": "test", "ok": True, "error": None, "ms": 1}], "provider": "test", **META}

    def stop(self):
        pass


@pytest.fixture
def fake(request):
    worker = FakeWorker(getattr(request, "param", {}))
    market.set_worker(worker)
    yield worker
    market.set_worker(None)


client = TestClient(app)
HOLDER = {"owner": "Vanguard", "date": "2026-06-30", "shares": 110.0, "change": 10.0}


@pytest.mark.parametrize("fake", [{"institutional": {"rows": [HOLDER, {**HOLDER, "owner": "New", "shares": 5.0, "change": 5.0}]}}], indirect=True)
def test_one_failed_section_leaves_the_rest_of_the_panel(fake):
    res = client.get("/research/ownership/aapl")
    assert res.status_code == 200
    body = res.json()
    assert "insider" not in body and "short" not in body
    assert set(body["errors"]) == {"insider", "short"}
    assert body["institutional"]["rows"][0]["change_pct"] == pytest.approx(0.1)
    assert body["institutional"]["rows"][1]["change_pct"] is None  # a new holder has no base to compare with


def test_ownership_fails_with_every_attempt_when_nothing_answers(fake):
    res = client.get("/research/ownership/AAPL")
    assert res.status_code == 502
    assert len(res.json()["attempts"]) == 3


EARNINGS = [
    {"date": "2026-11-09", "symbol": "SMALL", "market_cap": 1.0},
    {"date": "2026-11-09", "symbol": "BIG", "market_cap": 9.0},
    {"date": "2026-11-07", "symbol": "LATE", "market_cap": None},
]


@pytest.mark.parametrize("fake", [{"earnings_calendar": {"rows": EARNINGS}, "economic_calendar": {"rows": []}}], indirect=True)
def test_calendar_sorts_filters_and_limits(fake):
    body = client.get("/research/calendar?days=14").json()
    assert [r["symbol"] for r in body["earnings"]["rows"]] == ["LATE", "BIG", "SMALL"]
    assert ("earnings_calendar", {"days": 14}) in fake.calls
    body = client.get("/research/calendar?symbols=small,big&limit=1").json()
    assert [r["symbol"] for r in body["earnings"]["rows"]] == ["BIG"]
    assert body["earnings"]["total"] == 3


def test_research_routes_reject_bad_input(fake):
    assert client.get("/research/options/AAPL?expiration=soon").status_code == 422
    assert client.get("/research/calendar?days=99").status_code == 422
    assert client.get("/research/filings/bad$ymbol").status_code == 422
    assert client.get("/research/calendar?symbols=AAPL,bad$").status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize("fake", [{"yield_curve": treasury(curve("2026-11-05"))}], indirect=True)
def test_yield_curve_route_names_its_source(fake):
    body = client.get("/research/curve").json()
    assert body["provider_name"] == "Test provider" and body["date"] == "2026-11-05"
