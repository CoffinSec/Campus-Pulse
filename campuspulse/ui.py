"""Presentation helpers. Uploaded names and model text are always HTML-escaped."""

from html import escape

import streamlit as st

CSS = """
<style>
.stApp {background: #f6f8f7;}
.stMainBlockContainer {max-width: 1200px; padding-top: 2.5rem; padding-bottom: 5rem;}
h1 {letter-spacing: -.055em; font-weight: 750 !important;}
h2,h3 {letter-spacing: -.025em;}
[data-testid="stMetric"] {background: white; border: 1px solid #dce6e3;
 border-radius: 14px; padding: 1rem 1.1rem; height: 100%;}
[data-testid="stMetricValue"] {font-size: clamp(1.3rem, 2.3vw, 2rem); letter-spacing: -.035em;}
[data-testid="stMetricValue"] > div {white-space: normal; overflow-wrap: anywhere;}
[data-testid="stMetricLabel"] {color: #526d67;}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 16px;}
[data-testid="stChatMessage"] {background: white; border: 1px solid #dce6e3;
 border-radius: 16px; padding: 1.25rem;}
[data-testid="stFileUploaderDropzone"] {background: #f0f7f4; border: 1px dashed #8cb8ad;
 border-radius: 12px; min-height: 150px;}
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {
 border-radius: 10px; min-height: 42px;}
[data-testid="stButton"] button p, [data-testid="stDownloadButton"] button p {
 white-space: normal; overflow-wrap: anywhere;}
.st-key-question_suggestions button {min-height: 64px; text-align: left;}
[data-testid="stButton"] button:focus-visible, [data-testid="stDownloadButton"] button:focus-visible {
 outline: 3px solid #0b7869; outline-offset: 3px;}
[data-testid="stAlert"] {border-radius: 12px;}
.cp-eyebrow {font-size: .72rem; font-weight: 750; letter-spacing: .13em;
 text-transform: uppercase; color: #247566; margin: .3rem 0 .5rem;}
.cp-lead {font-size: 1.15rem; color: #46655d; line-height: 1.6; margin-bottom: .65rem;}
.cp-steps {display: grid; grid-template-columns: repeat(3,1fr); gap: .75rem; margin: .5rem 0 1.1rem;}
.cp-step {border-top: 3px solid #d6e2dd; padding: .7rem .1rem; color: #526d67; font-size: .86rem;}
.cp-step.active {border-color: #0b7869; color: #164e43; font-weight: 700;}
.cp-step.done {border-color: #88b9a8;}
.cp-step span {font-size: .7rem; margin-right: .55rem;}
.cp-answer {font-size: clamp(1.25rem, 2.3vw, 1.7rem); line-height: 1.45; font-weight: 700;
 letter-spacing: -.025em; color: #193f35; margin: .4rem 0 .8rem; overflow-wrap: anywhere;}
.cp-formula {font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: .84rem;
 line-height: 1.7; background: #f0f6f3; border-left: 3px solid #7cae9a; border-radius: 0 8px 8px 0;
 padding: .65rem .85rem; margin: .4rem 0; overflow-wrap: anywhere; white-space: pre-wrap;}
.cp-file {font-weight: 650; color: #234d41; overflow-wrap: anywhere; margin: .2rem 0;}
.cp-help {font-size: .84rem; color: #526d67; line-height: 1.6;}
@media (max-width: 640px) {
 .stMainBlockContainer {padding: 1.2rem 1rem 5rem;}
 .cp-steps {gap: .4rem;} .cp-step {font-size: .77rem;}
 [data-testid="stChatMessage"] {padding: .75rem;}
 [data-testid="stMetricValue"] {font-size: 1.65rem;}
}
</style>
"""


def styled_text(text: str, kind: str) -> None:
    """Only internal styles are allowed; content is never interpreted as markup."""
    if kind not in {"eyebrow", "lead", "answer", "formula", "file", "help"}:
        raise ValueError("Unknown text style")
    st.markdown(f'<div class="cp-{kind}">{escape(text)}</div>', unsafe_allow_html=True)


def progress_steps(stage: int) -> None:
    labels = ["Add a report", "Check your data", "Explore & ask"]
    parts = []
    for index, label in enumerate(labels):
        state = "active" if index == stage else "done" if index < stage else ""
        number = "✓" if index < stage else f"0{index + 1}"
        parts.append(f'<div class="cp-step {state}"><span>{number}</span>{label}</div>')
    st.markdown('<div class="cp-steps">' + "".join(parts) + "</div>", unsafe_allow_html=True)
