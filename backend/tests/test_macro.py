import pytest

from finhub_backend import macro

META = {"provider_name": "OECD (via OpenBB)", "fetched_at": "2026-11-05T00:00:00+00:00"}


def raw(kind, unit, pts, series="unemployment"):
    return {"series": series, "label": "Unemployment rate", "country": "united_states", "unit_kind": kind, "unit": unit, "points": pts}


def test_fraction_series_and_year_on_year_change():
    pts = [{"date": "2024-09-01", "value": 0.041}, {"date": "2025-06-01", "value": 0.042}, {"date": "2025-09-01", "value": 0.044}]
    out = macro.summarise(raw("fraction", "fraction (OpenBB normalised percent)", pts), META)
    assert out["latest"]["unit"] == "fraction" and out["latest"]["value"] == pytest.approx(0.044)
    assert out["change_1y"]["value"] == pytest.approx(0.003)  # vs 2024-09-01, not the June value
    assert "unit: fraction" in out["latest"]["source"]["detail"]


def test_undeclared_units_stay_as_reported():
    out = macro.summarise(raw("as_reported", "not stated by the provider", [{"date": "2025-01-01", "value": 5.0}], "gdp_real"), META)
    assert out["latest"]["unit"] == "as_reported"
    assert "change_1y" not in out  # no observation a year earlier


def test_country_codes():
    assert macro.country_name("gb") == "united_kingdom"
    assert macro.country_name("United Kingdom") == "united_kingdom"
    with pytest.raises(ValueError):
        macro.country_name("../../etc")
