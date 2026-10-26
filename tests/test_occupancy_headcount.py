"""Headcounts must not be accumulated over different months."""

import pandas as pd
import pytest

from campuspulse.analysis_engine import calculate
from campuspulse.models import AnalysisPlan, Filter
from campuspulse.presentation import calculation_lines
from conftest import dataset_from_csv


def make_plan(intent="group_comparison", aggregation="sum", group_by=None, filters=None):
    return AnalysisPlan(
        intent=intent,
        metric="occupancy",
        aggregation=aggregation,
        group_by=["building_name"] if group_by is None else group_by,
        filters=[] if filters is None else filters,
    )


def test_all_building_headcounts_latest_month_only(dataset):
    result = calculate(dataset, make_plan())
    assert result.status == "ok"
    assert result.evidence.month.unique().tolist() == ["2026-06"]
    assert len(result.evidence) == 5
    assert dict(zip(result.values.label, result.values.value)) == {
        "Academic Block A": 800.0,
        "Academic Block B": 600.0,
        "Boys Hostel": 400.0,
        "Girls Hostel": 350.0,
        "Library": pytest.approx(float('nan'), nan_ok=True),
    }
    assert "2026-06" in result.answer
    assert "4,800" not in result.answer
    assert "Library: unavailable" in result.answer
    assert "4,800" not in "\n".join(calculation_lines(result))


def test_filtered_month_uses_requested_month(dataset):
    result = calculate(dataset, make_plan(filters=[Filter(column="month", operator="eq", value="2026-03")]))
    assert result.evidence.month.unique().tolist() == ["2026-03"]
    assert result.values.loc[result.values.label.eq("Academic Block A"), "value"].item() == 800


def test_overall_occupancy_is_partial_snapshot(dataset):
    result = calculate(dataset, make_plan("aggregate", group_by=[]))
    assert result.status == "ok"
    assert result.values.value.iloc[0] == 2150
    assert "4 of 5" in result.answer
    assert "not a complete campus headcount" in result.answer


def test_occupancy_ranking_uses_latest_month(dataset):
    result = calculate(dataset, make_plan("ranking"))
    assert result.values.iloc[0].label == "Academic Block A"
    assert result.values.iloc[0].value == 800
    assert "2026-06" in result.answer


def test_historic_mean_uses_all_months():
    ds = dataset_from_csv(b"building_name,month,electricity_kwh,occupancy\nA,2026-05,10,100\nA,2026-06,11,200\nB,2026-05,20,300\nB,2026-06,21,400\n")
    result = calculate(ds, make_plan(aggregation="mean"))
    assert result.values.set_index("label").value.to_dict() == {"A": 150.0, "B": 350.0}
    assert len(result.evidence) == 4


def test_headcount_changes_across_months():
    ds = dataset_from_csv(b"building_name,month,electricity_kwh,occupancy\nA,2026-05,10,100\nA,2026-06,11,200\n")
    result = calculate(ds, make_plan())
    assert result.values.value.iloc[0] == 200
    assert result.evidence.month.unique().tolist() == ["2026-06"]


def test_missing_only_occupancy_not_filled(dataset):
    result = calculate(dataset, make_plan())
    assert pd.isna(result.values.loc[result.values.label.eq("Library"), "value"].item())
    assert any(w.code == "selected_missing" for w in result.warnings)
