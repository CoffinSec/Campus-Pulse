"""Offline source-aware tests; no model or network involved."""

import pandas as pd
import pytest

from campuspulse.analysis_engine import calculate
from campuspulse.config import Settings
from campuspulse.csv_parser import parse_csv
from campuspulse.evidence import export_evidence
from campuspulse.models import AnalysisPlan, DataError, PlanError
from campuspulse.multi_source import (SourceEntry, combine_sources,
                                      remove_source, replace_source, source_id_for,
                                      reviewed_building_match)
from campuspulse.normalization import apply_custom_tariff, normalize, suggest_mapping
from campuspulse.reporting import answer_pdf


def dataset(rows: str):
    tab = parse_csv(("building_name,month,electricity_kwh,occupancy\n" + rows).encode(),
                    "fictional.csv", Settings())[0]
    return normalize(tab, suggest_mapping(tab.frame.columns.tolist()), "kWh", "SYNTHETIC DEMONSTRATION DATA")


@pytest.fixture
def multi():
    old = dataset("A,2026-05,100,10\nA,2026-06,200,10\nB,2026-05,50,5\nB,2026-06,0,5\n")
    new = dataset("A,2026-05,110,10\nA,2026-06,220,10\nB,2026-05,60,5\nB,2026-06,0,5\n")
    return combine_sources([SourceEntry("fy-old", "old.csv", "FY Old", old),
                            SourceEntry("fy-new", "new.csv", "FY New", new)])


def plan(intent="compare_sources", metric="electricity_kwh", **kwargs):
    return AnalysisPlan(intent=intent, metric=metric, aggregation=kwargs.pop("aggregation", "sum"), **kwargs)


def test_ingestion_cross_source_overlap_allowed_and_traced(multi):
    assert len(multi.frame) == 8
    assert multi.frame.duplicated(["source_id", "building_name", "month"]).sum() == 0
    assert multi.frame.duplicated(["building_name", "month"]).sum() == 4
    assert multi.frame.row_id.is_unique
    assert set(multi.frame.source_label) == {"FY Old", "FY New"}


def test_duplicate_inside_one_file_still_rejected():
    with pytest.raises(DataError, match="Duplicate"):
        dataset("A,2026-05,1,2\nA,2026-05,3,4\n")


def test_source_id_sanitized_and_de_duped():
    assert source_id_for("../Hello World.csv", set()) == "hello-world"
    assert source_id_for("Hello World.csv", {"hello-world"}) == "hello-world-2"


def test_source_comparison_values_and_zero_baseline(multi):
    result = calculate(multi, plan(group_by=["building_name"]))
    assert result.status == "ok"
    assert result.values.loc[result.values.label.eq("A"), "value"].tolist() == [300, 330]
    changes = result.breakdown.set_index("group")
    assert changes.loc["A", "change"] == 30
    assert changes.loc["A", "percent"] == pytest.approx(10)
    assert changes.loc["B", "percent"] == pytest.approx(20)
    z = dataset("A,2026-06,0,10\n")
    q = dataset("A,2026-06,1,10\n")
    ds = combine_sources([SourceEntry("zero", "zero.csv", "zero", z),
                          SourceEntry("other", "other.csv", "other", q)])
    result = calculate(ds, plan())
    assert pd.isna(result.breakdown.percent.iloc[0])
    assert any(w.code == "zero_denominator" for w in result.warnings)


def test_missing_and_per_student_comparison():
    old = dataset("A,2026-06,100,10\nB,2026-06,20,5\n")
    new = dataset("A,2026-06,110,10\nB,2026-06,30,\n")
    ds = combine_sources([SourceEntry("old", "one.csv", "Old", old),
                          SourceEntry("new", "two.csv", "New", new)])
    result = calculate(ds, plan(metric="kwh_per_student", aggregation="mean", group_by=["building_name"]))
    assert result.values.loc[(result.values.label.eq("A")) & (result.values.source_id.eq("new")), "value"].iloc[0] == 11
    assert result.values.loc[(result.values.label.eq("B")) & (result.values.source_id.eq("new")), "value"].isna().all()


