import pytest

from finhub_backend import fundamentals as fa

META = {"provider": "t", "provider_name": "Test provider", "fetched_at": "2026-11-05T00:00:00+00:00", "attempts": []}


def stmt(rows, periods=("2025-12-31", "2024-12-31"), currency="USD"):
    return {"periods": list(periods), "currency": currency, "rows": [{"field": f, "values": v} for f, v in rows.items()]}


# Yahoo-style names on one statement, SEC/OpenBB-style snake_case on another: both must map.
INCOME = stmt({"Total Revenue": [400.0, 320.0], "Gross Profit": [180.0, 140.0], "Operating Income": [120.0, 90.0], "Net Income Common Stockholders": [100.0, 80.0]})
BALANCE = stmt({"total_assets": [1000.0, 900.0], "total_debt": [150.0, 160.0], "stockholders_equity": [500.0, 450.0], "cash_and_cash_equivalents": [60.0, 50.0]})
CASH = stmt({"Operating Cash Flow": [130.0, 100.0], "Capital Expenditure": [-30.0, -25.0]})


def test_ratios_and_their_receipts():
    r = fa.key_ratios({"income": INCOME, "balance": BALANCE, "cash": CASH}, {"income": META, "balance": META, "cash": META})
    assert r["gross_margin"]["value"] == pytest.approx(0.45)
    assert r["net_margin"]["value"] == pytest.approx(0.25)
    assert r["revenue_growth"]["value"] == pytest.approx(0.25)
    assert r["roe"]["value"] == pytest.approx(0.2)
    assert r["debt_to_equity"]["value"] == pytest.approx(0.3) and r["debt_to_equity"]["unit"] == "ratio"
    assert r["free_cash_flow"]["value"] == pytest.approx(100.0)  # capex sign normalised: 130 - |-30|
    assert r["fcf_margin"]["value"] == pytest.approx(0.25)
    # The receipt names the exact provider field and period behind each input.
    rev = r["gross_margin"]["inputs"][1]
    assert rev["source"]["detail"] == "Total Revenue · period ending 2025-12-31"
    assert r["roe"]["inputs"][1]["source"]["detail"].startswith("stockholders_equity")


def test_missing_inputs_mean_no_ratio_rather_than_a_guess():
    r = fa.key_ratios({"income": stmt({"Total Revenue": [400.0]})}, {"income": META})
    assert set(r) == {"revenue"}


def test_negative_equity_skips_roe():
    bal = stmt({"stockholders_equity": [-50.0], "total_debt": [100.0]})
    r = fa.key_ratios({"income": INCOME, "balance": bal}, {"income": META, "balance": META})
    assert "roe" not in r and "debt_to_equity" not in r
