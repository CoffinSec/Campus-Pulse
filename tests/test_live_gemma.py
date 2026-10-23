"""Opt-in REAL Gemma planning. No mocks or deterministic language fallback."""

import os

import pytest

from campuspulse.analysis_engine import calculate
from campuspulse.config import Settings
from campuspulse.explanations import explain_result
from campuspulse.gemma_client import GemmaClient
from campuspulse.question_planner import plan_question

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_GEMMA") != "1",
        reason="Opt-in live model test: set RUN_LIVE_GEMMA=1 after installing Gemma 4.",
    ),
]


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_GEMMA") != "1",
    reason="Opt-in live model test: set RUN_LIVE_GEMMA=1 after installing Gemma 4.",
)
@pytest.mark.parametrize(
    "question,kind",
    [
        ("Which building consumed the most electricity in June 2026?", "ranking"),
        ("Compare May 2026 and June 2026 electricity consumption.", "comparison"),
        ("Show the monthly electricity consumption trend.", "trend"),
        ("What was the electricity cost in December 2026?", "missing"),
        ("June 2026 mein sabse zyada electricity kis building ne use ki?", "ranking"),
        ("जून 2026 में किस इमारत ने सबसे अधिक बिजली का उपयोग किया?", "ranking"),
        ("Compare kWh per student in June 2026.", "per_student"),
        ("What if the hostels cut electricity usage by 10% in June 2026?", "scenario"),
    ],
)
def test_live_gemma(dataset, question, kind):
    settings = Settings.from_env()
    client = GemmaClient(settings)
    status = client.check()
    assert status.ready, status.message
    # Explicit opt-in remote disclosure for unattended integration testing.
    allow_remote = os.getenv("ALLOW_REMOTE_INFERENCE") == "1"
    plan = plan_question(question, dataset, settings, client, allow_remote)
    result = calculate(dataset, plan)
    if kind == "ranking":
        assert plan.intent == "ranking"
        assert result.values.iloc[0].label == "Boys Hostel"
        assert result.values.iloc[0].value == 6200
    elif kind == "comparison":
        assert result.details["absolute_change"] == 850
    elif kind == "trend":
        assert result.values.value.tolist() == [18800, 19000, 19500, 20150, 21100, 21950]
    elif kind == "per_student":
        assert "Library" not in result.values.label.tolist()
        assert result.values.set_index("label").value["Boys Hostel"] == 15.5
        assert any(w.code == "missing_denominator" for w in result.warnings)
    elif kind == "scenario":
        assert result.details["saving"] == 1170
        assert result.details["new"] == 20780
    else:
        assert result.status == "unavailable"
        assert result.values.empty


def test_live_followup(dataset):
    settings = Settings.from_env()
    client = GemmaClient(settings)
    allow_remote = os.getenv("ALLOW_REMOTE_INFERENCE") == "1"
    previous = plan_question(
        "Which building used most electricity in June 2026?",
        dataset,
        settings,
        client,
        allow_remote,
    )
    following = plan_question(
        "and in May?", dataset, settings, client, allow_remote, previous_plan=previous
    )
    assert calculate(dataset, following).values.value.iloc[0] == 5800


@pytest.mark.parametrize(
    "question",
    [
        "Which building used most electricity in June 2026?",
        "जून 2026 में किस इमारत ने सबसे अधिक बिजली का उपयोग किया?",
    ],
)
def test_live_verified_explanation(dataset, question):
    settings = Settings.from_env()
    client = GemmaClient(settings)
    allow_remote = os.getenv("ALLOW_REMOTE_INFERENCE") == "1"
    plan = plan_question(question, dataset, settings, client, allow_remote)
    result = calculate(dataset, plan)
    explanation = explain_result(result, question, settings, client, allow_remote)
    assert explanation.generated
    assert "6,200.00" in explanation.meaning
