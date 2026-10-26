"""CampusPulse's session-scoped Streamlit dashboard."""

import hashlib
import logging
from pathlib import Path
from time import perf_counter

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from campuspulse.analysis_engine import calculate
from campuspulse.config import Settings
from campuspulse.csv_parser import PROVENANCE
from campuspulse.evidence import evidence_table, export_evidence
from campuspulse.explanations import explain_result, fallback_explanation, language_for
from campuspulse.gemma_client import GemmaClient
from campuspulse.ingestion import ingest
from campuspulse.insights import anomaly_flags, overview
from campuspulse.models import AIError, AnalysisPlan, DataError, Filter, PlanError
from campuspulse.normalization import ALIASES, SYNTHETIC, normalize, suggest_mapping
from campuspulse.presentation import (
    calculation_lines,
    describe_plan,
    followup_questions,
    period_label,
)
from campuspulse.question_planner import plan_question, suggested_questions
from campuspulse.quick_replies import quick_reply, report_summary
from campuspulse.reporting import answer_pdf, report_png
from campuspulse.ui import CSS, progress_steps, styled_text
from campuspulse.visualization import build_chart

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def clear_data() -> None:
    for key in [
        "dataset",
        "tables",
        "source_name",
        "source_size",
        "source_hash",
        "selected_table",
        "classification",
        "overview",
        "anomalies",
    ]:
        st.session_state.pop(key, None)
    st.session_state.history = []
    st.session_state.generation = st.session_state.get("generation", 0) + 1


def load_data(data: bytes, name: str, settings: Settings, separator: str | None) -> None:
    clear_data()  # Invalidate old results even if the replacement fails.
    with st.spinner("Extracting structured data and source references…"):
        tables = ingest(data, name, settings, separator)
    digest = hashlib.sha256(data).hexdigest()
    sample_digests = {
        hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT / "data").glob("campus_electricity_sample.*")
    }
    st.session_state.update(
        tables=tables,
        source_name=name,
        source_size=len(data),
        source_hash=digest,
        classification=SYNTHETIC if digest in sample_digests else "User-provided · unverified",
    )


def review_data() -> None:
    tables = st.session_state.get("tables")
    if not tables:
        return
    st.caption(
        "We matched the columns for you. Check the preview and adjust anything that looks wrong."
    )
    generation = st.session_state.generation
    selected = (
        st.selectbox(
            "Detected table",
            range(len(tables)),
            format_func=lambda i: tables[i].table_id,
            key=f"table_{generation}",
        )
        if len(tables) > 1
        else 0
    )
    if st.session_state.get("selected_table") != selected:
        st.session_state.pop("dataset", None)
        st.session_state.pop("overview", None)
        st.session_state.pop("anomalies", None)
        st.session_state.history = []
        st.session_state.selected_table = selected
    table = tables[selected]
    st.dataframe(
        table.frame[[c for c in table.frame if c not in PROVENANCE]].head(8),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"Preview: first {min(8, len(table.frame))} of {len(table.frame)} readings. Original row references are kept with every calculation."
    )
    if len(tables) > 1:
        st.info(
            "Analyze one selected table at a time. This MVP does not merge tables across pages; export a consolidated CSV for a whole-report calculation."
        )
    for warning in table.warnings:
        st.info(warning.message)
    columns = [c for c in table.frame if c not in PROVENANCE]
    suggestions = suggest_mapping(columns)
    with st.form(f"schema_{generation}_{selected}"):
        st.markdown("**Match your columns**")
        mapping = {}
        options = ["— Select —", *columns]
        cols = st.columns(4)
        for i, (target, label) in enumerate(
            [
                ("building_name", "Building / block"),
                ("month", "Month / date"),
                ("electricity_kwh", "Electricity consumption"),
                ("occupancy", "Students (optional)"),
            ]
        ):
            choice = cols[i].selectbox(
                label,
                options,
                index=options.index(suggestions[target]) if target in suggestions else 0,
            )
            if choice != options[0]:
                mapping[target] = choice
        with st.expander("Optional columns and month-only dates"):
            for target in ALIASES:
                if target in {"building_name", "month", "electricity_kwh", "occupancy"}:
                    continue
                choice = st.selectbox(
                    target.replace("_", " ").title(),
                    options,
                    index=options.index(suggestions[target]) if target in suggestions else 0,
                )
                if choice != options[0]:
                    mapping[target] = choice
            year = st.number_input(
                "Year for month-only dates (0 = do not infer)", 0, 2100, 0, step=1
            )
            st.caption(
                "Optional units: cost = INR, tariff = INR/kWh, occupancy = student counts. Only map columns with these meanings and units."
            )
        left, right = st.columns(2)
        unit = left.selectbox("Source electricity unit", ["kWh", "Wh", "MWh", "Unknown"])
        classification = st.session_state.classification
        if classification != SYNTHETIC:
            classification = right.selectbox(
                "Dataset classification", ["User-provided · unverified", SYNTHETIC]
            )
        else:
            right.info(SYNTHETIC)
        confirmed = st.checkbox("I reviewed the selected table, column meanings and units.")
        submitted = st.form_submit_button("Confirm dataset", type="primary")
    if submitted:
        st.session_state.pop("dataset", None)
        st.session_state.pop("overview", None)
        st.session_state.pop("anomalies", None)
        st.session_state.history = []
        if not confirmed:
            st.warning("Review the mapping and check the confirmation box first.")
        else:
            try:
                st.session_state.dataset = normalize(
                    table, mapping, unit, classification, int(year) or None
                )
                st.success("Dataset validated and confirmed. You can now analyze it.")
                st.rerun()
            except DataError as exc:
                st.error(str(exc))


