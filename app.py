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
from campuspulse.ingestion import safe_filename
from campuspulse.multi_source import (
    SourceEntry,
    combine_sources,
    remove_source,
    replace_source,
    source_id_for,
    reviewed_building_match,
)
from campuspulse.models import AIError, AnalysisPlan, DataError, Filter, PlanError
from campuspulse.normalization import (
    ALIASES,
    SYNTHETIC,
    apply_custom_tariff,
    normalize,
    suggest_mapping,
)
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
        "base_dataset",
        "active_cost_mode",
        "active_cost_rate",
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
    # Outside the form so selecting Other reveals the rate box immediately.
    rate_choice = "Other — enter a custom ₹/kWh rate"
    cost_options = ["— Select —", rate_choice, *columns]
    suggested_cost = suggestions.get("electricity_cost_inr", "— Select —")
    cost_choice = st.selectbox(
        "Electricity cost (INR)",
        cost_options,
        index=cost_options.index(suggested_cost),
        key=f"cost_choice_{generation}_{selected}",
        help="Select an existing cost column or Other to estimate cost from kWh using one rate for the entire dataset.",
    )
    custom_rate = None
    if cost_choice == rate_choice:
        custom_rate = st.number_input(
            "Electricity rate for ALL buildings and months (₹ per kWh)",
            min_value=0.0,
            max_value=1_000_000.0,
            value=10.0,
            step=0.5,
            format="%.2f",
            key=f"initial_cost_rate_{generation}_{selected}",
        )
        st.caption(
            "Estimated INR cost = recorded kWh × this rate, for every row. "
            "This is not a real bill (fixed charges, taxes and slab rates excluded)."
        )
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
        if cost_choice not in {"— Select —", rate_choice}:
            mapping["electricity_cost_inr"] = cost_choice
        with st.expander("Optional columns and month-only dates"):
            for target in ALIASES:
                if target in {"building_name", "month", "electricity_kwh", "occupancy", "electricity_cost_inr"}:
                    continue
                # A custom flat tariff takes priority over source tariff/cost columns.
                if target == "tariff_inr_per_kwh" and cost_choice == rate_choice:
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
        if not confirmed:
            st.warning("Review the mapping and check the confirmation box first.")
        else:
            try:
                base = normalize(table, mapping, unit, classification, int(year) or None)
                source_id = st.session_state.get("current_source_id")
                if source_id:
                    item = st.session_state.pending_sources.pop(source_id)
                    st.session_state.sources = replace_source(st.session_state.sources,
                        SourceEntry(source_id, item["filename"], item["filename"], base))
                    if custom_rate is not None:
                        st.session_state.active_cost_mode = "Other — custom rate"
                        st.session_state.active_cost_rate = float(custom_rate)
                    rebuild_combined()
                else:
                    st.session_state.base_dataset = base
                    st.session_state.dataset = apply_custom_tariff(base, custom_rate)
                st.success("Source confirmed and ready to explore.")
                st.rerun()
            except DataError as exc:
                st.error(str(exc))


def rebuild_combined() -> None:
    """Rebuild from original confirmed in-memory datasets, never estimated rows."""
    entries = st.session_state.get("sources", [])
    st.session_state.history = []
    st.session_state.pop("overview", None)
    st.session_state.pop("anomalies", None)
    st.session_state.generation = st.session_state.get("generation", 0) + 1
    if not entries:
        st.session_state.pop("dataset", None)
        st.session_state.pop("base_dataset", None)
        return
    base = combine_sources(entries)
    st.session_state.base_dataset = base
    rate = (float(st.session_state.get("active_cost_rate", 10.0))
            if st.session_state.get("active_cost_mode") == "Other — custom rate" else None)
    st.session_state.dataset = apply_custom_tariff(base, rate)


