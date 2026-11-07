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


def test_macro_units_come_from_openbb_metadata_not_guesses():
    from pydantic import BaseModel, Field

    class Normalised(BaseModel):
        value: float = Field(json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100})

    class Misspelt(BaseModel):  # OpenBB's interest-rate model spells the key "measurment"
        value: float = Field(json_schema_extra={"x-unit_measurment": "percent", "x-frontend_multiply": 100})

    class Labelled(BaseModel):
        value: float
        unit: str | None = None

    class Silent(BaseModel):
        value: float

    assert providers.unit_of(Normalised(value=0.04))[0] == "fraction"
    assert providers.unit_of(Misspelt(value=0.04))[0] == "fraction"
    assert providers.unit_of(Labelled(value=2.9, unit="Growth rate, same period previous year")) == ("as_reported", "Growth rate, same period previous year")
    assert providers.unit_of(Silent(value=5.0)) == ("as_reported", "not stated by the provider")


def test_oecd_percent_with_a_multiplier_of_100_is_a_fraction():
    from pydantic import BaseModel

    class Row(BaseModel):
        value: float
        unit: str | None = None
        unit_multiplier: int | float | None = None

    # OECD CPI reports 3.6% as 0.036, with unit "percent change" and unit_multiplier 100.
    kind, text = providers.unit_of(Row(value=0.036, unit="Year-over-year (YOY) percent change", unit_multiplier=100))
    assert kind == "fraction"
    assert "Year-over-year (YOY) percent change" in text
    # Other multipliers, and units that aren't percents, stay exactly as reported.
    assert providers.unit_of(Row(value=3.6, unit="Year-over-year (YOY) percent change", unit_multiplier=1))[0] == "as_reported"
    assert providers.unit_of(Row(value=120.0, unit="Index", unit_multiplier=100))[0] == "as_reported"