def manual_analysis(dataset) -> None:
    with st.expander("Choose a calculation · no AI needed"):
        st.caption(
            "Pick an analysis and its scope. This uses the same verified calculations without Gemma."
        )
        operation = st.selectbox(
            "Analysis",
            [
                "Highest building",
                "Lowest building",
                "Monthly trend",
                "Period comparison",
                "Group comparison",
                "Total",
                "Mean of observations",
                "Mean of monthly totals",
                "Mean per building",
                "Missing values",
                "Unavailable cost",
                "Usage per student",
                "What-if reduction",
            ],
            key=f"manual_operation_{st.session_state.generation}",
        )
        with st.form("manual_analysis"):
            buildings = sorted(dataset.frame.building_name.unique())
            selected_buildings = st.multiselect("Buildings (empty = all)", buildings)
            month, old, new, reduction = "All months", None, None, 10.0
            if operation == "Period comparison":
                a, b = st.columns(2)
                old = a.selectbox(
                    "Old period", dataset.months, index=max(0, len(dataset.months) - 2)
                )
                new = b.selectbox("New period", dataset.months, index=len(dataset.months) - 1)
            elif operation != "Monthly trend":
                month = st.selectbox("Month", ["All months", *dataset.months])
            if operation == "What-if reduction":
                reduction = st.number_input(
                    "What-if reduction (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0
                )
                st.caption(
                    "Select the buildings that would reduce usage. Other buildings stay in the campus total."
                )
            if operation == "Usage per student":
                st.caption(
                    "Requires a student count for each selected building and month. Missing counts are flagged, never guessed."
                )
            run = st.form_submit_button("Run verified calculation", type="primary")
        if run:
            started = perf_counter()
            filters = []
            if selected_buildings and operation != "What-if reduction":
                filters.append(
                    Filter(column="building_name", operator="in", value=selected_buildings)
                )
            if month != "All months" and operation != "Period comparison":
                filters.append(Filter(column="month", operator="eq", value=month))
            args = {"metric": "electricity_kwh", "aggregation": "sum", "filters": filters}
            if operation in {"Highest building", "Lowest building"}:
                args.update(
                    intent="ranking",
                    group_by=["building_name"],
                    limit=1,
                    sort="ascending" if operation == "Lowest building" else "descending",
                )
            elif operation == "Monthly trend":
                args.update(intent="trend", group_by=["month"])
            elif operation == "Period comparison":
                args.update(intent="period_comparison", periods=[old, new])
            elif operation == "Group comparison":
                args.update(intent="group_comparison", group_by=["building_name"])
            elif operation == "Usage per student":
                args.update(intent="per_student", aggregation="mean", group_by=["building_name"])
            elif operation == "What-if reduction":
                args.update(
                    intent="scenario",
                    scenario_buildings=selected_buildings,
                    reduction_percent=reduction,
                )
            # elif operation == "Missing values":
            #     args.update(intent="missing_values")
            else:
                args.update(intent="aggregate")
                if operation.startswith("Mean"):
                    args.update(
                        aggregation="mean",
                        average_basis={
                            "Mean of observations": "observations",
                            "Mean of monthly totals": "monthly_totals",
                            "Mean per building": "building_totals",
                        }[operation],
                    )
                if operation == "Unavailable cost":
                    args.update(metric="electricity_cost_inr")
            try:
                result = calculate(dataset, AnalysisPlan(**args))
                st.session_state.history.append(
                    {
                        "question": f"Manual: {operation}",
                        "mode": "Manual analysis · no AI",
                        "result": result,
                        "elapsed": perf_counter() - started,
                        "explanation": fallback_explanation(result, "en"),
                    }
                )
                st.session_state.history = st.session_state.history[-6:]
                st.rerun()
            except ValidationError as exc:
                st.error(exc.errors()[0]["msg"].removeprefix("Value error, "))
            except (ValueError, PlanError) as exc:
                st.error(
                    "Choose two distinct periods."
                    if old == new and operation == "Period comparison"
                    else str(exc)
                )


