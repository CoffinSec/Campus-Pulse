"""Immediate overview and conservative within-building anomaly flags."""

import numpy as np
import pandas as pd

from campuspulse.analysis_engine import calculate
from campuspulse.models import AnalysisPlan, Dataset


def overview(dataset: Dataset) -> dict:
    totals = dataset.frame.groupby("building_name").electricity_kwh.sum(min_count=1).dropna()
    totals = totals.loc[np.isfinite(totals)]
    winners = [] if totals.empty else totals.index[totals.eq(totals.max())].tolist()
    trend = calculate(
        dataset,
        AnalysisPlan(
            intent="trend", metric="electricity_kwh", aggregation="sum", group_by=["month"]
        ),
    )
    total = dataset.frame.electricity_kwh.sum(min_count=1)
    return {
        "total": total if np.isfinite(total) else float("nan"),
        "buildings": dataset.frame.building_name.nunique(),
        "months": len(dataset.months),
        "highest": ", ".join(winners) or "Unavailable",
        "highest_value": None if totals.empty else float(totals.max()),
        "trend": trend,
    }


def anomaly_flags(dataset: Dataset) -> pd.DataFrame:
    """Flag deviations from at least 3 PRIOR consecutive-month percentage changes.

    Threshold: max(20 percentage points, 3 × 1.4826 × prior MAD). Only observed
    adjacent months with a positive baseline participate. Never infer a cause.
    """
    flags = []
    for building, rows in dataset.frame.groupby("building_name"):
        rows = rows.sort_values("month")
        history = []
        previous = None
        for row in rows.itertuples():
            current = row.electricity_kwh
            if previous is not None:
                consecutive = (
                    pd.Period(row.month, "M").ordinal - pd.Period(previous.month, "M").ordinal == 1
                )
                if (
                    consecutive
                    and pd.notna(current)
                    and pd.notna(previous.electricity_kwh)
                    and previous.electricity_kwh > 0
                ):
                    change = (current - previous.electricity_kwh) / previous.electricity_kwh * 100
                    if len(history) >= 3:
                        median = float(np.median(history))
                        mad = float(np.median(np.abs(np.array(history) - median)))
                        threshold = max(20.0, 3 * 1.4826 * mad)
                        if abs(change - median) > threshold:
                            flags.append(
                                {
                                    "Building": building,
                                    "Month": row.month,
                                    "Change (%)": change,
                                    "Typical prior change (%)": median,
                                    "Threshold (percentage points)": threshold,
                                    "Note": "Unusually large change compared with this building’s prior history; cause unknown.",
                                    "Source file": row.source_file,
                                    "Source page": row.source_page,
                                    "Source row": row.source_row,
                                }
                            )
                    history.append(change)
            previous = row
    return pd.DataFrame(flags)
