"""Friendly short replies and accurate, report-wide summaries.

Natural language follows the Gemma planner unless it is clearly a greeting or a
request for an *entire report* overview. Those low-latency responses are calculated
from the user's uploaded data and never rely on a particular set of fixture numbers.
"""

import re
import unicodedata
from difflib import get_close_matches

import pandas as pd

from campuspulse.insights import overview
from campuspulse.models import Dataset


# Never convert a scoped request into an all-campus summary. Send it to Gemma.
_SCOPED = re.compile(
    r"\b(?:hostel|hostels|library|blocks?|building|buildings|department|departmental|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|"
    r"20\d\d|specific|only|compare|comparison|versus|vs|difference|"
    r"increase|decrease|trend|daily|weekly|monthly|per.student|"
    r"occupancy|student|students|costs?|prices?|tariffs?|bills?|expenses?|"
    r"highest|lowest|top|least|maximum|minimum|savings?|reduce|reduction)\b",
    re.IGNORECASE,
)
_OVERVIEW = re.compile(
    r"\b(?:summary|summari[sz](?:e|ing|ation)|overview|recap|highlights?|"
    r"snapshot|gist|summarise|summarize|sum\s+up|big\s+picture|"
    r"key\s+points|short\s+description|short\s+explanation|"
    r"brief\s+overview|brief\s+explanation|saar|saransh|saraansh)\b",
    re.IGNORECASE,
)
_OPEN_QUESTION = re.compile(
    r"\b(?:what(?:'s|\s+is|\s+does)\s+(?:in|this|the|my|our)|"
    r"what\s+(?:does|can)\s+(?:this|the|my|our)\s+(?:report|data|dataset|pdf)|"
    r"explain\s+(?:this|the|my|our)\s+(?:report|data|dataset|pdf)|"
    r"tell\s+me\s+about\s+(?:this|the|my|our)\s+(?:report|data|dataset|pdf)|"
    r"report\s+(?:ke?\s+baare\s+me|ka\s+saar)|"
    r"(?:data|report)\s+me\s+kya\s+hai|"
    r"(?:data|report)\s+(?:samjhao|samjha\s+do))\b",
    re.IGNORECASE,
)


def _normalise(question: str) -> str:
    clean = unicodedata.normalize("NFKC", question).casefold()
    clean = re.sub(r"[^\w\s'-]", " ", clean)
    return " ".join(clean.split())


def is_report_overview_request(question: str) -> bool:
    """Recognise loose whole-report wording while leaving scoped questions to AI.

    The model can additionally identify novel phrasings through report_overview
    intent; this function is an intentionally conservative fast path, not a
    complete question interpreter.
    """
    q = _normalise(question)
    if not q or _SCOPED.search(q):
        return False
    if _OVERVIEW.search(q) or _OPEN_QUESTION.search(q):
        return True
    # Typo-tolerant: e.g. 'summry', 'summery', 'summeryyy'. Only consider
    # whole words, never arbitrary substrings of unrelated questions.
    tokens = re.findall(r"\b[a-z]{5,14}\b", q)
    for token in tokens:
        if get_close_matches(token, ["summary", "summarize", "summarise", "overview"], n=1, cutoff=0.81):
            return True
    return False


def report_summary(dataset: Dataset) -> str:
    """Report-wide factual overview derived exclusively from confirmed rows."""
    info = overview(dataset)
    total = info["total"]
    total_text = f"{total:,.0f} kWh" if pd.notna(total) else "unavailable"
    months = dataset.months
    period_text = f"{months[0]} to {months[-1]}" if months else "no months available"
    highest = info["highest"]
    high_value = info["highest_value"]
    high_text = (
        f"{highest} ({high_value:,.0f} kWh)" if high_value is not None else "unavailable"
    )

    lines = [
        f"Here's a summary of your electricity report ({dataset.classification}).",
        f"Coverage: {info['buildings']} buildings, {info['months']} months ({period_text}); "
        f"{len(dataset.frame)} source readings.",
        f"Total observed electricity: {total_text}.",
        f"Highest total electricity usage: {high_text}.",
    ]
    if pd.notna(total) and total > 0 and high_value is not None:
        lines.append(f"The highest-usage building represents {high_value / total * 100:.1f}% of recorded campus usage.")

    trend = info["trend"]
    if trend.status == "ok" and len(trend.values) >= 2:
        first = trend.values.iloc[0]
        last = trend.values.iloc[-1]
        if pd.notna(first.value) and pd.notna(last.value):
            if first.value > 0:
                change = (last.value - first.value) / first.value * 100
                lines.append(
                    f"Monthly campus usage went from {first.value:,.0f} kWh in {first.label} "
                    f"to {last.value:,.0f} kWh in {last.label} "
                    f"({'+' if change >= 0 else ''}{change:.1f}% between those months)."
                )
            else:
                lines.append(
                    f"Monthly campus usage: {first.value:,.0f} kWh in {first.label} "
                    f"and {last.value:,.0f} kWh in {last.label}."
                )

    missing = [
        f"{int(dataset.frame[col.name].isna().sum())} missing {col.name} values"
        for col in dataset.columns
        if col.dtype == "number" and col.name != "occupancy" and dataset.frame[col.name].isna().any()
    ]
    lines.append(
        "Data quality: " + (
            "; ".join(missing) if missing
            else "No missing electricity readings; optional building occupancy may be unavailable."
        )
    )
    lines.append(
        "These are observed totals only. Missing values are not treated as zero; "
        "usage alone cannot establish waste, efficiency or causes."
    )
    return "\n".join(lines)


def quick_reply(question: str, dataset: Dataset) -> str | None:
    q = _normalise(question)
    if re.fullmatch(r"(?:hi|hello|hey|hii+|namaste|namaskar|hola|hey there|hello there)", q):
        return (
            "Hi! I can analyze your uploaded electricity report. "
            "Ask me for a summary, to compare buildings, show trends, "
            "or calculate electricity usage."
        )
    if is_report_overview_request(question):
        return report_summary(dataset)
    return None