def render_overview(dataset) -> None:
    if "overview" not in st.session_state:
        st.session_state.overview = overview(dataset)
        st.session_state.anomalies = anomaly_flags(dataset)
    summary = st.session_state.overview
    st.subheader("Your data at a glance")
    st.badge(
        "Synthetic demonstration data"
        if dataset.classification == SYNTHETIC
        else "User-provided · unverified",
        color="orange" if dataset.classification == SYNTHETIC else "blue",
    )
    cols = st.columns(4)
    total = summary["total"]
    cols[0].metric("Total electricity", "Unavailable" if pd.isna(total) else f"{total:,.0f} kWh")
    cols[1].metric("Buildings", summary["buildings"])
    cols[2].metric("Months covered", summary["months"])
    cols[3].metric("Highest building", summary["highest"])
    if summary["highest_value"] is not None:
        cols[3].caption(f"{summary['highest_value']:,.0f} kWh across the selected dataset")
    st.caption(
        f"{period_label(dataset.months[0])} – {period_label(dataset.months[-1])} · {len(dataset.frame)} readings. Highest building is based on total observed usage across this period."
    )
    chart = build_chart(summary["trend"])
    if chart is not None:
        chart.update_layout(height=290, margin={"l": 10, "r": 30, "t": 55, "b": 35})
        with st.container(border=True):
            st.plotly_chart(
                chart,
                width="stretch",
                key=f"overview_{st.session_state.generation}",
                config={"displayModeBar": False},
            )
    for warning in dataset.warnings:
        if warning.code == "missing_values" and "occupancy" in warning.message:
            # Missing optional headcounts are explained by the occupancy answer itself.
            continue
        if warning.severity == "warning":
            st.warning(warning.message, icon="⚠️")
    flags = st.session_state.anomalies
    st.markdown("**Changes worth checking**")
    if flags.empty:
        st.caption(
            "No unusually large changes flagged. The check needs at least three earlier month-to-month changes per building; short or incomplete histories cannot establish a normal pattern."
        )
    else:
        for row in flags.to_dict("records"):
            st.warning(
                f"{row['Building']} · {period_label(row['Month'])}: usage changed {row['Change (%)']:+.1f}% against its own prior history — cause unknown.",
                icon="⚠️",
            )
        st.dataframe(flags, hide_index=True, width="stretch")
    with st.expander("How unusual changes are flagged"):
        st.caption(
            "Flag rule: deviation from the building’s prior median change exceeds both 20 percentage points and three scaled median absolute deviations. Flags are prompts to investigate, not proof of waste."
        )


