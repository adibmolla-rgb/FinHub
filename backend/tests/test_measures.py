import pytest
from fastapi.testclient import TestClient

from finhub_backend import lab, market, research
from finhub_backend.server import app


def vol_answer(**over) -> dict:
    base = {
        "days": 8000, "start": "1993-02-01", "end": "2026-11-06", "current": 0.28, "last_month": 0.19, "sample": 0.18, "long_run": None,
        "persistence": 0.995, "half_life_days": 158.0, "alpha": 0.1, "beta": 0.89,
        "forecasts": [{"days": 1, "annual_volatility": 0.26}, {"days": 21, "annual_volatility": 0.25}],
        "check": {"months": 36, "model_error": 0.05, "naive_error": 0.07, "average_miss": 0.01, "rows": []}, "series": [],
    }
    return {**base, **over}


def test_vol_sends_returns_and_puts_receipts_on_what_it_shows(monkeypatch):
    sent = {}
    monkeypatch.setattr(market, "aligned_closes", lambda symbols, range_: (["2026-01-02", "2026-01-05", "2026-01-06"], [[100.0], [110.0], [99.0]], {"SPY": {"provider": "Yahoo", "adjusted": True, "bars": 3}}))
    monkeypatch.setattr(lab, "run", lambda task, request: sent.update(task=task, **request) or vol_answer())
    out = lab.volatility("spy")
    assert sent["task"] == "volatility" and sent["dates"] == ["2026-01-05", "2026-01-06"]
    assert sent["returns"] == pytest.approx([0.1, -0.1])  # fractions, computed from the raw prices
    assert out["symbol"] == "SPY" and out["current"]["unit"] == "fraction" and out["current"]["value"] == 0.28
    assert "Yahoo" in out["current"]["source"]["detail"]
    assert out["long_run"] is None  # withheld by the engine when the model can't pin it down
    assert out["forecasts"][0]["receipt"]["value"] == 0.26


def test_vol_warns_when_prices_are_not_adjusted(monkeypatch):
    monkeypatch.setattr(market, "aligned_closes", lambda symbols, range_: (["2026-01-02", "2026-01-05"], [[100.0], [110.0]], {"SPY": {"provider": "Cboe", "adjusted": False, "bars": 2}}))
    monkeypatch.setattr(lab, "run", lambda task, request: vol_answer())
    assert any("SPY" in w for w in lab.volatility("SPY")["warnings"])


@pytest.mark.parametrize("args, message", [
    ((4.5, 10, None), "coupon"),  # 4.5 here would be 450%: percent must already have been converted
    ((0.04, 0.1, None), "maturity"),
    ((0.04, 101, None), "maturity"),
    ((0.04, 5, -1.0), "price"),
    ((0.04, 5, 0.0), "price"),
])
def test_bond_refuses_impossible_terms(args, message):
    with pytest.raises(lab.LabError, match=message):
        lab.bond(*args, None, None)


def bond_answer(fair=None) -> dict:
    return {"clean_price": 97.0, "yield": 0.049, "modified_duration": 7.9, "convexity": 75.0, "fair_price": fair}


def test_bond_gets_its_curve_from_the_treasury_and_says_where_it_came_from(monkeypatch):
    sent = {}
    monkeypatch.setattr(research, "yield_curve", lambda: {
        "unit_kind": "fraction", "date": "2026-11-06", "provider_name": "US Treasury",
        "tenors": [{"years": 1 / 12, "latest": {"value": 0.04}}, {"years": 2.0, "latest": {"value": 0.045}}, {"years": 10.0, "latest": {"value": 0.0486}}],
    })
    monkeypatch.setattr(lab, "run", lambda task, request: sent.update(request) or bond_answer(fair=97.0))
    body = TestClient(app).post("/lab/bond", json={"coupon": 0.045, "years": 10}).json()
    assert [p["years"] for p in sent["curve"]] == [2.0, 10.0]  # under 3 months is too short to build a curve on
    assert sent["price"] is None and body["price_given"] is False
    assert "2026-11-06" in body["fair_receipt"]["source"]["detail"] and "US Treasury" in body["fair_receipt"]["source"]["detail"]
    assert body["yield_receipt"]["unit"] == "fraction"


