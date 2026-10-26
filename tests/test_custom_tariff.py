"""Custom electricity rates create traceable, dataset-wide INR estimates."""

import math

import pandas as pd
import pytest

from conftest import dataset_from_csv

from campuspulse.analysis_engine import calculate
from campuspulse.evidence import evidence_table, export_evidence
from campuspulse.models import AnalysisPlan, DataError, Filter
from campuspulse.normalization import apply_custom_tariff
from campuspulse.presentation import calculation_lines
from campuspulse.quick_replies import report_summary


def cost_plan(intent="aggregate", **kwargs):
    return AnalysisPlan(intent=intent, metric="electricity_cost_inr", aggregation="sum", **kwargs)


def test_flat_rate_applies_to_every_building_and_month(dataset):
    rated = apply_custom_tariff(dataset, 10)
    assert rated.custom_tariff_inr_per_kwh == 10
    assert len(rated.frame) == 30
    assert rated.frame.tariff_inr_per_kwh.eq(10).all()
    pd.testing.assert_series_equal(
        rated.frame.electricity_cost_inr,
        dataset.frame.electricity_kwh * 10,
        check_names=False,
    )
    assert "electricity_cost_inr" not in dataset.frame
    assert calculate(rated, cost_plan()).values.value.iloc[0] == 1_205_000
    assert calculate(rated, cost_plan("group_comparison", group_by=["building_name"])).values.set_index("label").value["Boys Hostel"] == 322_000
    june = calculate(rated, cost_plan(filters=[Filter(column="month", operator="eq", value="2026-06")]))
    assert june.values.value.iloc[0] == 219_500
    assert "₹10.00/kWh" in calculation_lines(june)[0]
    assert "₹10.00/kWh" in report_summary(rated)
    evidence = evidence_table(june)
    assert {"electricity_kwh", "tariff_inr_per_kwh", "electricity_cost_inr", "raw_electricity_kwh"} <= set(evidence)
    assert "tariff_inr_per_kwh" in export_evidence(june).decode("utf-8-sig")
    assert any(w.code == "estimated_electricity_cost" for w in rated.warnings)
    assert not any(w.code == "estimated_electricity_cost" for w in dataset.warnings)


def test_changing_rate_does_not_compound(dataset):
    first = apply_custom_tariff(dataset, 10)
    second = apply_custom_tariff(dataset, 12)
    assert calculate(first, cost_plan()).values.value.iloc[0] == 1_205_000
    assert calculate(second, cost_plan()).values.value.iloc[0] == 1_446_000
    assert dataset.frame.equals(first.frame[dataset.frame.columns])


def test_missing_kwh_stays_missing_and_zero_is_zero():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-05,\nA,2026-06,0\n")
    rated = apply_custom_tariff(ds, 10)
    assert math.isnan(rated.frame.electricity_cost_inr.iloc[0])
    assert rated.frame.electricity_cost_inr.iloc[1] == 0


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf"), -float("inf"), 1_000_001, True, "10"])
def test_reject_invalid_rates(dataset, rate):
    with pytest.raises(DataError):
        apply_custom_tariff(dataset, rate)


def test_no_rate_keeps_original_cost_unmodified(dataset):
    assert apply_custom_tariff(dataset, None) is dataset
    assert "electricity_cost_inr" not in dataset.frame
