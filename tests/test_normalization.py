from pathlib import Path

import pytest
from conftest import dataset_from_csv

from campuspulse.csv_parser import parse_csv
from campuspulse.models import DataError
from campuspulse.normalization import normalize, parse_month, parse_number, suggest_mapping


@pytest.mark.parametrize("raw", ["2026-06", "2026-06-15", "June 2026", "Jun 2026", "2026 Jun"])
def test_month_formats(raw):
    assert parse_month(raw) == "2026-06"


@pytest.mark.parametrize("raw", ["2026-13", "2026-02-30", "06/07/2026", "June", "", "June 26"])
def test_ambiguous_or_invalid_periods(raw):
    with pytest.raises(DataError):
        parse_month(raw)
    assert parse_month("June", 2026) == "2026-06"


@pytest.mark.parametrize("raw,expected", [("1,200.50", 1200.5), ("1200 kWh", 1200), ("0", 0)])
def test_numeric_parsing(raw, expected):
    assert parse_number(raw, "kWh") == expected


@pytest.mark.parametrize("raw", ["1,23", "12.4.5", "five", "1 MWh", "-10", "inf", "1e999", "=2+2"])
def test_reject_ambiguous_numeric(raw):
    with pytest.raises(DataError):
        parse_number(raw, "kWh")


def test_missing_is_distinct_from_zero():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-05,\nA,2026-06,0\n")
    assert ds.frame.electricity_kwh.isna().sum() == 1
    assert ds.frame.electricity_kwh.iloc[1] == 0
    assert any(w.code == "missing_values" for w in ds.warnings)


def test_duplicates_rejected():
    with pytest.raises(DataError, match="Duplicate building/month"):
        dataset_from_csv(b"Building,Month,kWh\nA,2026-05,1\nA,2026-05,2\n")


def test_gaps_and_partial_observations():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-01,1\nA,2026-03,2\nB,2026-03,4\n")
    assert {"missing_periods", "partial_coverage"} <= {w.code for w in ds.warnings}
    assert len(ds.frame) == 3


def test_required_fields_and_mapping(csv_bytes, settings):
    table = parse_csv(csv_bytes, "data.csv", settings)[0]
    mapping = suggest_mapping(list(table.frame))
    with pytest.raises(DataError, match="Map a building"):
        normalize(table, {}, "kWh")
    with pytest.raises(DataError, match="only one"):
        normalize(table, mapping | {"month": "building_name"}, "kWh")
    with pytest.raises(DataError, match="kWh"):
        normalize(table, mapping, "MWh")


def test_header_unit_conflict(settings):
    table = parse_csv(b"Building,Month,Usage MWh\nA,2026-06,2", "x.csv", settings)[0]
    with pytest.raises(DataError, match="different unit"):
        normalize(
            table,
            {"building_name": "Building", "month": "Month", "electricity_kwh": "Usage MWh"},
            "kWh",
        )


def test_ambiguous_alias_not_suggested():
    assert "electricity_kwh" not in suggest_mapping(["Building", "Month", "kWh", "Consumption"])


def test_malformed_fixture():
    with pytest.raises(DataError):
        dataset_from_csv((Path(__file__).parent / "fixtures/malformed.csv").read_bytes())
