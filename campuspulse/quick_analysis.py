"""Explicit preset choices execute locally; they are never labelled AI answers."""

from campuspulse.models import AnalysisPlan, Filter


def quick_questions(dataset) -> list[tuple[str, AnalysisPlan]]:
    latest = dataset.months[-1]
    month = [Filter(column="month", operator="eq", value=latest)]

    def plan(intent, **kwargs):
        return AnalysisPlan(intent=intent, metric="electricity_kwh", aggregation="sum", **kwargs)

    choices = [
        (
            f"Which building used the most electricity in {latest}?",
            plan("ranking", group_by=["building_name"], limit=1, filters=month),
        ),
    ]
    if len(dataset.months) >= 2:
        choices.append(
            (
                f"Compare {dataset.months[-2]} and {latest} electricity consumption.",
                plan("period_comparison", periods=dataset.months[-2:]),
            )
        )
    choices.extend(
        [
            ("Show the monthly electricity consumption trend.", plan("trend", group_by=["month"])),
            ("Month with highest electricity use", plan("ranking", group_by=["month"], limit=1)),
        ]
    )
    if "occupancy" in dataset.frame:
        choices.append(
            (
                f"Compare kWh per student in {latest}.",
                AnalysisPlan(
                    intent="per_student",
                    metric="electricity_kwh",
                    aggregation="mean",
                    group_by=["building_name"],
                    filters=month,
                ),
            )
        )
    hostels = [
        str(b) for b in dataset.frame.building_name.unique() if "hostel" in str(b).casefold()
    ]
    if hostels:
        choices.append(
            (
                f"What if the hostels cut usage by 10% in {latest}?",
                plan("scenario", scenario_buildings=hostels, reduction_percent=10, filters=month),
            )
        )
    choices.append(
        (
            "What was the electricity cost?"
            if "electricity_cost_inr" not in dataset.frame
            else "What is the total electricity cost?",
            AnalysisPlan(intent="aggregate", metric="electricity_cost_inr", aggregation="sum"),
        )
    )
    return choices
