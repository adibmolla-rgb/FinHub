import json
import subprocess
import sys
from pathlib import Path

import pytest

import providers

HERE = Path(__file__).resolve().parents[1]


def ok(**kw):
    return {"served": True, **kw}


def boom(**kw):
    raise ConnectionError("network unreachable")


def empty(**kw):
    raise providers.NoData("nothing")


def test_chain_falls_back_and_records_every_attempt():
    out = providers.run_chain("quote", {"yahoo": boom, "cboe": empty, "nasdaq": ok}, {"symbol": "X"})
    assert out["provider"] == "nasdaq"
    assert [(a["provider"], a["ok"]) for a in out["attempts"]] == [("yahoo", False), ("cboe", False), ("nasdaq", True)]
    assert "ConnectionError" in out["attempts"][0]["error"]


def test_chain_failure_carries_attempts():
    with pytest.raises(providers.ChainFailed) as err:
        providers.run_chain("quote", {"yahoo": boom, "cboe": boom}, {"symbol": "X"}, chain=["yahoo", "cboe"])
    assert len(err.value.attempts) == 2


def test_field_keeps_source_name_and_skips_nan():
    rec = {"a": float("nan"), "b": 2.0}
    assert providers.numeric(rec, "a", "b") == {"value": 2.0, "field": "b"}
    assert providers.field(rec, "missing") is None


def _worker():
    return subprocess.Popen(
        [sys.executable, str(HERE / "worker.py")],
        cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )


def test_worker_protocol_and_exit_on_stdin_close():
    proc = _worker()
    proc.stdin.write(json.dumps({"id": 7, "method": "ping"}) + "\n")
    proc.stdin.write(json.dumps({"id": 8, "method": "nope"}) + "\n")
    proc.stdin.flush()
    replies = {r["id"]: r for r in (json.loads(proc.stdout.readline()) for _ in range(2))}
    assert replies[7]["ok"] and replies[7]["result"]["pong"]
    assert not replies[8]["ok"] and "unknown method" in replies[8]["error"]
    proc.stdin.close()
    assert proc.wait(timeout=10) == 0


def test_openbb_calls_run_on_one_thread_even_when_requested_concurrently():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    seen = set()

    def record(**kw):
        seen.add(threading.get_ident())
        return {}

    wrapped = providers.on_obb_thread(record)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: wrapped(symbol="X"), range(32)))
    assert len(seen) == 1


def test_yahoo_quote_reports_the_real_cause_not_keyerror(monkeypatch):
    class FastInfo:
        def __getitem__(self, name):
            try:
                raise ConnectionError("tunnel refused")
            except ConnectionError as exc:
                raise KeyError(name) from exc

    class Ticker:
        def __init__(self, _):
            self.fast_info = FastInfo()

    class YF:
        pass

    YF.Ticker = Ticker
    monkeypatch.setattr(providers, "_yf", lambda: YF)
    with pytest.raises(providers.NoData) as err:
        providers.yahoo_quote("X")
    assert "ConnectionError: tunnel refused" in str(err.value)


def test_statement_from_yfinance_frame():
    import pandas as pd

    df = pd.DataFrame(
        {pd.Timestamp("2025-09-30"): [400.0, 180.0, float("nan")], pd.Timestamp("2024-09-30"): [390.0, 170.0, float("nan")]},
        index=["Total Revenue", "Gross Profit", "Empty Row"],
    )
    out = providers.statement_from_frame(df, "income", "annual", "x")
    assert out["periods"] == ["2025-09-30", "2024-09-30"]
    assert [r["field"] for r in out["rows"]] == ["Total Revenue", "Gross Profit"]  # all-empty rows dropped


def test_statement_from_openbb_records_transposes():
    recs = [
        {"period_ending": "2025-12-31", "fiscal_year": 2025, "revenue": 100.0, "net_income": 10.0, "currency": "USD"},
        {"period_ending": "2024-12-31", "fiscal_year": 2024, "revenue": 90.0, "net_income": None},
    ]
    out = providers.statement_from_records(recs, "income", "annual", "x")
    assert out["periods"] == ["2025-12-31", "2024-12-31"] and out["currency"] == "USD"
    assert out["rows"] == [{"field": "revenue", "values": [100.0, 90.0]}, {"field": "net_income", "values": [10.0, None]}]


def test_statement_rejects_bad_arguments():
    with pytest.raises(ValueError):
        providers.yahoo_statement("X", "nope")
