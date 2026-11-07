import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from finhub_backend import market, mcp_server, options
from finhub_backend.server import app
from finhub_backend.worker_client import EngineWorker

from .test_market import QUOTE_RESULT


def test_python_options_port_matches_reference():
    assert options.black_scholes("call", 100, 100, 1, 0.05, 0, 0.2) == pytest.approx(10.450583572185565, abs=1e-9)
    put = options.black_scholes("put", 100, 110, 1, 0.05, 0, 0.3)
    assert options.binomial("put", 100, 110, 1, 0.05, 0, 0.3, american=True) > put + 0.1
    assert options.implied_vol(put, "put", 100, 110, 1, 0.05, 0) == pytest.approx(0.3, abs=1e-7)
    assert options.implied_vol(1000, "call", 100, 100, 1, 0.05, 0) is None
    g = options.greeks("call", 100, 100, 1, 0.05, 0, 0.2)
    h = 1e-4
    fd = (options.black_scholes("call", 100 + h, 100, 1, 0.05, 0, 0.2) - options.black_scholes("call", 100 - h, 100, 1, 0.05, 0, 0.2)) / (2 * h)
    assert g["delta"] == pytest.approx(fd, abs=1e-6)


def test_price_option_tool_works_without_the_app():
    out = mcp_server.finhub_price_option("call", 100, 100, 365, 0.2, 0.05, 0.0, market_price=10.450583572185565)
    assert out["european_black_scholes"] == pytest.approx(10.4506, abs=1e-4)
    assert out["implied_volatility"] == pytest.approx(0.2, abs=1e-6)


def test_tools_explain_when_finhub_is_not_running(monkeypatch):
    monkeypatch.setattr(mcp_server, "BACKEND", "http://127.0.0.1:9")  # nothing listens on port 9
    with pytest.raises(mcp_server.FinHubUnavailable, match="Open the FinHub app"):
        mcp_server.finhub_watchlist()


def test_quote_tool_goes_through_the_app(monkeypatch, tmp_path):
    script = tmp_path / "w.py"
    script.write_text(
        "import json,sys\n"
        f"R={json.dumps(QUOTE_RESULT)!r}\n"
        "for l in sys.stdin:\n"
        "    q=json.loads(l); print(json.dumps({'id':q['id'],'ok':True,'result':json.loads(R)}),flush=True)\n"
    )
    w = EngineWorker(Path(sys.executable), script)
    market.set_worker(w)
    monkeypatch.setattr(mcp_server, "_client", lambda: TestClient(app))
    try:
        out = mcp_server.finhub_quote("test")
        assert out["values"]["change_pct"] == {"value": pytest.approx(0.1), "unit": "fraction", "source": "computed by FinHub", "formula": "Change ÷ Previous close"}
        assert out["fallback_used"] is True
    finally:
        w.stop()
        market.set_worker(None)


def test_stdio_protocol_end_to_end():
    """Launch finhub-mcp like Claude Desktop would and speak MCP to it over stdio."""
    exe = Path(sys.executable).parent / ("finhub-mcp.exe" if sys.platform == "win32" else "finhub-mcp")
    proc = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

    def send(msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def recv(want_id):
        while True:
            line = proc.stdout.readline()
            assert line, "server closed the connection"
            msg = json.loads(line)
            if msg.get("id") == want_id:
                return msg

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
        init = recv(1)
        assert init["result"]["serverInfo"]["name"] == "finhub"
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"]: t for t in recv(2)["result"]["tools"]}
        assert {"finhub_quote", "finhub_history", "finhub_backtest", "finhub_portfolio_risk", "finhub_price_option", "finhub_watchlist",
                "finhub_arena_state", "finhub_arena_order", "finhub_arena_cancel", "finhub_arena_advance",
                "finhub_fundamentals", "finhub_macro", "finhub_screen", "finhub_add_alert", "finhub_alerts",
                "finhub_volatility", "finhub_bond", "finhub_find_symbols", "finhub_news_sentiment", "finhub_read_filing", "finhub_optimise", "finhub_performance_report", "finhub_paper_accounts", "finhub_alpha_library", "finhub_factors", "finhub_cot", "finhub_fed", "finhub_ownership", "finhub_options_chain", "finhub_calendar", "finhub_filings", "finhub_etf_holdings", "finhub_yield_curve", "finhub_portfolio"} <= set(tools)
        assert tools["finhub_add_alert"]["annotations"]["readOnlyHint"] is False
        assert tools["finhub_arena_order"]["annotations"]["readOnlyHint"] is False
        assert "SIMULATED" in tools["finhub_arena_order"]["description"]
        assert tools["finhub_quote"]["annotations"]["readOnlyHint"] is True
        assert tools["finhub_ownership"]["annotations"]["readOnlyHint"] is True
        assert tools["finhub_portfolio"]["annotations"]["readOnlyHint"] is True
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "finhub_price_option", "arguments": {
            "option_type": "call", "spot": 100, "strike": 100, "days_to_expiry": 365, "volatility": 0.2, "rate": 0.05}}})
        res = recv(3)["result"]
        assert not res.get("isError")
        payload = res.get("structuredContent") or json.loads(res["content"][0]["text"])
        assert payload["european_black_scholes"] == pytest.approx(10.4506, abs=1e-4)
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)


