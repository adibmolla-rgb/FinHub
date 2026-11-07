"""One analysis at a time, in the agent engine's environment: portfolio tests, performance reports and factor analysis.

Started by the FinHub backend for a single job. It reads one JSON request from stdin and writes one JSON answer to
stdout. Everything here is local maths on data passed in, except `factor`, which loads Vibe-Trading's S&P 500 panel.
No AI model is involved. Units in answers are fractions (0.05 = 5%).
"""

from __future__ import annotations

import math
import sys
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore")

TRADING_DAYS = 252
MAX_STABLE_PERSISTENCE = 0.98
MIN_REPORT_DAYS = 20


def clean(value: Any) -> float | None:
    """A plain float, or None for anything that isn't a real number. Nothing downstream should guess at a NaN."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def series_stats(returns) -> dict:
    """The same arithmetic for every portfolio, so differences come from the portfolios and not the formulas."""
    import numpy as np

    r = np.asarray(returns, dtype=float)
    equity = np.cumprod(1 + r)
    peak = np.maximum.accumulate(np.concatenate(([1.0], equity)))[1:]
    volatility = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
    return {
        "annual_return": clean(equity[-1] ** (TRADING_DAYS / len(r)) - 1),
        "annual_volatility": clean(volatility),
        "sharpe": clean(r.mean() / r.std(ddof=1) * math.sqrt(TRADING_DAYS)) if volatility > 0 else None,
        "max_drawdown": clean((equity / peak - 1).min()),
        "total_return": clean(equity[-1] - 1),
    }


def optimise(request: dict) -> dict:
    """Walk forward: fit on the past year, hold for the next quarter, repeat. Only the held quarters count."""
    import numpy as np
    import pandas as pd
    from skfolio import RiskMeasure
    from skfolio.model_selection import WalkForward, cross_val_predict
    from skfolio.optimization import EqualWeighted, HierarchicalRiskParity, InverseVolatility, MeanRisk, ObjectiveFunction

    symbols = request["symbols"]
    X = pd.DataFrame(request["returns"], index=pd.to_datetime(request["dates"]), columns=symbols)
    train, test = int(request.get("train", TRADING_DAYS)), int(request.get("test", 63))
    if len(X) < train + test:
        raise ValueError(f"needs at least {train + test} shared trading days, and these have {len(X)}")
    cv = WalkForward(train_size=train, test_size=test)
    models = {
        "Equal weights": EqualWeighted(),
        "Inverse volatility": InverseVolatility(),
        "Minimum variance": MeanRisk(risk_measure=RiskMeasure.VARIANCE),
        "Maximum Sharpe": MeanRisk(objective_function=ObjectiveFunction.MAXIMIZE_RATIO, risk_measure=RiskMeasure.VARIANCE),
        "Hierarchical risk parity": HierarchicalRiskParity(),
    }
    rows, problems, held_index = [], [], None
    for name, model in models.items():
        try:
            prediction = cross_val_predict(model, X, cv=cv)
            held = pd.Series(np.asarray(prediction.returns, dtype=float), index=pd.to_datetime(prediction.observations))
            held_index = held.index
            model.fit(X.iloc[-train:])
            rows.append({"name": name, **series_stats(held.to_numpy()), "weights": {s: clean(w) for s, w in zip(symbols, model.weights_)}, "yours": False})
        except Exception as exc:  # noqa: BLE001 - one method failing shouldn't lose the others
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
            if "Maximum Ratio" in str(exc):
                reason = "in at least one year, every asset had a negative expected return, so there was no best ratio to find"
            problems.append({"name": name, "error": reason})
    if held_index is None:
        raise ValueError("no method could be tested: " + "; ".join(p["error"] for p in problems))
    weights = np.asarray(request["weights"], dtype=float)
    yours = X.loc[held_index].to_numpy() @ weights
    rows.append({"name": "Your weights", **series_stats(yours), "weights": {s: clean(w) for s, w in zip(symbols, weights)}, "yours": True})
    rows.sort(key=lambda r: r["sharpe"] if r["sharpe"] is not None else -math.inf, reverse=True)
    return {
        "rows": rows,
        "problems": problems,
        "train_days": train,
        "test_days": test,
        "held_days": len(held_index),
        "windows": cv.get_n_splits(X),
        "start": held_index[0].date().isoformat(),
        "end": held_index[-1].date().isoformat(),
    }


REPORT_METRICS = (
    # key, label, unit, how to get it from quantstats
    ("total_return", "Total return", "fraction", lambda qs, r: qs.stats.comp(r)),
    ("cagr", "Return a year (compound)", "fraction", lambda qs, r: (1 + qs.stats.comp(r)) ** (TRADING_DAYS / len(r)) - 1),
    ("volatility", "Volatility a year", "fraction", lambda qs, r: qs.stats.volatility(r, periods=TRADING_DAYS)),
    ("sharpe", "Sharpe ratio", "ratio", lambda qs, r: qs.stats.sharpe(r, periods=TRADING_DAYS)),
    ("sortino", "Sortino ratio", "ratio", lambda qs, r: qs.stats.sortino(r, periods=TRADING_DAYS)),
    ("max_drawdown", "Maximum drawdown", "fraction", lambda qs, r: qs.stats.max_drawdown(r)),
    ("calmar", "Calmar ratio", "ratio", lambda qs, r: qs.stats.calmar(r)),
    ("skew", "Skew", "ratio", lambda qs, r: qs.stats.skew(r)),
    ("kurtosis", "Kurtosis", "ratio", lambda qs, r: qs.stats.kurtosis(r)),
    ("var", "Daily value at risk (95%)", "fraction", lambda qs, r: qs.stats.value_at_risk(r)),
    ("cvar", "Expected shortfall (95%)", "fraction", lambda qs, r: qs.stats.conditional_value_at_risk(r)),
    ("win_rate", "Winning days", "fraction", lambda qs, r: qs.stats.win_rate(r)),
    ("best_day", "Best day", "fraction", lambda qs, r: qs.stats.best(r)),
    ("worst_day", "Worst day", "fraction", lambda qs, r: qs.stats.worst(r)),
    ("profit_factor", "Profit factor", "ratio", lambda qs, r: qs.stats.profit_factor(r)),
    ("tail_ratio", "Tail ratio", "ratio", lambda qs, r: qs.stats.tail_ratio(r)),
)


def _monthly_table(qs, r) -> list[dict]:
    table = qs.stats.monthly_returns(r)
    return [{"year": int(year), **{str(col): clean(value) for col, value in row.items()}} for year, row in table.sort_index(ascending=False).iterrows()]


def report(request: dict) -> dict:
    import pandas as pd
    import quantstats as qs

    r = pd.Series(request["returns"], index=pd.to_datetime(request["dates"]), dtype=float)
    if len(r) < MIN_REPORT_DAYS:
        raise ValueError(f"needs at least {MIN_REPORT_DAYS} days of returns, and this has {len(r)}")
    metrics = []
    for key, label, unit, get in REPORT_METRICS:
        try:
            value = clean(get(qs, r))
        except Exception:  # noqa: BLE001 - leave out what can't be worked out rather than fail the report
            value = None
        if value is not None:
            metrics.append({"key": key, "label": label, "unit": unit, "value": value})
    out: dict = {"days": len(r), "start": r.index[0].date().isoformat(), "end": r.index[-1].date().isoformat(), "metrics": metrics}
    try:
        out["monthly"] = _monthly_table(qs, r)
    except Exception:  # noqa: BLE001
        out["monthly"] = []
    try:
        details = qs.stats.drawdown_details(qs.stats.to_drawdown_series(r)).sort_values("max drawdown").head(5)
        out["drawdowns"] = [
            {"start": str(d["start"])[:10], "low": str(d["valley"])[:10], "end": str(d["end"])[:10], "days": int(d["days"]), "depth": clean(d["max drawdown"] / 100)}
            for _, d in details.iterrows()
        ]
    except Exception:  # noqa: BLE001
        out["drawdowns"] = []
    if request.get("benchmark"):
        b = pd.Series(request["benchmark"], index=r.index, dtype=float)
        compared = []
        for key, label, unit, get in REPORT_METRICS:
            try:
                value = clean(get(qs, b))
            except Exception:  # noqa: BLE001
                value = None
            if value is not None:
                compared.append({"key": key, "value": value})
        out["benchmark_metrics"] = compared
        relative = []
        try:
            greeks = qs.stats.greeks(r, b, periods=TRADING_DAYS)
            relative += [("alpha", "Alpha a year", "fraction", greeks.get("alpha")), ("beta", "Beta", "ratio", greeks.get("beta"))]
        except Exception:  # noqa: BLE001
            pass
        for key, label, get in (("r_squared", "R-squared", lambda: qs.stats.r_squared(r, b)), ("information_ratio", "Information ratio", lambda: qs.stats.information_ratio(r, b))):
            try:
                relative.append((key, label, "ratio", get()))
            except Exception:  # noqa: BLE001
                pass
        out["relative"] = [{"key": k, "label": label, "unit": unit, "value": clean(v)} for k, label, unit, v in relative if clean(v) is not None]
    return out


def factor(request: dict) -> dict:
    """How a signal behaves: does it separate winners from losers, over which horizon, and at what turnover?"""
    import alphalens as al
    import pandas as pd
    from src.factors.registry import get_default_registry
    from src.tools.alpha_bench_tool import _load_universe_panel

    alpha_id, period = request["alpha_id"], request["period"]
    periods = tuple(request.get("periods", (1, 5, 21)))
    quantiles = int(request.get("quantiles", 5))
    panel = _load_universe_panel("sp500", period)
    meta = panel.get("_meta") or {}
    values = get_default_registry().compute(alpha_id, panel)
    stacked = values.stack().dropna()
    stacked.index.names = ["date", "asset"]
    data = al.utils.get_clean_factor_and_forward_returns(stacked, panel["close"], periods=periods, quantiles=quantiles, max_loss=0.5)
    ic = al.performance.factor_information_coefficient(data)
    means, _ = al.performance.mean_return_by_quantile(data, by_date=False, demeaned=True)
    alpha_beta = al.performance.factor_alpha_beta(data)
    columns = list(ic.columns)
    horizons = []
    for column in columns:
        series = ic[column].dropna()
        horizons.append({
            "horizon": column,
            "ic_mean": clean(series.mean()),
            "ic_std": clean(series.std()),
            "ic_t": clean(series.mean() / (series.std() / math.sqrt(len(series)))) if series.std() > 0 else None,
            "ic_positive": clean((series > 0).mean()),
            "days": len(series),
            "spread": clean(means[column].loc[quantiles] - means[column].loc[1]),
            "annual_alpha": clean(alpha_beta.loc["Ann. alpha", column]),
            "beta": clean(alpha_beta.loc["beta", column]),
        })
    quantile_rows = [{"quantile": int(q), **{c: clean(means.loc[q, c]) for c in columns}} for q in means.index]
    first = periods[0]
    turnover = {
        "top": clean(al.performance.quantile_turnover(data["factor_quantile"], quantiles, first).mean()),
        "bottom": clean(al.performance.quantile_turnover(data["factor_quantile"], 1, first).mean()),
        "rank_autocorrelation": clean(al.performance.factor_rank_autocorrelation(data, first).mean()),
    }
    return {
        "alpha_id": alpha_id,
        "period": period,
        "quantiles": quantiles,
        "observations": len(data),
        "stocks": int(data.index.get_level_values("asset").nunique()),
        "start": str(data.index.get_level_values("date").min())[:10],
        "end": str(data.index.get_level_values("date").max())[:10],
        "horizons": horizons,
        "by_quantile": quantile_rows,
        "turnover": turnover,
        "meta": {k: meta.get(k) for k in ("survivorship_bias", "constituent_source_date", "requested_instruments", "fetched_instruments", "missing_instruments", "price_sources", "degraded") if k in meta},
    }


def volatility(request: dict) -> dict:
    """GARCH(1,1), and whether it actually forecast better than simply assuming the last month carries on."""
    import numpy as np
    import pandas as pd
    from arch import arch_model

    r = pd.Series(request["returns"], index=pd.to_datetime(request["dates"]), dtype=float) * 100  # arch expects percent
    if len(r) < 750:
        raise ValueError(f"needs at least 750 days of returns, and this has {len(r)}")

    def fit(series):
        return arch_model(series, mean="Constant", vol="GARCH", p=1, q=1, dist="t").fit(disp="off", show_warning=False)

    def annual(daily_variance):
        return math.sqrt(daily_variance * TRADING_DAYS) / 100

    result = fit(r)
    alpha, beta, omega = float(result.params["alpha[1]"]), float(result.params["beta[1]"]), float(result.params["omega"])
    persistence = alpha + beta
    variance = result.forecast(horizon=21, reindex=False).variance.iloc[-1].to_numpy()
    forecasts = [{"days": h, "annual_volatility": clean(annual(variance[:h].mean()))} for h in (1, 5, 21)]

    # Every month for up to three years: refit on the past only, forecast the next 21 days, then compare.
    step, errors_model, errors_naive, misses, checks = 21, [], [], [], []
    for end in range(max(500, len(r) - 756), len(r) - step + 1, step):
        past, future = r.iloc[:end], r.iloc[end:end + step]
        realised = float(np.sqrt((future**2).mean() * TRADING_DAYS)) / 100
        naive = float(np.sqrt((past.iloc[-step:] ** 2).mean() * TRADING_DAYS)) / 100
        predicted = annual(fit(past).forecast(horizon=step, reindex=False).variance.iloc[-1].to_numpy().mean())
        errors_model.append((predicted - realised) ** 2)
        errors_naive.append((naive - realised) ** 2)
        misses.append(predicted - realised)
        checks.append({"date": str(past.index[-1])[:10], "forecast": clean(predicted), "naive": clean(naive), "realised": clean(realised)})
    conditional = result.conditional_volatility * math.sqrt(TRADING_DAYS) / 100
    return {
        "days": len(r),
        "start": str(r.index[0])[:10],
        "end": str(r.index[-1])[:10],
        "current": clean(conditional.iloc[-1]),
        "last_month": clean(math.sqrt((r.iloc[-21:] ** 2).mean() * TRADING_DAYS) / 100),
        # Close to 1 this formula divides by almost nothing, and it can land well away from the history's own figure.
        "long_run": clean(annual(omega / (1 - persistence))) if persistence < MAX_STABLE_PERSISTENCE else None,
        "sample": clean(r.std() * math.sqrt(TRADING_DAYS) / 100),
        "persistence": clean(persistence),
        "half_life_days": clean(math.log(0.5) / math.log(persistence)) if 0 < persistence < 1 else None,
        "alpha": clean(alpha),
        "beta": clean(beta),
        "forecasts": forecasts,
        "check": {
            "months": len(checks),
            "model_error": clean(math.sqrt(np.mean(errors_model))) if errors_model else None,
            "naive_error": clean(math.sqrt(np.mean(errors_naive))) if errors_naive else None,
            "average_miss": clean(np.mean(misses)) if misses else None,
            "rows": checks,
        },
        "series": [[str(d)[:10], clean(v)] for d, v in conditional.iloc[-756:].items()],
    }


def bond(request: dict) -> dict:
    """A fixed-rate bond: yield and price from each other, its sensitivities, and its value on a yield curve."""
    import QuantLib as ql

    coupon, years, frequency = float(request["coupon"]), float(request["years"]), int(request.get("frequency", 2))
    today = ql.Date.todaysDate()
    ql.Settings.instance().evaluationDate = today
    calendar = ql.UnitedStates(ql.UnitedStates.GovernmentBond)
    settle = calendar.advance(today, 1, ql.Days)
    period = ql.Period(12 // frequency, ql.Months)

    def schedule_for(months: int):
        # Exactly N months on, not moved to a business day: that would leave a one-day first coupon.
        maturity = settle + ql.Period(months, ql.Months)
        return ql.MakeSchedule(settle, maturity, period, calendar=calendar, convention=ql.Unadjusted, terminalDateConvention=ql.Unadjusted, rule=ql.DateGeneration.Backward)

    schedule = schedule_for(round(years * 12))
    counting = ql.ActualActual(ql.ActualActual.Bond, schedule)
    instrument = ql.FixedRateBond(1, 100.0, schedule, [coupon], counting, ql.Unadjusted)

    fair = None
    curve_points = request.get("curve") or []
    if curve_points:
        helpers = []
        for point in curve_points:
            months = round(point["years"] * 12)
            if months < 1:
                continue
            sched = schedule_for(months)
            helpers.append(ql.FixedRateBondHelper(ql.QuoteHandle(ql.SimpleQuote(100.0)), 1, 100.0, sched, [point["rate"]], ql.ActualActual(ql.ActualActual.Bond, sched), ql.Unadjusted))
        curve = ql.PiecewiseLogCubicDiscount(settle, helpers, ql.Actual365Fixed())
        curve.enableExtrapolation()
        instrument.setPricingEngine(ql.DiscountingBondEngine(ql.YieldTermStructureHandle(curve)))
        fair = instrument.cleanPrice()

    price = request.get("price")
    price = float(price) if price is not None else fair
    if price is None:
        raise ValueError("give a price, as no yield curve was available to value it on")
    ytm = instrument.bondYield(ql.BondPrice(price, ql.BondPrice.Clean), counting, ql.Compounded, frequency)
    rate = ql.InterestRate(ytm, counting, ql.Compounded, frequency)
    flows = [{"date": c.date().ISO(), "amount": clean(c.amount())} for c in instrument.cashflows() if c.date() > settle]
    return {
        "coupon": clean(coupon),
        "years": clean(years),
        "frequency": frequency,
        "settlement": settle.ISO(),
        "maturity": instrument.maturityDate().ISO(),
        "clean_price": clean(price),
        "accrued": clean(instrument.accruedAmount()),
        "dirty_price": clean(price + instrument.accruedAmount()),
        "yield": clean(ytm),
        "macaulay_duration": clean(ql.BondFunctions.duration(instrument, rate, ql.Duration.Macaulay)),
        "modified_duration": clean(ql.BondFunctions.duration(instrument, rate, ql.Duration.Modified)),
        "convexity": clean(ql.BondFunctions.convexity(instrument, rate)),
        "dv01": clean(abs(ql.BondFunctions.basisPointValue(instrument, rate))),
        "fair_price": clean(fair),
        "cashflows": flows[:12],
        "cashflow_count": len(flows),
    }


TASKS = {"optimise": optimise, "report": report, "factor": factor, "volatility": volatility, "bond": bond}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from job_runner import run

    raise SystemExit(run(TASKS, "agent"))
