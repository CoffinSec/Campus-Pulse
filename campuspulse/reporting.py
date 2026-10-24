"""One-page PDF answer reports with an embedded vector chart; no browser dependency."""

from html import escape

import pandas as pd
import pymupdf

from campuspulse.presentation import calculation_lines, describe_plan

TEAL = (0.03, 0.50, 0.55)
GOLD = (0.86, 0.55, 0.15)
MUTED = (0.61, 0.74, 0.75)


def report_png(report: bytes) -> bytes:
    """Render the same one-page report for sharing, with its working and caveats."""
    with pymupdf.open(stream=report, filetype="pdf") as document:
        return document[0].get_pixmap(dpi=144, alpha=False).tobytes("png")


def _text(page, rect, text, size=9):
    page.insert_htmlbox(
        rect, f'<div style="font-size:{size}pt;color:#142f35">{escape(str(text))}</div>'
    )


def _chart(page, result):
    left, right, top, bottom = 65, 550, 270, 440
    if result.status != "ok":
        _text(
            page,
            pymupdf.Rect(left, top, right, bottom),
            "No chart: the requested information is unavailable.",
        )
        return
    if result.chart_type in {"metric", "none"}:
        _text(page, pymupdf.Rect(left, top, right, bottom), result.answer, size=22)
        return
    grouped = result.plan.intent == "period_comparison" and not result.breakdown.empty
    data = result.breakdown if not result.breakdown.empty else result.values
    labels = list(dict.fromkeys(data.label))[:10]
    data = data.loc[data.label.isin(labels)]
    maximum = float(data.value.max()) if data.value.notna().any() else 1
    maximum = max(maximum, 1)
    page.draw_line((left, top), (left, bottom), color=MUTED)
    page.draw_line((left, bottom), (right, bottom), color=MUTED)
    _text(
        page,
        pymupdf.Rect(38, top - 25, right, top),
        f"{result.unit} · zero baseline · chart shows up to ten categories",
        8,
    )
    slot = (right - left) / max(len(labels), 1)
    last_point = None
    winners = set(result.values.loc[result.values.value.eq(result.values.value.iloc[0]), "label"])
    for i, label in enumerate(labels):
        rows = data.loc[data.label.eq(label)]
        cx = left + slot * (i + 0.5)
        _text(
            page,
            pymupdf.Rect(left + i * slot, bottom + 4, left + (i + 1) * slot, bottom + 39),
            label,
            7,
        )
        if result.chart_type == "line":
            value = rows.value.iloc[0]
            if pd.isna(value):
                last_point = None
                continue
            point = (cx, bottom - float(value) / maximum * (bottom - top - 15))
            if last_point:
                page.draw_line(last_point, point, color=TEAL, width=2)
            page.draw_circle(point, 3, color=GOLD, fill=GOLD)
            _text(
                page,
                pymupdf.Rect(cx - 25, point[1] - 19, cx + 25, point[1] - 3),
                f"{value:,.0f}",
                7,
            )
            last_point = point
        else:
            series = result.plan.periods if grouped else [None]
            for j, period in enumerate(series):
                selected = rows.loc[rows.period.eq(period)] if grouped else rows
                if selected.empty or pd.isna(selected.value.iloc[0]):
                    continue
                value = float(selected.value.iloc[0])
                width = slot * 0.7 / len(series)
                x = cx - slot * 0.35 + j * width
                y = bottom - value / maximum * (bottom - top - 15)
                color = (
                    (MUTED if j == 0 else TEAL)
                    if grouped
                    else (GOLD if result.plan.intent == "ranking" and label in winners else TEAL)
                )
                page.draw_rect(pymupdf.Rect(x, y, x + width * 0.9, bottom), color=color, fill=color)
                _text(page, pymupdf.Rect(x - 4, y - 18, x + width + 4, y - 2), f"{value:,.0f}", 7)
    if grouped:
        _text(
            page,
            pymupdf.Rect(left, bottom + 40, right, bottom + 59),
            f"Light teal: {result.plan.periods[0]}  |  Teal: {result.plan.periods[1]}",
            8,
        )


def answer_pdf(
    result, question: str, classification: str, explanation=None, ai: bool = False
) -> bytes:
    with pymupdf.open() as document:
        page = document.new_page(width=595, height=842)
        header = f"""<h1 style='color:#087f8c'>CampusPulse</h1>
        <p><b>{escape(classification)}</b></p>
        <h3>{escape(question[:500])}</h3><p>{escape(result.answer[:1100])}</p>
        <p>{escape(describe_plan(result, ai))}</p>"""
        page.insert_htmlbox(
            pymupdf.Rect(35, 15, 560, 235),
            header,
            css="body {font-family:sans-serif;font-size:11pt;} h1 {margin:0}",
        )
        _chart(page, result)
        working = calculation_lines(result)
        warnings = [w.message for w in result.warnings]
        body = (
            "<b>Actual calculation and source references</b><ul>"
            + "".join(f"<li>{escape(v[:650])}</li>" for v in working[:4])
            + "</ul>"
        )
        if len(working) > 4:
            body += f"<p>{len(working) - 4} additional working lines are shown in the app; download the evidence CSV for the full source rows.</p>"
        if explanation:
            body += "<b>What this means</b><p>" + escape(explanation.meaning[:600]) + "</p>"
        body += (
            "<b>Caveats</b><ul>"
            + "".join(f"<li>{escape(v[:400])}</li>" for v in warnings[:6])
            + "</ul>"
        )
        if len(warnings) > 6:
            body += f"<p>{len(warnings) - 6} further caveats are visible in the app.</p>"
        body += "<p>Generated from verified calculations. PDF source rows include the header; CSV references are physical end-lines. No university endorsement is claimed.</p>"
        page.insert_htmlbox(
            pymupdf.Rect(35, 510, 560, 815),
            body,
            css="body {font-family:sans-serif;font-size:9pt;} p,ul {margin:4pt 0}",
        )
        document.set_metadata({"title": "CampusPulse answer report", "author": "CampusPulse"})
        return document.tobytes(deflate=True)
