import math

import pytest

from finhub_backend import market, research

META = {"provider_name": "Test", "fetched_at": "2026-11-07T00:00:00+00:00"}


def factor_rows(values):
    return [{"date": f"20{20 + i // 12}-{i % 12 + 1:02d}-01", "mkt_rf": v, "smb": None, "hml": None, "rmw": None, "cma": None, "mom": None, "rf": 0.3} for i, v in enumerate(values)]


def test_factor_stats_are_worked_out_from_percent_returns():
    values = [1.0, -1.0, 2.0, 0.0] * 3  # percent per month
    out = research.factors_view({"unit_kind": "percent", "unit": "percent", "rows": factor_rows(values)}, META)
    market_factor = out["factors"][0]
    assert [f["key"] for f in out["factors"]] == ["mkt_rf"]  # factors with no data are left out, not zero
    fractions = [v / 100 for v in values]
    mean = sum(fractions) / 12
    sd = math.sqrt(sum((f - mean) ** 2 for f in fractions) / 11)
    assert market_factor["latest"]["value"] == pytest.approx(0.0)
    assert market_factor["latest"]["unit"] == "fraction"
    assert market_factor["annual_return"]["value"] == pytest.approx(mean * 12)
    assert market_factor["annual_volatility"]["value"] == pytest.approx(sd * math.sqrt(12))
    assert market_factor["t_stat"]["value"] == pytest.approx(mean / (sd / math.sqrt(12)))
    assert market_factor["last_12m"]["value"] == pytest.approx(math.prod(1 + f for f in fractions) - 1)
    assert market_factor["curve"][-1][1] == pytest.approx(math.prod(1 + f for f in fractions))
    assert "Mean monthly return" in market_factor["annual_return"]["formula"]


def test_factor_units_must_be_declared():
    with pytest.raises(ValueError):
        research.factors_view({"unit_kind": "as_reported", "unit": "?", "rows": factor_rows([1.0, 2.0])}, META)


def test_a_short_history_has_no_12_month_figure():
    out = research.factors_view({"unit_kind": "percent", "unit": "percent", "rows": factor_rows([1.0, 2.0, 3.0])}, META)
    assert "last_12m" not in out["factors"][0]


def test_factors_refuse_an_unknown_region():
    with pytest.raises(ValueError, match="region must be"):
        research.factors("MARS")


def cot_data():
    return {
        "query": "gold", "market": "GOLD", "contract": "GOLD", "lookback_weeks": 52,
        "zones": {"large_specs": "neutral", "small_specs": "under-owned", "commercials": "neutral"},
        "matches": [],
        "rows": [
            {"date": "2026-10-27", "open_interest": 400.0, "large_specs_net": 100.0, "small_specs_net": 10.0, "commercials_net": -110.0, "large_specs_score": 30.0, "small_specs_score": 5.0, "commercials_score": 20.0},
            {"date": "2026-11-03", "open_interest": 500.0, "large_specs_net": 150.0, "small_specs_net": None, "commercials_net": -160.0, "large_specs_score": 26.0, "small_specs_score": None, "commercials_score": None},
        ],
    }


def test_cot_shares_come_from_contract_counts():
    out = research.cot_market_view(cot_data(), META)
    large = out["sides"][0]
    assert large["share_of_oi"]["value"] == pytest.approx(0.3)
    assert large["share_of_oi"]["unit"] == "fraction"
    assert large["change_1w"]["value"] == 50
    assert large["score"]["value"] == 26
    assert large["zone"] == "neutral"
    assert [s["key"] for s in out["sides"]] == ["large_specs", "commercials"]  # a missing side is left out
    assert "score" not in out["sides"][1]
    assert out["report_date"] == "2026-11-03"
    assert out["history"][-1]["large_specs"] == pytest.approx(0.3)
    assert out["history"][-1]["small_specs"] is None


def test_cot_overview_converts_percent_once():
    row = {"market": "Gold", "date": "2026-11-03", "open_interest": 10.0, "large_specs_score": 26.1, "large_specs_change": -7.0, "large_specs_pct": 44.98, "large_specs_zone": "neutral",
           "small_specs_score": None, "small_specs_change": None, "small_specs_pct": None, "small_specs_zone": None, "commercials_score": 1.0, "commercials_change": 1.0, "commercials_pct": -51.33, "commercials_zone": "crowded"}
    out = research.cot_overview_view({"rows": [row]})
    sides = out["rows"][0]["sides"]
    assert sides["large_specs"]["share_of_oi"] == pytest.approx(0.4498)
    assert sides["small_specs"]["share_of_oi"] is None
    assert sides["large_specs"]["score"] == 26.1  # a score isn't a percent
    assert out["report_date"] == "2026-11-03"


