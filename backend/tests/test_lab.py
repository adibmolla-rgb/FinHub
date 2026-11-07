import importlib.util
import json
import math
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from finhub_backend import agent, alpha, engines, installer, lab, market
from finhub_backend.server import app


def load_engine_script():
    path = engines.engines_dir() / "vibe-trading" / "lab.py"
    spec = importlib.util.spec_from_file_location("engine_lab", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_portfolio_gets_the_same_arithmetic():
    script = load_engine_script()
    returns = [0.01, -0.02, 0.03, -0.01, 0.02]
    stats = script.series_stats(returns)
    total = math.prod(1 + r for r in returns)
    assert stats["total_return"] == pytest.approx(total - 1)
    assert stats["annual_return"] == pytest.approx(total ** (252 / 5) - 1)
    mean = sum(returns) / 5
    sd = math.sqrt(sum((r - mean) ** 2 for r in returns) / 4)
    assert stats["sharpe"] == pytest.approx(mean / sd * math.sqrt(252))
    assert stats["annual_volatility"] == pytest.approx(sd * math.sqrt(252))
    assert stats["max_drawdown"] == pytest.approx(0.98 - 1)  # the -2% day, from the 1% peak before it


def test_drawdown_counts_from_the_starting_value():
    script = load_engine_script()
    assert script.series_stats([-0.1, -0.1, 0.05])["max_drawdown"] == pytest.approx(0.9 * 0.9 - 1)


def test_not_a_number_is_none_not_a_guess():
    script = load_engine_script()
    assert script.clean(float("nan")) is None
    assert script.clean(float("inf")) is None
    assert script.clean("x") is None
    assert script.clean(None) is None
    assert script.clean(1.5) == 1.5


def run_script(request: dict) -> dict:
    path = engines.engines_dir() / "vibe-trading" / "lab.py"
    done = subprocess.run([sys.executable, str(path)], input=json.dumps(request), capture_output=True, text=True, timeout=60)
    return json.loads(done.stdout)


def test_the_script_answers_with_clean_json_even_when_things_go_wrong():
    assert "KeyError" in run_script({"task": "nope"})["error"]
    assert run_script({"task": "report", "dates": ["2026-01-02"], "returns": [0.01]})["ok"] is False


def test_an_engine_without_the_libraries_says_how_to_fix_it():
    # The backend's own environment has no skfolio, like an engine from before the update.
    answer = run_script({"task": "optimise", "symbols": ["A"], "dates": [], "returns": [], "weights": [1]})
    assert answer["ok"] is False and "reinstall it from SYS" in answer["error"]


@pytest.fixture
def engine(tmp_path, monkeypatch):
    """A stand-in for the engine's python: this interpreter, running a script we control."""
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path / "data"))
    folder = tmp_path / "engines" / "vibe-trading"
    folder.mkdir(parents=True)
    monkeypatch.setenv("FINHUB_ENGINES_DIR", str(tmp_path / "engines"))
    monkeypatch.setattr(engines, "engine_python", lambda engine_id: type("P", (), {"exists": lambda self: True, "__str__": lambda self: sys.executable})())
    monkeypatch.setattr(installer.state("vibe-trading"), "state", "idle")
    return folder / "lab.py"