def test_worker_children_do_not_inherit_the_request_pipe(tmp_path):
    # OpenBB runs git while it loads. A child sharing the request pipe hangs on Windows while the worker
    # waits for the next line, so a lone first request never finished. Here a child reading stdin would
    # block on the open pipe on any system.
    (tmp_path / "worker.py").write_text((HERE / "worker.py").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "providers.py").write_text(
        "import subprocess, sys\n"
        "class ChainFailed(Exception):\n    pass\n"
        "def child(**kw):\n"
        "    code = 'import sys; print(repr(sys.stdin.read()))'\n"
        "    return subprocess.run([sys.executable, '-c', code], stdout=subprocess.PIPE, text=True, timeout=20).stdout.strip()\n"
        "FETCHERS = {'child': {'x': child}}\n"
        "def run_chain(kind, fetchers, params, chain=None):\n    return fetchers['x'](**params)\n",
        encoding="utf-8",
    )
    proc = subprocess.Popen([sys.executable, str(tmp_path / "worker.py")], cwd=tmp_path, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    proc.stdin.write(json.dumps({"id": 1, "method": "child"}) + "\n")
    proc.stdin.flush()
    reply = json.loads(proc.stdout.readline())
    proc.stdin.close()
    proc.wait(timeout=10)
    assert reply["ok"], reply
    assert reply["result"] == "''"  # the child's stdin is empty, not our pipe


def test_insider_rows_keep_raw_values_and_flag_plans():
    rows = providers.insider_rows([
        {"transaction_date": "2026-10-01", "securities_transacted": 10.0, "owner_name": "Old", "footnote": None, "filing_url": "https://www.sec.gov/a"},
        {"transaction_date": "2026-11-03", "securities_transacted": 20.0, "transaction_price": 325.75, "securities_owned": 29997.0,
         "acquisition_or_disposition": "Disposition", "footnote": "made pursuant to a Rule 10b5-1 trading plan"},
        {"transaction_date": None, "securities_transacted": 5.0},
        {"transaction_date": "2026-11-01", "securities_transacted": None},
    ])
    assert [r["date"] for r in rows] == ["2026-11-03", "2026-10-01"]
    assert rows[0]["plan_10b5_1"] is True and rows[1]["plan_10b5_1"] is False
    assert rows[0]["shares_after"] == 29997.0 and rows[0]["direction"] == "Disposition"
    with pytest.raises(providers.NoData):
        providers.insider_rows([])


def test_short_rows_keep_counts_and_ignore_provider_percentages():
    # FINRA's -12.29 means percent, Nasdaq's 0.0897 is a fraction: neither crosses to the backend.
    rows = providers.short_rows([
        {"settlement_date": "2026-10-15", "current_short_position": 2.0, "previous_short_position": 1.0, "avg_daily_volume": 4.0, "change_pct": -12.29},
        {"settlement_date": "2026-09-30", "current_short_position": 1.0},
    ])
    assert [r["date"] for r in rows] == ["2026-09-30", "2026-10-15"]
    assert "change_pct" not in rows[1] and rows[1]["avg_volume"] == 4.0
    assert len(providers.short_rows([{"settlement_date": f"2026-01-{d:02d}", "current_short_position": 1.0} for d in range(1, 11)], keep=3)) == 3


CHAIN_ROWS = [
    {"expiration": exp, "strike": 100.0, "option_type": kind, "bid": 1.0, "ask": 2.0, "implied_volatility": 0.3, "underlying_price": 101.0}
    for exp in ("2026-11-06", "2026-11-13", "2026-12-18") for kind in ("call", "put")
]


def test_chain_defaults_to_an_expiration_a_week_out():
    out = providers.chain_view(CHAIN_ROWS, "aapl", None, providers.date(2026, 11, 6), "fraction")
    assert out["symbol"] == "AAPL" and out["expiration"] == "2026-11-13"
    assert out["expirations"] == ["2026-11-06", "2026-11-13", "2026-12-18"]
    assert len(out["contracts"]) == 2 and out["underlying"] == {"value": 101.0, "field": "underlying_price"}
    late = providers.chain_view(CHAIN_ROWS, "AAPL", None, providers.date(2027, 6, 1), "fraction")
    assert late["expiration"] == "2026-12-18"  # nothing a week out: the last one, not a crash


def test_chain_rejects_an_unknown_expiration_and_empty_chains():
    assert providers.chain_view(CHAIN_ROWS, "AAPL", "2026-12-18", providers.date(2026, 11, 6), "fraction")["expiration"] == "2026-12-18"
    with pytest.raises(providers.NoData):
        providers.chain_view(CHAIN_ROWS, "AAPL", "2001-01-01", providers.date(2026, 11, 6), "fraction")
    with pytest.raises(providers.NoData):
        providers.chain_view([], "AAPL", None, providers.date(2026, 11, 6), "fraction")


def test_calendar_rows_clean_provider_placeholders():
    earnings = providers.earnings_rows([
        {"report_date": "2026-11-13", "symbol": "MUFG", "eps_consensus": 0.45, "reporting_time": "not-supplied", "market_cap": 2.5e11},
        {"report_date": "2026-11-13", "symbol": None},
    ])
    assert len(earnings) == 1 and earnings[0]["time"] is None and earnings[0]["eps_consensus"] == 0.45
    events = providers.economic_rows([
        {"date": "2026-11-10 08:00:00", "country": "Japan", "event": "Later", "consensus": " ", "previous": "1,178.4B", "actual": "-"},
        {"date": "2026-11-09 18:50:00", "country": "US", "event": "Sooner", "previous": "0.3%"},
    ])
    assert [e["event"] for e in events] == ["Sooner", "Later"]
    assert events[1]["consensus"] is None and events[1]["actual"] is None
    assert events[1]["previous"] == "1,178.4B"  # stays text: each event has its own unit
    assert events[0]["date"] == "2026-11-09 18:50"


def test_tenors_become_years():
    assert providers._tenor_years("10 Yr") == 10
    assert providers._tenor_years("1.5 Month") == pytest.approx(0.125)
    assert providers._tenor_years("3 Mo") == pytest.approx(0.25)
    assert providers._tenor_years("year_30") == 30
    assert providers._tenor_years("month_6") == pytest.approx(0.5)
    assert providers._tenor_years("week_4") == pytest.approx(4 / 52)
    assert providers._tenor_years("Date") is None


def test_treasury_csv_is_parsed_oldest_first_and_keeps_percent():
    text = 'Date,"1 Mo","1.5 Month","10 Yr","30 Yr"\n11/06/2026,4.02,4.07,4.25,\n11/05/2026,4.00,,4.20,4.70\nnot a date,1,2,3,4\n'
    curves = providers.parse_treasury_csv(text)
    assert [c["date"] for c in curves] == ["2026-11-05", "2026-11-06"]
    newest = curves[-1]["points"]
    assert [p["tenor"] for p in newest] == ["1 Mo", "1.5 Month", "10 Yr"]  # the blank 30 Yr is left out, not zero
    assert newest[-1] == {"tenor": "10 Yr", "years": 10.0, "value": 4.25}
    with pytest.raises(providers.NoData):
        providers.parse_treasury_csv("<html>maintenance</html>")


def test_units_come_only_from_declared_metadata():
    from pydantic import BaseModel, Field

    class Row(BaseModel):
        weight: float = Field(json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100})
        iv: float = Field(json_schema_extra={"x-unit_measurement": "decimal"})
        silent: float = 0.0

    row = Row(weight=0.07, iv=0.3)
    assert providers._unit_kind(row, "weight") == "fraction"
    assert providers._unit_kind(row, "iv") == "as_reported"  # "decimal" counts only where the caller says so
    assert providers._unit_kind(row, "iv", "decimal") == "fraction"
    assert providers._unit_kind(row, "silent") == "as_reported"
    assert providers._unit_kind(row, "missing") == "as_reported"


