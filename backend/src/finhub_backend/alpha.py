"""ALPHA: Vibe-Trading's library of published signals, and testing them on the S&P 500.

A test downloads about 500 stocks and takes minutes, and Vibe-Trading forgets it when its process restarts. So a
thread here follows each run from start to finish and saves the result in FinHub's data folder, whether or not
anyone is still looking at the screen. None of this uses an AI model.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from datetime import UTC, date, datetime

from finhub_backend import agent, lab

UNIVERSE = "sp500"
# gtja191 is the rest of Vibe-Trading's 478 signals, but it only runs on Chinese shares.
ZOOS = ("academic", "alpha101", "fundamental", "qlib158")
_ALPHA_ID = re.compile(r"^[a-z][a-z0-9]+_[a-z0-9_]{1,64}$")
_PERIOD = re.compile(r"^(\d{4})-(\d{4})$")
POLL_SECONDS = 5.0
FACTOR_TIMEOUT = 1800.0  # downloading the universe takes minutes when it isn't cached
MAX_POLL_ERRORS = 12
FINISHED = ("done", "error", "lost")
META_FIELDS = (
    "survivorship_bias", "constituent_source", "constituent_source_date", "requested_instruments", "fetched_instruments",
    "missing_instruments", "price_sources", "degraded",
)

_runs: dict[str, dict] = {}
_lock = threading.Lock()


class AlphaError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def _engine(method: str, path: str, **kwargs):
    try:
        return agent.call_engine(method, path, **kwargs)
    except agent.EngineError as exc:
        raise AlphaError(str(exc), status=exc.status) from exc


def library(zoo: str | None = None, theme: str | None = None, limit: int = 1000) -> dict:
    params = {"universe": "equity_us", "limit": limit, **({"zoo": zoo} if zoo else {}), **({"theme": theme} if theme else {})}
    found = _engine("GET", "/alpha/list", params=params)
    return {"alphas": found.get("alphas", []), "total": found.get("total", 0), "zoos": list(ZOOS)}


def detail(alpha_id: str) -> dict:
    if not _ALPHA_ID.match(alpha_id):
        raise AlphaError("invalid alpha id")
    return _engine("GET", f"/alpha/{alpha_id}").get("alpha", {})


def check_period(period: str, today: date | None = None) -> str:
    match = _PERIOD.match(period)
    this_year = (today or date.today()).year
    if not match or not 2000 <= int(match[1]) <= int(match[2]) <= this_year:
        raise AlphaError(f"period must be two years like 2020-{this_year}, from 2000 to this year")
    return period


def summarise(kind: str, raw: dict) -> dict:
    """Keep what a person reads. Every run is ranked by IR, and what might flatter the result travels with it.

    A comparison returns every signal. A whole-library test only returns the best five and counts, and gives
    skipped signals as a number rather than a list.
    """
    rows = raw.get("ranking") if kind == "compare" else raw.get("top5_by_ir")
    rows = sorted(rows or [], key=lambda r: r.get("ir") or 0, reverse=True)
    meta = raw.get("meta") or {}
    skipped = raw.get("skipped") or []
    summary = {
        "rows": [{k: r.get(k) for k in ("id", "ic_mean", "ic_std", "ir", "ic_positive_ratio", "ic_count", "theme")} for r in rows],
        "skipped": [{"id": s.get("id") or s.get("alpha_id"), "reason": s.get("reason")} for s in skipped] if isinstance(skipped, list) else [],
        "n_skipped": len(skipped) if isinstance(skipped, list) else int(skipped),
        "meta": {k: meta.get(k) for k in META_FIELDS if k in meta},
    }
    for field in ("alive", "reversed", "dead", "n_alphas_tested", "by_theme"):
        if field in raw:
            summary[field] = raw[field]
    return summary


# --------------------------------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------------------------------


def _folder():
    return agent.data_dir() / "alpha-runs"


def _save(run: dict) -> None:
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{run['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(run), encoding="utf-8")
    os.replace(tmp, path)


def _start(kind: str, path: str, body: dict, request: dict) -> dict:
    with _lock:
        if any(r["status"] not in FINISHED for r in _runs.values()):
            raise AlphaError("a test is already running; wait for it to finish", status=409)
        job = _engine("POST", path, json=body)
        run = {"id": job["job_id"], "kind": kind, "status": "queued", "request": request, "started_at": datetime.now(UTC).isoformat(), "progress": None, "error": None, "result": None}
        _runs[run["id"]] = run
    threading.Thread(target=_follow, args=(run,), daemon=True, name=f"alpha-{run['id'][:8]}").start()
    return run


def _follow(run: dict, sleep=time.sleep) -> None:
    errors = 0
    while True:
        sleep(POLL_SECONDS)
        try:
            snapshot = agent.call_engine("GET", f"/alpha/{run['kind']}/{run['id']}")
            errors = 0
        except agent.AgentNotReady:
            snapshot = None
            errors = MAX_POLL_ERRORS
        except agent.EngineError as exc:
            snapshot = None
            errors = MAX_POLL_ERRORS if exc.status == 404 else errors + 1
        if snapshot is None:
            if errors >= MAX_POLL_ERRORS:
                run.update(status="lost", error="the agent engine stopped, so this test was lost; please run it again")
                break
            continue
        run.update(status=snapshot.get("status"), progress=snapshot.get("progress"))
        if run["status"] == "done":
            try:
                run["result"] = summarise(run["kind"], snapshot.get("result") or {})
            except (TypeError, ValueError, AttributeError) as exc:  # a run must never stay "running" forever
                run.update(status="error", error=f"couldn't read the result: {exc}")
            break
        if run["status"] == "error":
            run["error"] = snapshot.get("error") or "the test failed"
            break
    run["finished_at"] = datetime.now(UTC).isoformat()
    _save(run)


def start_compare(alpha_ids: list[str], period: str) -> dict:
    unique = list(dict.fromkeys(alpha_ids))
    if not 2 <= len(unique) <= 50 or not all(_ALPHA_ID.match(a) for a in unique):
        raise AlphaError("pick between 2 and 50 signals to compare")
    check_period(period)
    return _start("compare", "/alpha/compare", {"alpha_ids": unique, "universe": UNIVERSE, "period": period, "sort": "ir"}, {"alpha_ids": unique, "universe": UNIVERSE, "period": period})


def start_bench(zoo: str, period: str, top: int = 20) -> dict:
    if zoo not in ZOOS:
        raise AlphaError(f"library must be one of {', '.join(ZOOS)}")
    check_period(period)
    return _start("bench", "/alpha/bench", {"zoo": zoo, "universe": UNIVERSE, "period": period, "top": top}, {"zoo": zoo, "universe": UNIVERSE, "period": period})


def start_factor(alpha_id: str, period: str) -> dict:
    """Alphalens on one signal: does it separate winners from losers, over which horizon, at what turnover?"""
    if not _ALPHA_ID.match(alpha_id):
        raise AlphaError("invalid signal id")
    check_period(period)
    with _lock:
        if any(r["status"] not in FINISHED for r in _runs.values()):
            raise AlphaError("a test is already running; wait for it to finish", status=409)
        run_id = uuid.uuid4().hex
        record = {"id": run_id, "kind": "factor", "status": "running", "request": {"alpha_id": alpha_id, "universe": UNIVERSE, "period": period}, "started_at": datetime.now(UTC).isoformat(), "progress": None, "error": None, "result": None}
        _runs[run_id] = record
    threading.Thread(target=_analyse, args=(record,), daemon=True, name=f"alpha-{run_id[:8]}").start()
    return record


def _analyse(record: dict) -> None:
    try:
        record["result"] = lab.run("factor", {"alpha_id": record["request"]["alpha_id"], "period": record["request"]["period"]}, timeout=FACTOR_TIMEOUT)
        record["status"] = "done"
    except lab.LabError as exc:
        record.update(status="error", error=str(exc))
    record["finished_at"] = datetime.now(UTC).isoformat()
    _save(record)


def run(run_id: str) -> dict | None:
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", run_id):
        raise AlphaError("invalid run id")
    if run_id in _runs:
        return _runs[run_id]
    path = _folder() / f"{run_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def runs(limit: int = 20) -> list[dict]:
    """Newest first, without their results, so the list stays light."""
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
    newest = sorted(found.values(), key=lambda r: r.get("started_at") or "", reverse=True)[:limit]
    return [{k: v for k, v in r.items() if k != "result"} for r in newest]
