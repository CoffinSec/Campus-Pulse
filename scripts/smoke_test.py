"""Offline acceptance smoke: actual uploads through extraction, math and charts."""

import json
from pathlib import Path

from campuspulse.analysis_engine import calculate
from campuspulse.config import Settings
from campuspulse.ingestion import ingest
from campuspulse.models import AnalysisPlan, Filter
from campuspulse.normalization import SYNTHETIC, normalize, suggest_mapping
from campuspulse.visualization import build_chart


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    for extension in ["pdf", "csv"]:
        path = root / "data" / f"campus_electricity_sample.{extension}"
        tables = ingest(path.read_bytes(), path.name, Settings())
        dataset = normalize(tables[0], suggest_mapping(list(tables[0].frame)), "kWh", SYNTHETIC)
        plans = [
            AnalysisPlan(
                intent="ranking",
                metric="electricity_kwh",
                aggregation="sum",
                group_by=["building_name"],
                limit=1,
                filters=[Filter(column="month", operator="eq", value="2026-06")],
            ),
            AnalysisPlan(
                intent="period_comparison",
                metric="electricity_kwh",
                aggregation="sum",
                periods=["2026-05", "2026-06"],
            ),
            AnalysisPlan(
                intent="trend", metric="electricity_kwh", aggregation="sum", group_by=["month"]
            ),
            AnalysisPlan(intent="aggregate", metric="electricity_cost_inr", aggregation="sum"),
        ]
        results = [calculate(dataset, p) for p in plans]
        assert results[0].values.iloc[0].value == 6200
        assert results[1].details["absolute_change"] == 850
        assert results[2].values.value.tolist() == [18800, 19000, 19500, 20150, 21100, 21950]
        assert results[3].status == "unavailable"
        for result in results[:3]:
            assert build_chart(result) is not None
            assert not result.evidence.empty
        print(
            json.dumps(
                {
                    "input": extension,
                    "rows": len(dataset.frame),
                    "answers": [r.answer for r in results],
                },
                indent=2,
            )
        )
    print("Offline smoke passed. No AI inference was performed.")


if __name__ == "__main__":
    main()
