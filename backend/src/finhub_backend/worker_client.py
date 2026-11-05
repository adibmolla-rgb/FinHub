"""Talk to an engine worker: a long-lived subprocess in the engine's own environment.

Requests and responses are JSON lines over the worker's stdin/stdout. Many requests can be in flight at
once; a reader thread routes each response to its waiting caller by id. If the worker dies, the next
call restarts it. Closing our end of stdin makes the worker exit, so it never outlives the backend.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import threading
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path

from finhub_backend.engines import NO_WINDOW


class WorkerError(Exception):
    def __init__(self, message: str, attempts: list[dict] | None = None):
        super().__init__(message)
        self.attempts = attempts or []


class WorkerUnavailable(WorkerError):
    pass


class EngineWorker:
    def __init__(self, python: Path, script: Path):
        self.python = python
        self.script = script
        self._proc: subprocess.Popen | None = None
        self._pending: dict[int, Future] = {}
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _start(self) -> None:
        if not self.python.exists():
            raise WorkerUnavailable(f"engine not installed ({self.python} missing)")
        self._proc = subprocess.Popen(
            [str(self.python), str(self.script)],
            cwd=self.script.parent,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            **NO_WINDOW,
        )
        threading.Thread(target=self._read, args=(self._proc,), daemon=True, name="worker-reader").start()

    def _read(self, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            fut = self._pending.pop(msg.get("id"), None)
            if fut is not None and not fut.done():
                fut.set_result(msg)
        # Worker exited: fail everything still waiting on it.
        for rid, fut in list(self._pending.items()):
            if not fut.done():
                fut.set_exception(WorkerUnavailable("engine worker exited"))
            self._pending.pop(rid, None)

    def call(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict:
        with self._lock:
            if not self.running:
                self._start()
            rid = next(self._ids)
            fut: Future = Future()
            self._pending[rid] = fut
            try:
                assert self._proc and self._proc.stdin
                self._proc.stdin.write(json.dumps({"id": rid, "method": method, "params": params or {}}) + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                self._pending.pop(rid, None)
                raise WorkerUnavailable(f"engine worker not accepting requests: {exc}") from exc
        try:
            msg = fut.result(timeout=timeout)
        except FutureTimeout as exc:
            self._pending.pop(rid, None)
            raise WorkerError(f"{method} timed out after {timeout:.0f}s") from exc
        if not msg.get("ok"):
            raise WorkerError(msg.get("error") or "unknown error", msg.get("attempts"))
        return msg["result"]

    def stop(self) -> None:
        with self._lock:
            if self._proc and self._proc.stdin:
                try:
                    self._proc.stdin.close()
                except OSError:
                    pass
            self._proc = None