def test_run_returns_the_answer_and_keeps_keys_out_of_the_process(engine, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    engine.write_text("import json,os,sys\nr=json.loads(sys.stdin.readline())\nprint(json.dumps({'ok':True,'result':{'task':r['task'],'x':r['x'],'key':os.environ.get('ANTHROPIC_API_KEY')}}))\n")
    assert lab.run("report", {"x": 1}) == {"task": "report", "x": 1, "key": None}


def test_run_turns_failures_into_readable_errors(engine):
    engine.write_text("import json;print(json.dumps({'ok':False,'error':'ValueError: needs at least 20 days'}))\n")
    with pytest.raises(lab.LabError, match="^needs at least 20 days$"):
        lab.run("report", {})
    engine.write_text("import sys;sys.stderr.write('it broke');sys.exit(3)\n")
    with pytest.raises(lab.LabError, match="it broke") as caught:
        lab.run("report", {})
    assert caught.value.status == 502
    engine.write_text("import time;time.sleep(30)\n")
    with pytest.raises(lab.LabError, match="stopped") as caught:
        lab.run("report", {}, timeout=0.2)
    assert caught.value.status == 504


def test_run_waits_for_an_engine_update_and_explains_a_missing_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(installer.state("vibe-trading"), "state", "running")
    with pytest.raises(lab.LabError, match="updating") as caught:
        lab.run("report", {})
    assert caught.value.status == 503
    monkeypatch.setattr(installer.state("vibe-trading"), "state", "idle")
    monkeypatch.setenv("FINHUB_ENGINE_ENVS_DIR", str(tmp_path / "nothing"))
    with pytest.raises(lab.LabError, match="install it from SYS"):
        lab.run("report", {})


def closes(symbols, range_):
    rows = [[100.0 + i, 50.0 - i * 0.1] for i in range(4)]
    return ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"], rows, {"AAA": {"provider": "Yahoo", "adjusted": True}, "BBB": {"provider": "Yahoo", "adjusted": False}}


def test_optimise_sends_normalised_weights_and_returns_from_prices(monkeypatch):
    seen = {}

    def fake_run(task, request, timeout=300.0):
        seen.update(request, task=task)
        return {"rows": [{"name": "Your weights", "yours": True, "annual_return": 0.1, "annual_volatility": 0.2, "sharpe": 0.5, "max_drawdown": None, "weights": {"AAA": 0.75, "BBB": 0.25}}], "problems": [], "held_days": 3, "windows": 1, "start": "2026-01-05", "end": "2026-01-07", "train_days": 1, "test_days": 1}

    monkeypatch.setattr(market, "aligned_closes", closes)
    monkeypatch.setattr(lab, "run", fake_run)
    out = lab.optimise([{"symbol": "aaa", "weight": 60}, {"symbol": "bbb", "weight": 20}], "5Y")
    assert seen["task"] == "optimise"
    assert seen["weights"] == pytest.approx([0.75, 0.25])
    assert seen["dates"] == ["2026-01-05", "2026-01-06", "2026-01-07"]
    assert seen["returns"][0] == pytest.approx([0.01, -0.002])
    row = out["rows"][0]
    assert row["sharpe"]["value"] == 0.5 and row["sharpe"]["unit"] == "ratio"
    assert row["annual_return"]["unit"] == "fraction" and "held" in row["annual_return"]["formula"]
    assert row["max_drawdown"] is None  # not filled in with a guess
    assert "BBB" in out["warnings"][0] and "AAA" not in out["warnings"][0]  # a split would look like a crash


@pytest.mark.parametrize("holdings, message", [([{"symbol": "A", "weight": 1}], "two"), ([{"symbol": "A", "weight": 1}, {"symbol": "a", "weight": 1}], "only once")])
def test_optimise_refuses_bad_holdings(holdings, message):
    with pytest.raises(lab.LabError, match=message):
        lab.optimise(holdings)


def test_report_for_a_ticker_gives_receipts_and_keeps_the_benchmark_separate(monkeypatch):
    def fake_run(task, request, timeout=300.0):
        assert request["returns"][0] == pytest.approx(0.01) and request["benchmark"][0] == pytest.approx(-0.002)
        return {
            "days": 3, "start": "2026-01-05", "end": "2026-01-07", "monthly": [], "drawdowns": [],
            "metrics": [{"key": "sharpe", "label": "Sharpe ratio", "unit": "ratio", "value": 1.5}],
            "benchmark_metrics": [{"key": "sharpe", "value": 0.5}],
            "relative": [{"key": "beta", "label": "Beta", "unit": "ratio", "value": 0.9}],
        }

    monkeypatch.setattr(market, "aligned_closes", closes)
    monkeypatch.setattr(lab, "run", fake_run)
    out = lab.report_symbol("aaa", "bbb", "5Y")
    metric = out["metrics"][0]
    assert metric["receipt"]["value"] == 1.5 and metric["benchmark"]["value"] == 0.5
    assert "QuantStats" in metric["receipt"]["source"]["provider"]
    assert "benchmark_metrics" not in out
    assert out["relative"][0]["receipt"]["value"] == 0.9
    assert out["label"] == "AAA" and out["benchmark_label"] == "BBB"


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"dates": ["2026-01-02"], "equity": [1.0, 2.0]}, "same length"),
        ({"dates": ["2026-01-02", "2026-01-03"], "equity": [1.0, -2.0]}, "positive"),
        ({"dates": ["2026-01-02", "2026-01-03"], "equity": [1.0, float("inf")]}, "positive"),
        ({"dates": ["2026-01-03", "2026-01-02"], "equity": [1.0, 2.0]}, "in order"),
        ({"dates": ["2026-01-02", "2026-01-02"], "equity": [1.0, 2.0]}, "in order"),
        ({"dates": ["2026-01-02", "2026-01-03"], "equity": [1.0, 2.0], "benchmark_equity": [1.0]}, "same length"),
    ],
)
def test_bad_equity_curves_are_refused(kwargs, message):
    with pytest.raises(lab.LabError, match=message):
        lab.report_series("Test", **kwargs)


