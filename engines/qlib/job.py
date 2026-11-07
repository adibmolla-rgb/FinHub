"""Microsoft's Qlib workflow on prices FinHub supplies: Alpha158 features, LightGBM, then a test on years it never saw.

Qlib's public datasets are unreliable, so this writes the prices it's given into Qlib's own file format in its own
folder. One job per process: JSON in on stdin, JSON out on stdout. No AI provider is involved.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

FIELDS = ("open", "high", "low", "close", "volume")
HOLD = 5  # stocks held on each side of the long-short test
ROUNDS = 300


def clean(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _write_series(path: Path, start: int, values) -> None:
    """Qlib's format: the first value is where the series starts in the calendar, then little-endian floats."""
    import numpy as np

    with open(path, "wb") as f:
        f.write(struct.pack("<f", start))
        f.write(np.asarray(values, dtype="<f4").tobytes())


def write_dataset(root: Path, panels: dict[str, dict]) -> list[str]:
    import numpy as np

    calendar = sorted({day for panel in panels.values() for day in panel["dates"]})
    place = {day: i for i, day in enumerate(calendar)}
    for folder in ("calendars", "instruments", "features"):
        (root / folder).mkdir(parents=True)
    (root / "calendars" / "day.txt").write_text("\n".join(calendar), encoding="utf-8")
    lines = []
    for symbol, panel in panels.items():
        start = place[panel["dates"][0]]
        slots = {day: i for i, day in enumerate(calendar[start: place[panel["dates"][-1]] + 1])}
        folder = root / "features" / symbol.lower()
        folder.mkdir()
        series = {}
        for field in FIELDS:
            values = np.full(len(slots), np.nan, dtype=float)
            for day, value in zip(panel["dates"], panel[field]):
                values[slots[day]] = np.nan if value is None else value
            series[field] = values
            _write_series(folder / f"{field}.day.bin", start, values)
        _write_series(folder / "vwap.day.bin", start, (series["high"] + series["low"] + series["close"]) / 3)
        _write_series(folder / "factor.day.bin", start, np.ones(len(slots)))
        lines.append(f"{symbol}\t{panel['dates'][0]}\t{panel['dates'][-1]}")
    (root / "instruments" / "all.txt").write_text("\n".join(lines), encoding="utf-8")
    return calendar


def segments(calendar: list[str], test_years: int = 3, valid_years: int = 2) -> dict:
    last = int(calendar[-1][:4])
    test_start, valid_start = f"{last - test_years + 1}-01-01", f"{last - test_years - valid_years + 1}-01-01"
    def before(day: str) -> str:
        return max(d for d in calendar if d < day)
    return {"train": (calendar[0], before(valid_start)), "valid": (valid_start, before(test_start)), "test": (test_start, calendar[-1])}


def daily_stats(frame) -> dict:
    """Prediction against what followed, on the test years only."""
    ic = frame.groupby(level="datetime").apply(lambda g: g["pred"].corr(g["label"])).dropna()
    rank = frame.groupby(level="datetime").apply(lambda g: g["pred"].corr(g["label"], method="spearman")).dropna()

    def spread(g):
        ordered = g.sort_values("pred")
        return ordered["label"].tail(HOLD).mean() - ordered["label"].head(HOLD).mean()

    long_short = frame.groupby(level="datetime").apply(spread).dropna()
    days = len(long_short)
    return {
        "ic": clean(ic.mean()),
        "icir": clean(ic.mean() / ic.std()) if ic.std() > 0 else None,
        "rank_ic": clean(rank.mean()),
        "ic_positive": clean((ic > 0).mean()),
        "days": len(ic),
        "long_short_annual": clean(long_short.mean() * 252),
        "long_short_t": clean(long_short.mean() / (long_short.std() / math.sqrt(days))) if days > 1 and long_short.std() > 0 else None,
    }


def train(request: dict) -> dict:
    import pandas as pd
    import qlib
    from qlib.constant import REG_US
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.data.dataset import DatasetH

    # Its database stays locked on Windows until this process ends, so this is cleared at the start of the next run instead.
    root = Path.cwd() / "workspace"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    calendar = write_dataset(root / "data", request["panels"])
    split = segments(calendar)
    os.chdir(root)  # Qlib records the working folder's git state, which this one hasn't got
    # MLflow no longer accepts its old file store, so its records go in a throwaway database.
    qlib.init(
        provider_uri=str(root / "data"), region=REG_US, kernels=1, joblib_backend="threading", logging_level=40,
        exp_manager={"class": "MLflowExpManager", "module_path": "qlib.workflow.expm", "kwargs": {"uri": f"sqlite:///{(root / 'runs.db').as_posix()}", "default_exp_name": "finhub"}},
    )
    handler = Alpha158(instruments="all", start_time=split["train"][0], end_time=split["test"][1], fit_start_time=split["train"][0], fit_end_time=split["train"][1])
    dataset = DatasetH(handler=handler, segments=split)
    model = LGBModel(loss="mse", learning_rate=0.05, num_leaves=31, max_depth=6, num_boost_round=ROUNDS, early_stopping_rounds=30, num_threads=4, verbosity=-1)
    model.fit(dataset, verbose_eval=0)
    predictions = model.predict(dataset, segment="test")
    labels = dataset.prepare("test", col_set="label")
    frame = pd.DataFrame({"pred": predictions, "label": labels.iloc[:, 0]}).dropna()
    features = list(dataset.prepare("valid", col_set="feature").columns)
    importance = model.get_feature_importance().head(10)
    top_features = [{"name": features[int(name.split("_")[1])] if "_" in str(name) else str(name), "score": clean(score)} for name, score in importance.items()]
    last_day = predictions.index.get_level_values("datetime").max()
    latest = predictions.xs(last_day, level="datetime").sort_values(ascending=False)
    return {
        "segments": {k: list(v) for k, v in split.items()},
        "stocks": len(request["panels"]),
        "rounds_used": int(model.model.best_iteration),
        "rounds_allowed": ROUNDS,
        "test": daily_stats(frame),
        "top_features": top_features,
        "latest_day": str(last_day)[:10],
        "highest": [{"symbol": str(s)} for s in latest.head(HOLD).index],
        "lowest": [{"symbol": str(s)} for s in latest.tail(HOLD).index],
        "distinct_predictions": int(latest.round(8).nunique()),
        "label_average": clean(frame["label"].mean()),
    }


TASKS = {"train": train}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from job_runner import run

    raise SystemExit(run(TASKS, "Qlib"))
