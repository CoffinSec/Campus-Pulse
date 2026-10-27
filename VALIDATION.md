# Validation record

Validated in the cloud checkout using Python 3.12.14. This records actual execution, not a hosted deployment or a successful model demonstration.

| Check | Observed result |
|---|---|
| `python -m pytest -q` | **151 passed, 11 skipped**; skipped cases require opt-in live Gemma inference |
| `python -m scripts.smoke_test` | Passed: real PDF and CSV ingestion, normalization, ranking, comparison, trend, missing cost, charts and evidence |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed |
| `python -m pip check` | No broken requirements |
| `bash scripts/setup_cloud.sh` | Passed: repeatable pinned installation, dependency check and smoke |
| Running Streamlit service | Started; health endpoint returned HTTP 200 and `ok` |
| Real Chromium browser, 1440 × 1100 | Main-screen PDF upload, confirmation, immediate overview, winner-highlighted ranking, grouped comparison, visible missing-occupancy warning, actual PDF/CSV downloads and reset verified after a fresh server launch; no browser page errors |
| `python -m scripts.check_model` | **Unavailable, exit 1:** local Ollama endpoint refused connection |
| Gemini API provider (`GEMMA_PROVIDER=gemini`) | **Not run.** Code added without network access; syntax-compiled only. Needs `check_model` and live tests with a real key |
| Model catalog / registry requests | Blocked by network proxy policy with HTTP 403; exact candidate tag unverified |

Streamlit AppTest additionally exercises PDF-to-CSV replacement, stale-result clearing, confirmation gating, ranking/comparison/what-if controls, follow-ups tied to their own parent answer, response timing, and chat with explicitly mocked successful/invalid model output. Invalid explanation numbers preserve the calculated answer and produce a visible fallback. The mocked tests do not prove language understanding or real inference.

Additional tests cover per-student denominators, scenario scope and bounds, overview totals, prior-history anomaly flags without future-data leakage, explanation fact validation and remote consent, and single-page PDF generation across six analysis types. The browser-downloaded PDF was opened and visually inspected for its chart, formula, source citation and caveats. Main-screen upload and overview screenshots were also inspected; trend extrema labels are visible without clipping.

### UI refresh checked on 24 October 2026

Compared the supplied `Campus-Pulse-updated.zip` with the existing application and adapted its guided upload flow, prominent answer text, calculation styling, visible student mapping and image-export idea. The existing calculation engine, explanation validation and parent-specific follow-up handling were retained.

- Full suite: **151 passed, 11 skipped**; Ruff lint, format and whitespace checks passed.
- Chromium at **1440 × 1050** and **390 × 844**: actual PDF upload, confirmation, overview, manual ranking, PDF/PNG/CSV downloads and file reset passed, with no application exceptions.
- At mobile width, the page had no horizontal overflow. A separate CSV flow verified that the full multi-row formula and citation wrap within their container, with no browser page errors.
- AppTest verifies that comparison periods and scenario percentages appear only for the relevant analysis, that student mapping remains available, and that June scenario results remain **21,950 → 20,780 kWh** with **1,170 kWh** saved.
- PNG tests check the file signature and page aspect ratio against the PDF. The real browser download also returned valid PNG bytes. No new dependency or live inference is required for the UI or export changes.

The [landing screenshot](docs/screenshots/landing.png) is from the actual browser run. Mobile checks emulate viewport dimensions; they do not claim testing on a physical phone.

## Actual sample results

- PDF and CSV each extract 30 equivalent observations.
- June highest building: **Boys Hostel, 6,200 kWh**.
- May total: **21,100 kWh**; June total: **21,950 kWh**.
- Difference: **850 kWh**; percentage: **4.028436018957346…%**.
- Chronological monthly totals: **18,800; 19,000; 19,500; 20,150; 21,100; 21,950 kWh**.
- Unavailable cost produces no numeric answer and no chart.
- Overview: **120,500 kWh**, **5 buildings**, **6 months**; highest total **Boys Hostel, 32,200 kWh**.
- Browser Plotly inspection confirmed June ranking values **6,200; 5,600; 5,500; 3,100; 1,550 kWh**, with a different winner color, and grouped May/June bars whose sums match the totals above.
- June per-student usage: Boys Hostel **15.5 kWh/student**; Library is excluded with a visible missing-occupancy warning. Multi-month ratios are explicitly labelled per student-month.
- June hostels reduced by 10%: conditional saving **1,170 kWh**, campus total **21,950 → 20,780 kWh**. The baseline includes unaffected buildings.
- The smooth synthetic sample produces no anomaly flags. An injected spike is flagged in a test with its source row and “cause unknown” wording.