def test_source_filters_and_source_trends(multi):
    single = calculate(multi, plan("aggregate", sources=["fy-old"]))
    assert single.values.value.iloc[0] == 350
    assert set(single.evidence.source_id) == {"fy-old"}
    trend = calculate(multi, plan("trend", group_by=["month"], group_by_source=True))
    assert set(trend.values.source_id) == {"fy-old", "fy-new"}
    assert len(trend.values) == 4


def test_unknown_source_rejected(multi):
    with pytest.raises(PlanError, match="Unknown source"):
        calculate(multi, plan(sources=["not-present"]))


def test_one_source_caveat_and_ties():
    old = dataset("A,2026-06,10,1\nB,2026-06,10,1\n")
    ds = combine_sources([SourceEntry("one", "one.csv", "One", old)])
    result = calculate(ds, plan())
    assert result.status == "unavailable"
    other = dataset("A,2026-06,11,1\nB,2026-06,11,1\n")
    ds = combine_sources([SourceEntry("one", "one.csv", "One", old),
                          SourceEntry("two", "two.csv", "Two", other)])
    result = calculate(ds, plan(group_by=["building_name"]))
    assert result.breakdown.change.tolist() == [1, 1]


def test_evidence_and_pdf_include_source_metadata(multi):
    result = calculate(multi, plan(group_by=["building_name"]))
    evidence = export_evidence(result).decode("utf-8-sig")
    assert "source_id" in evidence and "source_label" in evidence
    assert "fy-old" in evidence and "FY New" in evidence
    report = answer_pdf(result, "compare reports", multi.classification)
    import pymupdf
    with pymupdf.open(stream=report, filetype="pdf") as document:
        text = document[0].get_text()
    assert "FY Old" in text or "fy-old" in text


def test_global_cost_and_registry_invalidation(multi):
    old = dataset("A,2026-06,100,10\n")
    new = dataset("A,2026-06,200,10\n")
    entries = [SourceEntry("x", "x.csv", "X", old), SourceEntry("y", "y.csv", "Y", new)]
    assert len(replace_source(entries, SourceEntry("x", "x.csv", "Changed", old))) == 2
    assert [e.source_id for e in remove_source(entries, "x")] == ["y"]
    rated = apply_custom_tariff(combine_sources(entries), 10)
    assert rated.frame.electricity_cost_inr.sum() == 3000


def test_single_file_calculation_regression():
    ds = dataset("A,2026-06,100,10\n")
    result = calculate(ds, plan("aggregate"))
    assert result.values.value.iloc[0] == 100


def test_reconfirmation_preserves_source_comparison_order():
    old = dataset("A,2026-06,10,1\n")
    new = dataset("A,2026-06,12,1\n")
    entries = [SourceEntry("old", "old.csv", "Original", old),
               SourceEntry("new", "new.csv", "Revised", new)]
    reconfirmed = replace_source(entries, SourceEntry("old", "old.csv", "Original", old))
    assert [entry.source_id for entry in reconfirmed] == ["old", "new"]
    ds = combine_sources(reconfirmed)
    assert calculate(ds, plan()).breakdown.change.iloc[0] == 2


def test_reviewed_building_match_preserves_provenance():
    ds = dataset("Academic Block A,2026-06,12,2\n")
    source = SourceEntry("review", "review.csv", "Review", ds)
    revised = reviewed_building_match(source, "Academic Block A", "Academic Block Alpha")
    assert revised.dataset.frame.building_name.iloc[0] == "Academic Block Alpha"
    assert revised.dataset.frame.raw_building_name.iloc[0] == "Academic Block A"
    assert revised.dataset.frame.raw_cells.equals(ds.frame.raw_cells)
    assert ds.frame.building_name.iloc[0] == "Academic Block A"


def test_reviewed_match_cannot_create_duplicate_inside_file():
    ds = dataset("Academic Block A,2026-06,12,2\nAcademic Block Alpha,2026-06,10,2\n")
    entry = SourceEntry("review", "review.csv", "Review", ds)
    with pytest.raises(DataError, match="duplicate"):
        reviewed_building_match(entry, "Academic Block A", "Academic Block Alpha")


def test_exact_source_label_recognition_no_guessing(multi):
    from campuspulse.question_planner import referenced_source_ids
    assert referenced_source_ids("Compare FY Old and FY New", multi) == ["fy-old", "fy-new"]
    assert referenced_source_ids("Show FY New usage", multi) == ["fy-new"]
    assert referenced_source_ids("Show yearly usage", multi) == []
