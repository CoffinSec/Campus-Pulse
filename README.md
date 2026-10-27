# ⚡ CampusPulse

**Understand campus electricity. See the calculation. Follow the evidence.**

Turn a campus PDF or CSV into a clear overview, useful comparisons and answers you can trace back to the original readings. Ask questions in English, Hindi or Hinglish, then explore the chart, formula and source rows together.

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Hackathon](https://img.shields.io/badge/Hacktoberfest-Hackday%202026-orange)

[Get started](docs/SETUP.md) · [Try the demo](#try-the-demo) · [Features](#what-you-can-do) · [Data format](#supported-data) · [Documentation](#documentation)

![CampusPulse upload screen showing the guided workflow and sample reports](docs/screenshots/landing.png)

*Upload-screen preview from an earlier UI revision. The current app includes further layout and custom-rate improvements.*

Built for **Hacktoberfest Hackday 2026 · Track 1 — Best Use of Gemma 4 · PS 03 — Community and Environmental Data Intelligence**.

The pilot context is IIMT University, Meerut, India. CampusPulse is an independent prototype with no university endorsement. The bundled reports contain **synthetic demonstration data**, not official campus records.

## Why CampusPulse

A total alone does not explain which building changed, whether a comparison is fair, or where a number came from. CampusPulse connects each answer to the data behind it.

Gemma helps interpret the question. Python performs the calculation. The app shows the result, its working and any missing information so users can check the answer themselves.

## What you can do

| Task | What you see |
|---|---|
| Understand a report | Total electricity, building count, months covered, highest-use building and a trend before asking a question |
| Compare buildings and months | Rankings with highlighted results, labelled bars, grouped comparisons and changes |
| Compare usage per student | Ratios based on available student counts, with named warnings when a building cannot be compared |
| Review occupancy | A headcount snapshot for the latest selected month, rather than adding the same students across months |
| Estimate electricity cost | An explicitly chosen flat ₹/kWh rate applied to all buildings and months, with costs labelled as estimates |
| Explore changes | Unusual changes against each building's own history, with the cause left unknown |
| Try a what-if scenario | Calculated savings and before/after usage for a specified reduction |
| Verify and share an answer | Visible formulas, original row references, caveats, and PDF, PNG or CSV downloads |

Follow-up questions such as **“and in May?”** use the previous validated plan. A manual calculator is available for exploring the data without AI.

## How it works

**Upload → Review → Ask → Calculate → Verify**

1. **Upload** a searchable PDF table or CSV.
2. **Review** the extracted table, column meanings and units before confirming.
3. **Ask** a question, or choose a manual calculation.
4. **Calculate** using predefined Python operations on the confirmed data.
5. **Verify** the chart, arithmetic, source rows and visible caveats.

The calculation engine executes predefined operations; it does not execute model-generated code. A valid plan can still misinterpret a question, so the displayed interpretation and working remain important.

## Try the demo

Start with the included [sample PDF](data/campus_electricity_sample.pdf) or [sample CSV](data/campus_electricity_sample.csv). Both contain the same fictional campus readings.

1. Open the app using the [setup guide](docs/SETUP.md).
2. Select **Load synthetic PDF** or upload a file.
3. Review the column mapping and select **Confirm dataset**.
4. Explore the overview, then try a question:

   - “Which building consumed the most electricity in June 2026?”
   - “Compare May and June 2026.”
   - “Show the monthly electricity trend.”
   - “Compare kWh per student in June.”
   - “What if the hostels cut usage by 10% in June?”
   - “जून 2026 में किस इमारत ने सबसे अधिक बिजली का उपयोग किया?”

5. Read **How this was calculated** and save the answer as a report or image.

### Numbers you can check

| Sample result | Value |
|---|---|
| Coverage | 5 buildings · January–June 2026 · 30 readings |
| Total electricity | 120,500 kWh |
| Highest-use building in June | Boys Hostel · 6,200 kWh |
| May → June campus total | 21,100 → 21,950 kWh |
| June usage per student, Boys Hostel | 15.5 kWh/student |
| June saving if both hostels reduce usage by 10% | 1,170 kWh |

Library student counts are intentionally missing. The app excludes it from per-student comparisons rather than inventing a denominator. Across several months, the ratio is labelled **kWh/student-month**.

### Estimate costs with your own rate

On **Check your data**, select **Other — enter a custom ₹/kWh rate** under **Electricity cost (INR)**. The app calculates estimated cost as **electricity usage × your rate**.

You can change the rate later using **Apply electricity rate to all data**. Previous answers are cleared so results from different rates are not mixed. See the [custom-rate guide](CUSTOM_RATE_GUIDE.md).

These are estimates, not utility bills: fixed charges, taxes and tiered tariffs are excluded. Without recorded costs or an explicitly selected rate, kWh alone cannot establish a bill amount.

## Supported data

| Column | Meaning | Required? |
|---|---|---|
| Building | Building, block or hostel name | Yes |
| Month | A month with a year, such as June 2026 | Yes |
| Electricity | Consumption in kWh | Yes |
| Occupancy | Student count for that building and month | For per-student analysis |
| Electricity cost | Recorded cost in INR | Optional |
| Department or building ID | Additional categories | Optional |

Column aliases are suggested during review. One observation per building and month is expected. Missing values remain missing, zero remains a measurement, and duplicate building/month records must be resolved before analysis. Convert Wh or MWh to kWh before uploading.

**PDF support:** searchable tables, especially clear grid layouts. Scanned PDFs need OCR outside the app. Multiple tables are detected, but one table is analysed at a time; use a consolidated CSV for a report split across pages. The default upload limit is **10 MB**.

## AI and data handling

The current model client sends requests to **Google's hosted Gemini API**, using the configured Gemma model. It requires an API key, internet access and available quota. Local Ollama settings remain in the repository, but the current client does not route inference through them.

Planning sends the question, schema, category labels and previous validated plan. Explanation requests send computed facts and caveats. These paths do not send the uploaded file itself or its full table of readings. Labels and questions can still contain sensitive information.

**Current UI limitation:** the connection panel labels inference as local, although the client calls Google's API, and the current question flow does not require a separate consent checkbox. Treat AI requests as remote processing. A “connected” badge checks for a configured key; it does not prove a successful API call.

Uploads and results are held in the app session. Keep API keys in your local environment file and never commit them. See the [setup and verification guide](docs/SETUP.md) for configuration details.

## Project status

CampusPulse is a working prototype with known issues. The latest recorded offline check of the imported application produced **199 passed, 12 failed and 14 skipped tests**, with **4 lint issues**. The suite is not fully passing, and those checks do not establish live model quality, API availability or laptop performance.

The project supports electricity analysis, headcount comparisons and flat-rate cost estimates. OCR, automatic table merging, utility billing rules and causal explanations remain outside its scope. Consumption alone does not prove waste or inefficiency.

**Stack:** Python, Streamlit, pandas, NumPy, PyMuPDF, Plotly, Pydantic and HTTPX. No database or separate API service is required.

## Documentation

| Guide | Purpose |
|---|---|
| [Setup and verification](docs/SETUP.md) | Installation commands, API configuration and checks |
| [Demo walkthrough](DEMO.md) | Example questions, calculations and presentation flow |
| [Custom electricity rate](CUSTOM_RATE_GUIDE.md) | Estimate costs and change the active rate |
| [Occupancy correction](OCCUPANCY_FIX.md) | Headcount handling and missing student data |
| [Architecture](ARCHITECTURE.md) | Components and calculation boundaries |
| [Historical validation record](VALIDATION.md) | Earlier check results; some predate the current imported version |

## License

A project distribution license has not yet been selected. Dependencies retain their own licenses, including PyMuPDF's AGPL/commercial terms. Choose an appropriate project license before distributing the repository as open source.
