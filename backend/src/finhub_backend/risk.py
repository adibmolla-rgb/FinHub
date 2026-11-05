"""Portfolio risk: VaR and Expected Shortfall three ways, a VaR backtest, and honest optimisation.

All returns are simple daily returns; the portfolio is rebalanced daily to the target weights.
Losses are reported as positive fractions of portfolio value (0.02 = a 2% loss).
"""

from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252


def norm_ppf(p: float) -> float:
    from finhub_backend.backtest import norm_ppf as ppf

    return ppf(p)


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


# --------------------------------------------------------------------------------------------------
# VaR and ES
# --------------------------------------------------------------------------------------------------


def historical_var_es(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """Empirical loss quantile and the mean loss beyond it."""
    losses = -np.asarray(r)
    var = float(np.quantile(losses, alpha))
    tail = losses[losses >= var]
    return var, float(tail.mean()) if len(tail) else var


def parametric_var_es(r: np.ndarray, alpha: float) -> tuple[float, float]:
    """Normal distribution with the sample mean and standard deviation."""
    mu, sd = float(np.mean(r)), float(np.std(r, ddof=1))
    z = norm_ppf(alpha)
    return -mu + z * sd, -mu + sd * norm_pdf(z) / (1 - alpha)


def monte_carlo_var_es(returns: np.ndarray, weights: np.ndarray, alpha: float, n: int = 100_000, seed: int = 7) -> tuple[float, float]:
    """Multivariate normal on the assets (keeps correlations), then aggregate to the portfolio."""
    rng = np.random.default_rng(seed)
    mu = returns.mean(axis=0)
    cov = np.cov(returns, rowvar=False)
    sims = rng.multivariate_normal(mu, np.atleast_2d(cov), size=n, method="eigh") @ weights
    return historical_var_es(sims, alpha)


# --------------------------------------------------------------------------------------------------
# VaR backtest (Kupiec proportion-of-failures test)
# --------------------------------------------------------------------------------------------------


def chi2_sf_1(x: float) -> float:
    """Survival function of chi-square with 1 degree of freedom."""
    return math.erfc(math.sqrt(max(x, 0) / 2))


def kupiec(exceptions: int, days: int, alpha: float) -> dict:
    """Does the number of VaR breaches match the expected rate (1 - alpha)?"""
    p = 1 - alpha
    x, t = exceptions, days
    if t == 0:
        return {"lr": float("nan"), "p_value": float("nan")}

    def ll(prob: float) -> float:
        a = (t - x) * math.log(1 - prob) if x < t else 0.0
        b = x * math.log(prob) if x > 0 else 0.0
        return a + b

    phat = x / t
    lr = -2 * (ll(p) - (ll(phat) if 0 < phat < 1 else 0.0))
    return {"lr": lr, "p_value": chi2_sf_1(lr)}


def var_backtest(r: np.ndarray, alpha: float, window: int = 250) -> dict:
    """Each day, forecast tomorrow's historical VaR from the previous `window` days, then count breaches."""
    r = np.asarray(r)
    if len(r) <= window + 20:
        return {"available": False, "reason": f"needs more than {window + 20} days of data"}
    breaches = []
    for t in range(window, len(r)):
        var_t, _ = historical_var_es(r[t - window : t], alpha)
        breaches.append(-r[t] > var_t)
    days = len(breaches)
    x = int(np.sum(breaches))
    k = kupiec(x, days, alpha)
    expected = (1 - alpha) * days
    return {
        "available": True,
        "window": window,
        "days": days,
        "exceptions": x,
        "expected": expected,
        "p_value": k["p_value"],
        "verdict": "consistent" if k["p_value"] >= 0.05 else ("too many breaches: VaR underestimates risk" if x > expected else "too few breaches: VaR is too conservative"),
    }


# --------------------------------------------------------------------------------------------------
# Optimisation on the long-only simplex
# --------------------------------------------------------------------------------------------------


def project_simplex(v: np.ndarray) -> np.ndarray:
    """Euclidean projection onto {w : w >= 0, sum w = 1} (Duchi et al., 2008)."""
    n = len(v)
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, n + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1)
    return np.maximum(v - theta, 0)


def min_variance(cov: np.ndarray, iters: int = 5000) -> np.ndarray:
    n = cov.shape[0]
    w = np.full(n, 1 / n)
    step = 1 / (2 * np.linalg.norm(cov, 2) + 1e-18)
    for _ in range(iters):
        w = project_simplex(w - step * 2 * cov @ w)
    return w


def max_sharpe(mu: np.ndarray, cov: np.ndarray, iters: int = 4000) -> np.ndarray:
    """Maximise mu.w / sqrt(w.Σ.w) on the simplex by projected gradient ascent."""
    n = len(mu)
    if np.all(mu <= 0):
        return min_variance(cov)
    w = np.full(n, 1 / n)
    step = 0.5 / (np.linalg.norm(cov, 2) / max(float(np.max(np.abs(mu))), 1e-12) + 1)
    best, best_s = w, -np.inf
    for _ in range(iters):
        s2 = float(w @ cov @ w)
        s = math.sqrt(max(s2, 1e-18))
        ret = float(mu @ w)
        grad = mu / s - ret * (cov @ w) / (s2 * s)
        w = project_simplex(w + step * grad * s)
        sr = float(mu @ w) / math.sqrt(max(float(w @ cov @ w), 1e-18))
        if sr > best_s:
            best, best_s = w.copy(), sr
    return best


