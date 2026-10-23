from conftest import plan

from campuspulse.analysis_engine import calculate
from campuspulse.evidence import evidence_table
from campuspulse.ingestion import ingest
from campuspulse.normalization import normalize, suggest_mapping
from campuspulse.question_planner import parse_plan
from campuspulse.visualization import build_chart


def test_pdf_upload_through_chart_and_evidence(pdf_bytes, settings):
    table = ingest(pdf_bytes, "uploaded_report.pdf", settings)[0]
    dataset = normalize(table, suggest_mapping(list(table.frame)), "kWh")
    parsed = parse_plan(
        plan("period_comparison", periods=["2026-05", "2026-06"]).model_dump_json(), dataset
    )
    result = calculate(dataset, parsed)
    assert result.status == "ok"
    assert result.details["absolute_change"] == 850
    chart = build_chart(result)
    assert chart.layout.barmode == "group"
    assert chart.data[0].y == (5200, 3200, 5800, 5300, 1600)
    assert chart.data[1].y == (5600, 3100, 6200, 5500, 1550)
    assert sum(chart.data[0].y) == 21100
    assert sum(chart.data[1].y) == 21950
    evidence = evidence_table(result)
    assert len(evidence) == 10
    assert evidence.source_file.eq("uploaded_report.pdf").all()
    assert evidence.source_page.eq(1).all()
    assert evidence.source_row.tolist() == list(range(22, 32))
