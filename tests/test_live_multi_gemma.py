"""Opt-in real-model language smoke; NEVER implies live success by default."""

import os

import pytest

from campuspulse.config import Settings
from campuspulse.csv_parser import parse_csv
from campuspulse.gemma_client import GemmaClient
from campuspulse.multi_source import SourceEntry, combine_sources
from campuspulse.normalization import normalize, suggest_mapping
from campuspulse.question_planner import plan_question

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def live_context():
    if os.getenv("RUN_LIVE_GEMMA") != "1":
        pytest.skip("Live multi-source Gemma tests require RUN_LIVE_GEMMA=1")
    settings = Settings.from_env()
    client = GemmaClient(settings)
    if not client.check().ready:
        pytest.skip("Configured model not available")
    rows = b"building_name,month,electricity_kwh\nA,2026-06,100\n"
    table = parse_csv(rows, "test.csv", settings)[0]
    ds = normalize(table, suggest_mapping(list(table.frame)), "kWh", "SYNTHETIC DEMONSTRATION DATA")
    combined = combine_sources([SourceEntry("report-2025", "old.csv", "FY2025", ds),
                                SourceEntry("report-2026", "new.csv", "FY2026", ds)])
    return settings, client, combined


@pytest.mark.parametrize("question", [
    "Compare FY2025 and FY2026 reports",
    "Dono files ki electricity compare karo",
    "दो रिपोर्ट की बिजली खपत की तुलना करो",
])
def test_live_multilingual_sources(question, live_context):
    settings, client, data = live_context
    planned = plan_question(question, data, settings, client, allow_remote=True)
    assert planned.intent == "compare_sources"
    assert not planned.sources or set(planned.sources).issubset({"report-2025", "report-2026"})
