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
| Model catalog / registry requests | Blocked by network proxy policy with HTTP 403; exact candidate tag unverified |

Streamlit AppTest additionally exercises PDF-to-CSV replacement, stale-result clearing, confirmation gating, ranking/comparison/what-if controls, follow-ups tied to their own parent answer, response timing, and chat with explicitly mocked successful/invalid model output. Invalid explanation numbers preserve the calculated answer and produce a visible fallback. The mocked tests do not prove language understanding or real inference.

Additional tests cover per-student denominators, scenario scope and bounds, overview totals, prior-history anomaly flags without future-data leakage, explanation fact validation and remote consent, and single-page PDF generation across six analysis types. The browser-downloaded PDF was opened and visually inspected for its chart, formula, source citation and caveats. Main-screen upload and overview screenshots were also inspected; trend extrema labels are visible without clipping.

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
