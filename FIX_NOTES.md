# CampusPulse AI plan validation fix

Fixes in this package:

- Reads final Gemini API output instead of mistaking a `thought: true` response part for JSON.
- Enables Gemma 4 minimal thinking to reduce waiting for simple plans.
- Sends the Google API key in a request header, not in a URL.
- Extracts complete JSON objects from prose/fenced responses and safely retries once if a plan fails strict validation.
- Handles `hi`, `hello`, `give me a summary`, and similar report-wide summary requests without an API call. Summaries calculate values directly from the loaded report, not from hallucinated AI numbers.
- Retains strict validation and original source-linked calculations.

**Setup**: The `.env` file and API key are intentionally **not included** in this downloadable archive. Copy your original `.env` from your own project into this project's root folder. Never publish it to GitHub. Restart with `streamlit run app.py`.

**Important:** The Google Gemini API is a **hosted/online** Gemma model, not a local offline model, regardless of any UI badge. Live API inference could not be tested without calling the external service. See `tests/test_fix_regressions.py` for network-free regression tests.
