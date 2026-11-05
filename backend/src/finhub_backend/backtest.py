"""FinHub's backtester: simple strategies, tested in ways that make fooling yourself hard.

Rules this engine enforces (each one closes a common way student and retail backtests go wrong):

1. Next-bar fills. A signal computed from day t's close is traded at day t+1's close, so the
   strategy never trades at the price it used to decide. It first earns the return from close t+1
   to close t+2.
2. Costs on every change of position: commission + slippage in basis points, per unit of turnover.
3. A causality check on every run: signals computed on truncated history must equal the same
   signals computed on full history. If a strategy peeked at the future, they would differ.
4. A benchmark: buy-and-hold over exactly the same days.
5. Walk-forward evaluation: parameters are chosen on past data only, then tested on the next block.
6. Multiple-testing correction: the deflated Sharpe ratio (Bailey & López de Prado, 2014) accounts
   for how many parameter combinations were tried.
7. Warnings for results that should make you suspicious.

Returns are simple daily returns; a position of 1 means fully invested, -1 fully short, 0 cash.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from itertools import product

import numpy as np

TRADING_DAYS = 252
EULER_GAMMA = 0.5772156649015329


# --------------------------------------------------------------------------------------------------
# Strategies: each maps closes -> target position per day, using only data up to that day
# --------------------------------------------------------------------------------------------------


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if n <= len(x):
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1 :] = (c[n:] - c[:-n]) / n
    return out


def sma_cross(closes: np.ndarray, fast: int, slow: int, allow_short: bool = False) -> np.ndarray:
    f, s = _sma(closes, fast), _sma(closes, slow)
    pos = np.where(f > s, 1.0, -1.0 if allow_short else 0.0)
    pos[np.isnan(f) | np.isnan(s)] = 0.0
    return pos


def momentum(closes: np.ndarray, lookback: int, allow_short: bool = False) -> np.ndarray:
    pos = np.zeros(len(closes))
    if lookback < len(closes):
        past = closes[:-lookback]
        ret = closes[lookback:] / past - 1
        pos[lookback:] = np.where(ret > 0, 1.0, -1.0 if allow_short else 0.0)
    return pos


def mean_reversion(closes: np.ndarray, lookback: int, entry_z: float, allow_short: bool = False) -> np.ndarray:
    """Long when price is entry_z standard deviations below its rolling mean; exit at the mean."""
    n = len(closes)
    pos = np.zeros(n)
    mean = _sma(closes, lookback)
    sq = _sma(closes**2, lookback)
    std = np.sqrt(np.maximum(sq - mean**2, 0))
    held = 0.0
    for t in range(n):
        if np.isnan(mean[t]) or std[t] == 0:
            pos[t] = 0.0
            continue
        z = (closes[t] - mean[t]) / std[t]
        if held == 0.0:
            if z < -entry_z:
                held = 1.0
            elif allow_short and z > entry_z:
                held = -1.0
        elif (held > 0 and z >= 0) or (held < 0 and z <= 0):
            held = 0.0
        pos[t] = held
    return pos


def buy_and_hold(closes: np.ndarray) -> np.ndarray:
    return np.ones(len(closes))


@dataclass(frozen=True)
class StrategySpec:
    name: str
    label: str
    params: tuple[str, ...]
    defaults: dict
    grid: dict  # parameter grid for walk-forward
    fn: Callable[..., np.ndarray]
    valid: Callable[[dict], bool] = lambda p: True


STRATEGIES: dict[str, StrategySpec] = {
    "sma": StrategySpec(
        "sma",
        "Moving-average crossover",
        ("fast", "slow"),
        {"fast": 20, "slow": 50},
        {"fast": [5, 10, 20, 50], "slow": [50, 100, 150, 200]},
        sma_cross,
        lambda p: p["fast"] < p["slow"],
    ),
    "momentum": StrategySpec(
        "momentum",
        "Time-series momentum",
        ("lookback",),
        {"lookback": 126},
        {"lookback": [21, 63, 126, 189, 252]},
        momentum,
    ),
    "meanrev": StrategySpec(
        "meanrev",
        "Mean reversion (z-score)",
        ("lookback", "entry_z"),
        {"lookback": 20, "entry_z": 2.0},
        {"lookback": [10, 20, 40], "entry_z": [1.0, 1.5, 2.0, 2.5]},
        mean_reversion,
    ),
}


def signals(spec: StrategySpec, closes: np.ndarray, params: dict, allow_short: bool) -> np.ndarray:
    kwargs = {k: params[k] for k in spec.params}
    if spec.fn is buy_and_hold:
        return buy_and_hold(closes)
    return spec.fn(closes, **kwargs, allow_short=allow_short)


# --------------------------------------------------------------------------------------------------
# Simulation and metrics
# --------------------------------------------------------------------------------------------------


@dataclass
class Run:
    returns: np.ndarray  # net daily strategy returns, aligned with asset returns[1:]
    gross: np.ndarray  # before costs
    position: np.ndarray  # position held over each return
    turnover: np.ndarray


def simulate(closes: np.ndarray, target: np.ndarray, cost_bps: float, slippage_bps: float) -> Run:
    """Apply next-bar fills and costs.

    r[i] is the return from close i to close i+1. target[t] is decided at close t and filled at close
    t+1, so the first return it earns is r[t+1]: the position held over r[i] is target[i-1].
    (Holding target[i] over r[i] would mean trading at the same close used to compute the signal.)
    """
    r = closes[1:] / closes[:-1] - 1
    held = np.zeros(len(r))
    held[1:] = target[: len(r) - 1]
    prev = np.concatenate([[0.0], held[:-1]])
    turnover = np.abs(held - prev)
    cost = turnover * (cost_bps + slippage_bps) / 1e4
    gross = held * r
    # Costs are paid at the fill, before that position earns its first return: (1 - cost)(1 + gross).
    net = (1 - cost) * (1 + gross) - 1
    return Run(returns=net, gross=gross, position=held, turnover=turnover)


def _max_drawdown(rets: np.ndarray) -> float:
    if not len(rets):
        return 0.0
    eq = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    return float(np.min(eq / peak - 1))


def sharpe(rets: np.ndarray) -> float:
    sd = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    return float(np.mean(rets) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else 0.0


def metrics(rets: np.ndarray, position: np.ndarray | None = None, turnover: np.ndarray | None = None) -> dict:
    n = len(rets)
    years = n / TRADING_DAYS if n else 0
    growth = float(np.prod(1 + rets)) if n else 1.0
    cagr = growth ** (1 / years) - 1 if years > 0 and growth > 0 else float("nan")
    vol = float(np.std(rets, ddof=1) * math.sqrt(TRADING_DAYS)) if n > 1 else 0.0
    downside = rets[rets < 0]
    dd = float(np.sqrt(np.mean(downside**2)) * math.sqrt(TRADING_DAYS)) if len(downside) else 0.0
    mdd = _max_drawdown(rets)
    out = {
        "total_return": growth - 1,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe(rets),
        "sortino": float(np.mean(rets) * TRADING_DAYS / dd) if dd > 0 else 0.0,
        "max_drawdown": mdd,
        "calmar": (cagr / abs(mdd)) if mdd < 0 and not math.isnan(cagr) else 0.0,
        "days": n,
        "years": years,
    }
    if position is not None and turnover is not None:
        changes = int(np.count_nonzero(turnover > 1e-12))
        out.update(
            exposure=float(np.mean(np.abs(position) > 0)) if n else 0.0,
            trades=changes,
            turnover_per_year=float(np.sum(turnover) / years) if years > 0 else 0.0,
        )
    return out


# --------------------------------------------------------------------------------------------------
# Validation: causality, walk-forward, deflated Sharpe
# --------------------------------------------------------------------------------------------------


def causality_check(spec: StrategySpec, closes: np.ndarray, params: dict, allow_short: bool, cuts: int = 12) -> bool:
    """Signals on truncated data must match signals on full data at every shared date."""
    full = signals(spec, closes, params, allow_short)
    n = len(closes)
    for k in range(1, cuts + 1):
        cut = max(2, (n * k) // (cuts + 1))
        part = signals(spec, closes[:cut], params, allow_short)
        if not np.array_equal(part, full[:cut]):
            return False
    return True


def norm_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's algorithm, relative error < 1.2e-9)."""
    if not 0 < p < 1:
        raise ValueError("p must be in (0, 1)")
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


