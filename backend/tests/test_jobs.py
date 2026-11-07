import importlib.util
import json
import os
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from finhub_backend import agent, engines, installer, jobs, lab, market
from finhub_backend.server import app


@pytest.fixture
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(jobs, "_runs", {})


def wait(run: dict) -> dict:
    for _ in range(200):
        if run["status"] != "running" and run.get("finished_at"):
            for thread in threading.enumerate():
                if thread.name.startswith("job-"):
                    thread.join(5)  # it saves the run just after marking it finished
            return run
        time.sleep(0.01)
    raise AssertionError("the run never finished")


def load(engine: str):
    path = engines.engines_dir() / engine / "job.py"
    spec = importlib.util.spec_from_file_location(f"job_{engine}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_finished_run_is_saved_and_survives_a_restart(clean):
    run = wait(jobs.start("qlib", {"x": 1}, lambda: {"ic": 0.01}))
    assert run["status"] == "done" and run["result"] == {"ic": 0.01}
    jobs._runs.clear()
    assert jobs.get(run["id"])["result"] == {"ic": 0.01}
    assert [r["id"] for r in jobs.listing("qlib")] == [run["id"]]
    assert "result" not in jobs.listing("qlib")[0]
    assert jobs.listing("agents") == []


def test_only_one_of_a_kind_runs_at_a_time(clean):
    release = threading.Event()
    first = jobs.start("agents", {}, lambda: release.wait(5) and {})
    with pytest.raises(jobs.JobError) as refused:
        jobs.start("agents", {}, dict)
    assert refused.value.status == 409
    other = wait(jobs.start("qlib", {}, dict))  # another kind isn't held up
    assert other["status"] == "done"
    release.set()
    wait(first)
    wait(jobs.start("agents", {}, dict))  # and the next can start once the first has ended


@pytest.mark.parametrize("failure", [lab.LabError("needs the engine", status=503), KeyError("surprise"), OSError("disk")])
def test_a_run_always_ends_even_on_an_unexpected_failure(clean, failure):
    def work():
        raise failure

    run = wait(jobs.start("qlib", {}, work))
    assert run["status"] == "error" and run["error"]
    wait(jobs.start("qlib", {}, dict))  # otherwise no run could ever start again


def test_a_bad_or_unknown_id_finds_nothing(clean):
    assert jobs.get("../../etc/passwd") is None
    assert jobs.get("0123456789abcdef") is None
    (agent.data_dir() / "jobs").mkdir(parents=True)
    (agent.data_dir() / "jobs" / "broken.json").write_text("{not json")
    assert jobs.listing("qlib") == []


def test_agents_needs_a_provider_and_only_it_receives_the_key(clean, monkeypatch):
    client = TestClient(app)
    run = client.post("/jobs/agents", json={"symbol": "tsla"}).json()
    assert run["request"]["symbol"] == "TSLA"
    deadline = time.time() + 2
    while client.get(f"/jobs/{run['id']}").json()["status"] == "running" and time.time() < deadline:
        time.sleep(0.01)
    assert "no AI provider" in client.get(f"/jobs/{run['id']}").json()["error"]

    calls = []
    monkeypatch.setattr(lab, "run", lambda task, request, **kw: calls.append((task, request, kw)) or {"rating": "Hold"})
    agent.save_settings({"provider": "anthropic", "api_key": "sk-test-12345"})
    from finhub_backend import server

    server._agents_work("TSLA", "2026-11-06")
    task, request, kw = calls[0]
    assert task == "analyse" and kw["engine"] == "tradingagents"
    assert kw["extra_env"] == {"ANTHROPIC_API_KEY": "sk-test-12345"}
    assert "sk-test" not in json.dumps(request)  # the request is saved with the run, and must not hold the key


def test_ollama_being_down_is_explained_in_its_own_terms(clean, monkeypatch):
    from finhub_backend import server

    def down(*a, **k):
        raise lab.LabError("OpenAIConnectionError: Connection error.")

    monkeypatch.setattr(lab, "run", down)
    agent.save_settings({"provider": "ollama"})
    with pytest.raises(lab.LabError, match="couldn't reach Ollama at http://127.0.0.1:11434"):
        server._agents_work("TSLA", "2026-11-06")


def test_jobs_routes_refuse_bad_input(clean):
    client = TestClient(app)
    assert client.post("/jobs/agents", json={"symbol": "not a ticker!"}).status_code == 422
    assert client.get("/jobs?kind=nope").status_code == 422
    assert client.get("/jobs/0123456789abcdef").status_code == 404


def test_qlib_refuses_too_few_stocks(clean, monkeypatch):
    from finhub_backend import server

    monkeypatch.setattr(market, "history", lambda *a, **k: (_ for _ in ()).throw(market.MarketDataError("down", [])))
    with pytest.raises(lab.LabError, match="it needs 20"):
        server._qlib_work()


# The stop-when-abandoned pipe: an AGENTS run mustn't keep spending after FinHub has closed.


def _start_job(tmp_path, body: str) -> subprocess.Popen:
    script = tmp_path / "job.py"
    runner = engines.engines_dir()
    script.write_text(f"import sys,time\nsys.path.insert(0, {str(runner)!r})\nfrom job_runner import run\n{body}\nraise SystemExit(run(TASKS, 'test'))\n")
    return subprocess.Popen([sys.executable, str(script)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)


def test_a_job_stops_when_the_backend_goes_away(tmp_path):
    proc = _start_job(tmp_path, "TASKS = {'slow': lambda r: time.sleep(60)}")
    proc.stdin.write(json.dumps({"task": "slow", "lifeline": True}) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)
    assert proc.poll() is None
    proc.stdin.close()
    assert proc.wait(timeout=10) == 3


def test_a_job_without_a_lifeline_runs_to_the_end(tmp_path):
    proc = _start_job(tmp_path, "TASKS = {'quick': lambda r: time.sleep(0.3) or {'done': r['x']}}")
    out, _ = proc.communicate(json.dumps({"task": "quick", "x": 7}), timeout=20)
    assert json.loads(out) == {"ok": True, "result": {"done": 7}}


def test_a_missing_library_says_how_to_fix_it(tmp_path):
    proc = _start_job(tmp_path, "def t(r):\n    import not_a_real_library\nTASKS = {'t': t}")
    out, _ = proc.communicate(json.dumps({"task": "t"}), timeout=20)
    assert "reinstall it from SYS" in json.loads(out)["error"]


def test_lab_run_lets_a_job_answer_and_keeps_keys_away_unless_given(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FINHUB_ENGINES_DIR", str(tmp_path / "engines"))
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    monkeypatch.setattr(engines, "engine_python", lambda engine_id: type("P", (), {"exists": lambda self: True, "__str__": lambda self: sys.executable})())
    folder = tmp_path / "engines" / "qlib"
    folder.mkdir(parents=True)
    (folder / "job.py").write_text("import json,os,sys\nr=json.loads(sys.stdin.readline())\nprint(json.dumps({'ok':True,'result':{'life':r['lifeline'],'openai':os.environ.get('OPENAI_API_KEY'),'given':os.environ.get('ANTHROPIC_API_KEY'),'hf':os.environ.get('HF_HOME')}}))\n")
    out = lab.run("train", {}, engine="qlib", extra_env={"ANTHROPIC_API_KEY": "given"})
    assert out["life"] is True and out["openai"] is None and out["given"] == "given"
    assert out["hf"].startswith(str(tmp_path / "data"))


def test_an_optional_engine_that_is_missing_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_ENGINE_ENVS_DIR", str(tmp_path / "nothing"))
    monkeypatch.setattr(installer.state("sentiment"), "state", "idle")
    with pytest.raises(lab.LabError, match="optional sentiment engine; install it from SYS") as caught:
        lab.run("mood", {}, engine="sentiment")
    assert caught.value.status == 503


def test_optional_engines_are_marked_and_the_others_are_not():
    optional = {e.id for e in engines.ENGINES if e.optional}
    assert optional == {"sentiment", "tradingagents", "qlib"}


def test_the_installer_uses_an_engines_own_python_over_the_computers_setting(tmp_path, monkeypatch):
    # This computer sets UV_PYTHON=3.13, and Qlib has no packages for it: found by testing the install, not by thinking.
    monkeypatch.setenv("UV_PYTHON", "3.13")
    project = tmp_path / "engines" / "qlib"
    project.mkdir(parents=True)
    (project / ".python-version").write_text("3.12\n")
    monkeypatch.setenv("FINHUB_ENGINES_DIR", str(tmp_path / "engines"))
    monkeypatch.setattr(installer, "uv_path", lambda: "uv")
    seen = {}

    class Fake:
        stdout: list[str] = []

        def __init__(self, cmd, **kw):
            seen.update(kw["env"])

        def wait(self):
            return 1

    monkeypatch.setattr(installer.subprocess, "Popen", Fake)
    installer._sync(installer.InstallState(engine="qlib"))
    assert seen["UV_PYTHON"] == "3.12"


# The job scripts' own logic, without their heavy libraries.


def test_tradingagents_is_pointed_at_the_chosen_provider():
    job = load("tradingagents")
    base = {"backend_url": None, "llm_provider": "openai", "max_debate_rounds": 3}
    local = job.config_for({"provider": "ollama", "model": "qwen2.5:7b", "ollama_url": "http://127.0.0.1:11434/"}, base)
    assert local["backend_url"] == "http://127.0.0.1:11434/v1" and local["deep_think_llm"] == local["quick_think_llm"] == "qwen2.5:7b"
    claude = job.config_for({"provider": "anthropic", "model": "claude-sonnet-5-5", "ollama_url": "x"}, base)
    assert claude["backend_url"] is None and claude["llm_provider"] == "anthropic"
    assert claude["max_debate_rounds"] == 1  # a single round keeps the cost of a run down


def test_qlib_splits_by_year_and_never_overlaps():
    job = load("qlib")
    calendar = [f"{y}-{m:02d}-15" for y in range(2010, 2027) for m in range(1, 13)]
    split = job.segments(calendar)
    assert split["test"][0] == "2024-01-01" and split["valid"][0] == "2022-01-01"
    assert split["train"][1] < split["valid"][0] <= split["valid"][1] < split["test"][0]


def test_qlib_files_are_written_in_its_format(tmp_path):
    job = load("qlib")
    import struct

    panels = {
        "AAA": {"dates": ["2020-01-02", "2020-01-03", "2020-01-06"], "open": [1, 2, 3], "high": [2, 3, 4], "low": [0.5, 1, 2], "close": [1.5, 2.5, 3.5], "volume": [10, 20, 30]},
        "BBB": {"dates": ["2020-01-03", "2020-01-06"], "open": [5, None], "high": [6, 7], "low": [4, 5], "close": [5.5, 6.5], "volume": [1, 2]},
    }
    calendar = job.write_dataset(tmp_path / "data", panels)
    assert calendar == ["2020-01-02", "2020-01-03", "2020-01-06"]
    raw = (tmp_path / "data" / "features" / "bbb" / "open.day.bin").read_bytes()
    values = struct.unpack("<3f", raw)
    assert values[0] == 1 and values[1] == 5  # BBB starts at the calendar's second day
    assert values[2] != values[2]  # a missing price stays missing rather than being guessed
    assert "BBB\t2020-01-03\t2020-01-06" in (tmp_path / "data" / "instruments" / "all.txt").read_text()


def test_the_engine_projects_are_ready_to_install():
    for engine in ("sentiment", "tradingagents", "qlib"):
        folder = engines.engines_dir() / engine
        assert (folder / "uv.lock").exists() and (folder / "job.py").exists() and (folder / "pyproject.toml").exists()
    assert (engines.engines_dir() / "qlib" / ".python-version").read_text().strip() == "3.12"
    assert os.path.exists(engines.engines_dir() / "job_runner.py")
