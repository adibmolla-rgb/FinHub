"""Checks arch and QuantLib against answers worked out by hand. Run in the engine's own environment:
uv run --with pytest pytest -q tests
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location("lab", Path(__file__).resolve().parents[1] / "lab.py")
lab = importlib.util.module_from_spec(spec)
sys.modules["lab"] = lab
spec.loader.exec_module(lab)


def par_curve(rate: float) -> list[dict]:
    return [{"years": y, "rate": rate} for y in (0.5, 1, 2, 3, 5, 7, 10, 20, 30)]


def test_a_bond_at_par_yields_its_coupon_and_matches_the_closed_form_duration():
    out = lab.bond({"coupon": 0.05, "years": 10, "price": 100})
    assert out["yield"] == pytest.approx(0.05, abs=1e-9)
    y, n = 0.05, 20
    assert out["modified_duration"] == pytest.approx((1 / y) * (1 - (1 + y / 2) ** -n), abs=1e-6)
    assert out["cashflow_count"] == 21  # 20 coupons and the principal, with no stray one-day first coupon


def test_a_zero_coupon_bonds_duration_is_its_life():
    out = lab.bond({"coupon": 0.0, "years": 10, "price": 60})
    assert out["macaulay_duration"] == pytest.approx(10, abs=0.01)
    assert out["yield"] == pytest.approx(2 * ((100 / 60) ** (1 / 20) - 1), abs=1e-4)


def test_price_and_yield_move_opposite_ways_and_duration_predicts_it():
    base = lab.bond({"coupon": 0.04, "years": 10, "price": 100})
    cheaper = lab.bond({"coupon": 0.04, "years": 10, "price": 95})
    assert cheaper["yield"] > base["yield"]
    predicted = -base["modified_duration"] * (cheaper["yield"] - base["yield"])
    assert predicted == pytest.approx(-0.05, abs=0.004)


def test_a_bond_paying_the_curves_rate_is_worth_par_on_that_curve():
    out = lab.bond({"coupon": 0.045, "years": 10, "curve": par_curve(0.045)})
    assert out["fair_price"] == pytest.approx(100, abs=0.01)
    assert out["clean_price"] == out["fair_price"]  # with no price given, the curve's value is used
    higher = lab.bond({"coupon": 0.06, "years": 10, "curve": par_curve(0.045)})
    assert higher["fair_price"] > 100


def test_a_given_price_is_kept_apart_from_the_curves_value():
    out = lab.bond({"coupon": 0.045, "years": 10, "price": 90, "curve": par_curve(0.045)})
    assert out["clean_price"] == 90 and out["fair_price"] == pytest.approx(100, abs=0.01)


def test_no_price_and_no_curve_is_refused_rather_than_guessed():
    with pytest.raises(ValueError, match="give a price"):
        lab.bond({"coupon": 0.05, "years": 10})


def garch_returns(n: int, omega=0.02, alpha=0.08, beta=0.85, seed=7) -> list[float]:
    """Returns in percent from a known GARCH(1,1), as fractions."""
    rng = np.random.default_rng(seed)
    variance, out = omega / (1 - alpha - beta), []
    for _ in range(n):
        r = np.sqrt(variance) * rng.standard_normal()
        out.append(r / 100)
        variance = omega + alpha * r * r + beta * variance
    return out


def request(returns: list[float]) -> dict:
    dates = [str(d.date()) for d in __import__("pandas").bdate_range("2000-01-03", periods=len(returns))]
    return {"dates": dates, "returns": returns}


def test_garch_finds_the_parameters_it_was_given():
    out = lab.volatility(request(garch_returns(6000)))
    assert out["alpha"] == pytest.approx(0.08, abs=0.025)
    assert out["beta"] == pytest.approx(0.85, abs=0.05)
    true_long_run = np.sqrt(0.02 / (1 - 0.93) * 252) / 100
    assert out["long_run"] == pytest.approx(true_long_run, abs=0.03)
    assert out["sample"] == pytest.approx(true_long_run, abs=0.03)
    assert out["half_life_days"] == pytest.approx(np.log(0.5) / np.log(out["persistence"]))


def test_its_check_only_uses_the_past_and_gives_every_month():
    out = lab.volatility(request(garch_returns(2000)))
    check = out["check"]
    assert check["months"] == len(check["rows"]) >= 30
    assert check["model_error"] > 0 and check["naive_error"] > 0
    dates = [r["date"] for r in check["rows"]]
    assert dates == sorted(dates) and dates[-1] < out["end"]


def test_a_nearly_permanent_shock_has_no_long_run_level_to_report():
    out = lab.volatility(request(garch_returns(4000, omega=0.002, alpha=0.1, beta=0.897)))
    assert out["persistence"] >= lab.MAX_STABLE_PERSISTENCE and out["long_run"] is None


def test_too_little_history_is_refused():
    with pytest.raises(ValueError, match="at least 750 days"):
        lab.volatility(request(garch_returns(300)))