def deflated_sharpe(rets: np.ndarray, trial_sharpes_daily: list[float]) -> dict:
    """Probability that the true Sharpe exceeds what the best of N random trials would show by luck.

    Bailey & López de Prado (2014). Sharpe ratios here are per-period (daily), not annualised.
    """
    n_trials = max(1, len(trial_sharpes_daily))
    t = len(rets)
    sd = float(np.std(rets, ddof=1)) if t > 1 else 0.0
    sr = float(np.mean(rets) / sd) if sd > 0 else 0.0
    if t < 3 or sd == 0:
        return {"dsr": float("nan"), "trials": n_trials, "sr0_annual": float("nan")}
    z = (rets - np.mean(rets)) / sd
    skew = float(np.mean(z**3))
    kurt = float(np.mean(z**4))
    var_trials = float(np.var(trial_sharpes_daily, ddof=1)) if n_trials > 1 else 0.0
    if n_trials > 1 and var_trials > 0:
        sr0 = math.sqrt(var_trials) * ((1 - EULER_GAMMA) * norm_ppf(1 - 1 / n_trials) + EULER_GAMMA * norm_ppf(1 - 1 / (n_trials * math.e)))
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    dsr = norm_cdf((sr - sr0) * math.sqrt(t - 1) / denom)
    return {"dsr": dsr, "trials": n_trials, "sr0_annual": sr0 * math.sqrt(TRADING_DAYS), "skew": skew, "kurtosis": kurt}


