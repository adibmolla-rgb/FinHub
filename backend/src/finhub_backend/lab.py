"""OPTIM and REPORT, and the analysis behind ALPHA's deep look: skfolio, QuantStats and Alphalens.

These libraries need pandas and more, so they live in the agent engine's environment and the backend stays numpy-only.
Each job is one short-lived process (engines/vibe-trading/lab.py). None of them uses an AI model.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import threading

from finhub_backend import agent, engines, installer, market
from finhub_backend.receipts import Quantity, Source, Unit

ENGINE = "vibe-trading"
MAX_POINTS = 30_000


class LabError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def run(task: str, request: dict, timeout: float = 300.0, engine: str = ENGINE, extra_env: dict[str, str] | None = None) -> dict:
    """One job in an engine's own environment. API keys only go to a job that's explicitly given one."""
    if installer.state(engine).state == "running":
        raise LabError(f"the {engine} engine is updating; try again in a few minutes", status=503)
    python = engines.engine_python(engine)
    if not python.exists():
        what = "the agent engine (no AI provider required)" if engine == ENGINE else f"the optional {engine} engine"
        raise LabError(f"this needs {what}; install it from SYS", status=503)
    script = engines.engines_dir() / engine / ("lab.py" if engine == ENGINE else "job.py")
    work = agent.data_dir() / engine
    work.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(VIBE_TRADING_HOME=str(work), HF_HOME=str(work / "models"), HF_HUB_DISABLE_SYMLINKS_WARNING="1", PYTHONIOENCODING="utf-8", **(extra_env or {}))
    proc = subprocess.Popen(
        [str(python), str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", cwd=work, env=env, **engines.NO_WINDOW,
    )
    outputs: dict[str, str] = {}

    def read(name: str, stream) -> None:
        outputs[name] = stream.read()

    readers = [threading.Thread(target=read, args=item, daemon=True) for item in (("out", proc.stdout), ("err", proc.stderr))]
    for reader in readers:
        reader.start()
    try:
        # The pipe stays open until the job ends: if this backend goes away, it closes and the job stops itself.
        proc.stdin.write(json.dumps({**request, "task": task, "lifeline": True}) + "\n")
        proc.stdin.flush()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise LabError(f"this took more than {timeout / 60:.0f} minutes and was stopped", status=504) from exc
    except OSError:
        pass  # it had already stopped; what it said is read below
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        for reader in readers:
            reader.join(timeout=5)
        try:
            proc.stdin.close()
        except OSError:
            pass
    try:
        answer = json.loads(outputs.get("out", ""))
    except ValueError as exc:
        raise LabError(f"the analysis stopped unexpectedly: {outputs.get('err', '')[-300:].strip() or 'no output'}", status=502) from exc
    if not answer.get("ok"):
        raise LabError(str(answer.get("error", "the analysis failed")).removeprefix("ValueError: "))
    return answer["result"]


def _returns(closes: list[float]) -> list[float]:
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]


def _price_warnings(origins: dict[str, dict]) -> list[str]:
    unadjusted = [s for s, o in origins.items() if not o["adjusted"]]
    if not unadjusted:
        return []
    return [f"Prices for {', '.join(unadjusted)} aren't adjusted for splits and dividends, so a split shows up as a fake crash."]


def _receipt(value: float, unit: str, label: str, formula: str, detail: str, tool: str) -> dict:
    return Quantity(
        value=value, unit=Unit.FRACTION if unit == "fraction" else Unit.RATIO, label=label,
        source=Source(provider=f"computed by FinHub with {tool}", detail=detail), formula=formula,
    ).receipt()


# --------------------------------------------------------------------------------------------------
# OPTIM: does a way of choosing weights hold up on data it hasn't seen?
# --------------------------------------------------------------------------------------------------


def optimise(holdings: list[dict], range_: str = "MAX") -> dict:
    symbols = [h["symbol"].upper() for h in holdings]
    if len(set(symbols)) != len(symbols):
        raise LabError("each ticker can appear only once")
    if len(symbols) < 2:
        raise LabError("OPTIM needs at least two tickers")
    total = sum(h["weight"] for h in holdings)
    weights = [h["weight"] / total for h in holdings]
    dates, closes, origins = market.aligned_closes(symbols, range_)
    by_symbol = [_returns([row[i] for row in closes]) for i in range(len(symbols))]
    returns = [list(row) for row in zip(*by_symbol)]
    out = run("optimise", {"symbols": symbols, "dates": dates[1:], "returns": returns, "weights": weights})
    window = f"{out['start']} to {out['end']}, {out['held_days']} days held out of sample"
    detail = "dividend-adjusted prices from " + ", ".join(sorted({o["provider"] for o in origins.values()}))
    fields = (
        ("annual_return", "fraction", "return a year", "Compound return of the held days, annualised"),
        ("annual_volatility", "fraction", "volatility a year", "Standard deviation of held daily returns × √252"),
        ("sharpe", "ratio", "Sharpe ratio", "Mean ÷ standard deviation of held daily returns × √252, risk-free rate 0"),
        ("max_drawdown", "fraction", "maximum drawdown", "Largest fall from a peak in the held days"),
    )
    for row in out["rows"]:
        for key, unit, name, formula in fields:
            if row.get(key) is not None:
                row[key] = _receipt(row[key], unit, f"{row['name']}: {name}", f"{formula} ({window})", detail, "skfolio")
    return {**out, "symbols": symbols, "range": range_, "warnings": _price_warnings(origins)}


# --------------------------------------------------------------------------------------------------
# VOL: GARCH volatility, and whether it beats a simple guess
# --------------------------------------------------------------------------------------------------


def volatility(symbol: str, range_: str = "MAX") -> dict:
    symbol = symbol.upper()
    dates, closes, origins = market.aligned_closes([symbol], range_)
    out = run("volatility", {"dates": dates[1:], "returns": _returns([row[0] for row in closes])})
    detail = "dividend-adjusted prices from " + ", ".join(sorted({o["provider"] for o in origins.values()}))
    window = f"GARCH(1,1) with fat tails, fitted on {out['start']} to {out['end']}"
    for key, name, formula in (
        ("current", "Current volatility", f"Model's volatility today, annualised ({window})"),
        ("last_month", "Volatility over the last month", "Root mean squared daily return over 21 days × √252"),
        ("sample", "Volatility over all the history", f"Standard deviation of daily returns × √252 ({out['start']} to {out['end']})"),
        ("long_run", "Long-run volatility", f"√(ω ÷ (1 − α − β)), annualised ({window})"),
    ):
        if out.get(key) is not None:
            out[key] = _receipt(out[key], "fraction", f"{symbol}: {name}", formula, detail, "arch")
    for row in out["forecasts"]:
        row["receipt"] = _receipt(row["annual_volatility"], "fraction", f"{symbol}: forecast volatility, next {row['days']} days", f"Average forecast variance over {row['days']} days, annualised ({window})", detail, "arch")
    return {**out, "symbol": symbol, "warnings": _price_warnings(origins)}


# --------------------------------------------------------------------------------------------------
# BOND: QuantLib's fixed-income maths
# --------------------------------------------------------------------------------------------------


def bond(coupon: float, years: float, price: float | None, curve: list[dict] | None, curve_detail: str | None) -> dict:
    if not (0 <= coupon <= 0.5):
        raise LabError("the coupon must be between 0% and 50%")
    if not (0.25 <= years <= 100):
        raise LabError("the maturity must be between 3 months and 100 years")
    if price is not None and not (0 < price <= 1000):
        raise LabError("the price is per 100 of face value, so it must be between 0 and 1,000")
    out = run("bond", {"coupon": coupon, "years": years, "price": price, "curve": curve or []})
    label = f"{coupon * 100:g}% {years:g}-year bond"
    detail = "QuantLib fixed-rate bond, semi-annual coupons, Actual/Actual (Bond)"
    out["yield_receipt"] = _receipt(out["yield"], "fraction", f"{label}: yield to maturity", f"Yield that discounts the coupons and principal to a clean price of {out['clean_price']:.4f}", detail, "QuantLib")
    out["modified_receipt"] = _receipt(out["modified_duration"], "ratio", f"{label}: modified duration", "% fall in price for a 1 point rise in yield", detail, "QuantLib")
    out["convexity_receipt"] = _receipt(out["convexity"], "ratio", f"{label}: convexity", "How duration itself changes as the yield moves", detail, "QuantLib")
    if out.get("fair_price") is not None:
        out["fair_receipt"] = _receipt(out["fair_price"], "ratio", f"{label}: value on the Treasury curve", "Coupons and principal discounted on a curve built from Treasury par yields", curve_detail or detail, "QuantLib")
    return {**out, "label": label, "price_given": price is not None}


# --------------------------------------------------------------------------------------------------
# MOOD: finBERT on the latest headlines
# --------------------------------------------------------------------------------------------------


def mood(symbol: str) -> dict:
    symbol = symbol.upper()
    news = market.news(symbol, 30)
    items = [i for i in news.get("items", []) if i.get("title")]
    if not items:
        raise LabError(f"no recent headlines for {symbol}")
    # The first use downloads the model, which is about 420 MB.
    out = run("mood", {"headlines": [i["title"] for i in items]}, timeout=1800.0, engine="sentiment")
    detail = f"{out['model']} on the headline, which came from {news.get('provider_name')} at {news.get('fetched_at')}"

    def confidence(row: dict) -> dict:
        return _receipt(row[row["label"]], "fraction", f"finBERT's confidence that this headline is {row['label']}", "The model's probability for its chosen tone (the three add up to 1)", detail, "finBERT")

    rows = [{**row, "confidence": confidence(row), "url": item.get("url"), "source": item.get("source"), "published": item.get("published")} for row, item in zip(out["rows"], items)]
    counts = {label: sum(1 for r in rows if r["label"] == label) for label in ("positive", "neutral", "negative")}
    return {"symbol": symbol, "rows": rows, "counts": counts, "model": out["model"], "news_provider": news.get("provider_name"), "fetched_at": news.get("fetched_at")}


# --------------------------------------------------------------------------------------------------
# QLIB: receipts for what Microsoft's workflow measured
# --------------------------------------------------------------------------------------------------


def qlib_receipts(out: dict, price_provider: str) -> dict:
    test, window = dict(out["test"]), f"{out['segments']['test'][0]} to {out['segments']['test'][1]}"
    detail = f"{out['stocks']} large caps, adjusted prices from {price_provider}, Alpha158 features, LightGBM, tested on {window}"
    for key, label, unit, formula in (
        ("ic", "Information coefficient", "ratio", "Daily correlation of predictions with the return from the next close to the one after, averaged"),
        ("rank_ic", "Rank information coefficient", "ratio", "Daily rank correlation of predictions with the return from the next close to the one after, averaged"),
        ("icir", "ICIR", "ratio", "Average daily information coefficient ÷ its standard deviation"),
        ("ic_positive", "Days with a positive information coefficient", "fraction", "Days with a positive coefficient ÷ all days tested"),
        ("long_short_annual", "Top 5 minus bottom 5, a year", "fraction", "Average daily return of the 5 highest minus the 5 lowest predictions × 252, before costs"),
    ):
        test[key] = _receipt(test[key], unit, label, formula, detail, "Qlib") if test.get(key) is not None else None
    return {**out, "test": test, "price_provider": price_provider}


# --------------------------------------------------------------------------------------------------
# REPORT: performance statistics for any series of returns
# --------------------------------------------------------------------------------------------------


def report_returns(label: str, dates: list[str], returns: list[float], benchmark: list[float] | None, benchmark_label: str | None, detail: str) -> dict:
    """Returns must be daily: the statistics annualise as if they are."""
    request: dict = {"dates": dates, "returns": returns}
    if benchmark is not None:
        request["benchmark"] = benchmark
    out = run("report", request)
    window = f"{out['start']} to {out['end']}, {out['days']} days, risk-free rate 0"
    versus = {m["key"]: m["value"] for m in out.pop("benchmark_metrics", [])}
    for m in out["metrics"]:
        other = versus.get(m["key"])
        m["benchmark"] = None if other is None else _receipt(other, m["unit"], f"{benchmark_label}: {m['label']}", f"QuantStats {m['key']} ({window})", detail, "QuantStats")
        m["receipt"] = _receipt(m["value"], m["unit"], f"{label}: {m['label']}", f"QuantStats {m['key']} ({window})", detail, "QuantStats")
    out["relative"] = [
        {**m, "receipt": _receipt(m["value"], m["unit"], f"{label} against {benchmark_label}: {m['label']}", f"QuantStats {m['key']} ({window})", detail, "QuantStats")}
        for m in out.get("relative", [])
    ]
    return {**out, "label": label, "benchmark_label": benchmark_label}


def report_symbol(symbol: str, benchmark: str | None = None, range_: str = "5Y") -> dict:
    symbol = symbol.upper()
    benchmark = benchmark.upper() if benchmark else None
    if benchmark == symbol:
        benchmark = None
    symbols = [symbol, benchmark] if benchmark else [symbol]
    dates, closes, origins = market.aligned_closes(symbols, range_)
    returns = _returns([row[0] for row in closes])
    against = _returns([row[1] for row in closes]) if benchmark else None
    detail = "dividend-adjusted prices from " + ", ".join(sorted({o["provider"] for o in origins.values()}))
    return {**report_returns(symbol, dates[1:], returns, against, benchmark, detail), "range": range_, "warnings": _price_warnings(origins)}


def report_series(label: str, dates: list[str], equity: list[float], benchmark_equity: list[float] | None = None, benchmark_label: str | None = None) -> dict:
    """A report for a daily equity curve, such as a paper account's value at each close."""
    if len(dates) != len(equity) or (benchmark_equity is not None and len(benchmark_equity) != len(equity)):
        raise LabError("dates and values must be the same length")
    if len(equity) > MAX_POINTS:
        raise LabError("too many points")
    for series in (equity, benchmark_equity or []):
        if not all(math.isfinite(v) and v > 0 for v in series):
            raise LabError("values must be positive numbers")
    if sorted(set(dates)) != dates:
        raise LabError("dates must be in order, with no repeats")
    return report_returns(label, dates[1:], _returns(equity), _returns(benchmark_equity) if benchmark_equity else None, benchmark_label, f"from the {label} equity curve")
