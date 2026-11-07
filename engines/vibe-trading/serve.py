"""Run Vibe-Trading's API server for FinHub.

Started by the FinHub backend inside the vibe-trading engine environment. It binds to 127.0.0.1 only,
and exits as soon as its stdin closes, so it can never outlive the backend that started it (the
backend holds the other end of the pipe).

Configuration comes from the environment, set by the backend:
  FINHUB_AGENT_PORT        port to listen on
  VIBE_TRADING_HOME        where Vibe-Trading keeps sessions and runs (inside FinHub's data folder)
  LANGCHAIN_PROVIDER, LANGCHAIN_MODEL_NAME, ANTHROPIC_API_KEY / OPENAI_API_KEY / OLLAMA_BASE_URL
"""

from __future__ import annotations

import os
import sys
import threading


def _exit_when_parent_goes(pipe: int) -> None:
    try:
        while os.read(pipe, 1024):
            pass
    except OSError:
        pass
    finally:
        os._exit(0)


def main() -> int:
    # Watch a private copy of the pipe and leave an empty stdin behind. On Windows, blocking on the real stdin
    # hangs anything else that touches it: importing Vibe-Trading stuck while loading a compiled module, and
    # never finished. It takes seconds otherwise. os.dup's copy isn't inherited by child processes either.
    pipe = os.dup(sys.stdin.fileno())
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, sys.stdin.fileno())
    os.close(null)
    threading.Thread(target=_exit_when_parent_goes, args=(pipe,), daemon=True, name="parent-watch").start()
    import api_server

    port = os.environ.get("FINHUB_AGENT_PORT", "8899")
    return api_server.serve_main(["--host", "127.0.0.1", "--port", port])


if __name__ == "__main__":
    raise SystemExit(main())
