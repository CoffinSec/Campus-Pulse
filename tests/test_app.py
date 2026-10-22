"""Real Streamlit state/widget execution; inference readiness is mocked offline."""

from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from campuspulse.gemma_client import ModelStatus
from campuspulse.models import AnalysisPlan, Filter


def button(app, label):
    return next(b for b in app.button if b.label == label)


def selectbox(app, label):
    return next(b for b in app.selectbox if b.label == label)


def test_dashboard_confirm_analyze_replace_clear():
    status = ModelStatus(False, "Offline test", "gemma4:e2b", "Local to app server")
    with patch("campuspulse.gemma_client.GemmaClient.check", return_value=status):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
        ).run()
        assert not app.exception
        assert app.title[0].value == "CampusPulse"
        button(app, "Load synthetic PDF").click().run()
        assert not app.exception
        assert "dataset" not in app.session_state
        button(app, "Confirm dataset").click().run()
        assert "dataset" not in app.session_state
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        assert not app.exception
        assert len(app.session_state["dataset"].frame) == 30
        assert app.chat_input[0].disabled
        selectbox(app, "Month filter (ignored for period comparison)").select("2026-06")
        button(app, "Run verified calculation").click().run()
        assert not app.exception
        assert "6,200.00 kWh" in app.session_state["history"][0]["result"].answer
        selectbox(app, "Analysis").select("Period comparison")
        button(app, "Run verified calculation").click().run()
        assert not app.exception
        assert app.session_state["history"][-1]["result"].details["absolute_change"] == 850
        button(app, "Load synthetic CSV").click().run()
        assert not app.exception
        assert "dataset" not in app.session_state
        assert not app.session_state["history"]
        button(app, "Clear dataset and chat").click().run()
        assert not app.exception
        assert "tables" not in app.session_state


def test_chat_with_mocked_gemma_and_failure_preserves_dataset():
    status = ModelStatus(True, "Mocked available model", "gemma4:e2b", "Local to app server")
    plan = AnalysisPlan(
        intent="ranking",
        metric="electricity_kwh",
        aggregation="sum",
        group_by=["building_name"],
        limit=1,
        filters=[Filter(column="month", operator="eq", value="2026-06")],
    )
    with (
        patch("campuspulse.gemma_client.GemmaClient.check", return_value=status),
        patch(
            "campuspulse.gemma_client.GemmaClient.plan_json",
            side_effect=[plan.model_dump_json(), "invalid JSON"],
        ),
    ):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
        ).run()
        button(app, "Load synthetic CSV").click().run()
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        app.chat_input[0].set_value(
            "Which building consumed the most electricity in June 2026?"
        ).run()
        assert not app.exception
        assert app.session_state["history"][0]["result"].values.value.iloc[0] == 6200
        app.chat_input[0].set_value("Another question").run()
        assert not app.exception
        assert "invalid" in app.session_state["history"][-1]["error"]
        assert len(app.session_state["dataset"].frame) == 30
