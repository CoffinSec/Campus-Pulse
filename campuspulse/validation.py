"""Semantic validation after Pydantic rejects malformed plans."""

import re

from campuspulse.models import AnalysisPlan, Dataset, PlanError
from campuspulse.normalization import NUMERIC_UNITS, parse_month


def validate_plan(plan: AnalysisPlan, dataset: Dataset) -> None:
    columns = {c.name: c for c in dataset.columns}
    if plan.metric not in NUMERIC_UNITS:
        raise PlanError("Unknown metric. Select an available numeric column.")
    if plan.intent == "scenario":
        if len(set(plan.scenario_buildings)) != len(plan.scenario_buildings):
            raise PlanError("Select each scenario building once.")
        if set(plan.scenario_buildings) - set(dataset.frame.building_name):
            raise PlanError("A scenario references a building absent from the dataset.")
    for group in plan.group_by:
        if group not in columns or columns[group].dtype == "number":
            raise PlanError("Grouping requires an available category or month column.")
    for period in plan.periods:
        if not re.fullmatch(r"\d{4}-\d{2}", period):
            raise PlanError("Comparison periods must use YYYY-MM.")
        try:
            parse_month(period)
        except ValueError as exc:
            raise PlanError("Invalid calendar month in comparison.") from exc
    for item in plan.filters:
        if item.column not in columns:
            raise PlanError("A filter references a column that is not available.")
        col = columns[item.column]
        values = item.value if isinstance(item.value, list) else [item.value]
        if col.dtype == "number":
            if item.operator == "in" or any(type(v) not in {float, int} for v in values):
                raise PlanError("Numeric filters need a finite numeric value and eq, gte or lte.")
        else:
            if any(not isinstance(v, str) or len(v) > 500 for v in values):
                raise PlanError("Category and date filters require text values.")
            if col.dtype == "category" and item.operator not in {"eq", "in"}:
                raise PlanError("Category filters support only eq or in.")
            if col.dtype == "month":
                for v in values:
                    if not re.fullmatch(r"\d{4}-\d{2}", v):
                        raise PlanError("Month filters must use explicit YYYY-MM values.")
                    try:
                        parse_month(v)
                    except ValueError as exc:
                        raise PlanError("Invalid calendar month in filter.") from exc
    if plan.intent == "period_comparison" and any(f.column == "month" for f in plan.filters):
        raise PlanError("Use comparison periods instead of an additional month filter.")
    if plan.metric == "tariff_inr_per_kwh" and plan.aggregation == "sum":
        raise PlanError(
            "Tariffs are rates; summing them is not meaningful. Use an explicitly defined mean, min or max."
        )
