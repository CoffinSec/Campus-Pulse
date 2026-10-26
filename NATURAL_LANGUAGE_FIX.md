# Natural-language question fix

Previous versions accepted a few *exact* summary strings (e.g. `give me a summary`).
Misspellings and rewordings were sent to the structured calculation planner, which
sometimes selected `clarification` and displayed the unhelpful “specify the metric,
building and/or two periods” message.

## What's changed

- Everyday whole-report requests such as `cam you give me a summary??`, `summry
  plz`, `Explain this report`, `report ka summary batao`, and `What does my report
  say?` now return an immediate verified overview.
- The overview is calculated using the uploaded and confirmed data, including
  actual kWh totals, the highest-use building, observed monthly first/last change,
  and missing numeric cells. No fixture-specific data is hardcoded in answers.
- Requests mentioning a specific building, month, cost, per-student calculation,
  or comparison still go to Gemma for precise interpretation.
- Gemma's schema now includes `report_overview`, so even novel non-keyword
  questions can be recognized as a broad request without hallucinating a
  calculation or asking for comparison periods.
- A genuine ambiguous calculation gets a friendlier clarification message.
- Strict typed-plan validation and trustworthy Python arithmetic remain intact.

## Install

1. Extract this project archive.
2. Copy your existing `.env` into the newly extracted project folder. This
   archive deliberately contains no API credentials.
3. Install project dependencies: `pip install -r requirements.txt`
4. Start it normally: `streamlit run app.py`

If Streamlit is already running, stop it and restart so Python loads the new
source files.

## Testing

Network-free regression tests for natural-language handling plus supported
calculations passed: 116 tests. The live Google API and full Streamlit UI were
not exercised in this environment. Certain older tests in the source project
still assert Ollama behavior despite the hosted-Gemini adaptation; those were
not fixed in this patch.

## Scope

CampusPulse is an assistant for answering questions **about the uploaded
campus-electricity report**. It is not unrestricted general chat: unrelated or
unverifiable requests may still be declined. Numeric claims remain derived
from the actual imported data.
