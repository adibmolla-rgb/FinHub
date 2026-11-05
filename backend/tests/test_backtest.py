"""Backtester tests on synthetic prices, where the right answer is known exactly."""

import math

import numpy as np
import pytest

from finhub_backend import backtest as bt


def dates(n):
    return [f"2020-01-{i:02d}" if i < 32 else f"d{i}" for i in range(1, n + 1)]


def gbm(n, drift=0.0, vol=0.01, seed=0):
    rng = np.random.default_rng(seed)
    return 100 * np.cumprod(np.concatenate([[1.0], 1 + drift + vol * rng.standard_normal(n - 1)]))


def test_next_bar_fill_timing_is_exact():
    closes = np.array([100, 110, 121, 133.1, 146.41])  # +10% every day
    target = np.array([0, 1, 0, 0, 0], dtype=float)  # decide to be long at close 1 only
    run = bt.simulate(closes, target, 0, 0)
    # Decided at close 1, filled at close 1+1=2, so it earns exactly one return: close 2 -> close 3.
    assert run.position.tolist() == [0, 0, 1, 0]
    assert run.returns == pytest.approx([0, 0, 0.1, 0])


def test_costs_charged_per_unit_of_turnover():
    closes = np.full(6, 100.0)
    target = np.array([1, 0, 1, 0, 0, 0], dtype=float)
    run = bt.simulate(closes, target, cost_bps=5, slippage_bps=5)
    assert run.turnover.sum() == 4  # in, out, in, out
    assert run.returns.sum() == pytest.approx(-4 * 10 / 1e4)


def test_causality_check_catches_a_strategy_that_peeks():
    peek = bt.StrategySpec("peek", "peek", (), {}, {}, lambda c, allow_short=False: np.append((np.diff(c) > 0).astype(float), 0.0))
    closes = gbm(400, seed=1)
    assert bt.causality_check(peek, closes, {}, False) is False
    for spec in bt.STRATEGIES.values():
        assert bt.causality_check(spec, closes, spec.defaults, True) is True


def test_peeking_cannot_profit_through_next_bar_fills():
    # Even a signal equal to the *current* day's return (a peek at today) earns nothing systematic
    # once it is filled at the next bar, because returns here are independent.
    closes = gbm(5000, seed=2)
    r = closes[1:] / closes[:-1] - 1
    target = np.append((r > 0).astype(float), 0.0)
    assert abs(bt.sharpe(bt.simulate(closes, target, 0, 0).returns)) < 0.6


def test_buy_and_hold_matches_price_change_minus_entry_cost():
    closes = gbm(300, drift=0.0005, seed=3)
    run = bt.simulate(closes, bt.buy_and_hold(closes), cost_bps=5, slippage_bps=5)
    # Filled at close 1, so it earns close 1 -> last close, minus one entry cost.
    assert np.prod(1 + run.returns) == pytest.approx(closes[-1] / closes[1] * (1 - 10 / 1e4), rel=1e-12)


def test_sma_and_momentum_signals():
    closes = np.concatenate([np.linspace(100, 50, 100), np.linspace(50, 150, 100)])
    pos = bt.sma_cross(closes, 5, 20)
    assert pos[50] == 0 and pos[190] == 1
    assert bt.sma_cross(closes, 5, 20, allow_short=True)[50] == -1
    mom = bt.momentum(closes, 10)
    assert mom[5] == 0 and mom[190] == 1


def test_mean_reversion_enters_below_band_and_exits_at_mean():
    closes = np.array([100.0] * 25 + [90.0] + [100.0] * 5)
    closes[:25] += np.tile([0.5, -0.5], 13)[:25]
    pos = bt.mean_reversion(closes, 20, 2.0)
    assert pos[25] == 1  # far below the mean: long
    assert pos[27] == 0  # back at/above the mean: flat


def test_deflated_sharpe_falls_as_trials_rise():
    rets = gbm(1500, drift=0.0006, seed=4)
    rets = rets[1:] / rets[:-1] - 1
    rng = np.random.default_rng(5)
    few = bt.deflated_sharpe(rets, list(rng.normal(0, 0.02, 3)))
    many = bt.deflated_sharpe(rets, list(rng.normal(0, 0.02, 300)))
    assert many["dsr"] < few["dsr"]
    assert 0 <= many["dsr"] <= 1


def test_norm_ppf_inverts_cdf():
    for p in [1e-6, 0.01, 0.2, 0.5, 0.9, 0.999]:
        assert bt.norm_cdf(bt.norm_ppf(p)) == pytest.approx(p, rel=1e-7)


def test_walk_forward_on_a_random_walk_finds_nothing():
    closes = gbm(2520, seed=6)  # 10 years, no edge by construction
    res = bt.run_backtest(dates(2520), closes.tolist(), "sma", {"fast": 20, "slow": 100})
    wf = res["walk_forward"]
    assert wf["available"] and wf["trials"] == 15  # 4 x 4 grid minus the one fast >= slow pair (50, 50)
    assert abs(wf["out_of_sample"]["sharpe"]) < 1.0
    assert res["causality_check"] is True


def test_warnings_flag_suspicious_inputs():
    smooth = 100 * np.cumprod(np.full(800, 1.002))  # a straight line up: Sharpe is enormous
    smooth[400:] *= 0.25  # and a fake 4-for-1 "split"
    res = bt.run_backtest(dates(800), smooth.tolist(), "momentum", {"lookback": 21}, adjusted=False)
    text = " ".join(res["warnings"])
    assert "not adjusted" in text and "40%" in text


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        bt.run_backtest(dates(10), [100.0] * 10, "sma")
    with pytest.raises(ValueError):
        bt.run_backtest(dates(100), [100.0] * 100, "nope")
    with pytest.raises(ValueError):
        bt.run_backtest(dates(100), [100.0] * 100, "sma", {"fast": 50, "slow": 20})


def test_walk_forward_reports_the_full_parameter_surface():
    closes = gbm(2520, seed=8)
    wf = bt.run_backtest(dates(2520), closes.tolist(), "momentum", {"lookback": 63})["walk_forward"]
    assert [row["params"]["lookback"] for row in wf["surface"]] == [21, 63, 126, 189, 252]
    assert all(isinstance(row["sharpe"], float) for row in wf["surface"])
