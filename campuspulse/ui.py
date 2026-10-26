"""Presentation helpers. Uploaded names and model text are always HTML-escaped.

UI polish intentionally retains CampusPulse's original green/off-white palette.
All styles are cosmetic: dataset, model, and numerical operations are untouched.
"""

from html import escape

import streamlit as st

CSS = """
<style>
/* Original CampusPulse palette — intentionally unchanged. */
:root {
  --cp-background: #f6f8f7;
  --cp-surface: #fff;
  --cp-soft: #f0f7f4;
  --cp-soft-2: #f0f6f3;
  --cp-border: #dce6e3;
  --cp-border-strong: #8cb8ad;
  --cp-accent: #0b7869;
  --cp-accent-dark: #164e43;
  --cp-ink: #193f35;
  --cp-muted: #526d67;
}

.stApp { background: var(--cp-background); }
.stMainBlockContainer {
  max-width: 1200px;
  padding-top: 2rem;
  padding-bottom: 6rem;
}
.stMainBlockContainer > div { gap: 1.15rem; }
h1 { letter-spacing: -.055em; font-weight: 750 !important; line-height: 1.12 !important; }
h2, h3 { letter-spacing: -.025em; line-height: 1.25 !important; }
h2 { font-size: clamp(1.35rem, 2.1vw, 1.75rem) !important; }
h3 { font-size: clamp(1.18rem, 1.75vw, 1.4rem) !important; }
[data-testid="stCaptionContainer"] { line-height: 1.55; }
[data-testid="stMarkdownContainer"] p { line-height: 1.6; }

/* Hero: same original background and type, better hierarchy/alignment. */
.st-key-campuspulse_header {
  padding: .65rem 0 1.15rem;
  border-bottom: 1px solid var(--cp-border);
}
.st-key-campuspulse_header h1 { margin: .15rem 0 .35rem; }
.st-key-campuspulse_header [data-testid="stColumn"]:last-child {
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.st-key-campuspulse_header [data-testid="stPopover"] button { width: 100%; }

/* More useful, clearly-scanned step navigation. */
.cp-steps {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .7rem;
  margin: .1rem 0 .5rem;
}
.cp-step {
  display: flex;
  align-items: center;
  gap: .7rem;
  border-top: 3px solid #d6e2dd;
  padding: .85rem .15rem .35rem;
  color: var(--cp-muted);
  font-size: .88rem;
  line-height: 1.35;
}
.cp-step.active { border-color: var(--cp-accent); color: var(--cp-accent-dark); font-weight: 700; }
.cp-step.done { border-color: #88b9a8; }
.cp-step span {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 1.8rem;
  height: 1.8rem;
  border-radius: 9px;
  background: var(--cp-soft);
  font-size: .73rem;
  font-weight: 750;
  color: var(--cp-muted);
}
.cp-step.active span { background: var(--cp-accent); color: var(--cp-surface); }
.cp-step.done span { color: var(--cp-accent); }

/* Cohesive card and form surfaces (same colours as the original app). */
[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: 16px;
  border-color: var(--cp-border);
}
.st-key-upload_section [data-testid="stVerticalBlockBorderWrapper"],
.st-key-source_card [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 18px; }
.st-key-upload_section [data-testid="stFileUploaderDropzone"] {
  min-height: 152px;
}
.st-key-upload_section [data-testid="stColumn"]:last-child { min-width: 0; }
[data-testid="stFileUploaderDropzone"] {
  background: var(--cp-soft);
  border: 1px dashed var(--cp-border-strong);
  border-radius: 12px;
  min-height: 150px;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--cp-accent); }
[data-testid="stForm"] {
  border: 1px solid var(--cp-border);
  border-radius: 16px;
  padding: 1.15rem;
  background: var(--cp-surface);
}
[data-testid="stExpander"] { border-radius: 12px; overflow: hidden; }
[data-testid="stExpander"] details { border-color: var(--cp-border); }
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }
[data-testid="stAlert"] { border-radius: 12px; }

/* Dashboard — aligned metrics, consistent whitespace and readable long names. */
.st-key-overview_panel { margin-top: .25rem; }
.st-key-overview_panel h2 { margin-bottom: .2rem; }
[data-testid="stMetric"] {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 14px;
  padding: 1.05rem 1.1rem;
  height: 100%;
  min-height: 115px;
}
[data-testid="stMetricValue"] {
  font-size: clamp(1.35rem, 2.25vw, 2rem);
  letter-spacing: -.035em;
  line-height: 1.18;
}
[data-testid="stMetricValue"] > div { white-space: normal; overflow-wrap: anywhere; }
[data-testid="stMetricLabel"] { color: var(--cp-muted); line-height: 1.4; }
.st-key-overview_panel [data-testid="stPlotlyChart"] { border-radius: 12px; overflow: hidden; }
.st-key-overview_panel [data-testid="stCaptionContainer"] { max-width: 100ch; }

/* Buttons, inputs and question prompts — no palette changes. */
[data-testid="stButton"] button,
[data-testid="stDownloadButton"] button {
  border-radius: 10px;
  min-height: 43px;
  transition: border-color .14s ease, background-color .14s ease, transform .14s ease;
}
[data-testid="stButton"] button p,
[data-testid="stDownloadButton"] button p { white-space: normal; overflow-wrap: anywhere; }
[data-testid="stButton"] button:not(:disabled):hover,
[data-testid="stDownloadButton"] button:not(:disabled):hover { border-color: var(--cp-accent); }
[data-testid="stButton"] button:focus-visible,
[data-testid="stDownloadButton"] button:focus-visible,
[data-testid="stFileUploaderDropzone"] button:focus-visible {
  outline: 3px solid var(--cp-accent);
  outline-offset: 3px;
}
.st-key-question_suggestions [data-testid="stButton"] button {
  min-height: 69px;
  height: 100%;
  width: 100%;
  padding: .8rem 1rem;
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  text-align: left;
  justify-content: flex-start;
  font-weight: 600;
  line-height: 1.35;
}
.st-key-question_suggestions [data-testid="stButton"] button:not(:disabled):hover {
  background: var(--cp-soft);
  border-color: var(--cp-accent);
  transform: translateY(-1px);
}
.st-key-question_suggestions [data-testid="stHorizontalBlock"] { row-gap: .55rem; }
[data-testid="stChatInput"] { border-radius: 13px; }

/* Conversation cards — results first, working available but not overwhelming. */
[data-testid="stChatMessage"] {
  background: var(--cp-surface);
  border: 1px solid var(--cp-border);
  border-radius: 16px;
  padding: 1.1rem 1.25rem;
  margin: .45rem 0;
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p { line-height: 1.7; }
[data-testid="stChatMessage"] [data-testid="stCaptionContainer"] { color: var(--cp-muted); }
.cp-answer {
  font-size: clamp(1.25rem, 2.3vw, 1.7rem);
  line-height: 1.45;
  font-weight: 700;
  letter-spacing: -.025em;
  color: var(--cp-ink);
  margin: .4rem 0 .8rem;
  overflow-wrap: anywhere;
}
.cp-formula {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: .84rem;
  line-height: 1.7;
  background: var(--cp-soft-2);
  border-left: 3px solid #7cae9a;
  border-radius: 0 8px 8px 0;
  padding: .65rem .85rem;
  margin: .4rem 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.cp-eyebrow {
  font-size: .72rem;
  font-weight: 750;
  letter-spacing: .13em;
  text-transform: uppercase;
  color: #247566;
  margin: .3rem 0 .5rem;
}
.cp-lead { font-size: 1.15rem; color: #46655d; line-height: 1.6; margin-bottom: .65rem; }
.cp-file { font-weight: 650; color: #234d41; overflow-wrap: anywhere; margin: .2rem 0; }
.cp-help { font-size: .84rem; color: var(--cp-muted); line-height: 1.6; }

/* Preserve familiar controls while keeping narrow screens usable. */
@media (max-width: 880px) {
  .stMainBlockContainer { padding-top: 1.4rem; }
  .st-key-overview_panel [data-testid="stMetric"] { min-height: 105px; }
  [data-testid="stMetricValue"] { font-size: 1.55rem; }
}
@media (max-width: 640px) {
  .stMainBlockContainer { padding: 1.1rem .85rem 5rem; }
  .stMainBlockContainer > div { gap: .9rem; }
  .st-key-campuspulse_header { padding: .1rem 0 .7rem; }
  .st-key-campuspulse_header h1 { font-size: 2.45rem !important; }
  .cp-lead { font-size: 1rem; }
  .cp-steps { gap: .35rem; }
  .cp-step { gap: .3rem; font-size: .72rem; align-items: flex-start; padding-top: .55rem; }
  .cp-step span { width: 1.45rem; height: 1.45rem; font-size: .64rem; border-radius: 7px; }
  [data-testid="stChatMessage"] { padding: .75rem .8rem; }
  [data-testid="stMetric"] { min-height: 95px; padding: .85rem; }
  [data-testid="stMetricValue"] { font-size: 1.5rem; }
  [data-testid="stForm"] { padding: .8rem; }
  .st-key-question_suggestions [data-testid="stButton"] button { min-height: 52px; padding: .7rem .8rem; }
  .cp-answer { font-size: 1.24rem; }
}
@media (prefers-reduced-motion: reduce) {
  [data-testid="stButton"] button,
  [data-testid="stDownloadButton"] button { transition: none; transform: none !important; }
}
</style>
"""


def styled_text(text: str, kind: str) -> None:
    """Only internal styles are allowed; content is never interpreted as markup."""
    if kind not in {"eyebrow", "lead", "answer", "formula", "file", "help"}:
        raise ValueError("Unknown text style")
    st.markdown(f'<div class="cp-{kind}">{escape(text)}</div>', unsafe_allow_html=True)


def progress_steps(stage: int) -> None:
    """Display the three upload-to-answer stages as an accessible progress strip."""
    labels = ["Add a report", "Check your data", "Explore & ask"]
    parts = []
    for index, label in enumerate(labels):
        state = "active" if index == stage else "done" if index < stage else ""
        number = "✓" if index < stage else f"0{index + 1}"
        current = ' aria-current="step"' if index == stage else ""
        parts.append(
            f'<div class="cp-step {state}"{current}>'
            f'<span aria-hidden="true">{number}</span>{label}</div>'
        )
    st.markdown(
        '<nav class="cp-steps" aria-label="CampusPulse progress">'
        + "".join(parts)
        + "</nav>",
        unsafe_allow_html=True,
    )