def electricity_cost_settings() -> None:
    """Global tariff applies to every confirmed report, with stale context cleared."""
    if st.session_state.get("base_dataset") is None:
        return
    with st.expander("Electricity cost (INR) · change global rate"):
        mode = st.selectbox("Cost mode", ["From uploaded report", "Other — custom rate"],
                            key="active_cost_mode")
        if mode == "Other — custom rate":
            if "active_cost_rate" not in st.session_state:
                st.session_state.active_cost_rate = 10.0
            st.number_input("Global electricity rate (₹ per kWh)", min_value=0.0,
                            max_value=1_000_000.0, step=0.5, format="%.2f",
                            key="active_cost_rate")
            st.caption("One rate applies to every confirmed file; estimated cost is not a bill.")
        if st.button("Apply electricity rate to all data", type="primary"):
            try:
                rebuild_combined()
                st.rerun()
            except DataError as exc:
                st.error(str(exc))
    current = st.session_state.dataset.custom_tariff_inr_per_kwh
    if current is not None:
        st.caption(f"Active global estimate: ₹{current:,.2f}/kWh, across all selected sources.")


def _ingest_source(data: bytes, filename: str, settings: Settings, separator: str | None) -> None:
    """Parse and keep only extracted tables; uploaded bytes are not stored."""
    digest = hashlib.sha256(data).hexdigest()
    seen = st.session_state.setdefault("seen_uploads", set())
    signature = (digest, safe_filename(filename))
    if signature in seen:
        return
    taken = {e.source_id for e in st.session_state.get("sources", [])} | set(st.session_state.get("pending_sources", {}))
    source_id = source_id_for(filename, taken)
    seen.add(signature)
    try:
        tables = ingest(data, filename, settings, separator)
        sample_digests = {hashlib.sha256(file.read_bytes()).hexdigest()
            for file in (ROOT / "data").glob("campus_electricity_sample*.*")}
        status = "pending"
        error = ""
    except DataError as exc:
        tables, sample_digests, status, error = [], set(), "error", str(exc)
    st.session_state.pending_sources[source_id] = {
        "filename": safe_filename(filename), "tables": tables, "bytes": len(data),
        "digest": digest, "status": status, "error": error,
        "classification": SYNTHETIC if digest in sample_digests else "User-provided · unverified",
    }