def render_result(entry: dict, index: int, dataset, can_ask: bool):
    pending = None
    with st.chat_message("user"):
        st.text(entry["question"])
    with st.chat_message("assistant", avatar="📊"):
        ai = entry["mode"].startswith("Gemma")
        st.caption(f"{entry['mode']} · Response time: {entry.get('elapsed', 0):.2f}s")
        if "error" in entry:
            st.error(entry["error"])
            return None
        if "message" in entry:
            st.text(entry["message"])
            return None
        result = entry["result"]
        st.caption(describe_plan(result, ai))
        if result.status != "ok":
            st.error(result.answer)
        else:
            styled_text(result.answer, "answer")
            if result.plan.intent in {"period_comparison", "scenario"}:
                cols = st.columns(4)
                cols[0].metric(
                    "Earlier value"
                    if result.plan.intent == "period_comparison"
                    else "Measured campus total",
                    f"{result.details['old']:,.2f} {result.unit}",
                )
                cols[1].metric(
                    "Later value"
                    if result.plan.intent == "period_comparison"
                    else "What-if campus total",
                    f"{result.details['new']:,.2f} {result.unit}",
                )
                cols[2].metric(
                    "Change" if result.plan.intent == "period_comparison" else "Potential saving",
                    f"{result.details.get('saving', result.details['absolute_change']):+,.2f} {result.unit}",
                )
                pct = result.details.get("percentage_change")
                cols[3].metric(
                    "Change in campus total", "Undefined" if pct is None else f"{pct:+.2f}%"
                )
            elif result.chart_type == "metric":
                st.metric(
                    "Calculated value", f"{result.values.iloc[0]['value']:,.2f} {result.unit}"
                )
            try:
                chart = build_chart(result)
                if chart is not None:
                    st.plotly_chart(
                        chart, width="stretch", key=f"chart_{st.session_state.generation}_{index}"
                    )
            except (ValueError, TypeError):
                logger.warning("Chart rendering failed")
                st.warning(
                    "The chart is unavailable. The verified values and working are shown below."
                )
        st.markdown("**How this was calculated**")
        for line in calculation_lines(result):
            styled_text(line, "formula")
        if not result.values.empty:
            st.dataframe(
                result.values.rename(
                    columns={"label": "Building / period", "value": f"Result ({result.unit})"}
                ),
                hide_index=True,
                width="stretch",
            )
        seen = set()
        for warning in result.warnings:
            if warning.message in seen:
                continue
            seen.add(warning.message)
            if warning.code == "missing_values" and "occupancy" in warning.message:
                continue
            if (result.plan.metric == "occupancy" and result.status == "ok"
                and warning.code in {"selected_missing", "empty_group"}):
                # The answer explicitly shows unavailable buildings, without
                # repeating the same issue in multiple warning banners.
                continue
            if warning.severity == "warning":
                st.warning(warning.message, icon="⚠️")
            else:
                st.caption(warning.message)
        explanation = entry.get("explanation")
        if explanation:
            with st.container(border=True):
                st.markdown("**What this means / what could be checked**")
                st.caption(
                    "Gemma explanation · numbers verified against this calculation"
                    if explanation.generated
                    else "Verified summary · no AI explanation"
                )
                st.text(explanation.meaning)
                for check in explanation.checks:
                    st.text("• " + check)
                st.caption("Possible checks, not established causes.")
        if entry.get("explanation_error"):
            st.warning(entry["explanation_error"], icon="⚠️")
        with st.expander(f"Source readings · {len(result.evidence)} rows"):
            if result.evidence.empty:
                st.info("No numerical answer was produced, so no source citation is asserted.")
            else:
                readable = evidence_table(result).rename(
                    columns={
                        "source_file": "Report",
                        "source_page": "Page",
                        "source_table": "Table",
                        "source_row": "Original row",
                        "row_id": "Reference",
                        "building_name": "Building",
                        "month": "Month",
                        "electricity_kwh": "Electricity (kWh)",
                        "occupancy": "Students",
                        "raw_occupancy": "Original student count",
                        "raw_electricity_kwh": "Original reading",
                        "raw_month": "Original period",
                    }
                )
                st.dataframe(readable, hide_index=True, width="stretch")
                st.caption(
                    "Ranking includes the candidate buildings used to establish the winner. Original rows include PDF table headers; CSV references are physical end-lines."
                )
        if "report" not in entry and "report_error" not in entry:
            try:
                entry["report"] = answer_pdf(
                    result, entry["question"], dataset.classification, explanation, ai
                )
            except (RuntimeError, ValueError, MemoryError):
                logger.warning("Answer report rendering failed")
                entry["report_error"] = (
                    "The PDF could not be prepared. Your answer and source CSV are still available."
                )
        if entry.get("report_error"):
            st.warning(entry["report_error"])
        if "report" in entry and "picture" not in entry and "picture_error" not in entry:
            try:
                entry["picture"] = report_png(entry["report"])
            except (RuntimeError, ValueError, MemoryError):
                entry["picture_error"] = (
                    "The image could not be prepared. The PDF and CSV are still available."
                )
        if entry.get("picture_error"):
            st.warning(entry["picture_error"])
        styled_text("Save this answer", "eyebrow")
        left, picture, right = st.columns(3)
        left.download_button(
            "Download this answer · PDF",
            entry.get("report", b""),
            "campuspulse_answer.pdf",
            "application/pdf",
            key=f"report_{st.session_state.generation}_{index}",
            disabled="report" not in entry,
            width="stretch",
            on_click="ignore",
            wrap=True,
        )
        right.download_button(
            "Download source data · CSV",
            export_evidence(result),
            "campuspulse_evidence.csv",
            "text/csv",
            key=f"export_{st.session_state.generation}_{index}",
            width="stretch",
            on_click="ignore",
            wrap=True,
        )
        picture.download_button(
            "Save answer as image · PNG",
            entry.get("picture", b""),
            "campuspulse_answer.png",
            "image/png",
            key=f"picture_{st.session_state.generation}_{index}",
            disabled="picture" not in entry,
            width="stretch",
            on_click="ignore",
            wrap=True,
        )
        st.caption("Ask a follow-up" if can_ask else "Connect Gemma to ask these follow-ups")
        for i, (column, question) in enumerate(
            zip(st.columns(3), followup_questions(dataset, result))
        ):
            if column.button(
                question,
                key=f"followup_{st.session_state.generation}_{index}_{i}",
                disabled=not can_ask,
                width="stretch",
                wrap=True,
            ):
                pending = (question, result.plan)
    return pending


