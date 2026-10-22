"""Charts consume verified result values only."""

import plotly.graph_objects as go

from campuspulse.models import CalculationResult


def build_chart(result: CalculationResult) -> go.Figure | None:
    if result.status != "ok" or result.values.empty or result.chart_type in {"none", "metric"}:
        return None
    x, y = result.values["label"].tolist(), result.values["value"].tolist()
    if result.chart_type == "line":
        fig = go.Figure(
            go.Scatter(
                x=x,
                y=y,
                mode="lines+markers",
                connectgaps=False,
                line={"color": "#087F8C", "width": 3},
            )
        )
    else:
        fig = go.Figure(go.Bar(x=x, y=y, marker_color="#087F8C"))
    fig.update_layout(
        title=f"{result.plan.metric.replace('_', ' ').title()} · {result.plan.aggregation}",
        xaxis_title=result.plan.group_by[0].replace("_", " ").title()
        if result.plan.group_by
        else "Period",
        yaxis_title=f"{result.plan.aggregation.title()} ({result.unit})",
        template="plotly_white",
        margin={"l": 20, "r": 20, "t": 60, "b": 40},
        height=380,
        showlegend=False,
    )
    fig.update_yaxes(rangemode="tozero")
    fig.update_xaxes(type="category")
    fig.update_traces(hovertemplate=f"%{{x}}<br>%{{y:,.2f}} {result.unit}<extra></extra>")
    return fig
