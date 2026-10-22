"""CampusPulse's session-scoped Streamlit dashboard."""

import hashlib
import logging
from pathlib import Path

import streamlit as st

from campuspulse.analysis_engine import calculate
from campuspulse.config import Settings
from campuspulse.csv_parser import PROVENANCE
from campuspulse.evidence import evidence_table, export_evidence
from campuspulse.gemma_client import GemmaClient
from campuspulse.ingestion import ingest
from campuspulse.models import AIError, AnalysisPlan, DataError, Filter, PlanError
from campuspulse.normalization import ALIASES, SYNTHETIC, normalize, suggest_mapping
from campuspulse.question_planner import plan_question, suggested_questions
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
        st.session_state.history = []
        st.session_state.selected_table = selected
    table = tables[selected]
    st.dataframe(table.frame.head(50), hide_index=True, width="stretch")
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
                "Optional units: cost = INR, tariff = INR/kWh, occupancy = people. Only map columns with these meanings and units."
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
        st.session_state.history = []
        if not confirmed:
            st.warning("Review the mapping and check the confirmation box first.")
        else:
            try:
                st.session_state.dataset = normalize(
                    table, mapping, unit, classification, int(year) or None
                )
                st.success("Dataset validated and confirmed. You can now analyze it.")
            except DataError as exc:
                st.error(str(exc))


def render_result(entry: dict, index: int) -> None:
    with st.chat_message("user"):
        st.text(entry["question"])
    with st.chat_message("assistant"):
        st.caption(entry["mode"])
        if "error" in entry:
            st.error(entry["error"])
            return
        result = entry["result"]
        if result.status != "ok":
            st.warning(result.answer)
        else:
            st.text(result.answer)
            if result.chart_type == "metric":
                st.metric(
                    result.plan.metric.replace("_", " ").title(),
                    f"{result.values.iloc[0]['value']:,.2f} {result.unit}",
                )
            try:
                figure = build_chart(result)
                if figure is not None:
                    st.plotly_chart(
                        figure, width="stretch", key=f"chart_{st.session_state.generation}_{index}"
                    )
            except (ValueError, TypeError):
                logger.warning("Chart rendering failed")
                st.warning(
                    "The chart could not be rendered. Verified values remain available below."
                )
            st.dataframe(result.values, hide_index=True, width="stretch")
        with st.expander("View calculation"):
            st.caption(
                "This trace comes from the executed Python operations. Values are rounded only for display."
            )
            for line in result.trace:
                st.text(line)
            if not result.evidence.empty:
                st.caption("Selected input rows, including missing cells and comparison candidates")
                st.dataframe(result.evidence, hide_index=True, width="stretch")
            st.json(result.plan.model_dump())
        with st.expander(f"View source data · {len(result.evidence)} selected rows"):
            if result.evidence.empty:
                st.info("No numerical answer was produced, so no source citation is asserted.")
            else:
                st.dataframe(evidence_table(result), hide_index=True, width="stretch")
                st.download_button(
                    "Export source evidence CSV",
                    export_evidence(result),
                    "campuspulse_evidence.csv",
                    "text/csv",
                    key=f"export_{st.session_state.generation}_{index}",
                )
                st.caption(
                    "Ranking evidence includes all candidates used to establish the ranking. CSV row numbers are physical end-lines; PDF row numbers are positions inside the detected table."
                )
        with st.expander(f"Assumptions and caveats · {len(result.warnings)}"):
            for warning in result.warnings:
                getattr(st, "warning" if warning.severity == "warning" else "info")(warning.message)


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
            run = st.form_submit_button("Run verified calculation")
        if run:
            filters = []
            if selected_buildings:
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
                    }
                )
                st.session_state.history = st.session_state.history[-6:]
                st.rerun()
            except (ValueError, PlanError) as exc:
                st.error(
                    "Choose two distinct periods."
                    if old == new and operation == "Period comparison"
                    else str(exc)
                )


