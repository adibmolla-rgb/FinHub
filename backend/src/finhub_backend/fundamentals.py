"""Financial statements and the key ratios derived from them, every ratio with a receipt.

Providers name the same line item differently ("Total Revenue", "total_revenue", "revenue", ...), so
each concept below lists the field names it accepts. A ratio is only computed when every input was
found, and its receipt names the exact provider field and period used, so a wrong mapping is visible.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from finhub_backend import market
from finhub_backend.receipts import Quantity, Source, Unit

CONCEPTS: dict[str, tuple[str, list[str]]] = {
    "revenue": ("Revenue", ["totalrevenue", "revenue", "totalrevenues", "operatingrevenue", "revenues"]),
    "gross_profit": ("Gross profit", ["grossprofit"]),
    "operating_income": ("Operating income", ["operatingincome", "totaloperatingincome", "operatingincomeloss", "operatingprofit"]),
    "net_income": ("Net income", ["netincomecommonstockholders", "netincome", "netincomeloss", "consolidatednetincome", "netincomeattributabletocommonshareholders", "netincomeattributabletoparent"]),
    "total_assets": ("Total assets", ["totalassets"]),
    "equity": ("Shareholders' equity", ["stockholdersequity", "commonstockequity", "totalshareholdersequity", "totalcommonequity", "totalequitygrossminorityinterest", "totalequity"]),
    "total_debt": ("Total debt", ["totaldebt", "totaldebtandcapitalleaseobligation", "longtermdebt"]),
    "cash": ("Cash and equivalents", ["cashandcashequivalents", "cashcashequivalentsandshortterminvestments", "cash"]),
    "operating_cash_flow": ("Operating cash flow", ["operatingcashflow", "netcashfromoperatingactivities", "cashflowfromcontinuingoperatingactivities", "netcashprovidedbyoperatingactivities", "netcashflowfromoperatingactivities"]),
    "capex": ("Capital expenditure", ["capitalexpenditure", "capitalexpenditures", "purchaseofpropertyplantandequipment", "paymentsforpropertyplantandequipment", "purchaseoffixedassets"]),
}

STATEMENT_OF = {
    "revenue": "income", "gross_profit": "income", "operating_income": "income", "net_income": "income",
    "total_assets": "balance", "equity": "balance", "total_debt": "balance", "cash": "balance",
    "operating_cash_flow": "cash", "capex": "cash",
}


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find(statement: dict, concept: str, column: int = 0) -> tuple[float, str] | None:
    """Value of a concept in a statement column, and the provider field it came from."""
    rows = {_norm(r["field"]): r for r in statement["rows"]}
    for candidate in CONCEPTS[concept][1]:
        row = rows.get(candidate)
        if row and column < len(row["values"]) and row["values"][column] is not None:
            return row["values"][column], row["field"]
    return None


def _quantity(concept: str, statement: dict, meta: dict, column: int = 0) -> Quantity | None:
    hit = find(statement, concept, column)
    if hit is None:
        return None
    value, field = hit
    period = statement["periods"][column] if column < len(statement["periods"]) else "?"
    label = CONCEPTS[concept][0] + ("" if column == 0 else f" ({period})")
    return Quantity(
        value=abs(value) if concept == "capex" else value,  # providers disagree on capex sign; use magnitude
        unit=Unit.CURRENCY,
        currency=statement.get("currency"),
        label=label,
        source=Source(provider=meta["provider_name"], fetched_at=datetime.fromisoformat(meta["fetched_at"]), detail=f"{field} · period ending {period}"),
    )


def _ratio(label: str, num: Quantity, den: Quantity, unit: Unit, formula: str) -> Quantity | None:
    if den.value == 0:
        return None
    return Quantity(value=num.value / den.value, unit=unit, label=label, source=Source(provider="computed by FinHub"), formula=formula, inputs=(num, den))


def key_ratios(statements: dict[str, dict], metas: dict[str, dict]) -> dict[str, dict]:
    """Latest-period ratios. statements/metas are keyed by income | balance | cash (any may be missing)."""
    q: dict[str, Quantity | None] = {}
    for concept, stmt in STATEMENT_OF.items():
        q[concept] = _quantity(concept, statements[stmt], metas[stmt]) if stmt in statements else None
    prev_rev = _quantity("revenue", statements["income"], metas["income"], 1) if "income" in statements else None

    out: dict[str, Quantity] = {}

    def add(key: str, quantity: Quantity | None) -> None:
        if quantity is not None:
            out[key] = quantity

    for key in ("revenue", "net_income", "operating_cash_flow", "cash", "total_debt"):
        add(key, q[key])
    if q["revenue"]:
        if q["gross_profit"]:
            add("gross_margin", _ratio("Gross margin", q["gross_profit"], q["revenue"], Unit.FRACTION, "Gross profit ÷ Revenue"))
        if q["operating_income"]:
            add("operating_margin", _ratio("Operating margin", q["operating_income"], q["revenue"], Unit.FRACTION, "Operating income ÷ Revenue"))
        if q["net_income"]:
            add("net_margin", _ratio("Net margin", q["net_income"], q["revenue"], Unit.FRACTION, "Net income ÷ Revenue"))
        if prev_rev and prev_rev.value:
            growth = Quantity(
                value=q["revenue"].value / prev_rev.value - 1, unit=Unit.FRACTION, label="Revenue growth",
                source=Source(provider="computed by FinHub"), formula="Revenue ÷ Revenue (previous period) − 1", inputs=(q["revenue"], prev_rev),
            )
            add("revenue_growth", growth)
    if q["net_income"] and q["equity"] and q["equity"].value > 0:
        add("roe", _ratio("Return on equity", q["net_income"], q["equity"], Unit.FRACTION, "Net income ÷ Shareholders' equity (period end)"))
    if q["net_income"] and q["total_assets"]:
        add("roa", _ratio("Return on assets", q["net_income"], q["total_assets"], Unit.FRACTION, "Net income ÷ Total assets (period end)"))
    if q["total_debt"] and q["equity"] and q["equity"].value > 0:
        add("debt_to_equity", _ratio("Debt to equity", q["total_debt"], q["equity"], Unit.RATIO, "Total debt ÷ Shareholders' equity"))
    if q["operating_cash_flow"] and q["capex"]:
        fcf = Quantity(
            value=q["operating_cash_flow"].value - q["capex"].value, unit=Unit.CURRENCY, currency=q["operating_cash_flow"].currency,
            label="Free cash flow", source=Source(provider="computed by FinHub"), formula="Operating cash flow − |Capital expenditure|",
            inputs=(q["operating_cash_flow"], q["capex"]),
        )
        add("free_cash_flow", fcf)
        if q["revenue"]:
            add("fcf_margin", _ratio("Free-cash-flow margin", fcf, q["revenue"], Unit.FRACTION, "Free cash flow ÷ Revenue"))
    return {k: v.receipt() for k, v in out.items()}


def fundamentals(symbol: str, period: str = "annual") -> dict:
    def one(stmt: str):
        try:
            res = market.worker().call("statement", {"symbol": symbol, "statement": stmt, "period": period}, timeout=120)
            market.record_attempts("statement", res["attempts"])
            return stmt, res, None
        except market.WorkerError as exc:
            market.record_attempts("statement", exc.attempts)
            return stmt, None, {"error": str(exc), "attempts": exc.attempts}

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(one, ("income", "balance", "cash")))
    statements = {s: r["data"] for s, r, _ in results if r}
    metas = {s: {k: r[k] for k in ("provider", "provider_name", "fetched_at", "attempts")} for s, r, _ in results if r}
    errors = {s: e for s, _, e in results if e}
    if not statements:
        first = next(iter(errors.values()))
        raise market.MarketDataError(first["error"], first["attempts"])
    return {
        "symbol": symbol.upper(),
        "period": period,
        "statements": {s: {**statements[s], **metas[s]} for s in statements},
        "errors": errors,
        "ratios": key_ratios(statements, metas),
    }