def bootstrap_weights(returns: np.ndarray, samples: int = 60, seed: int = 3) -> dict:
    """Re-estimate optimal weights on resampled history to show how unstable they are."""
    rng = np.random.default_rng(seed)
    t = len(returns)
    mv, ms = [], []
    for _ in range(samples):
        idx = rng.integers(0, t, t)
        r = returns[idx]
        cov = np.cov(r, rowvar=False) * TRADING_DAYS
        mu = r.mean(axis=0) * TRADING_DAYS
        mv.append(min_variance(np.atleast_2d(cov), 1500))
        ms.append(max_sharpe(mu, np.atleast_2d(cov), 1500))
    return {"min_variance_sd": np.std(mv, axis=0), "max_sharpe_sd": np.std(ms, axis=0)}


# --------------------------------------------------------------------------------------------------
# Full analysis
# --------------------------------------------------------------------------------------------------


def _max_drawdown(r: np.ndarray) -> float:
    eq = np.cumprod(1 + r)
    peak = np.maximum.accumulate(np.concatenate([[1.0], eq]))[1:]
    return float(np.min(eq / peak - 1))


def _worst(r: np.ndarray, dates: list[str], horizon: int) -> dict:
    if len(r) < horizon:
        return {}
    growth = np.array([np.prod(1 + r[i : i + horizon]) - 1 for i in range(len(r) - horizon + 1)])
    i = int(np.argmin(growth))
    return {"return": float(growth[i]), "start": dates[i], "end": dates[i + horizon - 1]}


def analyse(symbols: list[str], weights: list[float], dates: list[str], returns: np.ndarray, confidence: float = 0.99, value: float = 10_000.0) -> dict:
    """returns: (days, assets) simple daily returns aligned on `dates` (each return ends on that date)."""
    w = np.asarray(weights, dtype=float)
    if np.any(w < 0) or w.sum() <= 0:
        raise ValueError("weights must be non-negative and not all zero")
    w = w / w.sum()
    R = np.asarray(returns, dtype=float)
    if R.ndim != 2 or R.shape[1] != len(symbols) or R.shape[0] < 60:
        raise ValueError("need at least 60 days of returns for every holding")
    port = R @ w
    alpha = confidence

    hv, he = historical_var_es(port, alpha)
    pv, pe = parametric_var_es(port, alpha)
    mv, me = monte_carlo_var_es(R, w, alpha)

    cov_d = np.atleast_2d(np.cov(R, rowvar=False))
    cov = cov_d * TRADING_DAYS
    mu = R.mean(axis=0) * TRADING_DAYS
    vol_assets = np.sqrt(np.diag(cov))
    port_var = float(w @ cov @ w)
    port_vol = math.sqrt(port_var)
    contrib = w * (cov @ w) / port_var if port_var > 0 else np.zeros_like(w)
    corr = cov / np.outer(vol_assets, vol_assets) if np.all(vol_assets > 0) else np.eye(len(w))

    w_mv = min_variance(cov)
    w_ms = max_sharpe(mu, cov)
    boot = bootstrap_weights(R)

    def stats(wt: np.ndarray) -> dict:
        v = math.sqrt(float(wt @ cov @ wt))
        m = float(mu @ wt)
        return {"weights": wt.tolist(), "expected_return": m, "volatility": v, "sharpe": m / v if v > 0 else 0.0}

    skew = float(np.mean(((port - port.mean()) / port.std()) ** 3))
    kurt = float(np.mean(((port - port.mean()) / port.std()) ** 4))
    warnings: list[str] = []
    if kurt > 4:
        warnings.append(f"Fat tails (kurtosis {kurt:.1f} vs 3 for a normal): the parametric VaR likely understates extreme losses.")
    if max(boot["max_sharpe_sd"]) > 0.15:
        warnings.append(
            "The max-Sharpe weights are unstable: on resampled history they move by up to "
            f"±{max(boot['max_sharpe_sd']):.0%}. Expected returns are estimated very imprecisely; treat these weights as illustrative."
        )
    if len(port) < 500:
        warnings.append("Less than 2 years of data: risk estimates come from a single market regime.")

    hist_bins = np.histogram(port, bins=60)
    return {
        "symbols": symbols,
        "weights": w.tolist(),
        "period": {"start": dates[0], "end": dates[-1], "days": len(port)},
        "confidence": confidence,
        "value": value,
        "var": {
            "historical": {"var": hv, "es": he},
            "parametric": {"var": pv, "es": pe},
            "monte_carlo": {"var": mv, "es": me},
        },
        "var_backtest": var_backtest(port, alpha),
        "portfolio": {
            "volatility": port_vol,
            "expected_return": float(mu @ w),
            "max_drawdown": _max_drawdown(port),
            "skew": skew,
            "kurtosis": kurt,
            "worst_day": _worst(port, dates, 1),
            "worst_week": _worst(port, dates, 5),
            "worst_month": _worst(port, dates, 21),
        },
        "assets": [
            {"symbol": s, "weight": float(w[i]), "volatility": float(vol_assets[i]), "expected_return": float(mu[i]), "risk_contribution": float(contrib[i])}
            for i, s in enumerate(symbols)
        ],
        "correlation": corr.tolist(),
        "optimisation": {
            "current": stats(w),
            "min_variance": {**stats(w_mv), "weight_sd": boot["min_variance_sd"].tolist()},
            "max_sharpe": {**stats(w_ms), "weight_sd": boot["max_sharpe_sd"].tolist()},
        },
        "histogram": {"counts": hist_bins[0].tolist(), "edges": hist_bins[1].tolist()},
        "warnings": warnings,
    }