def test_arena_tools_trade_through_the_app(monkeypatch):
    from finhub_backend import sim

    sim.reset_arena(9)
    monkeypatch.setattr(mcp_server, "_client", lambda: TestClient(app))
    fill = mcp_server.finhub_arena_order("claude", "buy", 50)
    assert fill["filled"] == 50 and fill["account"]["position"] == 50
    mcp_server.finhub_arena_advance(20)
    st = mcp_server.finhub_arena_state("claude")
    assert st["step"] == 70 and st["your_account"]["position"] == 50
    assert any(r["name"] == "claude" for r in st["leaderboard"])


def test_screen_tool_uses_the_tickers_it_was_given(monkeypatch):
    sent = {}

    def fake_call(method, path, **kwargs):
        sent.update(kwargs["json"])
        return {"matches": []}

    monkeypatch.setattr(mcp_server, "_call", fake_call)
    mcp_server.finhub_screen(symbols=["AAA", "BBB"])
    assert sent["universe"] == "custom"
    assert sent["symbols"] == ["AAA", "BBB"]


def test_alert_and_screen_tools_go_through_the_app(monkeypatch, tmp_path):
    from finhub_backend import screener

    monkeypatch.setenv("FINHUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(mcp_server, "_client", lambda: TestClient(app))
    a = mcp_server.finhub_add_alert("spy", "move_down", 0.03)
    assert a["description"] == "SPY: day's change reaches or falls below −3%"
    assert mcp_server.finhub_alerts()["alerts"][0]["id"] == a["id"]
    screener._cache.clear()
    monkeypatch.setattr(market, "quote", lambda s: (_ for _ in ()).throw(market.MarketDataError("offline", [])))
    out = mcp_server.finhub_screen(universe="custom", symbols=["AAA", "BBB"], min_change=0.01)
    assert out["matches"] == [] and {f["symbol"] for f in out["failed"]} == {"AAA", "BBB"}


def test_an_assistant_is_told_why_a_tool_failed():
    # The SDK replaces any exception but ToolError with "Error executing tool <name>".
    proc = subprocess.Popen(
        [sys.executable, "-c", "from finhub_backend.mcp_server import main; main()"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env={**os.environ, "FINHUB_BACKEND_URL": "http://127.0.0.1:9"},
    )
    try:
        def ask(message):
            proc.stdin.write(json.dumps({"jsonrpc": "2.0", **message}) + "\n")
            proc.stdin.flush()

        def answer(wanted):
            for line in proc.stdout:
                reply = json.loads(line)
                if reply.get("id") == wanted:
                    return reply
            raise AssertionError("no reply")

        ask({"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
        answer(1)
        ask({"method": "notifications/initialized"})
        ask({"id": 2, "method": "tools/call", "params": {"name": "finhub_watchlist", "arguments": {}}})
        result = answer(2)["result"]
        assert result["isError"] is True
        assert "Open the FinHub app" in result["content"][0]["text"]
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)


def test_provider_errors_carry_their_reason(monkeypatch):
    from mcp.server.mcpserver.exceptions import ToolError

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, path, **kwargs):
            return httpx.Response(502, json={"error": "no provider could serve quote", "attempts": [{"provider": "yahoo", "ok": False, "error": "NoData"}]})

    monkeypatch.setattr(mcp_server, "_client", Client)
    with pytest.raises(ToolError, match="no provider could serve quote.*yahoo: NoData"):
        mcp_server.finhub_quote("ZZZ")
