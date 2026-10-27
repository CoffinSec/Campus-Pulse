"""Deterministic, network-free numerical operations. No generated code."""

import json

import numpy as np
import pandas as pd

from campuspulse.extended_analysis import per_student, scenario
from campuspulse.source_analysis import compare_sources, source_trend
from campuspulse.models import AnalysisPlan, CalculationResult, Caveat, Dataset
from campuspulse.validation import validate_plan


def _aggregate(series: pd.Series, operation: str) -> float:
    if operation == "sum":
        return float(series.sum(min_count=1))
    if operation == "mean":
        return float(series.mean())
    if operation == "min":
        return float(series.min())
    if operation == "max":
        return float(series.max())
    if operation == "count":
        return float(series.count())
    raise ValueError("Unsupported aggregation")


def _fmt(value: float) -> str:
    return "unavailable" if pd.isna(value) else f"{value:,.2f}"


def calculate(dataset: Dataset, plan: AnalysisPlan) -> CalculationResult:
    validate_plan(plan, dataset)
    warnings = list(dataset.warnings)
    frame = dataset.frame.copy()
    unit = "observations" if plan.aggregation == "count" else dataset.units.get(plan.metric, "")
    if plan.metric == "kwh_per_student":
        unit = "kWh/student-month"
    trace = [
        f"Metric: {plan.metric}; aggregation: {plan.aggregation}; average basis: {plan.average_basis}."
    ]
    if plan.metric == "electricity_cost_inr" and dataset.custom_tariff_inr_per_kwh is not None:
        trace.append(
            f"Estimated cost (not a utility bill): each observed kWh reading × "
            f"₹{dataset.custom_tariff_inr_per_kwh:,.2f}/kWh. "
            "Missing kWh stay missing; fixed charges, taxes and slabs excluded."
        )

    def unavailable(message: str, status: str = "unavailable") -> CalculationResult:
        return CalculationResult(
            status,
            plan,
            pd.DataFrame(),
            pd.DataFrame(),
            unit,
            message,
            trace.copy(),
            warnings.copy(),
        )

    if plan.intent in {"unavailable", "unsupported", "clarification"}:
        messages = {
            "unavailable": "The requested information is not available in this dataset.",
            "unsupported": "Consumption alone cannot establish waste, efficiency or a cause. Occupancy, building size and operating context are needed.",
            "clarification": "I need one more detail to calculate that specific result. Which building, metric or time period do you mean? For a report-wide overview, just ask for a summary.",
        }
        # Never present free-form model text as a verified factual explanation.
        return unavailable(messages[plan.intent], plan.intent)
    if "source_id" in frame:
        selected_sources = plan.sources or list(dict.fromkeys(frame.source_id.tolist()))
        frame = frame.loc[frame.source_id.isin(selected_sources)].copy()
        trace.append("Sources used: " + ", ".join(
            f"{source_id} ({frame.loc[frame.source_id.eq(source_id), 'source_label'].iloc[0]})"
            for source_id in selected_sources if frame.source_id.eq(source_id).any()))
    if plan.metric not in frame and not (plan.intent == "compare_sources" and plan.metric == "kwh_per_student"):
        message = f"The dataset does not contain {plan.metric}."
        if plan.metric == "electricity_cost_inr":
            message += " Cost requires recorded cost values or a validated tariff calculation; consumption alone is insufficient."
        return unavailable(message)
    for item in plan.filters:
        values = item.value if isinstance(item.value, list) else [item.value]
        if item.operator in {"eq", "in"} and item.column not in dataset.units:
            missing = set(values) - set(frame[item.column].unique())
            if missing:
                return unavailable(
                    f"Requested {item.column} value(s) unavailable in the selected data: {', '.join(sorted(missing))}."
                )
        if item.operator == "eq":
            frame = frame.loc[frame[item.column].eq(item.value)]
        elif item.operator == "in":
            frame = frame.loc[frame[item.column].isin(item.value)]
        elif item.operator == "gte":
            frame = frame.loc[frame[item.column].ge(item.value)]
        elif item.operator == "lte":
            frame = frame.loc[frame[item.column].le(item.value)]
        trace.append(
            f"Filter: {item.column} {item.operator} {json.dumps(item.value, ensure_ascii=False)}."
        )
    if frame.empty:
        return unavailable("No matching records were found for the requested filters.")
    if plan.intent == "period_comparison":
        missing = set(plan.periods) - set(frame["month"])
        if missing:
            return unavailable(
                f"Cannot compare: missing requested period(s) {', '.join(sorted(missing))}."
            )
        frame = frame.loc[frame["month"].isin(plan.periods)].copy()

    if plan.intent == "compare_sources":
        return compare_sources(frame, plan, warnings, trace, unit)
    if plan.intent == "trend" and plan.group_by_source and "source_id" in frame:
        return source_trend(frame, plan, warnings, trace, unit)

    # Occupancy is a monthly headcount, not an additive flow like electricity.
    # For an unqualified total or building comparison, use the latest MONTH
    # across the selected data so that the same students are not counted six
    # times. Explicit month comparisons, trends and averages keep their periods.
    occupancy_snapshot = (
        plan.metric == "occupancy"
        and plan.aggregation == "sum"
        and plan.intent in {"aggregate", "group_comparison", "ranking"}
        and plan.group_by != ["month"]
    )
    snapshot_month = None
    if occupancy_snapshot:
        snapshot_month = str(frame["month"].max())
        frame = frame.loc[frame["month"].eq(snapshot_month)].copy()
        trace.append(
            f"Occupancy is a headcount; used {snapshot_month} only. "
            "Never sum headcounts across separate months."
        )
    trace.append(
        f"Selected {len(frame)} source rows; {int(frame[plan.metric].count())} contain numeric values."
    )
    if frame[plan.metric].isna().any():
        warnings.append(
            Caveat(
                severity="warning",
                code="selected_missing",
                message="This answer uses incomplete observations. Missing values are excluded, never treated as zero.",
            )
        )
    if plan.intent == "per_student":
        if "source_id" in frame and frame.source_id.nunique() > 1:
            result = compare_sources(frame, AnalysisPlan(
                intent="compare_sources", metric="kwh_per_student", aggregation="mean",
                group_by=["building_name"], sources=plan.sources), warnings, trace, unit)
            result.plan = plan
            return result
        return per_student(frame, plan, warnings, trace)
    if plan.intent == "scenario":
        return scenario(frame, plan, warnings, trace)
    if plan.intent == "missing_values":
        value = int(frame[plan.metric].isna().sum())
        return CalculationResult(
            "ok",
            plan,
            pd.DataFrame({"label": ["Missing observations"], "value": [value]}),
            frame,
            "observations",
            f"{value} of {len(frame)} selected observations are missing {plan.metric}.",
            trace + ["Counted missing numeric cells with isna().sum()."],
            warnings,
            "metric",
        )
    if frame[plan.metric].notna().sum() == 0 and plan.aggregation != "count":
        return unavailable(
            "All matching numeric values are missing. No total or comparison can be calculated."
        )
    details = {}
    breakdown = pd.DataFrame()
    if plan.intent == "period_comparison":
        old_period, new_period = plan.periods
        groups = [frame.loc[frame.month.eq(p)] for p in plan.periods]
        old, new = [_aggregate(g[plan.metric], plan.aggregation) for g in groups]
        if pd.isna(old) or pd.isna(new):
            return unavailable(
                "One comparison period has no observed numeric values. The change is unavailable."
            )
        populations = [set(g.loc[g[plan.metric].notna(), "building_name"]) for g in groups]
        if populations[0] != populations[1]:
            warnings.append(
                Caveat(
                    severity="warning",
                    code="unequal_coverage",
                    message="These periods contain different observed buildings; this is not a like-for-like comparison.",
                )
            )
        delta = new - old
        percent = None if old == 0 else delta / old * 100
        if percent is None:
            warnings.append(
                Caveat(
                    severity="warning",
                    code="zero_denominator",
                    message="Percentage change is undefined because the old value is zero.",
                )
            )
        values = pd.DataFrame({"label": plan.periods, "value": [old, new]})
        breakdown = (
            frame.groupby(["building_name", "month"])[plan.metric]
            .apply(lambda s: _aggregate(s, plan.aggregation))
            .reset_index()
            .rename(columns={"building_name": "label", "month": "period", plan.metric: "value"})
        )
        details = {"old": old, "new": new, "absolute_change": delta, "percentage_change": percent}
        trace.extend(
            [
                f"{old_period}: {plan.aggregation} of {len(groups[0])} rows = {old!r} {unit}.",
                f"{new_period}: {plan.aggregation} of {len(groups[1])} rows = {new!r} {unit}.",
                f"Absolute change = {new!r} - {old!r} = {delta!r} {unit}.",
                f"Percentage change = (({new!r} - {old!r}) / {old!r}) × 100 = {percent!r}%."
                if percent is not None
                else "Percentage change = undefined (old value is zero).",
            ]
        )
        answer = f"{old_period}: {_fmt(old)} {unit}; {new_period}: {_fmt(new)} {unit}. Change: {delta:+,.2f} {unit}"
        answer += (
            f" ({percent:+.2f}%)." if percent is not None else "; percentage change is undefined."
        )
        chart = "bar"
    elif plan.group_by:
        group = plan.group_by[0]
        values = (
            frame.groupby(group, sort=True)[plan.metric]
            .apply(lambda s: _aggregate(s, plan.aggregation))
            .reset_index()
        )
        values.columns = ["label", "value"]
        trace.append(
            f"Grouped by {group}; applied {plan.aggregation} to observed {plan.metric} values in each group."
        )
        trace.append("All group results: " + values.to_json(orient="records", double_precision=15))
        if values.value.isna().any():
            warnings.append(
                Caveat(
                    severity="warning",
                    code="empty_group",
                    message="One or more groups have no numeric observations. They cannot be ranked and remain gaps in trends.",
                )
            )
        if plan.intent == "ranking":
            values = values.dropna(subset=["value"]).sort_values(
                ["value", "label"], ascending=[plan.sort == "ascending", True]
            )
            if values.empty:
                return unavailable("No groups contain numeric observations to rank.")
            breakdown = values.copy()
            # Include ties at the cutoff rather than arbitrarily dropping a co-winner.
            cutoff = values.iloc[min(plan.limit, len(values)) - 1]["value"]
            values = values.loc[
                values.value.le(cutoff) if plan.sort == "ascending" else values.value.ge(cutoff)
            ]
            first = values.iloc[0]
            winners = values.loc[values.value.eq(first.value), "label"].astype(str).tolist()
            word = "lowest" if plan.sort == "ascending" else "highest"
            answer = (
                f"{', '.join(winners)}: {word} occupancy as of {snapshot_month}, "
                f"{_fmt(first.value)} {unit}."
                if occupancy_snapshot
                else f"{', '.join(winners)}: {word} {plan.aggregation}, {_fmt(first.value)} {unit}."
            )
            trace.append(
                f"Sorted {plan.sort}; retained top {plan.limit}, including ties at the cutoff."
            )
            chart = "bar"
        elif plan.intent == "trend":
            values = values.sort_values("label")
            # Insert null chart gaps only, never fabricated values or evidence rows.
            timeline = pd.period_range(values.label.min(), values.label.max(), freq="M").astype(str)
            values = values.set_index("label").reindex(timeline).rename_axis("label").reset_index()
            observed = values.dropna(subset=["value"])
            first, last = observed.iloc[0], observed.iloc[-1]
            answer = f"Observed monthly {plan.aggregation}: {_fmt(first.value)} {unit} in {first.label} to {_fmt(last.value)} {unit} in {last.label}. This is descriptive, not evidence of a cause or statistical significance."
            trace.append(
                "Ordered calendar months chronologically; absent months display as null chart gaps."
            )
            chart = "line"
        else:
            values = values.sort_values("label")
            answer = (
                "; ".join(
                    f"{r.label}: unavailable" if pd.isna(r.value)
                    else f"{r.label}: {_fmt(r.value)} {unit}"
                    for r in values.itertuples()
                )
                + (f" (headcounts for {snapshot_month}; unavailable means not recorded)."
                   if occupancy_snapshot else f" ({plan.aggregation}).")
            )
            chart = "bar"
    else:
        series = frame[plan.metric]
        if plan.average_basis != "observations":
            group = "month" if plan.average_basis == "monthly_totals" else "building_name"
            series = frame.groupby(group)[plan.metric].sum(min_count=1)
            trace.append(
                f"First sum observed values per {group}: {series.to_json(double_precision=15)}."
            )
        value = _aggregate(series, plan.aggregation)
        values = pd.DataFrame({"label": [plan.average_basis], "value": [value]})
        trace.append(
            f"{plan.aggregation} of {int(series.count())} observed {plan.average_basis} = {value!r} {unit}."
        )
        if plan.aggregation == "mean":
            trace.append(
                f"Mean = {float(series.sum(min_count=1))!r} / {int(series.count())} = {value!r}."
            )
        if occupancy_snapshot:
            observed = int(frame[plan.metric].notna().sum())
            answer = (
                f"Sum of recorded building occupancies for {snapshot_month}: {_fmt(value)} {unit} "
                f"across {observed} of {len(frame)} selected buildings. "
                "This is not a complete campus headcount; a building has no value, "
                "and people may be counted in multiple buildings."
                if observed < len(frame)
                else f"Sum of building occupancies for {snapshot_month}: {_fmt(value)} {unit}. "
                     "This may count the same people in more than one building."
            )
        else:
            answer = f"{plan.aggregation.capitalize()} of {plan.average_basis.replace('_', ' ')}: {_fmt(value)} {unit}."
        chart = "metric"
    if not np.isfinite(values["value"].dropna().to_numpy(dtype=float)).all() or any(
        isinstance(v, float) and not np.isfinite(v) for v in details.values() if v is not None
    ):
        return unavailable(
            "The calculation exceeded the supported numeric range. Check unusually large source values."
        )
    return CalculationResult(
        "ok",
        plan,
        values.reset_index(drop=True),
        frame,
        unit,
        answer,
        trace,
        warnings,
        chart,
        details,
        breakdown,
    )