def test_routes_explain_refusals(monkeypatch):
    def not_installed(*args, **kwargs):
        raise lab.LabError("install it from SYS", status=503)

    monkeypatch.setattr(lab, "optimise", not_installed)
    monkeypatch.setattr(lab, "report_symbol", not_installed)
    client = TestClient(app)
    body = {"holdings": [{"symbol": "SPY", "weight": 1}, {"symbol": "TLT", "weight": 1}]}
    assert client.post("/lab/optimise", json=body).status_code == 503
    assert client.post("/lab/report", json={"symbol": "SPY"}).status_code == 503
    assert client.post("/lab/optimise", json={"holdings": [{"symbol": "SPY", "weight": 1}]}).status_code == 422
    assert client.post("/lab/optimise", json={**body, "range": "1Y"}).status_code == 422  # a year can't fill a walk-forward window
    assert client.post("/lab/report", json={"symbol": "<b>"}).status_code == 422


def test_a_market_failure_keeps_its_attempts(monkeypatch):
    def down(symbols, range_):
        raise market.MarketDataError("couldn't load SPY", [{"provider": "yahoo", "ok": False, "error": "down", "ms": 1}])

    monkeypatch.setattr(market, "aligned_closes", down)
    res = TestClient(app).post("/lab/report", json={"symbol": "SPY"})
    assert res.status_code == 502 and res.json()["attempts"][0]["provider"] == "yahoo"


@pytest.fixture
def clean_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    alpha._runs.clear()
    yield
    alpha._runs.clear()


def new_factor_run():
    return {"id": "f1", "kind": "factor", "status": "running", "request": {"alpha_id": "academic_bab", "period": "2024-2025"}, "started_at": "2026-11-07T00:00:00+00:00", "progress": None, "error": None, "result": None}


def test_a_deep_look_is_saved_when_it_finishes(clean_runs, monkeypatch):
    monkeypatch.setattr(lab, "run", lambda task, request, timeout=300.0: {"alpha_id": request["alpha_id"], "horizons": []})
    record = new_factor_run()
    alpha._analyse(record)
    assert record["status"] == "done"
    assert alpha.run("f1")["result"]["alpha_id"] == "academic_bab"


def test_a_failed_deep_look_ends_with_its_reason(clean_runs, monkeypatch):
    def fails(*args, **kwargs):
        raise lab.LabError("no such signal")

    monkeypatch.setattr(lab, "run", fails)
    record = new_factor_run()
    alpha._analyse(record)
    assert record["status"] == "error" and record["error"] == "no such signal"


def test_a_deep_look_waits_its_turn_and_checks_its_input(clean_runs, monkeypatch):
    monkeypatch.setattr(alpha, "_analyse", lambda record: None)
    first = alpha.start_factor("academic_bab", "2024-2025")
    assert first["status"] == "running"
    with pytest.raises(alpha.AlphaError, match="already running"):
        alpha.start_factor("academic_hml", "2024-2025")
    first["status"] = "done"
    with pytest.raises(alpha.AlphaError, match="invalid signal"):
        alpha.start_factor("../x", "2024-2025")
    with pytest.raises(alpha.AlphaError, match="period"):
        alpha.start_factor("academic_bab", "1990-1991")


def test_a_backtest_report_uses_every_day_not_the_thinned_chart_curve(monkeypatch):
    # The chart keeps about 600 points. Treating those as days gave a Sharpe of 0.51 for a backtest whose real one is 0.35.
    closes_ = [100 * 1.0005 ** i + (i % 7) for i in range(1300)]
    bars = [{"time": f"{2015 + i // 260}-{i % 12 + 1:02d}-{i % 28 + 1:02d}", "close": c} for i, c in enumerate(closes_)]
    monkeypatch.setattr(market, "history", lambda symbol, range_, adjusted=False: {"symbol": "SPY", "provider_name": "Test", "fetched_at": "2026-11-07T00:00:00+00:00", "adjusted": True, "attempts": [], "bars": bars})
    sent = {}

    def fake_run(task, request, timeout=300.0):
        sent.update(request)
        return {"days": len(request["returns"]), "start": request["dates"][0], "end": request["dates"][-1], "metrics": [], "monthly": [], "drawdowns": []}

    monkeypatch.setattr(lab, "run", fake_run)
    client = TestClient(app)
    body = {"symbol": "SPY", "strategy": "sma", "params": {"fast": 5, "slow": 20}}
    res = client.post("/lab/report/backtest", json=body)
    assert res.status_code == 200, res.text
    assert len(sent["returns"]) == 1299 and len(sent["benchmark"]) == 1299
    shown = client.post("/backtest", json=body).json()
    assert "daily" not in shown  # the chart's response stays small
    assert len(shown["curve"]) < 1299
    assert shown["metrics"]["strategy"]["total_return"] == pytest.approx(math.prod(1 + r for r in sent["returns"]) - 1)
    assert shown["curve"][-1]["buy_hold"] == pytest.approx(math.prod(1 + r for r in sent["benchmark"]))
