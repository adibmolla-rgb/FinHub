"""Reasoning agent: FinHub's bridge to Vibe-Trading.

The backend starts Vibe-Trading's API server as a child process (engines/vibe-trading/serve.py in the
engine's own environment), configured from FinHub's agent settings, and proxies a small surface of it:
create a research session, send a question, stream the agent's events, cancel.

Settings (provider, model, API key) live in a JSON file in FinHub's data folder, readable only by the
current user where the OS supports it. They are passed to the agent process as environment variables
and never sent anywhere except the chosen LLM provider.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path

from pydantic import BaseModel, Field

from finhub_backend import engines

AGENT_PORT = int(os.environ.get("FINHUB_AGENT_PORT", "8899"))
AGENT_URL = f"http://127.0.0.1:{AGENT_PORT}"

PROVIDERS = {
    "anthropic": {"label": "Claude (Anthropic)", "key_env": "ANTHROPIC_API_KEY", "default_model": "claude-sonnet-5-5"},
    "openai": {"label": "OpenAI", "key_env": "OPENAI_API_KEY", "default_model": "gpt-5.5"},
    "ollama": {"label": "Ollama (local, free)", "key_env": None, "default_model": "qwen2.5:7b"},
}


class AgentSettings(BaseModel):
    provider: str = Field("anthropic", pattern="^(anthropic|openai|ollama)$")
    model: str = ""
    api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"

    def public(self) -> dict:
        key = self.api_key
        return {
            "provider": self.provider,
            "model": self.model or PROVIDERS[self.provider]["default_model"],
            "ollama_url": self.ollama_url,
            "has_api_key": bool(key),
            "api_key_hint": f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else ""),
            "configured": self.provider == "ollama" or bool(key),
            "providers": {k: {"label": v["label"], "default_model": v["default_model"]} for k, v in PROVIDERS.items()},
        }


def data_dir() -> Path:
    base = os.environ.get("FINHUB_DATA_DIR")
    if base:
        return Path(base)
    return Path.home() / ".finhub"


def _settings_path() -> Path:
    return data_dir() / "agent-settings.json"


def load_settings() -> AgentSettings:
    try:
        return AgentSettings.model_validate_json(_settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return AgentSettings()


def save_settings(update: dict) -> AgentSettings:
    current = load_settings()
    merged = current.model_dump()
    for k, v in update.items():
        if k == "api_key" and v is None:
            continue  # None means "keep the stored key"
        if k in merged and v is not None:
            merged[k] = v
    if update.get("provider") and update["provider"] != current.provider and "model" not in update:
        merged["model"] = ""
    settings = AgentSettings.model_validate(merged)
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)
    server.stop()  # restart with the new settings on next use
    return settings


def agent_env(settings: AgentSettings) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    env.update(
        FINHUB_AGENT_PORT=str(AGENT_PORT),
        VIBE_TRADING_HOME=str(data_dir() / "vibe-trading"),
        LANGCHAIN_PROVIDER=settings.provider,
        LANGCHAIN_MODEL_NAME=settings.model or PROVIDERS[settings.provider]["default_model"],
        PYTHONIOENCODING="utf-8",
    )
    # Claude 5-family models only accept the default temperature (1); Vibe-Trading sends 0 by default,
    # which langchain-anthropic rejects before the request is even made.
    model = env["LANGCHAIN_MODEL_NAME"]
    if settings.provider == "anthropic" and re.match(r"claude-(fable|opus|sonnet|haiku)-5", model):
        env["LANGCHAIN_TEMPERATURE"] = "1"
    key_env = PROVIDERS[settings.provider]["key_env"]
    if key_env and settings.api_key:
        env[key_env] = settings.api_key
    if settings.provider == "ollama":
        env["OLLAMA_BASE_URL"] = settings.ollama_url
    return env


class AgentNotReady(Exception):
    pass


def _port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", AGENT_PORT), timeout=0.3):
            return True
    except OSError:
        return False


class AgentServer:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._log: Path | None = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def ensure(self, timeout: float = 180.0) -> None:
        """Start the agent server if needed and wait until it accepts connections."""
        with self._lock:
            if self.running and _port_open():
                return
            if not self.running:
                self._start()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _port_open():
                return
            if not self.running:
                raise AgentNotReady(f"the agent process exited; see {self._log}")
            time.sleep(0.5)
        raise AgentNotReady(f"the agent did not start within {timeout:.0f}s; see {self._log}")

    def _start(self) -> None:
        python = engines.engine_python("vibe-trading")
        if not python.exists():
            raise AgentNotReady("the reasoning-agent engine (Vibe-Trading) is not installed; install it from SYS")
        settings = load_settings()
        if not settings.public()["configured"]:
            raise AgentNotReady("no AI provider configured; set one with the AI command")
        if _port_open():
            raise AgentNotReady(f"port {AGENT_PORT} is already in use by another program")
        logs = data_dir() / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        self._log = logs / "agent.log"
        script = engines.engines_dir() / "vibe-trading" / "serve.py"
        work = data_dir() / "vibe-trading"
        work.mkdir(parents=True, exist_ok=True)
        self._proc = subprocess.Popen(
            [str(python), str(script)],
            cwd=work,
            stdin=subprocess.PIPE,
            stdout=open(self._log, "w", encoding="utf-8"),  # noqa: SIM115 (lives as long as the process)
            stderr=subprocess.STDOUT,
            env=agent_env(settings),
            **engines.NO_WINDOW,
        )

    def stop(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()  # serve.py exits when its stdin closes
                proc.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                proc.kill()

    def status(self) -> dict:
        return {"running": self.running and _port_open(), "port": AGENT_PORT, "log": str(self._log) if self._log else None}


server = AgentServer()


# --------------------------------------------------------------------------------------------------
# Prompt templates for the command bar
# --------------------------------------------------------------------------------------------------

VALIDATION_RULES = (
    "Rules for any backtest: use next-bar fills (never trade at the close used to compute the signal), "
    "include realistic transaction costs and slippage, compare against buy-and-hold over the same period, "
    "report Sharpe ratio, maximum drawdown, turnover and number of trades, say how many parameter variants "
    "you tried, and flag any result that looks too good (e.g. Sharpe above 2) as suspicious. "
    "State the data source and date range you used."
)


def build_prompt(kind: str, text: str) -> str:
    text = text.strip()
    if kind == "ask":
        return f"{text}\n\nShow your plan first, then the evidence. Cite the data source and dates for every number."
    if kind == "bt":
        return (
            f"Backtest this strategy: {text}. Use daily data for roughly the last 5 years unless I said otherwise. "
            f"{VALIDATION_RULES}"
        )
    if kind == "debate":
        return (
            f"Run an investment debate on {text}. First, the strongest bull case with evidence. Second, the "
            "strongest bear case with evidence. Third, a neutral judge who weighs both, names the key uncertainty, "
            "and says what data would change the conclusion. Cite data sources and dates. This is research, not advice."
        )
    raise ValueError(kind)


def attempt_state(session_id: str, attempt_id: str) -> dict | None:
    """Read an attempt's status and error from Vibe-Trading's session store.

    The event stream only replays a run that is still going, so a run that failed before the UI
    connected would otherwise never report why. The stored attempt record always has the answer.
    """
    if not (re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", session_id) and re.fullmatch(r"[A-Za-z0-9_\-]{1,80}", attempt_id)):
        return None
    path = data_dir() / "vibe-trading" / "sessions" / session_id / "attempts" / attempt_id / "attempt.json"
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return {"attempt_id": attempt_id, "status": record.get("status"), "error": record.get("error")}
