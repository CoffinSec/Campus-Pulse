"""Numerical and UI-support regression tests; model responses are explicitly mocked."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pandas as pd
import pymupdf
import pytest
from conftest import dataset_from_csv, plan
from pydantic import ValidationError

from campuspulse.analysis_engine import calculate
from campuspulse.explanations import (
    explain_result,
    fallback_explanation,
    language_for,
    validate_explanation,
    verified_facts,
)
from campuspulse.insights import anomaly_flags, overview
from campuspulse.models import AIError, AnalysisPlan, Filter, PlanError
from campuspulse.presentation import calculation_lines, describe_plan, followup_questions
from campuspulse.question_planner import plan_question
from campuspulse.reporting import answer_pdf
from campuspulse.visualization import WINNER, build_chart


def june():
    return [Filter(column="month", operator="eq", value="2026-06")]


def student_plan(filters=None):
    return AnalysisPlan(
        intent="per_student",
        metric="electricity_kwh",
        aggregation="mean",
        group_by=["building_name"],
        filters=filters or [],
    )


def scenario_plan(percent=10.0):
    return AnalysisPlan(
        intent="scenario",
        metric="electricity_kwh",
        aggregation="sum",
        scenario_buildings=["Boys Hostel", "Girls Hostel"],
        reduction_percent=percent,
        filters=june(),
    )


def test_overview_without_question(dataset):
    summary = overview(dataset)
    assert summary["total"] == 120500
    assert summary["buildings"] == 5
    assert summary["months"] == 6
    assert summary["highest"] == "Boys Hostel"
    assert summary["highest_value"] == 32200
    assert summary["trend"].values.value.tolist() == [18800, 19000, 19500, 20150, 21100, 21950]


def test_empty_numeric_overview_is_unavailable_not_zero():
    dataset = dataset_from_csv(b"Building,Month,kWh\nA,2026-06,\n")
    summary = overview(dataset)
    assert pd.isna(summary["total"])
    assert summary["highest"] == "Unavailable"
    assert summary["trend"].status == "unavailable"


def test_student_ratios_and_exclusion(dataset):
    result = calculate(dataset, student_plan(june()))
    actual = result.values.set_index("label").value.to_dict()
    assert actual == {
        "Academic Block A": 7,
        "Academic Block B": pytest.approx(3100 / 600),
        "Boys Hostel": 15.5,
        "Girls Hostel": pytest.approx(5500 / 350),
    }
    assert result.unit == "kWh/student"
    assert "Library" not in actual
    assert any("Library: no occupancy data" in w.message for w in result.warnings)
    assert result.evidence.occupancy.isna().sum() == 1
    assert any(
        "6,200.00 kWh ÷ 400 students = 15.50" in line and "row 29" in line
        for line in calculation_lines(result)
    )


@pytest.mark.parametrize("occupancy", ["", "0"])
def test_no_usable_denominator_never_divides(occupancy):
    ds = dataset_from_csv(f"Building,Month,kWh,occupancy\nA,2026-06,5,{occupancy}\n".encode())
    result = calculate(ds, student_plan())
    assert result.status == "unavailable"
    assert result.values.empty
    assert build_chart(result) is None


def test_no_occupancy_column():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-06,5\n")
    result = calculate(ds, student_plan())
    assert result.status == "unavailable"
    assert any(w.code == "no_occupancy" for w in result.warnings)


def test_incomplete_building_is_not_partially_compared():
    ds = dataset_from_csv(
        b"Building,Month,kWh,occupancy\nA,2026-05,4,2\nA,2026-06,6,\nB,2026-06,10,2\n"
    )
    result = calculate(ds, student_plan())
    assert result.values.label.tolist() == ["B"]
    assert result.unit == "kWh/student-month"


def test_multimonth_denominator_is_student_months(dataset):
    result = calculate(dataset, student_plan())
    assert result.unit == "kWh/student-month"
    assert result.values.set_index("label").value["Boys Hostel"] == pytest.approx(32200 / 2400)
    assert any(w.code == "student_months" for w in result.warnings)


def test_scenario_preserves_campus_baseline(dataset):
    result = calculate(dataset, scenario_plan())
    assert result.details["old"] == 21950
    assert result.details["affected_usage"] == 11700
    assert result.details["saving"] == 1170
    assert result.details["new"] == 20780
    assert result.details["percentage_change"] == pytest.approx(-1170 / 21950 * 100)
    assert len(result.evidence) == 5
    assert any(w.code == "hypothetical" for w in result.warnings)
    assert any("21,950.00 − 1,170.00 = 20,780.00" in line for line in calculation_lines(result))
    assert build_chart(result).data[0].y == (21950, 20780)


@pytest.mark.parametrize("percent,saving", [(0.0, 0.0), (100.0, 11700.0)])
def test_scenario_extremes(dataset, percent, saving):
    assert calculate(dataset, scenario_plan(percent)).details["saving"] == saving


@pytest.mark.parametrize("percent", [-1.0, 101.0, float("inf")])
def test_invalid_scenario_percentage(percent):
    with pytest.raises(ValidationError):
        scenario_plan(percent)


def test_scenario_missing_building_and_building_filter_rejected(dataset):
    payload = scenario_plan().model_dump()
    with pytest.raises(PlanError):
        calculate(dataset, AnalysisPlan(**(payload | {"scenario_buildings": ["Invented"]})))
    with pytest.raises(ValidationError):
        AnalysisPlan(
            **(
                payload
                | {"filters": [Filter(column="building_name", operator="eq", value="Boys Hostel")]}
            )
        )


def test_zero_usage_scenario_has_no_percentage():
    ds = dataset_from_csv(b"Building,Month,kWh\nA,2026-06,0\n")
    p = AnalysisPlan(
        intent="scenario",
        metric="electricity_kwh",
        aggregation="sum",
        reduction_percent=10.0,
        scenario_buildings=["A"],
    )
    result = calculate(ds, p)
    assert result.details["saving"] == 0
    assert result.details["percentage_change"] is None


def test_ranking_chart_shows_candidates_and_highlights_winner(dataset):
    result = calculate(
        dataset, plan("ranking", group_by=["building_name"], limit=1, filters=june())
    )
    chart = build_chart(result)
    assert len(chart.data[0].x) == 5
    assert chart.data[0].marker.color[0] == WINNER
    assert list(chart.data[0].marker.color).count(WINNER) == 1
    assert chart.data[0].texttemplate
    assert len(result.values) == 1
    lines = calculation_lines(result)
    assert "Boys Hostel = 6,200.00 kWh" in lines[0]
    assert "row 29" in lines[0]  # Real source row, never the illustrative row 28.
    assert "Gemma understood: ranking" in describe_plan(result)
    assert "June 2026" in describe_plan(result)


def test_trend_marks_both_extremes(dataset):
    result = calculate(dataset, plan("trend", group_by=["month"]))
    chart = build_chart(result)
    assert chart.data[1].name == "Highest"
    assert chart.data[1].y == (21950,)
    assert chart.data[2].name == "Lowest"
    assert chart.data[2].y == (18800,)


def historical_dataset(values, months=None):
    months = months or list(range(1, len(values) + 1))
    text = "Building,Month,kWh\n" + "".join(f"A,2026-{m:02d},{v}\n" for m, v in zip(months, values))
    return dataset_from_csv(text.encode())


def test_anomalies_use_only_past_history_and_cite_source():
    ds = historical_dataset([100, 100, 100, 100, 200, 200])
    flags = anomaly_flags(ds)
    assert flags.Month.tolist() == ["2026-05"]
    first = flags.iloc[0]
    assert first["Change (%)"] == 100
    assert first["Typical prior change (%)"] == 0
    assert first["Source row"] == 6
    assert "cause unknown" in first.Note
    # A future spike cannot affect whether the earlier observation was flagged.
    short = anomaly_flags(historical_dataset([100, 100, 100, 100, 200]))
    pd.testing.assert_series_equal(short.iloc[0], first)


def test_regular_or_short_history_does_not_claim_anomaly(dataset):
    assert anomaly_flags(dataset).empty
    assert anomaly_flags(historical_dataset([100, 1000])).empty
    assert anomaly_flags(historical_dataset([0, 100, 100, 100, 200])).empty
    assert anomaly_flags(historical_dataset([100, 100, 100, 200], [1, 2, 4, 6])).empty


def test_followup_passes_validated_plan_not_transcript(dataset, settings):
    previous = plan("ranking", group_by=["building_name"], limit=1, filters=june())
    expected = plan(
        "ranking",
        group_by=["building_name"],
        limit=1,
        filters=[Filter(column="month", operator="eq", value="2026-05")],
    )
    client = Mock()
    client.plan_json.return_value = expected.model_dump_json()
    got = plan_question("and in May?", dataset, settings, client, previous_plan=previous)
    payload = json.loads(client.plan_json.call_args.args[1])
    assert payload["previous_plan"] == previous.model_dump()
    assert got.filters[0].value == "2026-05"
    assert "history" not in payload
    result = calculate(dataset, got)
    assert result.values.value.iloc[0] == 5800
    assert len(followup_questions(dataset, result)) == 3


@pytest.mark.parametrize(
    "language,meaning",
    [("en", "The computed result is {{first}}."), ("hi", "गणना का परिणाम है {{first}}।")],
)
def test_verified_explanation_numbers_come_only_from_facts(dataset, language, meaning):
    result = calculate(
        dataset, plan("ranking", group_by=["building_name"], limit=1, filters=june())
    )
    facts = verified_facts(result, language)
    explanation = validate_explanation(
        json.dumps({"meaning": meaning, "checks": ["meter"]}), facts, language
    )
    assert "Boys Hostel: 6,200.00 kWh" in explanation.meaning
    assert explanation.generated
    assert "{{" not in explanation.meaning


@pytest.mark.parametrize(
    "meaning",
    [
        "Usage is 9000 kWh: {{first}}",
        "Usage rose ५%: {{first}}",
        "{{invented}}",
        "Usage doubled twice: {{first}}",
        "बचत दस है: {{first}}",
        "बचत ग्यारह है: {{first}}",
        "खपत सत्तर है: {{first}}",
        "Saving is a dozen units: {{first}}",
        "Usage fell by 2e3: {{first}}",
        "No source references",
    ],
)
def test_fabricated_explanation_numbers_rejected(meaning):
    with pytest.raises(AIError):
        validate_explanation(
            json.dumps({"meaning": meaning, "checks": ["meter"]}),
            {"first": "Boys Hostel: 6,200.00 kWh"},
            "en",
        )


def test_explanation_payload_is_verified_results_not_document(dataset, settings):
    result = calculate(
        dataset, plan("ranking", group_by=["building_name"], limit=1, filters=june())
    )
    client = Mock()
    client.explanation_json.return_value = json.dumps(
        {"meaning": "गणना का परिणाम है {{first}}।", "checks": ["coverage"]}
    )
    explanation = explain_result(result, "सबसे अधिक खपत?", settings, client)
    payload = json.loads(client.explanation_json.call_args.args[1])
    assert payload["language"] == "hi"
    assert set(payload) == {"language", "intent", "facts", "caveats"}
    assert "fixture.csv" not in json.dumps(payload)
    assert explanation.generated
    assert language_for("Hello") == "en"
    assert not fallback_explanation(result, "hi").generated
    with pytest.raises(AIError, match="remote"):
        explain_result(
            result, "question", replace(settings, ollama_host="https://remote.example"), client
        )


@pytest.mark.parametrize(
    "intent", ["ranking", "trend", "period_comparison", "per_student", "scenario", "unavailable"]
)
def test_downloadable_one_page_pdf(dataset, intent):
    plans = {
        "ranking": plan("ranking", group_by=["building_name"], limit=1, filters=june()),
        "trend": plan("trend", group_by=["month"]),
        "period_comparison": plan("period_comparison", periods=["2026-05", "2026-06"]),
        "per_student": student_plan(june()),
        "scenario": scenario_plan(),
        "unavailable": AnalysisPlan(
            intent="aggregate", metric="electricity_cost_inr", aggregation="sum"
        ),
    }
    result = calculate(dataset, plans[intent])
    report = answer_pdf(result, "Show the answer <script>alert(1)</script>", dataset.classification)
    assert report.startswith(b"%PDF")
    with pymupdf.open(stream=report, filetype="pdf") as document:
        assert document.page_count == 1
        text = document[0].get_text()
        assert "CampusPulse" in text
        assert "SYNTHETIC" in text
        assert "Caveats" in text
        if intent == "scenario":
            assert "20,780.00" in text
        if intent == "ranking":
            assert "6,200.00" in text