def test_a_curve_with_an_undeclared_unit_is_not_used(monkeypatch):
    # Rule 1: an as-reported number is never treated as a fraction.
    sent = {}
    monkeypatch.setattr(research, "yield_curve", lambda: {"unit_kind": "as_reported", "date": "x", "provider_name": "y", "tenors": [{"years": 2.0, "latest": {"value": 4.5}}]})
    monkeypatch.setattr(lab, "run", lambda task, request: sent.update(request) or bond_answer())
    TestClient(app).post("/lab/bond", json={"coupon": 0.045, "years": 10, "price": 97})
    assert sent["curve"] == []


def test_bond_still_works_with_a_price_when_the_curve_is_down(monkeypatch):
    def down():
        raise market.MarketDataError("down", [])

    monkeypatch.setattr(research, "yield_curve", down)
    monkeypatch.setattr(lab, "run", lambda task, request: bond_answer())
    body = TestClient(app).post("/lab/bond", json={"coupon": 0.045, "years": 10, "price": 97}).json()
    assert body["price_given"] is True and "fair_receipt" not in body


def test_bond_route_refuses_non_numbers():
    assert TestClient(app).post("/lab/bond", json={"coupon": "x", "years": 10}).status_code == 422


def test_mood_reads_headlines_and_gives_each_a_receipt(monkeypatch):
    monkeypatch.setattr(market, "news", lambda symbol, limit: {"provider_name": "Yahoo", "fetched_at": "2026-11-07T08:00:00Z", "items": [
        {"title": "Profits soar", "url": "https://a", "source": "A"}, {"title": None}, {"title": "Profits fall", "url": "https://b", "source": "B"},
    ]})
    sent = {}

    def fake_run(task, request, timeout, engine):
        sent.update(request, task=task, engine=engine)
        return {"model": "ProsusAI/finbert", "rows": [
            {"headline": "Profits soar", "label": "positive", "positive": 0.9, "neutral": 0.08, "negative": 0.02},
            {"headline": "Profits fall", "label": "negative", "positive": 0.03, "neutral": 0.07, "negative": 0.9},
        ]}

    monkeypatch.setattr(lab, "run", fake_run)
    out = lab.mood("aapl")
    assert sent["engine"] == "sentiment" and sent["headlines"] == ["Profits soar", "Profits fall"]  # no empty headline goes in
    assert out["counts"] == {"positive": 1, "neutral": 0, "negative": 1}
    assert out["rows"][1]["url"] == "https://b"  # each answer stays with its own headline
    assert out["rows"][1]["confidence"]["value"] == 0.9 and "Yahoo" in out["rows"][1]["confidence"]["source"]["detail"]


def test_mood_with_no_headlines_says_so(monkeypatch):
    monkeypatch.setattr(market, "news", lambda symbol, limit: {"items": []})
    with pytest.raises(lab.LabError, match="no recent headlines"):
        lab.mood("AAPL")


def test_qlib_receipts_leave_a_missing_number_missing():
    out = lab.qlib_receipts({"stocks": 90, "segments": {"test": ["2024-01-01", "2026-11-06"]}, "test": {"ic": 0.01, "rank_ic": 0.02, "icir": None, "ic_positive": 0.51, "long_short_annual": 0.04, "long_short_t": 1.1, "days": 700}}, "Yahoo")
    assert out["test"]["icir"] is None
    assert out["test"]["long_short_annual"]["unit"] == "fraction" and out["test"]["long_short_t"] == 1.1
    assert "90 large caps" in out["test"]["ic"]["source"]["detail"] and "Yahoo" in out["test"]["ic"]["source"]["detail"]


def test_find_passes_filters_through_and_reports_failures(monkeypatch):
    seen = {}

    def fake_fetch(kind, params, timeout=90.0):
        seen.update(params, kind_of_call=kind)
        return {"data": {"kind": params["kind"], "total": 1, "rows": [{"symbol": "AAPL"}]}, "provider": "financedatabase", "provider_name": "FinanceDatabase", "fetched_at": "t", "attempts": [{"ok": True}]}

    monkeypatch.setattr(market, "_fetch", fake_fetch)
    client = TestClient(app)
    body = client.get("/find", params={"query": "apple", "country": "United States", "limit": 5}).json()
    assert seen["kind_of_call"] == "find_symbols" and seen["query"] == "apple" and seen["country"] == "United States" and seen["limit"] == 5
    assert body["provider_name"] == "FinanceDatabase" and body["rows"] == [{"symbol": "AAPL"}]
    assert client.get("/find", params={"kind": "bonds"}).status_code == 422
    assert client.get("/find", params={"limit": 100000}).status_code == 422