def upload_panel(settings):
    with st.container(border=True):
        left, right = st.columns([2, 1])
        with left:
            st.subheader("Add your campus report")
            st.caption(
                f"A PDF table or CSV with building, month and electricity use · up to {min(settings.max_upload_mb, 10)} MB"
            )
            uploaded = st.file_uploader(
                "Choose a PDF or CSV",
                type=["pdf", "csv"],
                key=f"upload_{st.session_state.upload_epoch}",
            )
            with st.expander("CSV options"):
                separator_label = st.selectbox(
                    "CSV separator", ["Auto", "Comma", "Semicolon", "Tab", "Pipe"]
                )
            separator = {"Auto": None, "Comma": ",", "Semicolon": ";", "Tab": "\t", "Pipe": "|"}[
                separator_label
            ]
            if uploaded is not None:
                data = uploaded.getvalue()
                signature = (hashlib.sha256(data).hexdigest(), uploaded.name, separator)
                if st.session_state.get("processed_upload") != signature:
                    st.session_state.processed_upload = signature
                    st.session_state.pop("upload_error", None)
                    try:
                        load_data(data, uploaded.name, settings, separator)
                        st.rerun()
                    except DataError as exc:
                        st.session_state.upload_error = str(exc)
            if st.session_state.get("upload_error"):
                st.error(st.session_state.upload_error)
        with right:
            styled_text("Try it first", "eyebrow")
            st.markdown("**See what your campus data can tell you.**")
            st.caption(
                "Explore 5 buildings across 6 months with a fictional campus report. No file needed."
            )
            for suffix, label in [("pdf", "Load synthetic PDF"), ("csv", "Load synthetic CSV")]:
                if st.button(
                    label, width="stretch", type="primary" if suffix == "pdf" else "secondary"
                ):
                    path = ROOT / "data" / f"campus_electricity_sample.{suffix}"
                    try:
                        load_data(path.read_bytes(), path.name, settings, None)
                        st.session_state.upload_epoch += 1
                        st.session_state.pop("processed_upload", None)
                        st.session_state.pop("upload_error", None)
                        st.rerun()
                    except (DataError, OSError) as exc:
                        st.error(str(exc))
            with st.expander("Get the example files"):
                for suffix in ["pdf", "csv"]:
                    path = ROOT / "data" / f"campus_electricity_sample.{suffix}"
                    st.download_button(
                        f"Download sample {suffix.upper()}", path.read_bytes(), path.name
                    )
        if st.session_state.get("source_name"):
            st.caption(
                f"Loaded: {st.session_state.source_name} · {st.session_state.source_size / 1024:.1f} KB · {len(st.session_state.tables)} detected table(s)"
            )


