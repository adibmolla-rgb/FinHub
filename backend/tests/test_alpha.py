from datetime import date

import pytest
from fastapi.testclient import TestClient

from finhub_backend import agent, alpha
from finhub_backend.server import app


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    alpha._runs.clear()
    yield
    alpha._runs.clear()


def raw_compare():
    return {
        "ranking": [
            {"id": "academic_b", "ic_mean": 0.01, "ic_std": 0.1, "ir": 0.1, "ic_positive_ratio": 0.52, "ic_count": 500},
            {"id": "academic_a", "ic_mean": 0.03, "ic_std": 0.1, "ir": 0.3, "ic_positive_ratio": 0.55, "ic_count": 500},
        ],
        "skipped": [{"id": "academic_c", "reason": "not enough data"}],
        "meta": {"survivorship_bias": True, "constituent_source_date": "2026-05-17", "requested_instruments": 503, "missing_instruments": ["XYZ.US"], "data_diagnostics": {"huge": "blob"}},
    }


def test_results_rank_by_ir_and_keep_what_could_flatter_them():
    out = alpha.summarise("compare", raw_compare())
    assert [r["id"] for r in out["rows"]] == ["academic_a", "academic_b"]
    assert out["meta"]["survivorship_bias"] is True
    assert out["meta"]["missing_instruments"] == ["XYZ.US"]
    assert "data_diagnostics" not in out["meta"]
    assert out["skipped"] == [{"id": "academic_c", "reason": "not enough data"}]
    assert out["n_skipped"] == 1


def test_whole_library_results_use_the_shape_the_engine_really_sends():
    # Its route drops `rows`, and turns `skipped` from a list into a count.
    raw = {
        "top5_by_ir": [{"id": "x_1", "ic_mean": 0.01, "ir": 0.1, "theme": ["value"]}, {"id": "x_2", "ic_mean": 0.03, "ir": 0.5, "theme": ["momentum"]}],
        "alive": 1, "reversed": 1, "dead": 10, "n_alphas_tested": 12, "skipped": 3, "n_skipped": 3,
        "by_theme": {"value": {"alive": 0, "reversed": 1, "dead": 2, "count": 3}}, "meta": {"survivorship_bias": True},
    }
    out = alpha.summarise("bench", raw)
    assert [r["id"] for r in out["rows"]] == ["x_2", "x_1"]
    assert (out["alive"], out["reversed"], out["dead"], out["n_alphas_tested"]) == (1, 1, 10, 12)
    assert out["n_skipped"] == 3 and out["skipped"] == []
    assert out["by_theme"]["value"]["dead"] == 2
    assert out["meta"]["survivorship_bias"] is True


def test_a_result_that_cant_be_read_ends_the_run_instead_of_hanging_it(monkeypatch):
    monkeypatch.setattr(agent, "call_engine", Engine([{"status": "done", "result": {"top5_by_ir": ["not a row"]}}]))
    run = new_run("bench")
    alpha._follow(run, sleep=lambda s: None)
    assert run["status"] == "error" and "couldn't read" in run["error"]
    assert alpha.run("job1")["status"] == "error"


@pytest.mark.parametrize("period", ["2020", "2020-20", "2025-2020", "1999-2020", "2020-2099", "abc", "2020-2021; x"])
def test_bad_periods_are_refused(period):
    with pytest.raises(alpha.AlphaError, match="period"):
        alpha.check_period(period, date(2026, 11, 7))


def test_good_periods_pass():
    assert alpha.check_period("2024-2026", date(2026, 11, 7)) == "2024-2026"
    assert alpha.check_period("2026-2026", date(2026, 11, 7)) == "2026-2026"


class Engine:
    def __init__(self, snapshots=None):
        self.snapshots = list(snapshots or [])
        self.posts = []

    def __call__(self, method, path, timeout=120.0, **kwargs):
        if method == "POST":
            self.posts.append((path, kwargs["json"]))
            return {"status": "ok", "job_id": "job1"}
        item = self.snapshots.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def new_run(kind="compare"):
    return {"id": "job1", "kind": kind, "status": "queued", "request": {"period": "2024-2025"}, "started_at": "2026-11-07T00:00:00+00:00", "progress": None, "error": None, "result": None}


