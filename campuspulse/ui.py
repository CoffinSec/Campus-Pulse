"""Presentation helpers. Uploaded names and model text are always HTML-escaped."""

from html import escape

import streamlit as st

CSS = """
<style>
:root { --champagne:#EFE1CE; --rose-gold:#B9857C; --black-cherry:#721D35;
 --black-cherry-dark:#42121F; --near-black:#1C0B12;
 --accent-cyan:#45D7D1; --accent-gold:#F4CB72; --accent-lavender:#B7A2FF;
 --accent-coral:#FF9388; --accent-mint:#88E0AC; }
.stApp {background: radial-gradient(ellipse at top right,#42121F,#1C0B12 62%) !important;
 color:var(--champagne); }
.stMainBlockContainer {max-width:1280px;padding-top:2rem;padding-bottom:5rem;}
html, body, p, label, .stMarkdown {color:var(--champagne);}
h1,h2,h3 {color:var(--champagne)!important;letter-spacing:-.035em;}
h1 {font-family:Georgia,serif;font-weight:650!important;font-size:clamp(2.2rem,4.5vw,3.6rem)!important;}
h2,h3 {font-family:Georgia,serif;}
[data-testid="stMetric"] {background:linear-gradient(120deg,#51202D,#351721);
 border:1px solid #C58C94;border-radius:16px;padding:1rem 1.1rem;height:100%;}
[data-testid="stMetricValue"] {color:#EFE1CE;font-size:clamp(1.25rem,2.5vw,2rem);}
[data-testid="stMetricLabel"] {color:#F0C1B9;}
[data-testid="stVerticalBlockBorderWrapper"], [data-testid="stChatMessage"] {
 background:linear-gradient(145deg,#381A27,#26111C);border:1px solid #885268;
 border-radius:17px;padding:.8rem;}
[data-testid="stFileUploaderDropzone"] {background:#3E1B29;border:2px dashed #F4CB72;
 border-radius:13px;min-height:145px;}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button {
 border-radius:12px;min-height:42px;border:1px solid #C9939C;
 background:#582537;color:#FFF6E9;}
[data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover {
 border-color:#F4CB72;background:#721D35;color:#FFFFFF;}
[data-testid="stButton"] button[kind="primary"] {background:#F4CB72;color:#1C0B12;border-color:#F4CB72;font-weight:700;}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,
[data-testid="stChatInput"] textarea {background:#321725;color:#FFF6E9;border-color:#B9857C;}
[data-testid="stChatMessage"] {padding:1.2rem;}
[data-testid="stButton"] button p {white-space:normal;overflow-wrap:anywhere;}
.st-key-question_suggestions button {min-height:64px;text-align:left;}
[data-testid="stSidebar"] {background:#27121C;border-right:1px solid #885268;}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {color:#45D7D1;border-bottom:2px solid #45D7D1;}
[data-testid="stSelectbox"] [data-baseweb="select"],
[data-testid="stMultiSelect"] [data-baseweb="select"] {background:#321725;border-color:#B9857C;}
[data-testid="stMetricDelta"] {color:#88E0AC;}
[data-testid="stCaptionContainer"], .stCaption {color:#E7BCB7!important;}
[data-testid="stFileUploaderDropzone"] button {border:1px solid #F4CB72!important;}
button:focus-visible, input:focus-visible, textarea:focus-visible {outline:2px solid #45D7D1!important;outline-offset:2px;}
[data-testid="stAlert"] {border-radius:12px;}
.cp-eyebrow {font-size:.75rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;
 color:#B9857C;margin:.3rem 0 .5rem;}
.cp-lead {font-size:1.17rem;color:#DAB8AE;line-height:1.6;margin-bottom:.7rem;}
.cp-steps {display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;margin:.5rem 0 1.2rem;}
.cp-step {border-top:3px solid #42121F;padding:.65rem;color:#B9857C;font-size:.9rem;}
.cp-step.active {border-color:#45D7D1;color:#FFFFFF;font-weight:700;}
.cp-step.done {border-color:#F4CB72;color:#EFE1CE;}
.cp-step span {font-size:.7rem;margin-right:.55rem;}
.cp-answer {font-size:clamp(1.2rem,2.4vw,1.7rem);font-weight:650;
 line-height:1.5;color:#EFE1CE;overflow-wrap:anywhere;}
.cp-formula {font-family:ui-monospace,Consolas,monospace;font-size:.84rem;line-height:1.7;
 background:#42121F;border-left:3px solid #B9857C;border-radius:0 9px 9px 0;
 padding:.65rem .85rem;white-space:pre-wrap;overflow-wrap:anywhere;}
.cp-file {font-weight:650;color:#EFE1CE;overflow-wrap:anywhere;}
.cp-help {font-size:.84rem;color:#CBAAA2;line-height:1.6;}
@media(max-width:700px){.stMainBlockContainer{padding:1rem .8rem 5rem;}
 .cp-steps{gap:.3rem}.cp-step{font-size:.72rem}[data-testid="stChatMessage"]{padding:.6rem;}}
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