## Official-source verification

The official [Ollama README](https://github.com/ollama/ollama) and [Ollama Python client README](https://github.com/ollama/ollama-python) were successfully retrieved from their GitHub sources and document Gemma 4 usage. Access to `ollama.com`, `docs.ollama.com` and `registry.ollama.ai` was blocked. This confirms general documented support, **not** the availability or suitability of `gemma4:e2b` in this environment.

No model download was attempted. No other model or deterministic natural-language parser was substituted. No GPU performance, live inference, remote inference service, official university data, public deployment or GitHub CI run is claimed.

## Required before the live hackathon presentation

1. Permit access to the official model catalog/registry or use a trusted reachable Ollama endpoint.
2. Verify and explicitly install an official Gemma 4 tag suitable for the hardware; configure the exact tag in `OLLAMA_MODEL`.
3. Pass `python -m scripts.check_model`.
4. Run `RUN_LIVE_GEMMA=1 python -m pytest -m live -q` (remote endpoints also require `ALLOW_REMOTE_INFERENCE=1`).
5. Present the actual AI-assisted PDF workflow in [DEMO.md](DEMO.md). Manual mode is only a clearly labelled backup.

Python dependencies and generated demo files are retained on disk. Running services must restart in a new environment; see saved startup instructions. Draft configuration persistence, publication and fresh-task restoration are separate stages and are not established by the test results above.


## Multi-source change record — 27 October 2026

The original validation results above describe **older code** and must not be interpreted as current live-browser validation.

**Actually executed in this environment** (Python 3.13, not Python 3.12):

- `python -m pytest -q`: **222 passed, 19 skipped**. Existing Streamlit AppTest/UI state checks were skipped because Streamlit is absent here; the remaining skips are optional Google SDK and opt-in live-model tests. New deterministic source comparisons, explicit building-name review and previous single-file calculations passed.
- `python -m scripts.smoke_test`: **passed** PDF and CSV ingestion and original single-file numerical operations.
- Python bytecode compilation of `app.py` and `campuspulse/`: passed.
- Parsed genuine synthetic PDFs: original, second-half 2026, and overlapping-month variant all yielded one table with 30 rows.
- `python -m pip check`: reported an existing unrelated package conflict (`moviepy` requires Pillow under 12, container has Pillow 12.3). This is the sandbox environment, not an observed app deployment error.
- `python -m ruff check .` and `python -m ruff format --check .`: **not executed successfully** because Ruff is unavailable and package download failed (network blocked).
- Streamlit runtime/UI browser: **not tested** (Streamlit unavailable; package download failed).
- Live Gemma/Ollama/Gemini inference: **not tested**. `tests/test_live_multi_gemma.py` requires `RUN_LIVE_GEMMA=1` and reachable configured model.

Known limitations: PDF and PNG remain visual summary formats (the PDF embeds the entire evidence CSV as an attachment; the standalone evidence CSV includes every row, while the PNG remains a first-page summary); missing/nonoverlapping data cannot establish like-for-like causality. Existing browser-focused test assertions may require updates to reflect the multi-upload workflow once Streamlit is installed. Do not claim all CI checks passed on this build.


### Final packaged build

- Latest `python -m pytest -q`: **222 passed, 19 skipped** (Python 3.13 sandbox).
- `python -m scripts.smoke_test`: passed.
- `python -m compileall -q app.py campuspulse scripts tests`: passed.
- Ruff lint/format: unavailable because `ruff` is not installed here and no external package downloads succeeded. Run both locally before deployment.
- `python -m pip check`: returned an unrelated environment-wide MoviePy/Pillow conflict; it does not establish the lockfile as broken.
- Streamlit user interface, Google SDK integration, Google/Ollama live inference and multilingual accuracy: **not verified in this environment**.
- User-selected source labels are resolved conservatively (exact names), and model plans are still subject to strict allowlisted validation. This improves reliability but cannot guarantee that every free-form prompt is understood.
