"""Constrained, source-aware arithmetic; no inference or generated code."""

import numpy as np
import pandas as pd

from campuspulse.models import CalculationResult, Caveat


def _value(rows: pd.DataFrame, metric: str, aggregation: str) -> float:
    if metric == "kwh_per_student":
        if "occupancy" not in rows or rows.empty or rows[["electricity_kwh", "occupancy"]].isna().any().any() or (rows.occupancy <= 0).any():
            return float("nan")
        denominator = float(rows.occupancy.sum())
        return float(rows.electricity_kwh.sum()) / denominator if denominator else float("nan")
    values = rows[metric].dropna()
    if values.empty:
        return 0.0 if aggregation == "count" else float("nan")
    return float(getattr(values, aggregation)())


def compare_sources(frame, plan, warnings, trace, unit):
    ids = list(dict.fromkeys(frame.source_id.tolist()))
    if len(ids) < 2:
        return CalculationResult("unavailable", plan, pd.DataFrame(), frame.iloc[0:0], unit,
                                 "Compare reports needs at least two confirmed sources in the selection.",
                                 trace, warnings + [Caveat(severity="warning", code="need_two_sources",
                                 message="Select at least two confirmed reports for a cross-source comparison.")])
    metric = plan.metric
    if metric == "kwh_per_student":
        unit = "kWh/student-month" if frame.month.nunique() > 1 else "kWh/student"
    if plan.group_by:
        if len(plan.group_by) == 2:
            group = plan.group_by
            groups = list(frame.groupby(group, sort=True).groups)
        else:
            group = plan.group_by[0]
            groups = sorted(frame[group].dropna().unique())
    else:
        group, groups = None, ["All selected readings"]
    labels = frame.groupby("source_id", sort=False).source_label.first().to_dict()
    records = []
    changes = []
    for group_label in groups:
        if group is None:
            subset = frame
        elif isinstance(group, list):
            subset = frame.loc[(frame[group[0]].eq(group_label[0])) & (frame[group[1]].eq(group_label[1]))]
        else:
            subset = frame.loc[frame[group].eq(group_label)]
        entries = []
        for sid in ids:
            matching = subset.loc[subset.source_id.eq(sid)]
            number = _value(matching, metric, plan.aggregation)
            entries.append(number)
            records.append({"label": str(group_label), "value": number, "source_id": sid,
                            "source_label": labels[sid]})
        old = entries[0]
        for i in range(1, len(entries)):
            new = entries[i]
            delta = new - old if pd.notna(new) and pd.notna(old) else float("nan")
            percent = delta / old * 100 if pd.notna(delta) and old != 0 else float("nan")
            changes.append({"group": str(group_label), "from_source": labels[ids[0]],
                            "to_source": labels[ids[i]], "old": old, "new": new,
                            "change": delta, "percent": percent})
            if pd.notna(delta) and old == 0:
                warnings.append(Caveat(severity="warning", code="zero_denominator",
                    message=f"{group_label}: percentage change unavailable because {labels[ids[0]]} is zero."))
    values = pd.DataFrame(records)
    breakdown = pd.DataFrame(changes)
    trace.append("Compared each source independently; no cross-file row deduplication or implicit merge.")
    trace.append(f"Formula: {plan.aggregation}({metric}) per source/group; difference = new − reference; percent = difference ÷ reference × 100, undefined at zero reference.")
    if metric == "kwh_per_student":
        trace.append("Per-student formula: sum kWh / sum monthly occupancy; missing or non-positive denominators return unavailable.")
    if any(pd.isna(r['value']) for r in records):
        warnings.append(Caveat(severity="warning", code="partial_comparison",
            message="One or more source/group values are missing; missing comparisons remain unavailable."))
    overlap = set.intersection(*(set(frame.loc[frame.source_id.eq(s), 'month']) for s in ids))
    if not overlap:
        warnings.append(Caveat(severity="warning", code="not_same_period",
            message="Sources do not overlap in calendar months; differences reflect different reporting periods, not like-for-like change."))
    text = []
    for row in breakdown.to_dict('records')[:12]:
        delta = "unavailable" if pd.isna(row['change']) else f"{row['change']:+,.2f} {unit}"
        pc = "undefined" if pd.isna(row['percent']) else f"{row['percent']:+.2f}%"
        text.append(f"{row['group']}: {row['from_source']} → {row['to_source']}, change {delta} ({pc})")
    if group and any(pd.notna(row["change"]) for row in changes):
        peak = max(row["change"] for row in changes if pd.notna(row["change"]))
        winners = sorted(set(row["group"] for row in changes if pd.notna(row["change"]) and np.isclose(row["change"], peak)))
        trace.append("Largest observed absolute increase: " + ", ".join(winners) + f" ({peak:+,.2f} {unit}); ties retained.")
        text.insert(0, "Largest observed absolute increase: " + ", ".join(winners) + f" ({peak:+,.2f} {unit}).")
    if not text:
        text = ["Comparison not available for these sources."]
    return CalculationResult("ok", plan, values, frame, unit,
        "; ".join(text) + ".", trace, warnings, "bar", breakdown=breakdown)


def source_trend(frame, plan, warnings, trace, unit):
    """Separate source-specific monthly series with explicit NaN gaps."""
    observed = (
        frame.groupby(["source_id", "source_label", "month"], sort=True)[plan.metric]
        .agg(lambda x: x.sum(min_count=1) if plan.aggregation == "sum" else getattr(x, plan.aggregation)())
        .reset_index()
        .rename(columns={"month": "label", plan.metric: "value"})
    )
    parts = []
    for (_, _), sub in observed.groupby(["source_id", "source_label"], sort=False):
        timeline = pd.period_range(sub.label.min(), sub.label.max(), freq="M").astype(str)
        expanded = sub.set_index("label").reindex(timeline).rename_axis("label").reset_index()
        expanded["source_id"] = sub.source_id.iloc[0]
        expanded["source_label"] = sub.source_label.iloc[0]
        parts.append(expanded)
    values = pd.concat(parts, ignore_index=True)
    trace.append("Each source has its own monthly series; missing months are NaN gaps and never counted as zero.")
    return CalculationResult(
        "ok", plan, values, frame, unit,
        "Separate monthly trends by source: " + "; ".join(
            f"{name}: {len(rows)} observed months"
            for name, rows in observed.groupby("source_label")
        ) + ".",
        trace, warnings, "line",
    )