class FakeYahoo:
    def __init__(self, kind):
        self.kind = kind

    def Ticker(self, symbol):
        if isinstance(self.kind, Exception):
            raise self.kind
        return type("T", (), {"fast_info": {"quoteType": self.kind}})


class FakeEtfInfo:
    """Nasdaq's etf.info answers for stocks too; only funds report costs and assets."""

    def __init__(self, **row):
        self.row = row
        self.etf = self
        self.holdings_called = False

    def info(self, symbol, provider):
        return [self.row]

    def holdings(self, symbol, provider):
        self.holdings_called = True
        raise AssertionError("holdings must not be requested for a stock")


@pytest.mark.parametrize("kind, row, expected", [
    ("ETF", {}, True),
    ("MUTUALFUND", {}, True),
    ("EQUITY", {"expense_ratio": 0.1}, False),  # Yahoo's answer wins when it gives one
    (None, {"expense_ratio": 0.0009}, True),
    (None, {"aum": 7.8e8}, True),
    (None, {"name": "Apple Inc. Common Stock", "market_cap": 5e12}, False),
    (ConnectionError("down"), {"aum": 7.8e8}, True),
    (ConnectionError("down"), {"name": "Apple Inc. Common Stock"}, False),
])
def test_is_fund(monkeypatch, kind, row, expected):
    monkeypatch.setattr(providers, "_yf", lambda: FakeYahoo(kind))
    monkeypatch.setattr(providers, "obb", lambda: FakeEtfInfo(**row))
    assert providers.is_fund("X", "nasdaq") is expected


def test_etf_holdings_refuses_a_stock_instead_of_listing_funds_that_hold_it(monkeypatch):
    fake = FakeEtfInfo()
    monkeypatch.setattr(providers, "_yf", lambda: FakeYahoo("EQUITY"))
    monkeypatch.setattr(providers, "obb", lambda: fake)
    with pytest.raises(providers.NoData, match="isn't an ETF"):
        providers.openbb_etf_holdings("nasdaq")(symbol="AAPL")
    assert fake.holdings_called is False


def cboe_contract(option, **kw):
    return {"option": option, "bid": 1.0, "ask": 2.0, "iv": 0.25, "delta": 0.5, "volume": 3.0, "open_interest": 4.0, "last_trade_price": 1.5, **kw}


def test_cboe_feed_reads_the_contract_symbol():
    rows = providers.cboe_chain_rows({"data": {"current_price": 342.3, "options": [cboe_contract("AAPL261116C00342500"), cboe_contract("AAPL261116P00007500")]}}, "AAPL")
    assert rows[0]["expiration"] == "2026-11-16" and rows[0]["strike"] == 342.5 and rows[0]["option_type"] == "call"
    assert rows[1]["strike"] == 7.5 and rows[1]["option_type"] == "put"
    assert rows[0]["implied_volatility"] == 0.25 and rows[0]["underlying_price"] == 342.3


def test_cboe_feed_keeps_only_this_symbols_contracts():
    # These other products are what crash OpenBB's reader: their trade times are blank.
    options = [cboe_contract("SPY261106P00755000"), cboe_contract("B1SPY261106P00755000", last_trade_time=None), cboe_contract("SPY1261106P00755000"), cboe_contract("junk")]
    rows = providers.cboe_chain_rows({"data": {"options": options}}, "SPY")
    assert len(rows) == 1 and rows[0]["expiration"] == "2026-11-06"


def test_cboe_feed_accepts_an_index_s_own_roots():
    options = [cboe_contract("SPX261218C05000000"), cboe_contract("SPXW261218C05000000"), cboe_contract("B1SPX261218C05000000")]
    assert len(providers.cboe_chain_rows({"data": {"options": options}}, "^SPX")) == 2


@pytest.mark.parametrize("symbol", ["BRK-B", "SHEL.L", "EURUSD=X"])
def test_cboe_feed_is_not_asked_for_names_it_cannot_have(symbol):
    with pytest.raises(providers.NoData):
        providers.cboe_direct_chain(symbol)


def test_options_chain_tries_the_direct_feed_first():
    assert providers.CHAINS["options_chain"][0] == "cboe_direct"
    assert set(providers.CHAINS["options_chain"]) == set(providers.FETCHERS["options_chain"])
