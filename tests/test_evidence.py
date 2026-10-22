import pandas as pd
from conftest import dataset_from_csv, plan

from campuspulse.analysis_engine import calculate
from campuspulse.evidence import evidence_table, export_evidence
from campuspulse.models import Filter


def test_evidence_contains_all_real_contributors(dataset):
    result = calculate(
        dataset, plan(filters=[Filter(column="month", operator="eq", value="2026-06")])
    )
    evidence = evidence_table(result)
    assert evidence.source_row.tolist() == list(range(27, 32))
    assert (
        evidence.row_id.tolist()
        == dataset.frame.loc[dataset.frame.month.eq("2026-06"), "row_id"].tolist()
    )
    assert evidence.electricity_kwh.sum() == result.values.value.iloc[0]
    assert evidence.source_page.isna().all()


def test_exports_preserve_values_and_neutralize_formulas():
    import io

    ds = dataset_from_csv(b"Building,Month,kWh\n=HYPERLINK(evil),2026-06,4\n")
    result = calculate(ds, plan())
    exported = pd.read_csv(io.BytesIO(export_evidence(result)))
    assert exported.building_name.iloc[0].startswith("'=")
    assert exported.electricity_kwh.iloc[0] == 4
    assert ds.frame.building_name.iloc[0].startswith("=")  # Never mutate source.
