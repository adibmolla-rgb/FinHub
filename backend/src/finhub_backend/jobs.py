"""Long analyses that run in the background, so a person can leave the screen. Results are saved in the data folder."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from finhub_backend import agent, lab, market

FINISHED = ("done", "error")
_runs: dict[str, dict] = {}
_lock = threading.Lock()


class JobError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _folder():
    return agent.data_dir() / "jobs"


def _save(run: dict) -> None:
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{run['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(run), encoding="utf-8")
    os.replace(tmp, path)


def start(kind: str, request: dict, work: Callable[[], dict]) -> dict:
    """One of each kind at a time: these take minutes, and some spend the AI provider's credit."""
    with _lock:
        if any(r["kind"] == kind and r["status"] not in FINISHED for r in _runs.values()):
            raise JobError("one of these is already running; wait for it to finish", status=409)
        run = {"id": uuid.uuid4().hex, "kind": kind, "status": "running", "request": request, "started_at": datetime.now(UTC).isoformat(), "error": None, "result": None}
        _runs[run["id"]] = run
    threading.Thread(target=_work, args=(run, work), daemon=True, name=f"job-{kind}").start()
    return run


def _work(run: dict, work: Callable[[], dict]) -> None:
    try:
        run["result"] = work()
        run["status"] = "done"
    except (lab.LabError, market.MarketDataError, agent.AgentNotReady, JobError) as exc:
        run.update(status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - a run must always end, or the next one can never start
        run.update(status="error", error=f"{type(exc).__name__}: {exc}")
    run["finished_at"] = datetime.now(UTC).isoformat()
    try:
        _save(run)
    except OSError as exc:
        run["error"] = run["error"] or f"finished, but couldn't be saved: {exc}"


def get(run_id: str) -> dict | None:
    if not re.fullmatch(r"[a-f0-9]{8,64}", run_id):
        return None
    if run_id in _runs:
        return _runs[run_id]
    try:
        return json.loads((_folder() / f"{run_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def listing(kind: str, limit: int = 20) -> list[dict]:
    """Newest first, without results, so the list stays light."""
    found: dict[str, dict] = {}
    folder = _folder()
    if folder.exists():
        for path in folder.glob("*.json"):
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                found[saved["id"]] = saved
            except (OSError, ValueError, KeyError):
                continue  # one damaged file shouldn't hide the others
    found.update(_runs)
    mine = [r for r in found.values() if r.get("kind") == kind]
    newest = sorted(mine, key=lambda r: r.get("started_at") or "", reverse=True)[:limit]
    return [{k: v for k, v in r.items() if k != "result"} for r in newest]
