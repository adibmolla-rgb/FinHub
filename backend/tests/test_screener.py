import pytest

from finhub_backend import market, screener


def quote(price, change, cap, high, low):
    v = {
        "price": {"value": price}, "change_pct": {"value": change}, "market_cap": {"value": cap},
        "year_low": {"value": low}, "from_high_pct": {"value": price / high - 1},
    }
    return {"values": v, "currency": "USD", "provider_name": "Test"}


def test_filters_and_missing_data_fails_rather_than_passes():
    row = screener.row_from_quote("A", quote(95, 0.03, 2e12, 100, 50), "Information Technology")
    assert row["from_low_pct"] == pytest.approx(0.9)
    assert screener.passes(row, screener.Filters(min_change=0.02, max_from_high=0.06, min_market_cap=1e12))
    assert not screener.passes(row, screener.Filters(max_from_high=0.04))  # 5% below the high
    assert not screener.passes(row, screener.Filters(sectors=("Energy",)))
    sparse = {"symbol": "B", "price": 10, "change_pct": None, "market_cap": None}
    assert not screener.passes(sparse, screener.Filters(min_market_cap=1))
    assert screener.passes(sparse, screener.Filters(min_price=5))


def test_screen_reports_failures_and_sorts_by_size(monkeypatch, tmp_path):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    screener._cache.clear()
    data = {"AAA": quote(10, 0.01, 5e9, 12, 8), "BBB": quote(20, -0.02, 9e9, 21, 10)}

    def fake(sym):
        if sym not in data:
            raise market.MarketDataError("no provider could serve quote", [])
        return data[sym]

    monkeypatch.setattr(market, "quote", fake)
    out = screener.screen("custom", screener.Filters(), ["aaa", "bbb", "ccc"])
    assert [r["symbol"] for r in out["matches"]] == ["BBB", "AAA"]
    assert out["failed"][0]["symbol"] == "CCC"
    with pytest.raises(ValueError):
        screener.screen("custom", screener.Filters(), ["../x"])


def test_built_in_universe_covers_all_sectors():
    assert len(set(screener.LARGE_CAPS.values())) == 11
    assert len(screener.LARGE_CAPS) >= 55
