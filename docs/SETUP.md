# Setup and verification

[Back to CampusPulse](../README.md)

The main README is the project overview. This guide keeps installation commands and configuration examples in one place.

## Install the app

Use Python 3.11 or newer; the recorded cloud checks used Python 3.12. Run these commands from the repository root.

### Linux or macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
python -m streamlit run app.py
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The app can load sample data and run manual calculations without an API key. Natural-language planning and AI explanations need the hosted service configured below. Python installation does not download a model.

The runtime dependencies are in [requirements.txt](../requirements.txt). The existing [lock file](../requirements-lock.txt) records an earlier environment and does not include every later addition, such as the Google SDK listed in the runtime requirements.

## Configure hosted inference

The current [model client](../campuspulse/gemma_client.py) makes HTTP requests to Google's Gemini API. Obtain a key through [Google AI Studio](https://aistudio.google.com/apikey), verify that your account can access the model you choose, and edit your local `.env`:

```dotenv
GEMMA_PROVIDER=gemini
GEMINI_API_KEY=replace_with_your_own_key
GEMINI_MODEL=gemma-4-26b-a4b-it
APP_TIMEZONE=Asia/Kolkata
```

The model identifier above is the repository's configured default, not a guarantee of availability for your account. Never commit `.env` or share an actual key in screenshots. `.gitignore` excludes environment files; `.env.example` is only a template. Restart Streamlit after changing configuration.

Despite the app's current local-connection label, these requests go to Google. The current question flow also passes remote permission internally rather than displaying a separate consent gate. Use data you are comfortable sending to that service. The uploaded file is not sent as an attachment, but question text, schema labels, context and computed facts are transmitted.

Ollama configuration fields remain from earlier versions. Setting `GEMMA_PROVIDER=ollama` currently does not switch the model client to Ollama, so this guide does not present it as a working local-inference option.

## Check a real API request

With the virtual environment active:

```bash
python -m scripts.check_model
```

This command makes a live planning request and may consume API quota. It requires a valid key and available model. A successful request verifies that a reply was received; it does not prove every natural-language question will be interpreted correctly. The connection badge alone only reflects whether a key was supplied.

The current client uses a 300-second HTTP timeout and permits up to 2,048 output tokens. The planner may retry an invalid plan once, and successful calculations can trigger a separate explanation call. Older Ollama timeout settings do not control this hosted request. For immediate exploration while the service is slow or unavailable, use the manual calculator.

## Prepare a report

A minimal CSV looks like this:

```csv
building_name,month,electricity_kwh
Academic Block A,2026-05,5200
Academic Block A,2026-06,5600
```

These readings are synthetic examples. Use one row per building and month. Electricity must be in kWh. Supported month formats include `2026-06`, `2026-06-15`, `June 2026` and `Jun 2026`; month names without a year require an explicit year during review.

Optional mappings include `building_id`, `department`, `occupancy`, `electricity_cost_inr` and `tariff_inr_per_kwh`. The custom-rate workflow derives estimated INR amounts only when you explicitly select a global rate; see the [rate guide](../CUSTOM_RATE_GUIDE.md). Recorded bill amounts and estimated costs are distinct.

To recreate the fictional sample files:

```bash
python -m scripts.generate_demo_data
```

This rewrites the bundled sample PDF and CSV.

## Run checks

Install developer tools, then run the offline checks:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m scripts.smoke_test
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

The current imported version has known test and lint failures; the README records the last observed counts. Some provider tests still expect older client behavior. Earlier passing results in the historical validation document should not be treated as proof that the current suite passes.

The root `test_api.py` is a diagnostic script that contacts Google's API and probes models. It is not part of the default `tests/` collection. Do not run it as an offline check.

The repository also contains opt-in live tests:

```bash
RUN_LIVE_GEMMA=1 ALLOW_REMOTE_INFERENCE=1 python -m pytest -m live -q
```

PowerShell:

```powershell
$env:RUN_LIVE_GEMMA = "1"
$env:ALLOW_REMOTE_INFERENCE = "1"
.\.venv\Scripts\python.exe -m pytest -m live -q
```

These tests contact the configured service and may consume quota. The opt-in environment variable does not add a consent screen to the current app. Confirm the actual model and provider used when reporting live results.
