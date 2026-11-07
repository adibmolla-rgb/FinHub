"""What every one-job-per-process script shares: one JSON request in, one JSON answer out.

The request is a line on stdin, read from a private copy so nothing else can hang on the pipe (Windows, see CLAUDE.md
rule 12). The backend asks for a lifeline by keeping that pipe open: when the backend goes away the pipe closes and the
job stops, so an analysis that spends AI credit can't carry on after FinHub has closed.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from collections.abc import Callable


def _read_request() -> dict:
    private = os.dup(0)
    null = os.open(os.devnull, os.O_RDONLY)
    os.dup2(null, 0)
    os.close(null)
    stream = os.fdopen(private, encoding="utf-8")
    request = json.loads(stream.readline())
    if request.get("lifeline"):

        def stop_when_abandoned() -> None:
            stream.read()
            os._exit(3)

        threading.Thread(target=stop_when_abandoned, daemon=True, name="lifeline").start()
    return request


def run(tasks: dict[str, Callable[[dict], dict]], engine_name: str) -> int:
    # Libraries print progress to stdout, so keep the real one for the answer and send the rest to the log.
    answer = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    try:
        request = _read_request()
        result = {"ok": True, "result": tasks[request["task"]](request)}
    except ModuleNotFoundError as exc:
        result = {"ok": False, "error": f"the {engine_name} engine needs updating ({exc.name} is missing): reinstall it from SYS"}
    except Exception as exc:  # noqa: BLE001 - the caller shows this; it mustn't vanish into a traceback
        result = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:500]}"}
    json.dump(result, answer)
    answer.flush()
    return 0
