"""Question-specific charts use verified result tables only."""

from hashlib import sha256

import pandas as pd
import plotly.graph_objects as go

from campuspulse.models import CalculationResult
from campuspulse.presentation import METRICS, period_label

TEAL = "#45D7D1"  # high-contrast cyan for primary data
WINNER = "#F4CB72"  # gold highlight
MUTED = "#FF9388"  # coral for secondary period
SOURCE_COLORS = ("#45D7D1", "#F4CB72", "#B7A2FF", "#FF9388", "#88E0AC")


def source_palette(source_ids: list[str]) -> dict[str, str]:
    """Stable, legible colours per source within a comparison chart."""
    ordered = sorted(set(map(str, source_ids)))
    if len(ordered) <= len(SOURCE_COLORS):
        return {sid: SOURCE_COLORS[index] for index, sid in enumerate(ordered)}
    return {sid: SOURCE_COLORS[int.from_bytes(sha256(sid.encode()).digest()[:4], "big") % len(SOURCE_COLORS)] for sid in ordered}



def build_chart(result: CalculationResult) -> go.Figure | None:
    if result.status != "ok" or result.values.empty or result.chart_type in {"none", "metric"}:
        return None
    fig = go.Figure()
    intent = result.plan.intent
    if intent == "compare_sources" or (intent == "per_student" and "source_id" in result.values):
        palette = source_palette(result.values.source_id.tolist())
        for sid, rows in result.values.groupby("source_id", sort=False):
            fig.add_bar(name=str(rows.source_label.iloc[0]), x=rows.label.tolist(),
                        y=rows.value.tolist(), marker_color=palette[str(sid)])
        fig.update_layout(barmode="group", showlegend=True)
    elif result.plan.group_by_source and "source_id" in result.values:
        palette = source_palette(result.values.source_id.tolist())
        for sid, rows in result.values.groupby("source_id", sort=False):
            fig.add_scatter(x=rows.label.tolist(), y=rows.value.tolist(), mode="lines+markers",
                            name=str(rows.source_label.iloc[0]), connectgaps=False,
                            line={"color": palette[str(sid)], "width": 3})
        fig.update_layout(showlegend=True)
    elif intent == "period_comparison" and not result.breakdown.empty:
        buildings = sorted(result.breakdown.label.unique())
        for period, color in zip(result.plan.periods, [MUTED, TEAL]):
            rows = (
                result.breakdown.loc[result.breakdown.period.eq(period)]
                .set_index("label")
                .reindex(buildings)
            )
            fig.add_bar(
                name=period_label(period),
                x=buildings,
                y=rows.value.tolist(),
                marker_color=color,
                texttemplate="%{y:,.0f}",
                textposition="outside",
            )
        fig.update_layout(barmode="group", showlegend=True, xaxis_title="Building")
    elif result.chart_type == "line":
        values = result.values
        x, y = values.label.tolist(), values.value.tolist()
        fig.add_scatter(
            x=x,
            y=y,
            mode="lines+markers",
            connectgaps=False,
            name="Monthly usage",
            line={"color": TEAL, "width": 3},
            cliponaxis=False,
        )
        observed = values.dropna(subset=["value"])
        if not observed.empty:
            for tag, extreme, color, position in [
                ("Highest", observed.value.max(), WINNER, "top center"),
                ("Lowest", observed.value.min(), "#FF9388", "bottom center"),
            ]:
                points = observed.loc[observed.value.eq(extreme)]
                fig.add_scatter(
                    x=points.label.tolist(),
                    y=points.value.tolist(),
                    mode="markers+text",
                    marker={"color": color, "size": 12},
                    name=tag,
                    text=[f"{tag}: {v:,.0f}" for v in points.value],
                    textposition=position,
                    cliponaxis=False,
                )
        fig.update_layout(xaxis_title="Month", showlegend=False)
    else:
        values = (
            result.breakdown
            if intent == "ranking" and not result.breakdown.empty
            else result.values
        )
        x, y = values.label.tolist(), values.value.tolist()
        winners = set(
            result.values.loc[result.values.value.eq(result.values.value.iloc[0]), "label"]
        )
        colors = [WINNER if intent == "ranking" and label in winners else TEAL for label in x]
        fig.add_bar(
            x=x,
            y=y,
            marker_color=colors,
            texttemplate="%{y:,.2f}",
            textposition="outside",
            cliponaxis=False,
        )
        fig.update_layout(
            xaxis_title="Scenario" if intent == "scenario" else "Building", showlegend=False
        )
    title = {
        "ranking": "Building ranking · winner highlighted",
        "compare_sources": "Compare uploaded reports",
        "period_comparison": "Period comparison by building",
        "trend": "Monthly electricity trend",
        "per_student": "Usage per student · eligible buildings",
        "scenario": "Measured usage and what-if usage",
    }.get(intent, "Building comparison")
    fig.update_layout(
        title=title,
        yaxis_title=f"{METRICS.get(result.plan.metric, 'Usage').capitalize()} ({result.unit})",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "sans-serif", "color": "#EFE1CE", "size": 12},
        margin={"l": 20, "r": 20, "t": 65, "b": 50},
        height=340,
        legend={"orientation": "h", "y": -0.2},
    )
    fig.update_yaxes(
        rangemode="tozero", automargin=True, gridcolor="#754152", zerolinecolor="#98576A"
    )
    plotted = result.breakdown if intent == "period_comparison" and not result.breakdown.empty else result.values
    maximum = plotted.value.max()
    if pd.notna(maximum):
        fig.update_yaxes(range=[0, max(float(maximum) * 1.2, 1)])
    fig.update_xaxes(type="category", automargin=True)
    fig.update_traces(hovertemplate=f"%{{x}}<br>%{{y:,.2f}} {result.unit}<extra></extra>")
    if intent == "trend" and not result.plan.group_by_source:
        fig.update_xaxes(
            tickvals=result.values.label.tolist(),
            ticktext=[period_label(v) for v in result.values.label],
        )
    return fig
