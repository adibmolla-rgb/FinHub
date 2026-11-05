"""Price alerts: one-shot conditions on a ticker's price or daily move, checked in the background.

Alerts and the events they produce live in FinHub's data folder. A check fetches one quote per ticker
(through the same provider chain as the rest of the app) and fires every matching alert once.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from finhub_backend.agent import data_dir

KINDS = {
    "above": "price rises to or above",
    "below": "price falls to or below",
    "move_up": "day's change reaches or exceeds +",
    "move_down": "day's change reaches or falls below −",
}
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,14}$")
MAX_ALERTS = 100
CHECK_EVERY_SECONDS = 120

_lock = threading.RLock()


def _path():
    return data_dir() / "alerts.json"


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
        return {"alerts": data.get("alerts", []), "events": data.get("events", [])}
    except (OSError, ValueError):
        return {"alerts": [], "events": []}


def _save(data: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def describe(a: dict) -> str:
    t = a["threshold"]
    if a["kind"] in ("move_up", "move_down"):
        return f"{a['symbol']}: {KINDS[a['kind']]}{t * 100:g}%"
    return f"{a['symbol']}: {KINDS[a['kind']]} {t:g}"


def add(symbol: str, kind: str, threshold: float) -> dict:
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        raise ValueError("invalid ticker")
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {list(KINDS)}")
    if not (threshold > 0) or threshold != threshold:
        raise ValueError("threshold must be positive (moves are fractions: 0.05 = 5%)")
    if kind in ("move_up", "move_down") and threshold >= 1:
        raise ValueError("move thresholds are fractions below 1 (0.05 = 5%)")
    with _lock:
        data = _load()
        if sum(a["active"] for a in data["alerts"]) >= MAX_ALERTS:
            raise ValueError(f"at most {MAX_ALERTS} active alerts")
        alert = {"id": uuid.uuid4().hex[:10], "symbol": symbol, "kind": kind, "threshold": threshold, "active": True, "created_at": _now()}
        alert["description"] = describe(alert)
        data["alerts"].append(alert)
        _save(data)
        return alert


def remove(alert_id: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["alerts"])
        data["alerts"] = [a for a in data["alerts"] if a["id"] != alert_id]
        _save(data)
        return len(data["alerts"]) < before


def listing() -> dict:
    with _lock:
        data = _load()
        return {"alerts": data["alerts"], "events": data["events"][-100:]}


def evaluate(alert: dict, price: float | None, change_pct: float | None) -> bool:
    k, t = alert["kind"], alert["threshold"]
    if k == "above":
        return price is not None and price >= t
    if k == "below":
        return price is not None and price <= t
    if k == "move_up":
        return change_pct is not None and change_pct >= t
    if k == "move_down":
        return change_pct is not None and change_pct <= -t
    return False


QuoteFn = Callable[[str], dict]


def check(quote: QuoteFn) -> list[dict]:
    """Fetch one quote per ticker with an active alert; fire (once) every alert whose condition holds."""
    with _lock:
        data = _load()
        active = [a for a in data["alerts"] if a["active"]]
    symbols = sorted({a["symbol"] for a in active})
    quotes: dict[str, dict | None] = {}
    for s in symbols:
        try:
            quotes[s] = quote(s)
        except Exception:
            quotes[s] = None  # a failed fetch never fires an alert
    fired: list[dict] = []
    with _lock:
        data = _load()
        for a in data["alerts"]:
            if not a["active"] or quotes.get(a["symbol"]) is None:
                continue
            values = quotes[a["symbol"]]["values"]
            price = (values.get("price") or {}).get("value")
            change = (values.get("change_pct") or {}).get("value")
            if evaluate(a, price, change):
                a["active"] = False
                a["triggered_at"] = _now()
                a["triggered_price"] = price
                event = {
                    "id": uuid.uuid4().hex[:10],
                    "alert_id": a["id"],
                    "at": a["triggered_at"],
                    "symbol": a["symbol"],
                    "text": f"{a['description']} — now {price:g}" + (f" ({change * 100:+.2f}% today)" if change is not None else ""),
                    "provider": quotes[a["symbol"]].get("provider_name"),
                }
                data["events"].append(event)
                fired.append(event)
        data["events"] = data["events"][-500:]
        _save(data)
    return fired


def start_background(quote: QuoteFn, every: float = CHECK_EVERY_SECONDS) -> None:
    def loop() -> None:
        while True:
            time.sleep(every)
            try:
                if any(a["active"] for a in listing()["alerts"]):
                    check(quote)
            except Exception:
                pass

    threading.Thread(target=loop, daemon=True, name="alerts").start()
