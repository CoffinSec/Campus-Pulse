"""Evidence is a projection of actual contributing source rows."""

import pandas as pd

from campuspulse.csv_parser import PROVENANCE
from campuspulse.models import CalculationResult


def evidence_table(result: CalculationResult) -> pd.DataFrame:
    frame = result.evidence
    if frame.empty:
        return frame.copy()
    cols = [
        *PROVENANCE,
        *result.plan.group_by,
        *(item.column for item in result.plan.filters),
        "building_name",
        "month",
        result.plan.metric,
        f"raw_{result.plan.metric}",
        "raw_month",
    ]
    return frame.loc[:, list(dict.fromkeys(c for c in cols if c in frame))].copy()


def export_evidence(result: CalculationResult) -> bytes:
    frame = evidence_table(result)
    # Prevent spreadsheet formula execution when untrusted labels are exported.
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].map(
            lambda v: (
                "'" + v if isinstance(v, str) and v.lstrip().startswith(("=", "+", "-", "@")) else v
            )
        )
    return frame.to_csv(index=False).encode("utf-8-sig")