def _grid(spec: StrategySpec) -> list[dict]:
    keys = list(spec.grid)
    combos = [dict(zip(keys, vals, strict=True)) for vals in product(*(spec.grid[k] for k in keys))]
    return [c for c in combos if spec.valid(c)]


def walk_forward(spec: StrategySpec, closes: np.ndarray, allow_short: bool, cost_bps: float, slippage_bps: float, folds: int = 5) -> dict:
    """Expanding-window walk-forward: pick the best in-sample parameters, test on the next block."""
    grid = _grid(spec)
    n = len(closes)
    first_test = n // (folds + 1)
    if first_test < 260:
        return {"available": False, "reason": "needs at least ~6 years of daily data for 5 folds", "trials": len(grid)}
    # Precompute every parameter set on the full series once: signals are causal (checked above),
    # so slicing the full-series result equals recomputing on the past only.
    runs = {i: simulate(closes, signals(spec, closes, p, allow_short), cost_bps, slippage_bps) for i, p in enumerate(grid)}
    oos: list[np.ndarray] = []
    chosen: list[dict] = []
    edges = [first_test * (k + 1) for k in range(folds)] + [n - 1]
    for k in range(folds):
        train_end, test_end = edges[k], edges[k + 1]
        # returns[i] ends at close i+1: in-sample uses returns ending on or before close train_end.
        best = max(runs, key=lambda i: sharpe(runs[i].returns[:train_end]))
        chosen.append({"fold": k + 1, "params": grid[best], "in_sample_sharpe": sharpe(runs[best].returns[:train_end])})
        oos.append(runs[best].returns[train_end:test_end])
        chosen[-1]["out_of_sample_sharpe"] = sharpe(oos[-1])
    oos_all = np.concatenate(oos) if oos else np.array([])
    trial_sr_daily = [sharpe(r.returns) / math.sqrt(TRADING_DAYS) for r in runs.values()]
    return {
        "available": True,
        "trials": len(grid),
        # Full-sample Sharpe for every combination tried: a robust edge is a plateau, not a lone spike.
        "surface": [{"params": grid[i], "sharpe": sharpe(runs[i].returns)} for i in runs],
        "folds": chosen,
        "out_of_sample": metrics(oos_all),
        "trial_sharpes_daily": trial_sr_daily,
        "oos_start_index": edges[0],
    }


# --------------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------------


@dataclass
class BacktestResult:
    summary: dict
    warnings: list[str] = field(default_factory=list)