def fed_results():
    return {
        "fed_rates": {"unit_kind": "fraction", "unit": "fraction", "effr": [{"date": "2026-11-05", "rate": 0.0388, "upper": 0.04, "lower": 0.0375}], "sofr": [{"date": "2026-11-05", "rate": 0.0392}]},
        "fed_money": {"unit": "US dollars", "rows": [{"date": "2025-09-01", "m1": 1.0, "m2": 100.0}, {"date": "2026-09-01", "m1": 2.0, "m2": 105.0}]},
        "fed_expectations": {"unit_kind": "percent", "unit": "percent", "rows": [{"date": "2026-07-01", "cpi_1y": 2.43, "cpi_10y": 2.3}]},
    }


def fake_fetch(results):
    def fetch(kind, params, timeout=90.0):
        if isinstance(results[kind], Exception):
            raise results[kind]
        return {"data": results[kind], "provider": "test", "provider_name": "Test", "fetched_at": "2026-11-07T00:00:00+00:00", "attempts": [{"provider": "test", "ok": True, "ms": 1}]}
    return fetch


def test_fed_figures_and_their_arithmetic(monkeypatch):
    monkeypatch.setattr(market, "_fetch", fake_fetch(fed_results()))
    out = research.fed()
    assert out["errors"] == {}
    assert out["rates"]["effr"]["value"] == pytest.approx(0.0388)
    assert out["rates"]["sofr_minus_effr"]["value"] == pytest.approx(4.0)
    assert out["rates"]["sofr_minus_effr"]["unit"] == "bp"
    assert out["money"]["m2_growth"]["value"] == pytest.approx(0.05)
    assert out["money"]["series"] == [["2026-09-01", pytest.approx(0.05)]]
    assert out["expectations"]["cpi_1y"]["value"] == pytest.approx(0.0243)
    assert out["real_rate"]["value"] == pytest.approx(0.0388 - 0.0243)
    assert len(out["real_rate"]["inputs"]) == 2


def test_fed_panel_survives_one_failed_section_and_omits_what_needs_it(monkeypatch):
    results = fed_results()
    results["fed_expectations"] = market.MarketDataError("down", [{"provider": "test", "ok": False, "error": "down", "ms": 1}])
    monkeypatch.setattr(market, "_fetch", fake_fetch(results))
    out = research.fed()
    assert "expectations" in out["errors"]
    assert "real_rate" not in out
    assert out["rates"]["effr"]["value"] == pytest.approx(0.0388)


def test_fed_fails_when_nothing_answers(monkeypatch):
    failure = market.MarketDataError("down", [{"provider": "test", "ok": False, "error": "down", "ms": 1}])
    monkeypatch.setattr(market, "_fetch", fake_fetch({"fed_rates": failure, "fed_money": failure, "fed_expectations": failure}))
    with pytest.raises(market.MarketDataError):
        research.fed()


def test_undeclared_fed_units_are_refused():
    with pytest.raises(ValueError):
        research.fed_rates_view({"unit_kind": "as_reported", "unit": "?", "effr": [], "sofr": []}, META)


def test_a_section_that_cant_be_read_doesnt_blank_the_fed_panel(monkeypatch):
    results = fed_results()
    results["fed_rates"]["unit_kind"] = "as_reported"
    monkeypatch.setattr(market, "_fetch", fake_fetch(results))
    out = research.fed()
    assert "rates" in out["errors"] and "normalised percent" in out["errors"]["rates"]
    assert out["money"]["m2_growth"]["value"] == pytest.approx(0.05)
    assert "rates" not in out and "real_rate" not in out


def test_unreadable_data_is_a_data_error_with_its_attempts(monkeypatch):
    results = {"cot_market": {"rows": []}, "factors": {"unit_kind": "as_reported", "unit": "?", "rows": factor_rows([1.0, 2.0])}}
    monkeypatch.setattr(market, "_fetch", fake_fetch(results))
    with pytest.raises(market.MarketDataError) as cot_error:
        research.cot("gold")
    assert cot_error.value.attempts
    with pytest.raises(market.MarketDataError):
        research.factors("US")
    results2 = {"fed_rates": {**fed_results()["fed_rates"], "unit_kind": "as_reported"}, "fed_money": {"unit": "x", "rows": []}, "fed_expectations": {"unit_kind": "as_reported", "unit": "x", "rows": []}}
    monkeypatch.setattr(market, "_fetch", fake_fetch(results2))
    with pytest.raises(market.MarketDataError):
        research.fed()


