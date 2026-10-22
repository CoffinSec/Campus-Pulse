"""Opt-in REAL Gemma planning. No mocks or deterministic language fallback."""

import os

import pytest

from campuspulse.analysis_engine import calculate
from campuspulse.config import Settings
from campuspulse.gemma_client import GemmaClient
from campuspulse.question_planner import plan_question


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
    else:
        assert result.status == "unavailable"
        assert result.values.empty
