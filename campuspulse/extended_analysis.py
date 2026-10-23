"""Explicit denominators and conditional scenarios, computed without a model."""

import numpy as np
import pandas as pd

from campuspulse.models import CalculationResult, Caveat


def per_student(frame, plan, warnings, trace) -> CalculationResult:
    unit = "kWh/student" if frame.month.nunique() == 1 else "kWh/student-month"
    values, working = [], []
    if "occupancy" not in frame:
        warnings.append(
            Caveat(
                severity="warning",
                code="no_occupancy",
                message="No occupancy data is available. Add student counts to compare usage per student.",
            )
        )
    else:
        for building, rows in frame.groupby("building_name", sort=True):
            reason = None
            if rows.occupancy.isna().any():
                reason = "no occupancy data for one or more selected months"
            elif rows.occupancy.le(0).any():
                reason = "zero occupancy for one or more selected months"
            elif rows.electricity_kwh.isna().any():
                reason = "missing electricity data"
            if reason:
                warnings.append(
                    Caveat(
                        severity="warning",
                        code="missing_denominator",
                        message=f"{building}: {reason}, can’t compare.",
                    )
                )
                continue
            numerator = float(rows.electricity_kwh.sum())
            denominator = float(rows.occupancy.sum())
            if not np.isfinite(numerator) or not np.isfinite(denominator):
                warnings.append(
                    Caveat(
                        severity="warning",
                        code="numeric_range",
                        message=f"{building}: totals exceed the supported numeric range, can’t compare.",
                    )
                )
                continue
            value = numerator / denominator
            if not np.isfinite(value):
                continue
            values.append({"label": building, "value": value})
            working.append(
                f"{building} = {numerator:,.2f} kWh ÷ {denominator:,.0f} {'students' if frame.month.nunique() == 1 else 'student-months'} = {value:,.2f} {unit}."
            )
    warnings.append(
        Caveat(
            severity="info",
            code="occupancy_assumption",
            message="Occupancy is interpreted as the student count for each building and month. Shared facilities may not have comparable populations.",
        )
    )
    if frame.month.nunique() > 1:
        warnings.append(
            Caveat(
                severity="warning",
                code="student_months",
                message="Across multiple months, electricity is divided by total student-months, not by a unique student headcount. Buildings may cover different months.",
            )
        )
    if not values:
        return CalculationResult(
            "unavailable",
            plan,
            pd.DataFrame(),
            pd.DataFrame(),
            unit,
            "No building has complete electricity and positive occupancy for this comparison.",
            trace,
            warnings,
        )
    values = (
        pd.DataFrame(values)
        .sort_values("value", ascending=plan.sort == "ascending")
        .reset_index(drop=True)
    )
    answer = "; ".join(f"{r.label}: {r.value:,.2f} {unit}" for r in values.itertuples()) + "."
    return CalculationResult(
        "ok",
        plan,
        values,
        frame,
        unit,
        answer,
        trace
        + ["For each eligible building, sum electricity ÷ sum positive monthly student counts."],
        warnings,
        "bar",
        working=working,
    )


def scenario(frame, plan, warnings, trace) -> CalculationResult:
    targets = frame.building_name.isin(plan.scenario_buildings)
    missing = set(plan.scenario_buildings) - set(frame.building_name)
    if missing or not frame.loc[targets, "electricity_kwh"].notna().any():
        return CalculationResult(
            "unavailable",
            plan,
            pd.DataFrame(),
            pd.DataFrame(),
            "kWh",
            "The selected scenario buildings have no matching measured usage for this period.",
            trace,
            warnings,
        )
    before = float(frame.electricity_kwh.sum(min_count=1))
    affected = float(frame.loc[targets, "electricity_kwh"].sum(min_count=1))
    saving = affected * plan.reduction_percent / 100
    after = before - saving
    percentage = None if before == 0 else saving / before * 100
    if not all(np.isfinite(v) for v in [before, affected, saving, after]):
        return CalculationResult(
            "unavailable",
            plan,
            pd.DataFrame(),
            pd.DataFrame(),
            "kWh",
            "Scenario values exceed the supported numerical range.",
            trace,
            warnings,
        )
    warnings.append(
        Caveat(
            severity="warning",
            code="hypothetical",
            message="What-if scenario, not a prediction: only the selected buildings change; other usage is held constant. Cause and feasibility are unknown.",
        )
    )
    values = pd.DataFrame({"label": ["Measured total", "What-if total"], "value": [before, after]})
    details = {
        "old": before,
        "new": after,
        "saving": saving,
        "absolute_change": -saving,
        "percentage_change": None if percentage is None else -percentage,
        "affected_usage": affected,
        "reduction_percent": plan.reduction_percent,
    }
    working = [
        f"Selected buildings = {affected:,.2f} kWh.",
        f"Saving = {affected:,.2f} × {plan.reduction_percent:g}% = {saving:,.2f} kWh.",
        f"What-if campus total = {before:,.2f} − {saving:,.2f} = {after:,.2f} kWh.",
    ]
    return CalculationResult(
        "ok",
        plan,
        values,
        frame,
        "kWh",
        f"If the selected buildings reduce usage by {plan.reduction_percent:g}%, the campus total would be {after:,.2f} kWh, saving {saving:,.2f} kWh.",
        trace + working,
        warnings,
        "bar",
        details,
        working=working,
    )
