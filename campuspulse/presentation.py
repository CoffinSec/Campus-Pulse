"""Human-readable calculation working, without exposing model JSON."""

from datetime import datetime

import pandas as pd

from campuspulse.models import CalculationResult

METRICS = {
    "electricity_kwh": "electricity usage",
    "kwh_per_student": "electricity per student",
    "electricity_cost_inr": "electricity cost",
    "occupancy": "student count",
    "tariff_inr_per_kwh": "electricity tariff",
}


def period_label(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m").strftime("%B %Y")
    except (TypeError, ValueError):
        return str(value)


def describe_plan(result: CalculationResult, ai: bool = True) -> str:
    plan = result.plan
    names = {
        "ranking": "ranking",
        "compare_sources": "report comparison",
        "trend": "monthly trend",
        "aggregate": "summary",
        "period_comparison": "period comparison",
        "group_comparison": "building comparison",
        "per_student": "usage per student",
        "scenario": "what-if scenario",
        "missing_values": "missing readings",
        "unavailable": "unavailable information",
        "unsupported": "unsupported conclusion",
        "clarification": "clarification needed",
    }
    pieces = [names[plan.intent], METRICS.get(plan.metric, plan.metric.replace("_", " "))]
    if plan.intent not in {"per_student", "scenario"}:
        pieces.append(
            {
                "sum": "sum",
                "mean": "average",
                "count": "count of readings",
                "min": "minimum",
                "max": "maximum",
            }[plan.aggregation]
        )
    if plan.sources:
        labels = dict(zip(result.evidence.get("source_id", []), result.evidence.get("source_label", [])))
        pieces.append("sources: " + ", ".join(f"{labels.get(s, s)} ({s})" for s in plan.sources))
    if plan.periods:
        pieces.append(" → ".join(period_label(p) for p in plan.periods))
    for item in plan.filters:
        values = item.value if isinstance(item.value, list) else [item.value]
        if item.column == "month":
            pieces.append(", ".join(period_label(v) for v in values))
        elif item.column == "building_name":
            pieces.append(", ".join(str(v) for v in values))
    if not plan.periods and not any(f.column == "month" for f in plan.filters):
        pieces.append("all available months")
    return ("Gemma understood: " if ai else "You selected: ") + " · ".join(pieces)


def source_reference(rows: pd.DataFrame) -> str:
    if rows.empty:
        return "no observed source rows"
    references = []
    for (name, page, table), group in rows.groupby(
        ["source_file", "source_page", "source_table"], dropna=False, sort=False
    ):
        numbers = sorted(group.source_row.astype(int).unique())
        shown = ", ".join(map(str, numbers[:8]))
        if len(numbers) > 8:
            shown += f" and {len(numbers) - 8} more"
        location = "" if pd.isna(page) else f", page {int(page)}, table {int(table)}"
        references.append(f"{name}{location}, {'row' if len(numbers) == 1 else 'rows'} {shown}")
    return "; ".join(references)


def _expression(series: pd.Series, aggregation: str) -> str:
    observed = series.dropna()
    if observed.empty:
        return "no observed values"
    terms = (
        " + ".join(f"{v:,.2f}" for v in observed)
        if len(observed) <= 6
        else f"sum of {len(observed)} readings"
    )
    if aggregation == "sum":
        return terms
    if aggregation == "mean":
        return f"({terms}) ÷ {len(observed)}"
    if aggregation == "count":
        return f"count of {len(observed)} non-missing readings"
    return f"{aggregation}({', '.join(f'{v:,.2f}' for v in observed[:6])}{', …' if len(observed) > 6 else ''})"


def calculation_lines(result: CalculationResult) -> list[str]:
    if result.status != "ok":
        return ["No numerical answer was calculated; no source rows are claimed."]
    frame, plan = result.evidence, result.plan
    if plan.intent == "scenario":
        return result.working + ["Source: " + source_reference(frame)]
    if plan.intent == "compare_sources":
        lines = ["Files: " + ", ".join(f"{r.source_label} ({r.source_id})"
                 for r in frame[["source_id", "source_label"]].drop_duplicates().itertuples(index=False)),
                 "Calculation: each file/group calculated independently. Change = new - old; percentage = change / old × 100 (undefined if old is zero)."]
        if result.plan.metric == "kwh_per_student":
            lines.append("Per-student = sum electricity kWh / sum occupancy (student-months over multiple months).")
        for row in result.breakdown.head(10).itertuples(index=False):
            delta = "unavailable" if pd.isna(row.change) else f"{row.change:+,.2f}"
            lines.append(f"{row.group}: {row.from_source} → {row.to_source} = {delta} {result.unit}.")
        return lines + ["Original observations: " + source_reference(frame)]
    if result.plan.group_by_source and "source_id" in result.values:
        return ["Source-specific monthly trend; each report calculated independently.",
                "Original observations: " + source_reference(frame)]
    lines = []
    if plan.metric == "electricity_cost_inr" and any(
        w.code == "estimated_electricity_cost" for w in result.warnings
    ):
        unique_rates = frame["tariff_inr_per_kwh"].dropna().unique()
        if len(unique_rates) == 1:
            lines.append(
                f"Estimated cost = observed kWh × ₹{float(unique_rates[0]):,.2f}/kWh "
                "for each source row; excludes taxes, slabs and fixed charges."
            )
    for row in result.values.head(10).itertuples():
        if pd.isna(row.value):
            lines.append(f"{period_label(row.label)}: no observation; left as a gap.")
            continue
        selected = frame
        if plan.intent == "period_comparison":
            selected = frame.loc[frame.month.eq(row.label)]
        elif plan.group_by:
            selected = frame.loc[frame[plan.group_by[0]].eq(row.label)]
        if plan.intent == "per_student":
            expression = f"{selected.electricity_kwh.sum():,.2f} kWh ÷ {selected.occupancy.sum():,.0f} {'students' if frame.month.nunique() == 1 else 'student-months'}"
        elif plan.intent == "missing_values":
            expression = f"count missing cells among {len(selected)} readings"
        else:
            series = selected[plan.metric]
            if plan.average_basis != "observations":
                group = "month" if plan.average_basis == "monthly_totals" else "building_name"
                series = selected.groupby(group)[plan.metric].sum(min_count=1)
            expression = _expression(series, plan.aggregation)
        label = (
            period_label(row.label)
            if plan.intent in {"trend", "period_comparison"}
            else str(row.label).replace("_", " ")
        )
        formula = (
            f"{row.value:,.2f}"
            if expression == f"{row.value:,.2f}"
            else f"{expression} = {row.value:,.2f}"
        )
        lines.append(f"{label} = {formula} {result.unit} ({source_reference(selected)}).")
    if len(result.values) > 10:
        lines.append(
            f"Showing working for 10 of {len(result.values)} results; all values and source rows are available below and in the export."
        )
    if plan.intent == "period_comparison":
        old, new = result.details["old"], result.details["new"]
        lines.append(f"Change = {new:,.2f} − {old:,.2f} = {new - old:+,.2f} {result.unit}.")
        pct = result.details["percentage_change"]
        lines.append(
            f"Percentage change = ({new:,.2f} − {old:,.2f}) ÷ {old:,.2f} × 100 = {pct:+.2f}%."
            if pct is not None
            else "Percentage change is undefined because the earlier value is zero."
        )
    return lines


def followup_questions(dataset, result: CalculationResult) -> list[str]:
    months = dataset.months
    previous = months[max(0, len(months) - 2)]
    questions = [f"And in {period_label(previous)}?", "Show the monthly usage trend."]
    if any("hostel" in str(v).casefold() for v in dataset.frame.building_name):
        questions.append("What about hostels only?")
    else:
        questions.append("Which building used the least electricity?")
    if result.plan.intent == "scenario":
        questions[0] = "What if the same buildings cut usage by 20% instead?"
    elif result.plan.intent == "per_student":
        questions[1] = "Which buildings cannot be compared per student?"
    return questions
