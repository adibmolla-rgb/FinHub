import pytest

from finhub_backend.receipts import Quantity, Source, Unit, UnitMismatchError, add


def q(value: float, unit: Unit, label: str, currency: str | None = None) -> Quantity:
    return Quantity(value=value, unit=unit, label=label, currency=currency, source=Source(provider="test"))


def test_percent_and_fraction_cannot_be_added_silently():
    # The equity-risk-premium bug: dividend yield arrives in percent, buyback yield is a fraction.
    dividend_yield = q(0.99, Unit.PERCENT, "dividend yield")
    buyback_yield = q(0.025, Unit.FRACTION, "buyback yield")
    with pytest.raises(UnitMismatchError):
        add("shareholder yield", dividend_yield, buyback_yield)


def test_explicit_conversion_gives_the_right_answer():
    dividend_yield = q(0.99, Unit.PERCENT, "dividend yield").to(Unit.FRACTION)
    buyback_yield = q(0.025, Unit.FRACTION, "buyback yield")
    total = add("shareholder yield", dividend_yield, buyback_yield)
    assert total.value == pytest.approx(0.0349)
    assert total.to(Unit.PERCENT).value == pytest.approx(3.49)
    assert total.to(Unit.BASIS_POINTS).value == pytest.approx(349)


def test_receipt_keeps_every_input():
    total = add("sum", q(1, Unit.FRACTION, "a"), q(2, Unit.FRACTION, "b"))
    receipt = total.receipt()
    assert receipt["formula"] == "a + b"
    assert [i["label"] for i in receipt["inputs"]] == ["a", "b"]
    assert receipt["source"]["provider"] == "computed"


def test_non_rate_units_refuse_conversion():
    with pytest.raises(UnitMismatchError):
        q(100, Unit.CURRENCY, "price", "USD").to(Unit.PERCENT)


def test_different_currencies_cannot_be_added():
    with pytest.raises(UnitMismatchError):
        add("total", q(1, Unit.CURRENCY, "a", "USD"), q(1, Unit.CURRENCY, "b", "GBP"))
