"""Explicit mapping and conservative, auditable normalization."""

import re
from datetime import datetime

import numpy as np
import pandas as pd

from campuspulse.csv_parser import PROVENANCE
from campuspulse.models import Caveat, ColumnDefinition, DataError, Dataset, ExtractedTable

ALIASES = {
    "building_name": {"buildingname", "building", "block", "hostel"},
    "month": {"month", "period", "date", "billingmonth"},
    "electricity_kwh": {
        "electricitykwh",
        "kwh",
        "consumption",
        "unitsconsumed",
        "electricityusage",
        "consumptionkwh",
        "electricityusagekwh",
    },
    "department": {"department"},
    "building_id": {"buildingid"},
    "occupancy": {"occupancy", "students"},
    "tariff_inr_per_kwh": {"tariffinrperkwh"},
    "electricity_cost_inr": {"electricitycostinr", "costinr"},
}
NUMERIC_UNITS = {
    "electricity_kwh": "kWh",
    "occupancy": "people",
    "tariff_inr_per_kwh": "INR/kWh",
    "electricity_cost_inr": "INR",
}
REQUIRED = ["building_name", "month", "electricity_kwh"]
SYNTHETIC = "SYNTHETIC DEMONSTRATION DATA"


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    mapping = {}
    for target, aliases in ALIASES.items():
        matches = [c for c in columns if re.sub(r"[\W_]+", "", c.casefold()) in aliases]
        if len(matches) == 1:
            mapping[target] = matches[0]
    return mapping


def parse_month(value: str, default_year: int | None = None) -> str:
    text = " ".join(str(value).strip().split())
    if re.fullmatch(r"\d{4}-\d{2}", text):
        formats = ["%Y-%m"]
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        formats = ["%Y-%m-%d"]
    else:
        formats = ["%B %Y", "%b %Y", "%Y %B", "%Y %b"]
        if default_year is not None and re.fullmatch(r"[A-Za-z]+", text):
            text = f"{text} {default_year}"
    for fmt in formats:
        try:
            parsed = datetime.strptime(text, fmt)
            return f"{parsed.year:04d}-{parsed.month:02d}"
        except ValueError:
            pass
    raise DataError(
        "Invalid or ambiguous period. Use YYYY-MM, YYYY-MM-DD, June 2026 or specify a year for month-only values."
    )


def parse_number(value, unit: str) -> float:
    if (
        value is None
        or pd.isna(value)
        or str(value).strip().casefold() in {"", "na", "n/a", "null", "nan", "—", "-"}
    ):
        return float("nan")
    text = str(value).strip()
    if text.endswith(unit):
        text = text[: -len(unit)].strip()
    # Commas must be valid thousands grouping; decimal-comma values are ambiguous.
    if not re.fullmatch(r"[+]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?", text):
        raise DataError(
            f"Unrecognized numeric value or mixed units. Use nonnegative numbers in {unit}; blanks remain missing."
        )
    number = float(text.replace(",", ""))
    if not np.isfinite(number):
        raise DataError("Nonfinite numeric values are not supported.")
    return number


def normalize(
    table: ExtractedTable,
    mapping: dict[str, str],
    unit: str,
    classification: str = "User-provided · unverified",
    default_year: int | None = None,
) -> Dataset:
    if table.frame.empty:
        raise DataError("The selected table is empty.")
    if any(c not in mapping for c in REQUIRED):
        raise DataError(
            "Map a building column, a month column and an electricity-consumption column."
        )
    if any(k not in ALIASES for k in mapping) or any(
        v not in table.frame for v in mapping.values()
    ):
        raise DataError("The column mapping contains an unknown field.")
    if len(set(mapping.values())) != len(mapping):
        raise DataError("Each source column can map to only one field.")
    if unit != "kWh":
        raise DataError(
            "This prototype analyzes electricity in kWh. Convert other units explicitly before uploading; they are never silently relabelled."
        )
    metric_header = mapping["electricity_kwh"].lower()
    if re.search(r"\bmwh\b|(?<!k)\bwh\b|(?:_|\s)mwh$|(?:_|\s)wh$", metric_header):
        raise DataError(
            "The source header specifies a different unit. Convert to kWh before uploading."
        )
    if any(c not in table.frame for c in PROVENANCE):
        raise DataError("Source references are missing. Re-upload the original file.")
    frame = table.frame[PROVENANCE].copy()
    warnings = list(table.warnings)
    columns = []
    for target, source in mapping.items():
        raw = table.frame[source]
        frame[f"raw_{target}"] = raw
        if target == "month":
            frame[target] = raw.map(lambda x: parse_month(x, default_year))
            columns.append(ColumnDefinition(name=target, dtype="month"))
            if raw.astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").any():
                warnings.append(
                    Caveat(
                        severity="info",
                        code="date_to_month",
                        message="ISO dates were mapped to calendar months. This MVP expects one observation per building per month.",
                    )
                )
        elif target in NUMERIC_UNITS:
            try:
                frame[target] = raw.map(
                    lambda x, number_unit=NUMERIC_UNITS[target]: parse_number(x, number_unit)
                )
            except DataError as exc:
                raise DataError(f"Column {target}: {exc}") from exc
            columns.append(
                ColumnDefinition(name=target, dtype="number", unit=NUMERIC_UNITS[target])
            )
            if frame[target].isna().any():
                warnings.append(
                    Caveat(
                        severity="warning",
                        code="missing_values",
                        message=f"{int(frame[target].isna().sum())} missing values in {target}. They remain missing; aggregates use observed values only.",
                    )
                )
        else:
            frame[target] = (
                raw.fillna("").astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
            )
            if frame[target].eq("").any():
                raise DataError(
                    f"Column {target} contains missing labels. Correct the source before analysis."
                )
            columns.append(ColumnDefinition(name=target, dtype="category"))
    if frame.duplicated(["building_name", "month"]).any():
        raise DataError(
            "Duplicate building/month observations detected. Their meaning is ambiguous; resolve or aggregate them explicitly in the source before upload."
        )
    if not frame["row_id"].is_unique:
        raise DataError("Source row identifiers are not unique. Re-upload the original file.")
    months = sorted(frame["month"].unique())
    expected = pd.period_range(months[0], months[-1], freq="M").astype(str)
    gaps = sorted(set(expected) - set(months))
    if gaps:
        warnings.append(
            Caveat(
                severity="warning",
                code="missing_periods",
                message=f"Missing periods: {', '.join(gaps)}. No interpolation or zero filling is performed.",
            )
        )
    if len(frame) < frame["building_name"].nunique() * len(expected):
        warnings.append(
            Caveat(
                severity="warning",
                code="partial_coverage",
                message="Some building/month observations are absent. Totals and comparisons may cover different populations.",
            )
        )
    warnings.append(
        Caveat(
            severity="info",
            code="classification",
            message=(
                "Synthetic demonstration data, not official IIMT University consumption data."
                if classification == SYNTHETIC
                else "User-provided data. Its authenticity and official status have not been verified."
            ),
        )
    )
    return Dataset(frame, columns, classification, warnings)