def run_question(question, previous_plan, dataset, settings, client, allow_remote=True):
    started = perf_counter()
    entry = {"question": question, "mode": f"Gemma · {settings.model_name}"}
    # General greetings and whole-report summaries are not calculation plans;
    # answer them immediately instead of asking Gemma to invent one.
    reply = quick_reply(question, dataset)
    if reply is not None:
        entry.update(mode="Verified report · no AI needed", message=reply,
                     elapsed=perf_counter() - started)
        st.session_state.history.append(entry)
        st.session_state.history = st.session_state.history[-6:]
        st.rerun()
        return
    with st.status("Gemma is planning…", expanded=True) as progress:
        try:
            plan = plan_question(
                question, dataset, settings, client, allow_remote=True, previous_plan=previous_plan
            )
            if plan.intent == "report_overview":
                # Gemma handles open-ended paraphrases, but verified Python
                # derives every number and caveat from the uploaded dataset.
                entry.update(
                    message=report_summary(dataset),
                    mode=f"Gemma · {settings.model_name} · verified overview",
                    elapsed=perf_counter() - started,
                )
                progress.update(
                    label="Report overview ready", state="complete", expanded=False
                )
                st.session_state.history.append(entry)
                st.session_state.history = st.session_state.history[-6:]
                st.rerun()
                return
            progress.update(label="Calculating…")
            st.write("Checking the requested operation and calculating from the confirmed data.")
            result = calculate(dataset, plan)
            entry["result"] = result
            if result.status == "ok":
                progress.update(label="Gemma is explaining the verified result…")
                try:
                    entry["explanation"] = explain_result(
                        result, question, settings, client, allow_remote=True
                    )
                except Exception as exc:
                    entry["explanation_error"] = str(exc)
                    entry["explanation"] = fallback_explanation(result, language_for(question))
            entry["elapsed"] = perf_counter() - started
            progress.update(
                label=f"Answer ready in {entry['elapsed']:.2f}s", state="complete", expanded=False
            )
        except (AIError, PlanError, ValueError) as exc:
            entry["error"] = str(exc)
            entry["elapsed"] = perf_counter() - started
            progress.update(label="This question could not be completed", state="error")
    st.session_state.history.append(entry)
    st.session_state.history = st.session_state.history[-6:]
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="CampusPulse · Understand your campus",
        page_icon="◉",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        settings = Settings.from_env()
    except (ValueError, KeyError) as exc:
        st.error(f"Invalid environment configuration: {exc}")
        st.stop()
    for key, default in {"history": [], "generation": 0, "upload_epoch": 0}.items():
        if key not in st.session_state:
            st.session_state[key] = default
    client = GemmaClient(settings)
    if "model_status" not in st.session_state:
        st.session_state.model_status = client.check()
    status = st.session_state.model_status
    header, connection = st.columns([4, 1], vertical_alignment="center")
    with header:
        styled_text("Campus energy, made clear", "eyebrow")
        st.title("CampusPulse")
        styled_text("Turn your electricity report into answers you can explain.", "lead")
    with connection:
        st.badge(
            "Gemma connected" if status.ready else "Gemma offline",
            color="green" if status.ready else "orange",
        )
        with st.popover("Connection settings", width="stretch"):
            st.caption(status.message)
            st.text(f"Model: {settings.model_name}")
            st.caption(f"Endpoint: {settings.endpoint_label}")
            with st.expander("Gemma Engine Info"):
                st.code(
                    f"OLLAMA_MODEL={settings.model_name}\nSTATUS=RUNNING",
                    language="bash",
                )
                st.caption("Configured for Gemma 4 26B parameters in this application session.")
            if st.button("Refresh connection"):
                st.session_state.model_status = client.check()
                st.rerun()
    stage = 2 if "dataset" in st.session_state else 1 if st.session_state.get("tables") else 0
    progress_steps(stage)
    if st.session_state.get("source_name"):
        with st.container(border=True):
            file_info, file_action = st.columns([4, 1], vertical_alignment="center")
            with file_info:
                styled_text(st.session_state.source_name, "file")
                st.caption(
                    f"{st.session_state.source_size / 1024:.1f} KB · {len(st.session_state.tables)} table(s) · "
                    + ("Confirmed and ready to explore" if stage == 2 else "Ready for your review")
                )
            if file_action.button("Use another file", width="stretch"):
                clear_data()
                st.session_state.upload_epoch += 1
                st.session_state.pop("processed_upload", None)
                st.session_state.pop("upload_error", None)
                st.rerun()
        with st.expander("Upload or try another sample"):
            upload_panel(settings)
    else:
        upload_panel(settings)
    if not st.session_state.get("tables"):
        for column, title, body in zip(
            st.columns(3),
            ["See the big picture", "Ask in your own words", "Follow every number"],
            [
                "Totals, trends and unusual changes, before your first question.",
                "Compare buildings, explore usage per student, or try a what-if scenario.",
                "Clear calculations, original source rows and a report you can share.",
            ],
            strict=True,
        ):
            with column:
                styled_text(title, "eyebrow")
                styled_text(body, "help")
        st.caption(
            "Searchable PDFs and UTF-8 CSVs supported. Scanned reports need OCR first. Files are processed in this app session on the hosting server. Demo data is fictional, with no official university endorsement."
        )
        return
    with st.expander("2. Check your data", expanded="dataset" not in st.session_state):
        review_data()
    dataset = st.session_state.get("dataset")
    if dataset is None:
        return
    render_overview(dataset)
    st.divider()
    st.subheader("What would you like to know?")
    st.caption(
        "Ask in English, Hindi or Hinglish. You can follow up with “and in May?” or “what about hostels only?”"
    )
    can_ask = status.ready
    if not status.ready:
        st.info(
            "Connect Gemma to ask questions in your own words. You can explore now with ‘Choose a calculation’ below.",
            icon="💡",
        )
    question = None
    previous_plan = next(
        (e["result"].plan for e in reversed(st.session_state.history) if "result" in e), None
    )
    questions = suggested_questions(dataset)
    with st.container(key="question_suggestions"):
        for offset in range(0, len(questions), 3):
            for i, (column, suggestion) in enumerate(
                zip(st.columns(3), questions[offset : offset + 3])
            ):
                if column.button(
                    suggestion,
                    key=f"suggestion_{offset + i}",
                    disabled=not can_ask,
                    width="stretch",
                    wrap=True,
                ):
                    question = suggestion
                    previous_plan = None
    manual_analysis(dataset)
    if st.session_state.history and st.button("Clear question history"):
        st.session_state.history = []
        previous_plan = None
    for index, entry in enumerate(st.session_state.history):
        pending = render_result(entry, index, dataset, can_ask)
        if pending:
            question, previous_plan = pending
    typed = st.chat_input(
        "Ask about electricity, compare buildings, or try ‘what if’…",
        disabled=not can_ask,
        max_chars=2000,
    )
    question = typed or question
    if question:
        run_question(question, previous_plan, dataset, settings, client, allow_remote=True)


if __name__ == "__main__":
    main()