def sources_panel(settings: Settings) -> None:
    """Per-source status, review queue, label edits and removal."""
    st.subheader("Uploaded reports")
    sources = st.session_state.get("sources", [])
    pending = st.session_state.get("pending_sources", {})
    for entry in list(sources):
        a, b, c = st.columns([3, 1, 1], vertical_alignment="center")
        with a:
            label = st.text_input(f"Label · {entry.filename}", value=entry.label,
                                  max_chars=100, key=f"source_label_{entry.source_id}")
            st.caption(f"Confirmed · {len(entry.dataset.frame)} rows · "
                       f"{entry.dataset.months[0]} to {entry.dataset.months[-1]}")
        if b.button("Rename", key=f"rename_{entry.source_id}"):
            try:
                from campuspulse.multi_source import bind_source
                bind_source(entry.dataset, entry.source_id, label)
                entry.label = label.strip()
                rebuild_combined()
                st.rerun()
            except DataError as exc:
                st.error(str(exc))
        if c.button("Remove", key=f"remove_{entry.source_id}"):
            st.session_state.sources = remove_source(sources, entry.source_id)
            # Reset uploader selection so its old widget value cannot re-add it.
            st.session_state.upload_epoch += 1
            st.session_state.seen_uploads.clear()
            rebuild_combined()
            st.rerun()
    # Never auto-normalise a similar-looking building name. Show an explicit
    # review control; retain original raw labels and provenance after changes.
    if len(sources) > 1:
        from difflib import get_close_matches

        with st.expander("Review possible building-name matches · optional"):
            canonical = sorted(set(sources[0].dataset.frame.building_name))
            st.caption("These are only suggestions. Nothing is merged until you confirm.")
            for entry in sources[1:]:
                other = sorted(set(entry.dataset.frame.building_name) - set(canonical))
                for original in other:
                    candidates = get_close_matches(original, canonical, n=3, cutoff=0.65)
                    if not candidates:
                        continue
                    st.caption(f"{entry.label}: {original} may match {', '.join(candidates)}")
                    target = st.selectbox(
                        f"Canonical label for {original} ({entry.label})",
                        ["Keep separate", *candidates],
                        key=f"alias_{entry.source_id}_{original}",
                    )
                    agreed = st.checkbox(
                        f"I checked that {original} is the same building as {target}",
                        key=f"alias_confirm_{entry.source_id}_{original}",
                    )
                    if st.button("Apply reviewed match", key=f"alias_apply_{entry.source_id}_{original}"):
                        if target == "Keep separate" or not agreed:
                            st.error("Choose a label and explicitly confirm the match first.")
                        else:
                            try:
                                matched = reviewed_building_match(entry, original, target)
                                st.session_state.sources = replace_source(sources, matched)
                                rebuild_combined()
                                st.rerun()
                            except DataError as exc:
                                st.error(str(exc))
    for source_id, item in list(pending.items()):
        a, b = st.columns([4, 1], vertical_alignment="center")
        a.caption(f"{item['filename']} · {item['status']} · {item['bytes'] / 1024:.1f} KB"
                  + (f" · {item['error']}" if item['error'] else ""))
        if b.button("Remove", key=f"pending_remove_{source_id}"):
            del pending[source_id]
            st.session_state.upload_epoch += 1
            st.session_state.seen_uploads.clear()
            st.session_state.history = []
            st.rerun()
    if pending:
        active = st.selectbox("Choose a file to review and confirm", list(pending),
            format_func=lambda sid: pending[sid]["filename"], key="active_review")
        item = pending[active]
        if item['status'] == 'pending':
            if st.session_state.get('selected_review_id') != active:
                st.session_state.selected_review_id = active
                st.session_state.selected_table = None
                st.session_state.generation += 1
            st.session_state.tables = item['tables']
            st.session_state.classification = item['classification']
            st.session_state.source_name = item['filename']
            st.session_state.source_size = item['bytes']
            st.session_state.current_source_id = active
            with st.expander(f"Confirm {item['filename']}", expanded=True):
                review_data()
    elif not sources:
        st.info("Upload a file or load synthetic samples to begin.")



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
                "Trend per report",
                "Period comparison",
                "Group comparison",
                "Compare reports",
                "Total",
                "Mean of observations",
                "Mean of monthly totals",
                "Mean per building",
                "Missing values",
                "Electricity cost (INR)",
                "Usage per student",
                "What-if reduction",
            ],
            key=f"manual_operation_{st.session_state.generation}",
        )
        with st.form("manual_analysis"):
            cost_available = "electricity_cost_inr" in dataset.frame
            metric_option = st.selectbox(
                "Calculate using",
                ["Electricity usage (kWh)"]
                + (["Electricity cost (INR)"] if cost_available else []),
                help="Cost uses the rate you selected for the entire confirmed dataset.",
            )
            source_options = [e.source_id for e in st.session_state.get("sources", [])]
            source_labels = {e.source_id: e.label for e in st.session_state.get("sources", [])}
            picked_sources = st.multiselect("Sources", source_options, default=source_options,
                format_func=lambda sid: source_labels.get(sid, sid))
            buildings = sorted(dataset.frame.building_name.unique())
            selected_buildings = st.multiselect("Buildings (empty = all)", buildings)
            month, old, new, reduction = "All months", None, None, 10.0
            if operation == "Period comparison":
                a, b = st.columns(2)
                old = a.selectbox(
                    "Old period", dataset.months, index=max(0, len(dataset.months) - 2)
                )
                new = b.selectbox("New period", dataset.months, index=len(dataset.months) - 1)
            elif operation not in {"Monthly trend", "Trend per report"}:
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
            if not picked_sources:
                st.error("Select at least one source before running a calculation.")
                return
            started = perf_counter()
            filters = []
            if selected_buildings and operation != "What-if reduction":
                filters.append(
                    Filter(column="building_name", operator="in", value=selected_buildings)
                )
            if month != "All months" and operation != "Period comparison":
                filters.append(Filter(column="month", operator="eq", value=month))
            selected_metric = (
                "electricity_cost_inr" if metric_option == "Electricity cost (INR)"
                else "electricity_kwh"
            )
            args = {"metric": selected_metric, "aggregation": "sum", "filters": filters, "sources": picked_sources}
            if operation in {"Highest building", "Lowest building"}:
                args.update(
                    intent="ranking",
                    group_by=["building_name"],
                    limit=1,
                    sort="ascending" if operation == "Lowest building" else "descending",
                )
            elif operation in {"Monthly trend", "Trend per report"}:
                args.update(intent="trend", group_by=["month"],
                            group_by_source=(operation == "Trend per report"))
            elif operation == "Period comparison":
                args.update(intent="period_comparison", periods=[old, new])
            elif operation == "Group comparison":
                args.update(intent="group_comparison", group_by=["building_name"])
            elif operation == "Compare reports":
                args.update(intent="compare_sources", group_by=["building_name"])
            elif operation == "Usage per student":
                args.update(intent="per_student", metric="electricity_kwh", aggregation="mean", group_by=["building_name"])
            elif operation == "What-if reduction":
                args.update(
                    intent="scenario", metric="electricity_kwh",
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
                if operation == "Electricity cost (INR)":
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
    if dataset.custom_tariff_inr_per_kwh is not None:
        estimated_cost = dataset.frame["electricity_cost_inr"].sum(min_count=1)
        if pd.notna(estimated_cost):
            st.metric("Estimated electricity cost (INR)", f"₹{estimated_cost:,.2f}")
        st.caption(
            f"Based on a custom flat rate of ₹{dataset.custom_tariff_inr_per_kwh:,.2f}/kWh "
            "for every building and month; excludes slabs, fixed charges and taxes."
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
                        "electricity_cost_inr": (
                            "Estimated cost (INR)" if dataset.custom_tariff_inr_per_kwh is not None
                            else "Electricity cost (INR)"
                        ),
                        "tariff_inr_per_kwh": "Rate (INR/kWh)",
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
        st.subheader("Add campus reports")
        st.caption(f"Up to {settings.max_files} PDF/CSV files, {settings.max_upload_mb} MB per file; "
                   f"up to {settings.max_pdf_pages} pages per PDF. Confirm each file individually.")
        uploaded_files = st.file_uploader("Choose reports", type=["pdf", "csv"],
            accept_multiple_files=True, key=f"multi_upload_{st.session_state.upload_epoch}")
        separator_label = st.selectbox("CSV separator", ["Auto", "Comma", "Semicolon", "Tab", "Pipe"])
        separator = {"Auto": None, "Comma": ",", "Semicolon": ";", "Tab": "\t", "Pipe": "|"}[separator_label]
        for uploaded in uploaded_files or []:
            total = len(st.session_state.get("sources", [])) + len(st.session_state.pending_sources)
            if total >= settings.max_files:
                st.warning(f"Maximum {settings.max_files} reports per session. Remove one to add another.")
                break
            _ingest_source(uploaded.getvalue(), uploaded.name, settings, separator)
        if st.button("Load two synthetic samples", width="stretch"):
            paths = [ROOT / "data" / f"campus_electricity_sample{suffix}.csv"
                     for suffix in ("", "_overlap")]
            if all(p.exists() for p in paths):
                for path in paths:
                    _ingest_source(path.read_bytes(), path.name, settings, None)
                st.rerun()
            else:
                st.warning("The example generator has not produced the second sample yet.")
        sources_panel(settings)


def run_question(question, previous_plan, dataset, settings, client, allow_remote=True):
    started = perf_counter()
    entry = {"question": question, "mode": f"Gemma · {settings.model_name}"}
    # General greetings and whole-report summaries are not calculation plans;
    # answer them immediately instead of asking Gemma to invent one.
    chosen = st.session_state.get("selected_sources", [])
    if "source_id" in dataset.frame and chosen:
        scoped = dataset.frame.loc[dataset.frame.source_id.isin(chosen)].copy()
        dataset = type(dataset)(scoped, dataset.columns, dataset.classification,
                                dataset.warnings, dataset.custom_tariff_inr_per_kwh)
    reply = quick_reply(question, dataset) if "source_id" not in dataset.frame or dataset.frame.source_id.nunique() == 1 else None
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
                question, dataset, settings, client, allow_remote=allow_remote,
                previous_plan=previous_plan, selected_sources=chosen
            )
            if plan.intent == "report_overview":
                # Gemma handles open-ended paraphrases, but verified Python
                # derives every number and caveat from the uploaded dataset.
                entry.update(
                    message=report_summary(dataset, question),
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
            if not plan.sources and chosen:
                plan = plan.model_copy(update={"sources": chosen})
            result = calculate(dataset, plan)
            entry["result"] = result
            if result.status == "ok":
                progress.update(label="Gemma is explaining the verified result…")
                try:
                    entry["explanation"] = explain_result(
                        result, question, settings, client, allow_remote=True
                    )
                except Exception as exc:  # noqa: BLE001 - fall back if remote explanation fails
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
    st.session_state.setdefault("sources", [])
    st.session_state.setdefault("pending_sources", {})
    st.session_state.setdefault("seen_uploads", set())
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
            "Gemma configured" if status.ready else "Gemma offline",
            color="green" if status.ready else "orange",
        )
        with st.popover("Connection settings", width="stretch"):
            st.caption(status.message)
            st.text(f"Model: {settings.model_name}")
            st.caption(f"Endpoint: {settings.endpoint_label}")
            with st.expander("Gemma Engine Info"):
                st.code(
                    f"PROVIDER={settings.provider}\nMODEL={settings.gemini_model if settings.provider == 'gemini' else settings.ollama_model}",
                    language="bash",
                )
                st.caption("Hosted inference is not an offline or local model.")
            if st.button("Refresh connection"):
                st.session_state.model_status = client.check()
                st.rerun()
    stage = 2 if st.session_state.get("dataset") is not None else 1 if st.session_state.get("pending_sources") else 0
    progress_steps(stage)
    upload_panel(settings)
    dataset = st.session_state.get("dataset")
    if dataset is None:
        st.caption("PDFs must have selectable text; scanned PDFs require OCR first. "
                   "Uploaded bytes are not stored. Every source stays in this session.")
        return
    electricity_cost_settings()
    render_overview(dataset)
    st.divider()
    st.subheader("What would you like to know?")
    st.caption(
        "Ask in English, Hindi or Hinglish. You can follow up with “and in May?” or “what about hostels only?”"
    )
    options = [e.source_id for e in st.session_state.get("sources", [])]
    labels = {e.source_id: e.label for e in st.session_state.get("sources", [])}
    selected_sources = st.multiselect("Sources to use (leave all selected to analyze all reports)",
        options, default=options, format_func=lambda sid: labels.get(sid, sid),
        key=f"scope_{st.session_state.generation}")
    st.session_state.selected_sources = selected_sources
    if not selected_sources:
        st.warning("Select at least one source for analysis.")
    if settings.endpoint_kind == "Remote":
        st.checkbox("I agree to send my question, data schema/labels and verified summaries to the hosted model (not raw rows/files).",
                    key="remote_consent")
    can_ask = status.ready and bool(selected_sources)
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
        if settings.endpoint_kind == "Remote" and not st.session_state.get("remote_consent", False):
            st.warning("Please confirm hosted/remote Gemma processing before sending this question.")
        else:
            run_question(question, previous_plan, dataset, settings, client,
                         allow_remote=settings.endpoint_kind != "Remote" or st.session_state.remote_consent)


if __name__ == "__main__":
    main()
