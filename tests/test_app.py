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
        assert not app.sidebar.get("file_uploader")
        assert len(app.get("file_uploader")) == 1
        button(app, "Load synthetic PDF").click().run()
        assert not app.exception
        assert "dataset" not in app.session_state
        button(app, "Confirm dataset").click().run()
        assert "dataset" not in app.session_state
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        assert not app.exception
        assert len(app.session_state["dataset"].frame) == 30
        assert app.session_state["overview"]["total"] == 120500
        assert app.session_state["history"] == []
        assert not app.get("json")
        assert app.chat_input[0].disabled
        assert selectbox(app, "Students (optional)").value == "occupancy"
        assert not any(s.label == "Old period" for s in app.selectbox)
        assert not any(n.label == "What-if reduction (%)" for n in app.number_input)
        selectbox(app, "Month").select("2026-06")
        button(app, "Run verified calculation").click().run()
        assert not app.exception
        assert "6,200.00 kWh" in app.session_state["history"][0]["result"].answer
        assert any(m.value == "**How this was calculated**" for m in app.markdown)
        assert app.session_state["history"][0]["report"].startswith(b"%PDF")
        assert len([b for b in app.button if b.key and b.key.startswith("followup_")]) == 3
        selectbox(app, "Analysis").select("Period comparison").run()
        assert not any(s.label == "Month" for s in app.selectbox)
        assert selectbox(app, "Old period").value == "2026-05"
        button(app, "Run verified calculation").click().run()
        assert not app.exception
        assert app.session_state["history"][-1]["result"].details["absolute_change"] == 850
        selectbox(app, "Analysis").select("What-if reduction").run()
        selectbox(app, "Month").select("2026-06")
        next(m for m in app.multiselect if m.label == "Buildings (empty = all)").select(
            "Boys Hostel"
        ).select("Girls Hostel")
        button(app, "Run verified calculation").click().run()
        assert not app.exception
        scenario = app.session_state["history"][-1]["result"]
        assert scenario.details["old"] == 21950
        assert scenario.details["saving"] == 1170
        assert scenario.details["new"] == 20780
        assert not app.get("json")
        button(app, "Load synthetic CSV").click().run()
        assert not app.exception
        assert "dataset" not in app.session_state
        assert not app.session_state["history"]
        button(app, "Use another file").click().run()
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
        patch(
            "campuspulse.gemma_client.GemmaClient.explanation_json",
            return_value='{"meaning":"The calculated result is {{first}}.","checks":["meter"]}',
        ) as explainer,
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
        assert not app.session_state["history"][0]["explanation"].generated
        explainer.assert_not_called()
        button(app, "Explain with Gemma · optional").click().run()
        assert app.session_state["history"][0]["explanation"].generated
        assert explainer.call_count == 1
        assert app.session_state["history"][0]["elapsed"] > 0
        app.chat_input[0].set_value("Another question").run()
        assert not app.exception
        assert "invalid" in app.session_state["history"][-1]["error"]
        assert len(app.session_state["dataset"].frame) == 30


def test_followup_button_uses_its_own_parent_answer_and_reset_clears_context():
    import json

    status = ModelStatus(True, "Mocked model", "gemma4:e2b", "Local to app server")
    june = AnalysisPlan(
        intent="ranking",
        metric="electricity_kwh",
        aggregation="sum",
        group_by=["building_name"],
        limit=1,
        filters=[Filter(column="month", operator="eq", value="2026-06")],
    )
    may = june.model_copy(
        update={"filters": [Filter(column="month", operator="eq", value="2026-05")]}
    )
    hostels = june.model_copy(
        update={
            "filters": [
                *june.filters,
                Filter(
                    column="building_name", operator="in", value=["Boys Hostel", "Girls Hostel"]
                ),
            ]
        }
    )
    with (
        patch("campuspulse.gemma_client.GemmaClient.check", return_value=status),
        patch(
            "campuspulse.gemma_client.GemmaClient.plan_json",
            side_effect=[
                june.model_dump_json(),
                may.model_dump_json(),
                hostels.model_dump_json(),
                june.model_dump_json(),
            ],
        ) as planner,
        patch(
            "campuspulse.gemma_client.GemmaClient.explanation_json",
            return_value='{"meaning":"Result: {{first}}.","checks":["coverage"]}',
        ),
    ):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
        ).run()
        button(app, "Load synthetic CSV").click().run()
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        app.chat_input[0].set_value("Highest usage in June 2026?").run()
        app.chat_input[0].set_value("and in May?").run()
        assert (
            json.loads(planner.call_args.args[1])["previous_plan"]["filters"][0]["value"]
            == "2026-06"
        )
        assert app.session_state["history"][-1]["result"].values.value.iloc[0] == 5800
        next(
            b
            for b in app.button
            if b.key and b.key.endswith("_0_2") and b.key.startswith("followup_")
        ).click().run()
        assert not app.exception
        assert (
            json.loads(planner.call_args.args[1])["previous_plan"]["filters"][0]["value"]
            == "2026-06"
        )
        button(app, "Load synthetic PDF").click().run()
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        app.chat_input[0].set_value("Highest usage in June 2026?").run()
        assert "previous_plan" not in json.loads(planner.call_args.args[1])
        assert not app.exception


