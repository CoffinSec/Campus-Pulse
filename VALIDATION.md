# Validation record

Validated in the cloud checkout using Python 3.12.14. This records actual execution, not a hosted deployment or a successful model demonstration.

| Check | Observed result |
|---|---|
| `python -m pytest -q` | **109 passed, 6 skipped**; skipped cases require opt-in live Gemma inference |
| `python -m scripts.smoke_test` | Passed: real PDF and CSV ingestion, normalization, ranking, comparison, trend, missing cost, charts and evidence |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed |
| `python -m pip check` | No broken requirements |
| `bash scripts/setup_cloud.sh` | Passed: repeatable pinned installation, dependency check and smoke |
| Running Streamlit service | Started; health endpoint returned HTTP 200 and `ok` |
| Real Chromium browser, 1440 × 1050 | PDF file upload, review/confirmation, manual result, actual Plotly rendering, evidence export control and session reset verified; no browser page errors in the upload workflow |
| `python -m scripts.check_model` | **Unavailable, exit 1:** local Ollama endpoint refused connection |
| Model catalog / registry requests | Blocked by network proxy policy with HTTP 403; exact candidate tag unverified |

Streamlit AppTest additionally exercises PDF-to-CSV replacement, stale-result clearing, confirmation gating, ranking/comparison, and chat with explicitly mocked successful/invalid model output. The mocked tests do not prove language understanding or real inference.

## Actual sample results

- PDF and CSV each extract 30 equivalent observations.
- June highest building: **Boys Hostel, 6,200 kWh**.
- May total: **21,100 kWh**; June total: **21,950 kWh**.
- Difference: **850 kWh**; percentage: **4.028436018957346…%**.
- Chronological monthly totals: **18,800; 19,000; 19,500; 20,150; 21,100; 21,950 kWh**.
- Unavailable cost produces no numeric answer and no chart.
- Browser Plotly inspection confirmed the displayed all-month ranking value **32,200 kWh** for Boys Hostel, computed from its six source observations.

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
