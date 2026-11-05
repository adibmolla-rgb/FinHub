"""Receipts: every number the terminal shows carries where it came from and what unit it is in.

The point of this module is to make a whole class of silent bugs impossible. A real example from
another open-source terminal: a data source returned dividend yield in *percent* (0.99 meaning 0.99%),
the code treated it as a *fraction* (0.99 meaning 99%), and an equity risk premium of ~101% was shown
to users and fed to AI agents. Here, a value cannot be created without a unit, and values in different
units cannot be added together without an explicit conversion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Unit(StrEnum):
    FRACTION = "fraction"  # 0.05 means 5%
    PERCENT = "percent"  # 5.0 means 5%
    BASIS_POINTS = "bp"  # 500 means 5%
    CURRENCY = "currency"
    SHARES = "shares"
    RATIO = "ratio"  # dimensionless, not a rate (e.g. P/E, Sharpe)
    COUNT = "count"


# How many "fraction units" one unit of each rate-like unit is worth.
_RATE_SCALE: dict[Unit, float] = {
    Unit.FRACTION: 1.0,
    Unit.PERCENT: 0.01,
    Unit.BASIS_POINTS: 0.0001,
}


class UnitMismatchError(ValueError):
    """Raised when values with incompatible units are combined."""


class Source(BaseModel):
    """Where a value came from."""

    model_config = ConfigDict(frozen=True)

    provider: str  # e.g. "yfinance via OpenBB", "computed"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    detail: str | None = None  # e.g. the field name or endpoint the raw value came from


class Quantity(BaseModel):
    """A number with its unit, source and (for derived values) the formula and inputs behind it."""

    model_config = ConfigDict(frozen=True)

    value: float
    unit: Unit
    label: str
    source: Source
    currency: str | None = None
    formula: str | None = None
    inputs: tuple[Quantity, ...] = ()

    def to(self, unit: Unit) -> Quantity:
        """Convert between rate units (fraction / percent / bp). Other conversions are refused."""
        if unit == self.unit:
            return self
        if self.unit not in _RATE_SCALE or unit not in _RATE_SCALE:
            raise UnitMismatchError(f"cannot convert {self.label} from {self.unit} to {unit}")
        converted = self.value * _RATE_SCALE[self.unit] / _RATE_SCALE[unit]
        return self.model_copy(update={"value": converted, "unit": unit})

    def receipt(self) -> dict:
        """A JSON-friendly tree the UI shows when you click a number."""
        return {
            "label": self.label,
            "value": self.value,
            "unit": self.unit.value,
            "currency": self.currency,
            "source": self.source.model_dump(mode="json"),
            "formula": self.formula,
            "inputs": [q.receipt() for q in self.inputs],
        }


def _check_compatible(quantities: tuple[Quantity, ...]) -> None:
    units = {q.unit for q in quantities}
    if len(units) > 1:
        detail = ", ".join(f"{q.label}={q.unit}" for q in quantities)
        raise UnitMismatchError(f"refusing to combine different units ({detail}); convert explicitly first")
    currencies = {q.currency for q in quantities if q.currency}
    if len(currencies) > 1:
        raise UnitMismatchError(f"refusing to combine different currencies: {sorted(currencies)}")


def add(label: str, *quantities: Quantity) -> Quantity:
    """Sum quantities that share a unit. The result keeps every input in its receipt."""
    if not quantities:
        raise ValueError("add() needs at least one quantity")
    _check_compatible(quantities)
    first = quantities[0]
    return Quantity(
        value=sum(q.value for q in quantities),
        unit=first.unit,
        label=label,
        currency=first.currency,
        source=Source(provider="computed"),
        formula=" + ".join(q.label for q in quantities),
        inputs=tuple(quantities),
    )