def run_backtest(
    dates: list[str],
    closes: list[float],
    strategy: str,
    params: dict | None = None,
    cost_bps: float = 5.0,
    slippage_bps: float = 5.0,
    allow_short: bool = False,
    adjusted: bool = True,
) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {', '.join(STRATEGIES)}")
    spec = STRATEGIES[strategy]
    p = {**spec.defaults, **(params or {})}
    p = {k: (int(v) if isinstance(spec.defaults[k], int) else float(v)) for k, v in p.items() if k in spec.defaults}
    if not spec.valid(p):
        raise ValueError(f"invalid parameters {p}")
    px = np.asarray(closes, dtype=float)
    if len(px) < 60 or np.any(~np.isfinite(px)) or np.any(px <= 0):
        raise ValueError("need at least 60 positive daily closes")

    target = signals(spec, px, p, allow_short)
    run = simulate(px, target, cost_bps, slippage_bps)
    bh = simulate(px, buy_and_hold(px), cost_bps, slippage_bps)
    causal = causality_check(spec, px, p, allow_short)
    wf = walk_forward(spec, px, allow_short, cost_bps, slippage_bps)
    trial_sr = wf.get("trial_sharpes_daily") or [sharpe(run.returns) / math.sqrt(TRADING_DAYS)]
    dsr = deflated_sharpe(run.returns, trial_sr)

    strat_m = metrics(run.returns, run.position, run.turnover)
    gross_m = metrics(run.gross)
    bh_m = metrics(bh.returns, bh.position, bh.turnover)

    warnings: list[str] = []
    if not causal:
        warnings.append("Causality check FAILED: the strategy's signals depend on future data. Do not trust these results.")
    if not adjusted:
        warnings.append("Prices are not adjusted for splits and dividends; a split shows up as a fake crash or jump.")
    jumps = np.abs(px[1:] / px[:-1] - 1)
    if np.any(jumps > 0.4):
        warnings.append(f"{int(np.sum(jumps > 0.4))} daily move(s) larger than 40% in the data: check for splits or bad prices.")
    if strat_m["sharpe"] > 2:
        warnings.append("Sharpe above 2 on a simple daily strategy is very unusual; suspect a data problem or overfitting.")
    if strat_m.get("trades", 0) < 10:
        warnings.append(f"Only {strat_m.get('trades', 0)} position changes: too few to judge the strategy statistically.")
    if strat_m["years"] < 3:
        warnings.append("Less than 3 years of data: results depend heavily on one market regime.")
    if wf.get("available") and wf["out_of_sample"]["sharpe"] < 0.5 * strat_m["sharpe"]:
        warnings.append("Walk-forward Sharpe is less than half the full-sample Sharpe: the chosen parameters probably overfit.")
    if not math.isnan(dsr["dsr"]) and dsr["dsr"] < 0.95:
        warnings.append(
            f"Deflated Sharpe probability {dsr['dsr']:.0%} (< 95%): after accounting for {dsr['trials']} parameter "
            "combinations, this result is consistent with luck."
        )
    if gross_m["sharpe"] - strat_m["sharpe"] > 0.3:
        warnings.append(f"Costs cut the Sharpe ratio from {gross_m['sharpe']:.2f} to {strat_m['sharpe']:.2f}.")

    # Equity curves aligned to dates[1:] (each return ends on that date).
    eq = np.cumprod(1 + run.returns)
    eq_bh = np.cumprod(1 + bh.returns)
    peak = np.maximum.accumulate(eq)
    step = max(1, len(eq) // 600)  # cap points sent to the UI (a chart this size shows ~600 at most)
    curve = [
        {"time": dates[i + 1], "strategy": float(eq[i]), "buy_hold": float(eq_bh[i]), "drawdown": float(eq[i] / peak[i] - 1)}
        for i in range(0, len(eq), step)
    ]
    if curve and curve[-1]["time"] != dates[-1]:
        curve.append({"time": dates[-1], "strategy": float(eq[-1]), "buy_hold": float(eq_bh[-1]), "drawdown": float(eq[-1] / peak[-1] - 1)})

    wf_public = {k: v for k, v in wf.items() if k != "trial_sharpes_daily"}
    if wf.get("available"):
        wf_public["oos_start"] = dates[wf["oos_start_index"]]
    return {
        "strategy": spec.name,
        "label": spec.label,
        "params": p,
        "allow_short": allow_short,
        "costs": {"commission_bps": cost_bps, "slippage_bps": slippage_bps},
        "fills": "Signal at day t close, filled at day t+1 close",
        "period": {"start": dates[0], "end": dates[-1], "days": len(dates)},
        "metrics": {"strategy": strat_m, "strategy_before_costs": gross_m, "buy_hold": bh_m},
        "causality_check": causal,
        "walk_forward": wf_public,
        "deflated_sharpe": dsr,
        "warnings": warnings,
        "curve": curve,
    }


def describe() -> list[dict]:
    return [
        {"name": s.name, "label": s.label, "params": list(s.params), "defaults": s.defaults, "grid": s.grid}
        for s in STRATEGIES.values()
    ]
