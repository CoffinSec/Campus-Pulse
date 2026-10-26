# CampusPulse UI polish (original colours preserved)

This edition starts from **Campus-Pulse-Custom-Rate** and changes presentation only.

## What changed

- Retained the existing off-white, white and green/teal theme from `.streamlit/config.toml` and `campuspulse/ui.py`.
- Improved the header layout, spacing, progress-strip semantics, dashboard metric-card consistency, input/card alignment, chat results and responsive layout.
- Made suggested question buttons easier to scan and use on mobile.
- Kept calculations visible under the **Calculation breakdown & result table** expander, with source readings still available separately.
- Made report summaries and explanation text easier to read.
- Changed misleading `OLLAMA_MODEL=... STATUS=RUNNING` in *Connection settings* to a neutral model/status display that works for API and local modes.

## Files changed

- `app.py` — Streamlit layout containers and presentation of existing information.
- `campuspulse/ui.py` — CSS and accessible progress markup.

Business logic in `campuspulse/analysis_engine.py`, `normalization.py`, `gemma_client.py`, planners, calculations, exports and the custom electricity tariff feature was not changed. The original demo PDF and CSV are unchanged.

## Run

From the extracted project directory:

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Use the `.env` file from your existing working installation. **Do not commit `.env` or your API key**.

## Validation

- Python compilation and structural checks completed.
- Backend source, sample data and existing tests verified unchanged against the uploaded custom-rate ZIP.
- Full Streamlit browser rendering and pytest execution could not be run in the packaging environment because the dependencies could not be downloaded. Please verify on your local machine and run `python -m pytest -q` before committing.
