"""Regression tests: summaries are requests, not missing calculation inputs."""

from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from campuspulse.config import Settings
from campuspulse.models import AnalysisPlan
from campuspulse.question_planner import SYSTEM_PROMPT, parse_plan, plan_question
from campuspulse.quick_replies import (
    is_report_overview_request,
    quick_reply,
    report_summary,
)


@pytest.mark.parametrize(
    "question",
    [
        "cam you give me a summary??",
        "Can u pls give me a summary of this pdf?",
        "summry plz",
        "What does my report say?",
        "Explain this report to me",
        "tell me about this data",
        "report ka summary batao",
        "Please summarize my electricity data",
        "give overview!!",
        "What is in this dataset?",
        "Give me the highlights of this report",
        "Just sum up the data",
    ],
)
def test_flexible_summary_request(question, dataset):
    assert is_report_overview_request(question)
    answer = quick_reply(question, dataset)
    assert answer is not None
    assert "120,500 kWh" in answer
    assert "Boys Hostel (32,200 kWh)" in answer
    assert "6 missing occupancy values" not in answer
    assert "18,800 kWh" in answer
    assert "21,950 kWh" in answer


@pytest.mark.parametrize(
    "question",
    [
        "Give me a summary of Boys Hostel in May",
        "Summarize electricity use in April 2026",
        "Compare January and June",
        "Which building used the most electricity?",
        "Give a summary of electricity costs",
        "Show monthly trends",
        "summary for library only",
        "show the total electricity in June",
    ],
)
def test_scoped_questions_go_to_ai(question, dataset):
    assert not is_report_overview_request(question)
    assert quick_reply(question, dataset) is None


def test_gemma_can_classify_new_open_ended_paraphrases(dataset):
    client = Mock()
    client.plan_json.return_value = AnalysisPlan(
        intent="report_overview",
        metric="electricity_kwh",
        aggregation="sum",
        chart_type="none",
    ).model_dump_json()
    result = plan_question(
        "Could you walk me through what's going on with the supplied dataset?",
        dataset,
        Settings(),
        client,
    )
    assert result.intent == "report_overview"
    assert client.plan_json.call_count == 1
    assert "report_overview" in SYSTEM_PROMPT
    assert "never demand" in SYSTEM_PROMPT.casefold()


def test_summary_cannot_be_filtered_by_model(dataset):
    with pytest.raises(ValidationError, match="complete electricity dataset"):
        AnalysisPlan(
            intent="report_overview",
            metric="electricity_kwh",
            aggregation="sum",
            group_by=["building_name"],
        )
    plan = AnalysisPlan(intent="report_overview", metric="electricity_kwh", aggregation="sum")
    assert parse_plan(plan.model_dump_json(), dataset).intent == "report_overview"


def test_summary_is_derived_not_sample_numbers(dataset):
    dataset.frame.loc[:, "electricity_kwh"] *= 2
    answer = report_summary(dataset)
    assert "241,000 kWh" in answer
    assert "64,400 kWh" in answer
    assert "120,500 kWh" not in answer
