import pandas as pd
import pytest
from conftest import dataset_from_csv, plan

from campuspulse.analysis_engine import calculate
from campuspulse.models import AnalysisPlan, Filter, PlanError
from campuspulse.visualization import build_chart


def month(value):
    return Filter(column="month", operator="eq", value=value)


@pytest.mark.parametrize(
    "sort,name,value", [("descending", "Boys Hostel", 6200), ("ascending", "Library", 1550)]
)
def test_june_ranking(dataset, sort, name, value):
    result = calculate(
        dataset,
        plan("ranking", group_by=["building_name"], sort=sort, limit=1, filters=[month("2026-06")]),
    )
    assert result.status == "ok"
    assert result.values.to_dict("records") == [{"label": name, "value": value}]
    assert len(result.evidence) == 5


def test_tied_winners_not_hidden():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-06,5\nB,2026-06,5\n")
    result = calculate(ds, plan("ranking", group_by=["building_name"], limit=1))
    assert len(result.values) == 2


@pytest.mark.parametrize(
    "aggregation,expected",
    [("sum", 21100), ("mean", 4220), ("min", 1600), ("max", 5800), ("count", 5)],
)
def test_aggregate_operations(dataset, aggregation, expected):
    p = AnalysisPlan(
        intent="aggregate",
        metric="electricity_kwh",
        aggregation=aggregation,
        filters=[month("2026-05")],
    )
    result = calculate(dataset, p)
    assert result.values.value.iloc[0] == expected
    assert result.unit == ("observations" if aggregation == "count" else "kWh")


def test_period_comparison(dataset):
    result = calculate(dataset, plan("period_comparison", periods=["2026-05", "2026-06"]))
    assert result.details == {
        "old": 21100,
        "new": 21950,
        "absolute_change": 850,
        "percentage_change": pytest.approx(850 / 21100 * 100),
    }
    assert len(result.evidence) == 10
    assert any("21950.0 - 21100.0" in line for line in result.trace)
    assert build_chart(result).data[0].y == (21100, 21950)


def test_averages_have_explicit_denominators(dataset):
    total = dataset.frame.electricity_kwh.sum()
    for basis, denominator in [("observations", 30), ("monthly_totals", 6), ("building_totals", 5)]:
        result = calculate(
            dataset,
            AnalysisPlan(
                intent="aggregate",
                metric="electricity_kwh",
                aggregation="mean",
                average_basis=basis,
            ),
        )
        assert result.values.value.iloc[0] == pytest.approx(total / denominator)


def test_trend_order(dataset):
    result = calculate(dataset, plan("trend", group_by=["month"]))
    assert result.values.label.tolist() == [f"2026-{m:02d}" for m in range(1, 7)]
    assert result.values.value.tolist() == [18800, 19000, 19500, 20150, 21100, 21950]
    assert build_chart(result).data[0].connectgaps is False


def test_group_comparison(dataset):
    result = calculate(
        dataset,
        plan(
            "group_comparison",
            group_by=["building_name"],
            filters=[
                Filter(column="building_name", operator="in", value=["Boys Hostel", "Girls Hostel"])
            ],
        ),
    )
    assert result.values.value.tolist() == [32200, 29900]
    assert len(result.evidence) == 12


@pytest.mark.parametrize(
    "p",
    [
        plan(filters=[month("2026-12")]),
        plan("period_comparison", periods=["2026-05", "2026-12"]),
        plan(filters=[Filter(column="electricity_kwh", operator="gte", value=999999)]),
    ],
)
def test_unavailable_not_fabricated(dataset, p):
    result = calculate(dataset, p)
    assert result.status == "unavailable"
    assert result.values.empty and result.evidence.empty
    assert build_chart(result) is None


def test_unavailable_cost(dataset):
    result = calculate(
        dataset, AnalysisPlan(intent="aggregate", metric="electricity_cost_inr", aggregation="sum")
    )
    assert result.status == "unavailable"
    assert "tariff" in result.answer


def test_zero_denominator():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-05,0\nA,2026-06,5\n")
    result = calculate(ds, plan("period_comparison", periods=["2026-05", "2026-06"]))
    assert result.details["absolute_change"] == 5
    assert result.details["percentage_change"] is None
    assert any(w.code == "zero_denominator" for w in result.warnings)


def test_all_missing_never_sum_to_zero():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-05,\nA,2026-06,5\n")
    result = calculate(ds, plan(filters=[month("2026-05")]))
    assert result.status == "unavailable"
    result = calculate(ds, plan("period_comparison", periods=["2026-05", "2026-06"]))
    assert result.status == "unavailable"
    result = calculate(ds, plan("missing_values"))
    assert result.values.value.iloc[0] == 1


def test_missing_trend_month_is_null_not_zero():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-01,2\nA,2026-03,4\n")
    result = calculate(ds, plan("trend", group_by=["month"]))
    assert result.values.label.tolist() == ["2026-01", "2026-02", "2026-03"]
    assert pd.isna(result.values.value.iloc[1])
    assert len(result.evidence) == 2


def test_unequal_comparison_coverage():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-05,5\nA,2026-06,6\nB,2026-06,7\n")
    result = calculate(ds, plan("period_comparison", periods=["2026-05", "2026-06"]))
    assert any(w.code == "unequal_coverage" for w in result.warnings)


def test_unknown_column_and_injection_rejected(dataset):
    with pytest.raises(PlanError):
        calculate(
            dataset, plan(filters=[Filter(column="__import__('os')", operator="eq", value="x")])
        )
    with pytest.raises(PlanError):
        calculate(dataset, plan("ranking", group_by=["source_file"]))
