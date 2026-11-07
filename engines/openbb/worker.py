"""FinHub data worker: a long-lived process inside the OpenBB engine environment.

Protocol: one JSON object per line on stdin, one per line on stdout.
  request:  {"id": 1, "method": "quote", "params": {"symbol": "AAPL"}}
  response: {"id": 1, "ok": true, "result": {...}}
            {"id": 1, "ok": false, "error": "...", "attempts": [...]}

Requests are handled concurrently. The worker exits when stdin closes, so it can never outlive the
backend that started it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

# Libraries sometimes print to stdout; keep the protocol channel clean by moving them to stderr.
_protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1, encoding="utf-8")
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
sys.stdout = sys.stderr

# Requests move off stdin too, because child processes inherit it. On Windows, a child that touches a
# pipe this process is blocked reading hangs until the next line arrives, and OpenBB runs `git` as it
# loads: a first request with nothing after it would never finish. os.dup's copy isn't inherited.
_requests = os.fdopen(os.dup(sys.stdin.fileno()), "r", encoding="utf-8")
_null = os.open(os.devnull, os.O_RDONLY)
os.dup2(_null, sys.stdin.fileno())
os.close(_null)

import providers  # noqa: E402  (imported after the stdout swap on purpose)

_write_lock = threading.Lock()


def _send(message: dict) -> None:
    line = json.dumps(message, default=str)
    with _write_lock:
        _protocol.write(line + "\n")
        _protocol.flush()


def _warmup() -> dict:
    providers.obb()  # pays OpenBB's slow import once, in the background
    return {"warm": True}


def handle(request: dict) -> None:
    rid = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    try:
        if method == "ping":
            result = {"pong": True, "pid": os.getpid()}
        elif method == "warmup":
            result = _warmup()
        elif method in providers.FETCHERS:
            chain = params.pop("chain", None)
            result = providers.run_chain(method, providers.FETCHERS[method], params, chain)
        else:
            raise ValueError(f"unknown method {method!r}")
        _send({"id": rid, "ok": True, "result": result})
    except providers.ChainFailed as exc:
        _send({"id": rid, "ok": False, "error": str(exc), "attempts": exc.attempts})
    except Exception as exc:
        _send({"id": rid, "ok": False, "error": f"{type(exc).__name__}: {exc}", "attempts": []})


def main() -> None:
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="req")
    for line in _requests:  # ends when the backend closes our stdin or exits
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            _send({"id": None, "ok": False, "error": "invalid JSON", "attempts": []})
            continue
        pool.submit(handle, request)
    pool.shutdown(wait=False, cancel_futures=True)
    os._exit(0)


if __name__ == "__main__":
    main()