def test_new_panels_use_the_standard_data_timeout(monkeypatch):
    seen = []

    def fetch(kind, params, timeout=90.0):
        seen.append(timeout)
        raise market.MarketDataError("down", [])

    monkeypatch.setattr(market, "_fetch", fetch)
    for call in (lambda: research.factors("US"), lambda: research.cot("gold"), research.cot):
        with pytest.raises(market.MarketDataError):
            call()
    assert seen == [90.0, 90.0, 90.0]


def test_a_note_about_missing_momentum_reaches_the_panel():
    rows = factor_rows([1.0, 2.0])
    out = research.factors_view({"unit_kind": "percent", "unit": "percent", "rows": rows, "momentum_error": "ReadTimeout"}, META)
    assert "ReadTimeout" in out["warnings"][0]
    assert research.factors_view({"unit_kind": "percent", "unit": "percent", "rows": rows}, META)["warnings"] == []


def test_cot_api_accepts_real_contract_names(monkeypatch):
    from fastapi.testclient import TestClient

    from finhub_backend.server import app

    asked = []
    monkeypatch.setattr(research, "cot", lambda name=None: asked.append(name) or {"view": "market"})
    client = TestClient(app)
    assert client.get("/research/cot", params={"market": "MICRO E-MINI DJIA (x$0.5)"}).status_code == 200
    assert asked == ["MICRO E-MINI DJIA (x$0.5)"]
    assert client.get("/research/cot", params={"market": "<script>"}).status_code == 422


def filing_fetch(seen):
    def fetch(kind, params, timeout=90.0):
        seen.update(params, kind=kind)
        return {"data": {"company": "Apple Inc.", "form": "10-K", "filed": "2026-11-03", "accession": "x", "url": None, "sections": [{"id": "Item 1", "title": "Item 1. Business", "text": "Words"}]}, "provider": "edgar", "provider_name": "SEC EDGAR", "fetched_at": "2026-11-07T00:00:00+00:00", "attempts": [{"provider": "edgar", "ok": True, "ms": 1}]}
    return fetch


def test_reading_a_filing_asks_for_an_identity_first_and_never_invents_one(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from finhub_backend import store
    from finhub_backend.server import app

    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    seen = {}
    monkeypatch.setattr(market, "_fetch", filing_fetch(seen))
    client = TestClient(app)
    assert client.get("/settings/sec-identity").json() == {"configured": False}
    refused = client.get("/research/read", params={"symbol": "AAPL"})
    assert refused.status_code == 428 and "READ" in refused.json()["error"]
    assert seen == {}  # nothing goes to the SEC without one

    for body in ({"name": "", "email": "a@b.co"}, {"name": "A", "email": "not-an-email"}, {"name": "A", "email": "a b@c.co"}):
        assert client.put("/settings/sec-identity", json=body).status_code == 422
    assert client.put("/settings/sec-identity", json={"name": " Test  Person ", "email": "test@example.com"}).json() == {"configured": True}
    assert store.get_sec_identity() == {"name": "Test Person", "email": "test@example.com"}
    assert "test@example.com" not in client.get("/settings/sec-identity").text  # the API only says whether one is set

    res = client.get("/research/read", params={"symbol": "AAPL", "form": "10-q"})
    assert res.status_code == 200 and res.json()["sections"][0]["title"] == "Item 1. Business"
    assert seen["identity"] == "Test Person test@example.com" and seen["form"] == "10-Q" and seen["symbol"] == "AAPL"
    assert "test@example.com" not in res.text  # it doesn't come back in the answer

    seen.clear()
    assert client.get("/research/read", params={"accession": "0000320193-26-000026"}).status_code == 200
    assert seen["accession"] == "0000320193-26-000026" and "symbol" not in seen
    assert client.get("/research/read").status_code == 422
    assert client.get("/research/read", params={"accession": "../x"}).status_code == 422
    assert client.get("/research/read", params={"symbol": "<b>"}).status_code == 422


def test_a_damaged_identity_file_means_asking_again(tmp_path, monkeypatch):
    from finhub_backend import store

    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    store._sec_identity_path().write_text("{ not json", encoding="utf-8")
    assert store.get_sec_identity() is None
