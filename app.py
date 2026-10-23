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
from campuspulse.reporting import answer_pdf
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
        "Confirm what each column means before asking questions. Separate PDF tables stay separate."
    )
    generation = st.session_state.generation
    selected = st.selectbox(
        "Detected table",
        range(len(tables)),
        format_func=lambda i: tables[i].table_id,
        key=f"table_{generation}",
    )
    if st.session_state.get("selected_table") != selected:
        st.session_state.pop("dataset", None)
        st.session_state.pop("overview", None)
        st.session_state.pop("anomalies", None)
        st.session_state.history = []
        st.session_state.selected_table = selected
    table = tables[selected]
    st.dataframe(
        table.frame.head(50)
        .drop(columns=["row_id"])
        .rename(
            columns={
                "source_file": "Report",
                "source_page": "Page",
                "source_table": "Table",
                "source_row": "Original row",
            }
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"Preview: first {min(50, len(table.frame))} of {len(table.frame)} extracted rows. Source row = CSV physical end-line or PDF table row (header included)."
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
        st.markdown("**Column mapping**")
        mapping = {}
        options = ["— Select —", *columns]
        cols = st.columns(3)
        for i, (target, label) in enumerate(
            [
                ("building_name", "Building / block"),
                ("month", "Month / date"),
                ("electricity_kwh", "Electricity consumption"),
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
                if target in {"building_name", "month", "electricity_kwh"}:
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
    with st.expander("Manual analysis · no AI (available while Gemma is disconnected)"):
        st.info(
            "Choose structured operations directly. This mode does not interpret language and does not satisfy the Gemma demonstration requirement."
        )
        with st.form("manual_analysis"):
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
            )
            buildings = sorted(dataset.frame.building_name.unique())
            selected_buildings = st.multiselect("Buildings (empty = all)", buildings)
            month = st.selectbox(
                "Month filter (ignored for period comparison)", ["All months", *dataset.months]
            )
            a, b = st.columns(2)
            old = a.selectbox("Old period", dataset.months, index=max(0, len(dataset.months) - 2))
            new = b.selectbox("New period", dataset.months, index=len(dataset.months) - 1)
            reduction = st.number_input(
                "What-if reduction (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0
            )
            st.caption(
                "For a what-if scenario, select the affected buildings above. Other buildings remain in the campus total."
            )
            run = st.form_submit_button("Run verified calculation")
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
            elif operation == "Missing values":
                args.update(intent="missing_values")
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
    st.caption(
        f"{period_label(dataset.months[0])} – {period_label(dataset.months[-1])} · {len(dataset.frame)} readings. Highest building is based on total observed usage across this period."
    )
    chart = build_chart(summary["trend"])
    if chart is not None:
        chart.update_layout(height=250, margin={"l": 10, "r": 10, "t": 40, "b": 35})
        st.plotly_chart(chart, width="stretch", key=f"overview_{st.session_state.generation}")
    for warning in dataset.warnings:
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
    st.caption(
        "Flag rule: deviation from the building’s prior median change exceeds both 20 percentage points and three scaled median absolute deviations. Flags are prompts to investigate, not proof of waste."
    )


def render_result(entry: dict, index: int, dataset, can_ask: bool):
    pending = None
    with st.chat_message("user"):
        st.text(entry["question"])
    with st.chat_message("assistant"):
        ai = entry["mode"].startswith("Gemma")
        st.caption(f"{entry['mode']} · Response time: {entry.get('elapsed', 0):.2f}s")
        if "error" in entry:
            st.error(entry["error"])
            return None
        result = entry["result"]
        st.text(describe_plan(result, ai))
        if result.status != "ok":
            st.warning(result.answer, icon="⚠️")
        else:
            st.text(result.answer)
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
            st.text(line)
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
                    st.text(check)
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
        left, right = st.columns(2)
        left.download_button(
            "Download this answer · PDF",
            entry.get("report", b""),
            "campuspulse_answer.pdf",
            "application/pdf",
            key=f"report_{st.session_state.generation}_{index}",
            disabled="report" not in entry,
        )
        right.download_button(
            "Download source data · CSV",
            export_evidence(result),
            "campuspulse_evidence.csv",
            "text/csv",
            key=f"export_{st.session_state.generation}_{index}",
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
            ):
                pending = (question, result.plan)
    return pending


def upload_panel(settings):
    with st.container(border=True):
        left, right = st.columns([2, 1])
        with left:
            st.caption(
                f"Drop a searchable PDF table or CSV here · up to {min(settings.max_upload_mb, 10)} MB"
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
                    except DataError as exc:
                        st.session_state.upload_error = str(exc)
            if st.session_state.get("upload_error"):
                st.error(st.session_state.upload_error)
        with right:
            st.markdown("**Just exploring? Start here.**")
            st.caption("Try the same fictional campus report in either format.")
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


def run_question(question, previous_plan, dataset, settings, client, allow_remote):
    started = perf_counter()
    entry = {"question": question, "mode": f"Gemma · {settings.ollama_model}"}
    with st.status("Gemma is planning…", expanded=True) as progress:
        try:
            plan = plan_question(
                question, dataset, settings, client, allow_remote, previous_plan=previous_plan
            )
            progress.update(label="Calculating…")
            st.write("Checking the requested operation and calculating from the confirmed data.")
            result = calculate(dataset, plan)
            entry["result"] = result
            if result.status == "ok":
                progress.update(label="Gemma is explaining the verified result…")
                try:
                    entry["explanation"] = explain_result(
                        result, question, settings, client, allow_remote
                    )
                except AIError as exc:
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
        page_title="CampusPulse · Understand your campus", page_icon="◉", layout="wide"
    )
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
    with st.sidebar:
        st.subheader("Gemma connection")
        st.text(settings.ollama_model)
        st.caption(settings.endpoint_kind)
        if status.ready:
            st.success("Ready for questions")
        else:
            st.warning("Gemma is not connected")
        st.caption(status.message)
        if st.button("Check model connection"):
            st.session_state.model_status = client.check()
            st.rerun()
        with st.expander("Connection help"):
            st.code(
                f"ollama serve\nollama pull {settings.ollama_model}\nollama list", language="bash"
            )
            st.caption(
                "Verify the model tag before downloading. Model configuration is in .env; restart after changes."
            )
        st.caption("Hacktoberfest Hackday 2026 · PS 03")
    st.title("CampusPulse")
    st.write("Understand your campus. See the numbers. Follow the evidence.")
    st.caption(
        "Community & Environmental Data Intelligence · Examples are synthetic, with no official IIMT University data or endorsement."
    )
    with st.expander("1. Upload your report", expanded="dataset" not in st.session_state):
        upload_panel(settings)
    if st.session_state.get("source_name") and st.button("Clear dataset and chat"):
        clear_data()
        st.session_state.upload_epoch += 1
        st.session_state.pop("processed_upload", None)
        st.session_state.pop("upload_error", None)
        st.rerun()
    if not st.session_state.get("tables"):
        st.info(
            "Start with a report above. We’ll show a quick overview before you ask your first question."
        )
        st.caption(
            "Searchable table PDFs and UTF-8 CSVs are supported. Scanned reports need OCR first. Uploads remain in this app session; on a cloud host, processing takes place on that server."
        )
        return
    with st.expander("2. Check your data", expanded="dataset" not in st.session_state):
        review_data()
    dataset = st.session_state.get("dataset")
    if dataset is None:
        return
    render_overview(dataset)
    st.divider()
    st.subheader("3. Ask CampusPulse")
    st.caption(
        "Ask in English, Hindi or Hinglish. You can follow up with “and in May?” or “what about hostels only?”"
    )
    allow_remote = False
    if settings.endpoint_kind == "Remote":
        st.warning(
            "Remote Gemma receives your question, schema, category labels, previous validated plan and computed result summaries for explanations. Full documents and raw readings are not sent."
        )
        allow_remote = st.checkbox(
            "Allow questions, context and computed summaries to be sent to the remote Ollama endpoint"
        )
    else:
        st.caption(
            "Gemma runs at an endpoint local to the app server. In cloud hosting this is not your own device. It receives schema, question context and computed summaries; raw reports stay in the app."
        )
    can_ask = status.ready and (settings.endpoint_kind != "Remote" or allow_remote)
    question = None
    previous_plan = next(
        (e["result"].plan for e in reversed(st.session_state.history) if "result" in e), None
    )
    questions = suggested_questions(dataset)
    for offset in range(0, len(questions), 3):
        for i, (column, suggestion) in enumerate(
            zip(st.columns(3), questions[offset : offset + 3])
        ):
            if column.button(
                suggestion, key=f"suggestion_{offset + i}", disabled=not can_ask, width="stretch"
            ):
                question = suggestion
                previous_plan = None
    manual_analysis(dataset)
    if st.button("Clear question history"):
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
        run_question(question, previous_plan, dataset, settings, client, allow_remote)


if __name__ == "__main__":
    main()
