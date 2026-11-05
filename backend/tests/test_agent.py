import json

from fastapi.testclient import TestClient

from finhub_backend import agent
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