def main() -> None:
    st.set_page_config(
        page_title="CampusPulse · Evidence-first intelligence", page_icon="◉", layout="wide"
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
    st.title("CampusPulse")
    st.markdown("Community & Environmental Data Intelligence")
    st.caption("UPLOAD A REPORT  →  ASK A QUESTION  →  VERIFY THE ANSWER")
    with st.sidebar:
        st.subheader("Your report")
        st.caption(
            f"Start with a table-based PDF. CSV is also supported. Up to {min(settings.max_upload_mb, 10)} MB in this dashboard."
        )
        uploaded = st.file_uploader(
            "Upload a PDF report or CSV",
            type=["pdf", "csv"],
            key=f"upload_{st.session_state.upload_epoch}",
        )
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
                try:
                    load_data(data, uploaded.name, settings, separator)
                except DataError as exc:
                    st.error(str(exc))
        for suffix, label in [("pdf", "Load synthetic PDF"), ("csv", "Load synthetic CSV")]:
            if st.button(label, width="stretch"):
                sample = ROOT / "data" / f"campus_electricity_sample.{suffix}"
                try:
                    load_data(sample.read_bytes(), sample.name, settings, None)
                    st.session_state.upload_epoch += 1
                    st.session_state.pop("processed_upload", None)
                    st.rerun()
                except (DataError, OSError) as exc:
                    st.error(str(exc))
        with st.expander("Download sample reports"):
            for suffix in ["pdf", "csv"]:
                sample = ROOT / "data" / f"campus_electricity_sample.{suffix}"
                if sample.exists():
                    st.download_button(
                        f"Download sample {suffix.upper()}", sample.read_bytes(), sample.name
                    )
        if st.session_state.get("source_name"):
            st.text(st.session_state.source_name)
            st.caption(
                f"{st.session_state.source_size / 1024:.1f} KB · {len(st.session_state.tables)} detected table(s)"
            )
        if st.button("Clear dataset and chat", width="stretch"):
            clear_data()
            st.session_state.upload_epoch += 1
            st.session_state.pop("processed_upload", None)
            st.rerun()
        st.divider()
        st.subheader("Gemma 4")
        st.text(settings.ollama_model)
        st.caption(settings.endpoint_kind)
        if status.ready:
            st.success("Model available")
        else:
            st.warning("Disconnected / model unavailable")
        st.caption(status.message)
        if st.button("Check model connection"):
            st.session_state.model_status = client.check()
            st.rerun()
        with st.expander("Connection help"):
            st.code(
                f"ollama serve\nollama pull {settings.ollama_model}\nollama list", language="bash"
            )
            st.caption(
                "Install Ollama from its official site first. Pull downloads a model and is never run automatically. OLLAMA_HOST and OLLAMA_MODEL are configured in .env; restart the app after changes."
            )
        st.caption("Hacktoberfest Hackday 2026 · Track 1 · PS 03")
    st.info(
        "Synthetic examples use fictional campus buildings. No official IIMT University data or endorsement is claimed."
    )
    if not st.session_state.get("tables"):
        st.subheader("Turn a campus report into a verifiable answer")
        for column, title, body in zip(
            st.columns(3),
            ["01 · Bring a report", "02 · Confirm the data", "03 · Follow the evidence"],
            [
                "Upload a searchable PDF table or UTF-8 CSV.",
                "Review rows, map columns and confirm kWh units.",
                "Ask Gemma; inspect Python calculations, charts and original rows.",
            ],
        ):
            with column.container(border=True):
                st.markdown(f"**{title}**")
                st.write(body)
        st.caption(
            "PDF extraction does not support OCR. Uploaded bytes and results are kept in session memory, not written to disk. On a cloud host, processing takes place on that server."
        )
        return
    with st.expander("1. Review your extracted data", expanded="dataset" not in st.session_state):
        review_data()
    dataset = st.session_state.get("dataset")
    if dataset is None:
        return
    st.divider()
    for col, label, value in zip(
        st.columns(4),
        ["Observations", "Buildings", "Months", "Missing kWh"],
        [
            len(dataset.frame),
            dataset.frame.building_name.nunique(),
            len(dataset.months),
            int(dataset.frame.electricity_kwh.isna().sum()),
        ],
    ):
        col.metric(label, value)
    st.caption(f"{dataset.classification} · {dataset.months[0]} to {dataset.months[-1]} · kWh")
    for caveat in dataset.warnings:
        if caveat.severity == "warning":
            st.warning(caveat.message)
    st.subheader("2. Ask CampusPulse")
    st.caption(
        "Gemma interprets. Python calculates. Every answer keeps its calculation and source references."
    )
    allow_remote = False
    if settings.endpoint_kind == "Remote":
        st.warning(
            "Remote inference sends your question, schema, periods and up to 100 category labels per field to the configured server. Full document text and numeric rows are not sent."
        )
        allow_remote = st.checkbox(
            "Allow this session's question and schema to be sent to the remote Ollama endpoint"
        )
    else:
        st.caption(
            "Inference endpoint is local to the app server. In cloud hosting, this does not mean your own device. Only the question, schema, periods and category labels reach Ollama."
        )
    can_ask = status.ready and (settings.endpoint_kind != "Remote" or allow_remote)
    question = None
    with st.expander("Suggested questions · English / Hindi / Hinglish"):
        for index, suggestion in enumerate(suggested_questions(dataset)):
            if st.button(suggestion, key=f"suggestion_{index}", disabled=not can_ask):
                question = suggestion
        st.caption(
            "Try: Sabse zyada electricity kis building ne use ki? · बिजली की खपत का मासिक रुझान दिखाओ। Follow-up questions must repeat their building/period; hidden conversation context is not assumed."
        )
    manual_analysis(dataset)
    if st.button("Clear question history"):
        st.session_state.history = []
    for index, entry in enumerate(st.session_state.history):
        render_result(entry, index)
    typed = st.chat_input(
        "Ask about this dataset in English, Hindi or Hinglish…",
        disabled=not can_ask,
        max_chars=2000,
    )
    question = typed or question
    if question:
        entry = {
            "question": question,
            "mode": f"Gemma planning · {settings.ollama_model} · Python calculation",
        }
        with st.spinner("Gemma is planning; Python will verify the calculation…"):
            try:
                plan = plan_question(question, dataset, settings, client, allow_remote)
                entry["result"] = calculate(dataset, plan)
            except (AIError, PlanError, ValueError) as exc:
                entry["error"] = str(exc)
        st.session_state.history.append(entry)
        st.session_state.history = st.session_state.history[-6:]
        st.rerun()


if __name__ == "__main__":
    main()
