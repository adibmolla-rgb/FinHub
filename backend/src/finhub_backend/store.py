"""Small persistent state: the watchlist, and read-only access to past agent research.

Everything lives in FinHub's data folder (agent.data_dir()). Agent research is read straight from
Vibe-Trading's session store on disk, so past runs can be browsed without starting the agent.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from finhub_backend.agent import data_dir

SYMBOL = re.compile(r"^\^?[A-Z0-9][A-Z0-9.\-^=]{0,14}$")  # a leading ^ marks an index, e.g. ^GSPC
MAX_WATCHLIST = 50
DEFAULT_WATCHLIST = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "TLT", "GLD"]

_lock = threading.Lock()


def _watchlist_path() -> Path:
    return data_dir() / "watchlist.json"


def get_watchlist() -> list[str]:
    try:
        data = json.loads(_watchlist_path().read_text(encoding="utf-8"))
        return [s for s in data.get("symbols", []) if isinstance(s, str) and SYMBOL.match(s)]
    except (OSError, ValueError):
        return list(DEFAULT_WATCHLIST)


def set_watchlist(symbols: list[str]) -> list[str]:
    clean: list[str] = []
    for s in symbols:
        s = s.strip().upper()
        if not SYMBOL.match(s):
            raise ValueError(f"invalid ticker {s!r}")
        if s not in clean:
            clean.append(s)
    if len(clean) > MAX_WATCHLIST:
        raise ValueError(f"at most {MAX_WATCHLIST} tickers")
    with _lock:
        path = _watchlist_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"symbols": clean}, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    return clean


# --------------------------------------------------------------------------------------------------
# Past agent research ("notes")
# --------------------------------------------------------------------------------------------------

_ID = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")


def _sessions_dir() -> Path:
    return data_dir() / "vibe-trading" / "sessions"


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
    except OSError:
        pass
    return out


def _kind(title: str) -> str:
    head = title.split(":", 1)[0].strip().upper()
    return head.lower() if head in {"ASK", "BT", "DEBATE"} else "ask"


def list_notes(limit: int = 200) -> list[dict]:
    root = _sessions_dir()
    if not root.is_dir():
        return []
    notes = []
    for d in root.iterdir():
        meta = _read_json(d / "session.json") if d.is_dir() else None
        if not meta:
            continue
        attempt = _read_json(d / "attempts" / str(meta.get("last_attempt_id")) / "attempt.json") if meta.get("last_attempt_id") else None
        messages = _read_jsonl(d / "messages.jsonl")
        answer = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "assistant"), "")
        title = str(meta.get("title") or "")
        notes.append(
            {
                "id": meta.get("session_id", d.name),
                "title": title,
                "kind": _kind(title),
                "created_at": meta.get("created_at"),
                "status": (attempt or {}).get("status", "unknown"),
                "error": (attempt or {}).get("error"),
                "preview": answer[:240],
            }
        )
    notes.sort(key=lambda n: n.get("created_at") or "", reverse=True)
    return notes[:limit]


def get_note(note_id: str) -> dict | None:
    if not _ID.match(note_id):
        return None
    d = _sessions_dir() / note_id
    meta = _read_json(d / "session.json")
    if not meta:
        return None
    attempt = _read_json(d / "attempts" / str(meta.get("last_attempt_id")) / "attempt.json") if meta.get("last_attempt_id") else None
    messages = _read_jsonl(d / "messages.jsonl")
    steps: list[dict] = []
    for e in _read_jsonl(d / "trace.jsonl"):
        t = e.get("type")
        if t == "tool_call":
            steps.append({"id": e.get("call_id") or str(len(steps)), "tool": e.get("tool"), "args": e.get("args") or {}, "status": "running", "preview": None})
        elif t == "tool_result":
            match = next((s for s in reversed(steps) if s["id"] == e.get("call_id") or (s["tool"] == e.get("tool") and s["status"] == "running")), None)
            preview = e.get("preview") or e.get("result") or e.get("output") or e.get("error")
            update = {"status": e.get("status") or "ok", "preview": str(preview)[:2000] if preview is not None else None}
            if match:
                match.update(update)
            else:
                steps.append({"id": e.get("call_id") or str(len(steps)), "tool": e.get("tool"), "args": {}, **update})
    question = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
    answer = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "assistant"), "")
    return {
        "id": note_id,
        "title": meta.get("title"),
        "kind": _kind(str(meta.get("title") or "")),
        "created_at": meta.get("created_at"),
        "status": (attempt or {}).get("status", "unknown"),
        "error": (attempt or {}).get("error"),
        "prompt": question,
        "answer": answer,
        "steps": steps,
    }
