"""Risk tests on synthetic returns, where the true answer is known."""

import math

import numpy as np
import pytest

from finhub_backend import risk


def normal_returns(n, mu=0.0, sd=0.01, seed=0):
    return np.random.default_rng(seed).normal(mu, sd, n)


def test_var_methods_agree_on_normal_data():
    r = normal_returns(200_000, sd=0.01)
    hv, he = risk.historical_var_es(r, 0.99)
    pv, pe = risk.parametric_var_es(r, 0.99)
    assert hv == pytest.approx(2.326 * 0.01, rel=0.02)
    assert pv == pytest.approx(hv, rel=0.02)
    assert pe == pytest.approx(0.01 * risk.norm_pdf(2.3263) / 0.01, rel=0.02)  # ES of N(0,1) at 99% ≈ 2.665σ
    assert he > hv


def test_monte_carlo_keeps_correlation():
    rng = np.random.default_rng(1)
    z = rng.standard_normal(5000)
    R = np.column_stack([0.01 * z, 0.01 * z])  # perfectly correlated: no diversification
    mv, _ = risk.monte_carlo_var_es(R, np.array([0.5, 0.5]), 0.99)
    single, _ = risk.parametric_var_es(R[:, 0], 0.99)
    assert mv == pytest.approx(single, rel=0.05)


def test_kupiec_accepts_a_correct_model_and_rejects_a_bad_one():
    assert risk.kupiec(10, 1000, 0.99)["p_value"] > 0.5  # exactly the expected count
    assert risk.kupiec(30, 1000, 0.99)["p_value"] < 0.001  # three times too many breaches
    # Reference: LR for 20 breaches in 1000 days at 99% is about 7.83.
    assert risk.kupiec(20, 1000, 0.99)["lr"] == pytest.approx(7.83, abs=0.05)


def test_var_backtest_flags_fat_tails():
    rng = np.random.default_rng(2)
    calm = rng.normal(0, 0.005, 600)
    wild = rng.standard_t(2, 600) * 0.02  # regime change: historical VaR from the calm period breaks
    res = risk.var_backtest(np.concatenate([calm, wild]), 0.99)
    assert res["available"] and res["exceptions"] > res["expected"]
    assert res["p_value"] < 0.05


def test_simplex_projection():
    w = risk.project_simplex(np.array([0.8, 0.6, -0.5]))
    assert w.sum() == pytest.approx(1) and np.all(w >= 0)
    assert risk.project_simplex(np.array([0.2, 0.3, 0.5])) == pytest.approx([0.2, 0.3, 0.5])


def test_min_variance_matches_inverse_variance_for_uncorrelated_assets():
    cov = np.diag([0.04, 0.01, 0.09])
    w = risk.min_variance(cov)
    inv = 1 / np.diag(cov)
    assert w == pytest.approx(inv / inv.sum(), abs=1e-4)


def test_max_sharpe_matches_closed_form_when_long_only_is_not_binding():
    mu = np.array([0.08, 0.10, 0.12])
    cov = np.array([[0.04, 0.006, 0.004], [0.006, 0.05, 0.01], [0.004, 0.01, 0.07]])
    raw = np.linalg.solve(cov, mu)
    tangency = raw / raw.sum()
    assert np.all(tangency > 0)
    assert risk.max_sharpe(mu, cov) == pytest.approx(tangency, abs=2e-3)


def test_analyse_end_to_end():
    rng = np.random.default_rng(4)
    n = 800
    z = rng.standard_normal((n, 2))
    R = np.column_stack([0.0004 + 0.012 * z[:, 0], 0.0002 + 0.006 * (0.3 * z[:, 0] + math.sqrt(1 - 0.09) * z[:, 1])])
    dates = [f"d{i}" for i in range(n)]
    out = risk.analyse(["A", "B"], [60, 40], dates, R, confidence=0.95)
    assert out["weights"] == pytest.approx([0.6, 0.4])
    assert sum(a["risk_contribution"] for a in out["assets"]) == pytest.approx(1)
    assert out["correlation"][0][1] == pytest.approx(0.3, abs=0.08)
    v = out["var"]
    assert 0 < v["historical"]["var"] < v["historical"]["es"]
    assert v["parametric"]["var"] == pytest.approx(v["historical"]["var"], rel=0.2)
    assert out["var_backtest"]["available"]
    assert out["optimisation"]["min_variance"]["volatility"] <= out["optimisation"]["current"]["volatility"] + 1e-9


def test_rejects_bad_weights():
    with pytest.raises(ValueError):
        risk.analyse(["A"], [-1], ["d"] * 100, np.zeros((100, 1)))