def test_a_finished_test_is_saved_even_with_nobody_watching(monkeypatch):
    engine = Engine([{"status": "running", "progress": {"stage": "loading_data"}}, {"status": "done", "progress": {"n_done": 2}, "result": raw_compare()}])
    monkeypatch.setattr(agent, "call_engine", engine)
    run = new_run()
    alpha._follow(run, sleep=lambda s: None)
    assert run["status"] == "done"
    alpha._runs.clear()  # as after a restart
    saved = alpha.run("job1")
    assert saved["result"]["rows"][0]["id"] == "academic_a"
    listed = alpha.runs()
    assert listed[0]["id"] == "job1" and "result" not in listed[0]


def test_a_failed_test_keeps_its_error(monkeypatch):
    monkeypatch.setattr(agent, "call_engine", Engine([{"status": "error", "error": "internal error; see server logs"}]))
    run = new_run()
    alpha._follow(run, sleep=lambda s: None)
    assert run["status"] == "error" and "internal error" in run["error"]


@pytest.mark.parametrize("failure", [agent.EngineError("gone", 404), agent.AgentNotReady("stopped")])
def test_a_test_lost_with_the_engine_says_so(monkeypatch, failure):
    monkeypatch.setattr(agent, "call_engine", Engine([failure]))
    run = new_run()
    alpha._follow(run, sleep=lambda s: None)
    assert run["status"] == "lost" and "run it again" in run["error"]


def test_a_brief_engine_error_doesnt_lose_the_test(monkeypatch):
    engine = Engine([agent.EngineError("busy", 502), agent.EngineError("busy", 502), {"status": "done", "result": raw_compare()}])
    monkeypatch.setattr(agent, "call_engine", engine)
    run = new_run()
    alpha._follow(run, sleep=lambda s: None)
    assert run["status"] == "done"


def test_only_one_test_at_a_time(monkeypatch):
    engine = Engine()
    monkeypatch.setattr(agent, "call_engine", engine)
    monkeypatch.setattr(alpha, "_follow", lambda run: None)
    first = alpha.start_compare(["academic_a", "academic_b"], "2024-2025")
    assert engine.posts[0][1] == {"alpha_ids": ["academic_a", "academic_b"], "universe": "sp500", "period": "2024-2025", "sort": "ir"}
    with pytest.raises(alpha.AlphaError, match="already running") as caught:
        alpha.start_bench("academic", "2024-2025")
    assert caught.value.status == 409
    assert len(engine.posts) == 1
    first["status"] = "done"
    alpha.start_bench("academic", "2024-2025")
    assert engine.posts[1][0] == "/alpha/bench"


@pytest.mark.parametrize("ids", [["academic_a"], ["academic_a", "academic_a"], ["academic_a", "../etc"], [f"academic_{i}" for i in range(51)]])
def test_bad_comparisons_are_refused_before_reaching_the_engine(monkeypatch, ids):
    engine = Engine()
    monkeypatch.setattr(agent, "call_engine", engine)
    with pytest.raises(alpha.AlphaError, match="between 2 and 50"):
        alpha.start_compare(ids, "2024-2025")
    assert engine.posts == []


def test_routes(monkeypatch):
    monkeypatch.setattr(agent, "call_engine", lambda *a, **k: {"alphas": [{"id": "academic_a"}], "total": 1})
    client = TestClient(app)
    assert client.get("/alpha/library", params={"zoo": "academic"}).json()["total"] == 1
    assert client.get("/alpha/runs").json() == []
    assert client.get("/alpha/runs/missing").status_code == 404
    assert client.get("/alpha/runs/..%2Fx").status_code in (404, 422)
    assert client.post("/alpha/bench", json={"zoo": "nope", "period": "2024-2025"}).status_code == 422


def test_a_damaged_saved_test_doesnt_hide_the_others():
    folder = alpha._folder()
    folder.mkdir(parents=True)
    (folder / "bad.json").write_text("{ not json", encoding="utf-8")
    alpha._save(new_run())
    assert [r["id"] for r in alpha.runs()] == ["job1"]
    assert alpha.run("bad") is None
