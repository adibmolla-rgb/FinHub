import json
import os
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from finhub_backend import agent, engines, installer, server
from finhub_backend.server import app


def test_settings_round_trip_keeps_key_private(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    client = TestClient(app)
    assert client.get("/agent/settings").json()["configured"] is False
    body = client.put("/agent/settings", json={"provider": "anthropic", "api_key": "sk-ant-abcdefgh1234"}).json()
    assert body["configured"] is True
    assert "sk-ant" not in json.dumps(body)  # the key itself is never returned
    assert body["api_key_hint"] == "…1234"
    # Omitting the key keeps it; switching provider resets the model to that provider's default.
    body = client.put("/agent/settings", json={"provider": "openai"}).json()
    assert body["model"] == agent.PROVIDERS["openai"]["default_model"]
    assert agent.load_settings().api_key == "sk-ant-abcdefgh1234"


def test_claude_5_models_get_default_temperature():
    env = agent.agent_env(agent.AgentSettings(provider="anthropic", model="claude-sonnet-5-5", api_key="k"))
    assert env["LANGCHAIN_TEMPERATURE"] == "1"
    assert env["ANTHROPIC_API_KEY"] == "k"
    env = agent.agent_env(agent.AgentSettings(provider="openai", api_key="k"))
    assert "LANGCHAIN_TEMPERATURE" not in env and "ANTHROPIC_API_KEY" not in env


def test_ask_refuses_without_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    res = TestClient(app).post("/agent/ask", json={"kind": "ask", "text": "hello"})
    assert res.status_code == 503


def test_attempt_state_reads_stored_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    d = tmp_path / "vibe-trading" / "sessions" / "s1" / "attempts" / "a1"
    d.mkdir(parents=True)
    (d / "attempt.json").write_text(json.dumps({"status": "failed", "error": "boom"}))
    assert agent.attempt_state("s1", "a1") == {"attempt_id": "a1", "status": "failed", "error": "boom"}
    assert agent.attempt_state("../x", "a1") is None


def test_prompts_carry_validation_rules():
    assert "next-bar fills" in agent.build_prompt("bt", "SPY sma 20 50")
    assert "bear case" in agent.build_prompt("debate", "TSLA")


def test_agent_children_do_not_inherit_the_watch_pipe(tmp_path):
    # Vibe-Trading starts child processes as it imports. On Windows, one sharing the pipe that serve.py is
    # blocked reading hangs, so the agent never started. Here a child reading stdin would block on any system.
    (tmp_path / "api_server.py").write_text(
        "import subprocess, sys, time\n"
        "def serve_main(args):\n"
        "    code = 'import sys; print(repr(sys.stdin.read()))'\n"
        "    child = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=15)\n"
        "    print(child.stdout.strip(), flush=True)\n"
        "    time.sleep(60)\n"
    )
    serve = engines.engines_dir() / "vibe-trading" / "serve.py"
    proc = subprocess.Popen(
        [sys.executable, str(serve)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, env={**os.environ, "PYTHONPATH": str(tmp_path)},
    )
    try:
        assert proc.stdout.readline().strip() == "''"  # the child's stdin is empty, not our pipe
        proc.stdin.close()  # serve.py must still exit when the backend goes away
        assert proc.wait(timeout=10) == 0
    finally:
        proc.kill()
        proc.wait()


class SwarmAgent:
    """Stands in for the Vibe-Trading server: records what FinHub sends and answers like it does."""

    def __init__(self):
        self.calls = []
        self.runs = []

    async def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/swarm/runs" and method == "GET":
            return httpx.Response(200, json=self.runs)
        if path == "/swarm/presets":
            return httpx.Response(200, json=[{"name": "investment_committee", "variables": [{"name": "target", "required": True}, {"name": "market", "required": True}, {"name": "note", "required": False}]}])
        if path == "/swarm/runs" and method == "POST":
            return httpx.Response(200, json={"id": "swarm-1", "status": "running"})
        if path == "/swarm/runs/swarm-9":
            return httpx.Response(404, json={"detail": "Run swarm-9 not found"})
        return httpx.Response(200, json={"status": "cancelled"})


@pytest.fixture
def swarm_agent(monkeypatch):
    fake = SwarmAgent()
    monkeypatch.setattr(server, "_agent_request", fake.request)
    monkeypatch.setattr(agent.server, "ensure", lambda: None)
    return fake


def starts(fake):
    return [c for c in fake.calls if c[0] == "POST" and c[1] == "/swarm/runs"]


def test_swarm_starts_with_every_required_answer(swarm_agent):
    res = TestClient(app).post("/agent/swarm/runs", json={"preset": "investment_committee", "variables": {"target": " AAPL ", "market": "US", "note": "  "}})
    assert res.status_code == 200 and res.json()["id"] == "swarm-1"
    assert starts(swarm_agent)[0][2]["json"] == {"preset_name": "investment_committee", "user_vars": {"target": "AAPL", "market": "US"}}


def test_swarm_never_starts_with_a_question_unanswered(swarm_agent):
    res = TestClient(app).post("/agent/swarm/runs", json={"preset": "investment_committee", "variables": {"target": "AAPL", "market": "   "}})
    assert res.status_code == 422 and "market" in res.json()["error"]
    assert starts(swarm_agent) == []


def test_only_one_team_runs_at_a_time(swarm_agent):
    body = {"preset": "investment_committee", "variables": {"target": "AAPL", "market": "US"}}
    swarm_agent.runs = [{"id": "swarm-1", "status": "running", "is_stale": False}]
    res = TestClient(app).post("/agent/swarm/runs", json=body)
    assert res.status_code == 409 and "already running" in res.json()["error"]
    assert starts(swarm_agent) == []
    swarm_agent.runs = [{"id": "swarm-1", "status": "failed", "is_stale": False}, {"id": "swarm-2", "status": "running", "is_stale": True}]
    assert TestClient(app).post("/agent/swarm/runs", json=body).status_code == 200  # finished or stuck runs don't block
    assert len(starts(swarm_agent)) == 1


def test_swarm_refuses_an_unknown_team_and_bad_input(swarm_agent):
    client = TestClient(app)
    assert client.post("/agent/swarm/runs", json={"preset": "nope", "variables": {}}).status_code == 404
    assert client.post("/agent/swarm/runs", json={"preset": "../etc", "variables": {}}).status_code == 422
    assert client.post("/agent/swarm/runs", json={"preset": "investment_committee", "variables": {"target": "x" * 501, "market": "US"}}).status_code == 422
    assert client.get("/agent/swarm/runs/..%2Fx").status_code in (404, 422)
    assert starts(swarm_agent) == []


def test_swarm_reports_the_agents_own_errors(swarm_agent):
    res = TestClient(app).get("/agent/swarm/runs/swarm-9")
    assert res.status_code == 404 and "not found" in res.json()["error"]


def test_swarm_explains_when_the_agent_cant_start(monkeypatch):
    def not_ready():
        raise agent.AgentNotReady("no AI provider configured; set one with the AI command")

    monkeypatch.setattr(agent.server, "ensure", not_ready)
    res = TestClient(app).get("/agent/swarm/presets")
    assert res.status_code == 503 and "AI command" in res.json()["error"]


def test_agent_wont_start_while_its_engine_is_being_updated(monkeypatch):
    # Rule 11: a process that imports a half-installed package keeps the broken module for life.
    st = installer.state("vibe-trading")
    monkeypatch.setattr(st, "state", "running")
    monkeypatch.setattr(agent.server, "_proc", None)
    with pytest.raises(agent.AgentNotReady, match="updating"):
        agent.server.ensure()


def test_installing_the_agent_engine_stops_a_running_agent(monkeypatch):
    stopped = []
    monkeypatch.setattr(agent.server, "stop", lambda: stopped.append(True))
    monkeypatch.setattr(installer, "_run", lambda st: None)
    st = installer.state("vibe-trading")
    monkeypatch.setattr(st, "state", "idle")
    installer.install("vibe-trading")
    assert stopped == [True]
    st.state = "idle"


def test_the_engine_can_run_without_an_ai_provider_but_ai_features_still_ask_for_one(tmp_path, monkeypatch):
    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(type(agent.server), "running", property(lambda self: True))
    monkeypatch.setattr(agent, "_port_open", lambda: True)
    agent.server.ensure(require_ai=False)  # the paper ledger and signal library don't need one
    with pytest.raises(agent.AgentNotReady, match="AI provider"):
        agent.server.ensure()


def test_calling_the_engine_reports_its_errors(monkeypatch):
    monkeypatch.setattr(agent.server, "ensure", lambda require_ai=True: None)
    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: httpx.Response(422, json={"detail": "bad date"}))
    with pytest.raises(agent.EngineError, match="bad date") as caught:
        agent.call_engine("GET", "/x")
    assert caught.value.status == 422
    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: httpx.Response(200, text="not json"))
    with pytest.raises(agent.EngineError, match="didn't answer"):
        agent.call_engine("GET", "/x")
