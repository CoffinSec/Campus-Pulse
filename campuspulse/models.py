"""Typed boundaries between ingestion, model planning and computation."""

from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataError(ValueError):
    """Actionable ingestion or validation error safe for display."""


class PlanError(ValueError):
    """A requested operation cannot be applied safely."""


class AIError(RuntimeError):
    """A model connection or response failed."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Caveat(StrictModel):
    severity: Literal["info", "warning", "error"]
    code: str
    message: str


class ColumnDefinition(StrictModel):
    name: str
    dtype: Literal["category", "month", "number"]
    unit: str | None = None


class Filter(StrictModel):
    column: str = Field(min_length=1, max_length=80)
    operator: Literal["eq", "in", "gte", "lte"]
    value: str | float | int | list[str] = Field(union_mode="left_to_right")

    @model_validator(mode="after")
    def value_shape(self) -> "Filter":
        if self.operator == "in":
            if not isinstance(self.value, list) or not 1 <= len(self.value) <= 100:
                raise ValueError("An in filter needs 1–100 category values.")
        elif isinstance(self.value, list):
            raise ValueError("Only in filters accept a list.")
        return self


class AnalysisPlan(StrictModel):
    intent: Literal[
        "ranking",
        "report_overview",
        "trend",
        "period_comparison",
        "group_comparison",
        "aggregate",
        "missing_values",
        "unavailable",
        "unsupported",
        "clarification",
        "per_student",
        "scenario",
    ]
    metric: str = Field(min_length=1, max_length=80)
    aggregation: Literal["sum", "mean", "min", "max", "count"]
    group_by: list[str] = Field(default_factory=list, max_length=1)
    filters: list[Filter] = Field(default_factory=list, max_length=8)
    periods: list[str] = Field(default_factory=list, max_length=2)
    average_basis: Literal["observations", "monthly_totals", "building_totals"] = "observations"
    sort: Literal["ascending", "descending"] = "descending"
    limit: int = Field(default=10, ge=1, le=100)
    chart_type: Literal["bar", "line", "metric", "none"] = "bar"
    reason: str = Field(default="", max_length=500)
    reduction_percent: float | None = Field(default=None, ge=0, le=100)
    scenario_buildings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def coherent(self) -> "AnalysisPlan":
        if self.intent == "report_overview" and (
            self.metric != "electricity_kwh"
            or self.aggregation != "sum"
            or self.filters
            or self.group_by
            or self.periods
            or self.reduction_percent is not None
            or self.scenario_buildings
        ):
            raise ValueError("A report overview must use the complete electricity dataset.")
        if self.intent == "scenario":
            if self.reduction_percent is None or not self.scenario_buildings:
                raise ValueError("A scenario needs a reduction percentage and selected buildings.")
            if self.metric != "electricity_kwh" or self.aggregation != "sum" or self.group_by:
                raise ValueError("Scenarios compare total electricity usage.")
            if any(f.column == "building_name" for f in self.filters):
                raise ValueError(
                    "Select scenario buildings separately so the campus total retains other buildings."
                )
        elif self.reduction_percent is not None or self.scenario_buildings:
            raise ValueError("Only scenarios accept a reduction or scenario buildings.")
        if self.intent == "per_student" and (
            self.metric != "electricity_kwh"
            or self.aggregation != "mean"
            or self.group_by != ["building_name"]
        ):
            raise ValueError(
                "Per-student usage requires electricity, mean and grouping by building."
            )
        if self.intent == "period_comparison" and (len(set(self.periods)) != 2):
            raise ValueError("Period comparison needs two distinct months, old then new.")
        if self.intent != "period_comparison" and self.periods:
            raise ValueError("Only a period comparison accepts periods.")
        if self.intent in {"ranking", "group_comparison"} and not self.group_by:
            raise ValueError("Select a grouping column.")
        if self.intent == "trend" and self.group_by != ["month"]:
            raise ValueError("Trends must group by month.")
        if self.intent in {"aggregate", "period_comparison", "missing_values"} and self.group_by:
            raise ValueError("This operation does not accept group_by.")
        if self.average_basis != "observations" and (
            self.intent != "aggregate" or self.aggregation != "mean"
        ):
            raise ValueError("Grouped average bases require an aggregate mean.")
        return self


@dataclass
class ExtractedTable:
    table_id: str
    frame: pd.DataFrame
    warnings: list[Caveat] = field(default_factory=list)


@dataclass
class Dataset:
    frame: pd.DataFrame
    columns: list[ColumnDefinition]
    classification: str
    warnings: list[Caveat] = field(default_factory=list)

    @property
    def months(self) -> list[str]:
        return sorted(self.frame["month"].unique().tolist())

    @property
    def units(self) -> dict[str, str]:
        return {c.name: c.unit for c in self.columns if c.unit is not None}


@dataclass
class CalculationResult:
    status: Literal["ok", "unavailable", "unsupported", "clarification"]
    plan: AnalysisPlan
    values: pd.DataFrame
    evidence: pd.DataFrame
    unit: str
    answer: str
    trace: list[str]
    warnings: list[Caveat]
    chart_type: str = "none"
    details: dict[str, float | str | None] = field(default_factory=dict)
    breakdown: pd.DataFrame = field(default_factory=pd.DataFrame)
    working: list[str] = field(default_factory=list)
