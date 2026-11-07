"""One TradingAgents run: analysts, a bull and bear debate, a trader and a risk team. JSON in on stdin, JSON out on stdout.

It uses the AI provider set with FinHub's AI command. It can't reach a broker: its output is a written report.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

REPORTS = (
    ("market_report", "Market analyst"),
    ("news_report", "News analyst"),
    ("fundamentals_report", "Fundamentals analyst"),
    ("investment_plan", "Research team's plan"),
    ("trader_investment_plan", "Trader's plan"),
    ("final_trade_decision", "Risk team's final decision"),
)


def config_for(request: dict, base: dict) -> dict:
    provider, model = request["provider"], request["model"]
    config = {**base, "llm_provider": provider, "deep_think_llm": model, "quick_think_llm": model, "max_debate_rounds": 1, "max_risk_discuss_rounds": 1, "checkpoint_enabled": False}
    if provider == "ollama":
        config["backend_url"] = f"{request['ollama_url'].rstrip('/')}/v1"
    return config


def analyse(request: dict) -> dict:
    # Keep its files with FinHub's, not in the home folder. These are read when the package is imported.
    home = Path(request["home"])
    os.environ["TRADINGAGENTS_RESULTS_DIR"] = str(home / "results")
    os.environ["TRADINGAGENTS_CACHE_DIR"] = str(home / "cache")
    os.environ["TRADINGAGENTS_MEMORY_LOG_PATH"] = str(home / "memory.md")
    from tradingagents.default_config import build_default_config
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = TradingAgentsGraph(selected_analysts=("market", "news", "fundamentals"), config=config_for(request, build_default_config()))
    state, rating = graph.propagate(request["symbol"], request["date"])
    sections = [{"key": key, "title": title, "text": str(state.get(key) or "")} for key, title in REPORTS if state.get(key)]
    return {"symbol": request["symbol"], "date": request["date"], "rating": str(rating) if rating else None, "sections": sections, "provider": request["provider"], "model": request["model"]}


TASKS = {"analyse": analyse}


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from job_runner import run

    raise SystemExit(run(TASKS, "TradingAgents"))