def test_failed_explanation_preserves_answer_with_visible_fallback():
    status = ModelStatus(True, "Mocked model", "gemma4:e2b", "Local to app server")
    plan = AnalysisPlan(intent="aggregate", metric="electricity_kwh", aggregation="sum")
    with (
        patch("campuspulse.gemma_client.GemmaClient.check", return_value=status),
        patch(
            "campuspulse.gemma_client.GemmaClient.plan_json", return_value=plan.model_dump_json()
        ),
        patch(
            "campuspulse.gemma_client.GemmaClient.explanation_json",
            return_value='{"meaning":"900000 kWh saved! {{first}}","checks":["meter"]}',
        ),
    ):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
        ).run()
        button(app, "Load synthetic CSV").click().run()
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        app.chat_input[0].set_value("Total?").run()
        assert not app.exception
        button(app, "Explain with Gemma · optional").click().run()
        assert not app.exception
        entry = app.session_state["history"][0]
        assert entry["result"].values.value.iloc[0] == 120500
        assert not entry["explanation"].generated
        assert "unverified number" in entry["explanation_error"]
        assert "900000" not in entry["explanation"].meaning
        assert not app.get("json")


def test_quick_month_ranking_works_offline_without_any_inference():
    status = ModelStatus(False, "Offline", "gemma2:2b", "Local to app server")
    with (
        patch("campuspulse.gemma_client.GemmaClient.check", return_value=status),
        patch("campuspulse.gemma_client.GemmaClient.plan_json") as planner,
        patch("campuspulse.gemma_client.GemmaClient.explanation_json") as explainer,
    ):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
        ).run()
        button(app, "Load synthetic CSV").click().run()
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        button(app, "Month with highest electricity use").click().run()
        assert not app.exception
        entry = app.session_state["history"][-1]
        assert entry["mode"] == "Quick calculation · no AI"
        assert entry["result"].values.iloc[0].label == "2026-06"
        assert entry["result"].values.iloc[0].value == 21950
        assert not button(app, "What was the electricity cost?").disabled
        button(app, "What was the electricity cost?").click().run()
        assert app.session_state["history"][-1]["result"].status == "unavailable"
        planner.assert_not_called()
        explainer.assert_not_called()


def test_actual_bill_question_reports_missing_cost_without_waiting_for_ai():
    status = ModelStatus(True, "Configured model", "gemma2:2b", "Local to app server")
    with (
        patch("campuspulse.gemma_client.GemmaClient.check", return_value=status),
        patch("campuspulse.gemma_client.GemmaClient.plan_json") as planner,
        patch("campuspulse.gemma_client.GemmaClient.explanation_json") as explainer,
    ):
        app = AppTest.from_file(
            Path(__file__).resolve().parents[1] / "app.py", default_timeout=30
        ).run()
        button(app, "Load synthetic CSV").click().run()
        next(c for c in app.checkbox if c.label.startswith("I reviewed")).check()
        button(app, "Confirm dataset").click().run()
        app.chat_input[0].set_value("In which month the elctricity bill was higest").run()
        assert not app.exception
        entry = app.session_state["history"][-1]
        assert "error" not in entry
        assert entry["mode"] == "Data availability check · no AI"
        assert "bill amounts" in entry["result"].answer
        planner.assert_not_called()
        explainer.assert_not_called()
