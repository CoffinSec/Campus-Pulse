# CampusPulse: a 3–5 minute demonstration

Preflight: run `python -m pytest -q`, `python -m scripts.smoke_test`, and `python -m scripts.check_model`. Start `python -m streamlit run app.py`. The first two can pass without AI. Before promising Gemma inference, pass the model check and opt-in live tests in the README. Live inference was unavailable during implementation.

## 0:00–0:30 · Problem

Say: “Campus reports contain useful measurements, but charts can hide missing data and unfair comparisons. CampusPulse lets someone ask a question, see the calculation and inspect the source.”

Show model status and the exact tag in **Connection settings** beside the app title. Explain whether inference is local to the app server (Ollama) or remote (Gemini API: Gemma 4 26B hosted by Google). State it plainly; the track asks for Gemma 4, and the README names the model and provider. Do not call manual analysis AI.

## 0:30–1:15 · Upload and confirm

Upload `data/campus_electricity_sample.pdf` or use **Load synthetic PDF**. This really parses the PDF; it does not read the CSV instead.

Say: “This is SYNTHETIC DEMONSTRATION DATA: fictional buildings, with no official IIMT University data or endorsement.”

Show the core fields, optional student counts, kWh units and page/table/row references. Check the review checkbox and **Confirm dataset**. The immediate overview shows 120,500 kWh, five buildings, six months, Boys Hostel as the highest building and an annotated trend. All 30 kWh readings exist; Library student counts are intentionally missing.

## 1:15–2:00 · Ranking

Ask: **Which building consumed the most electricity in June 2026?**

Expected: **Boys Hostel, 6,200 kWh**.

| Building | June kWh | PDF page/table/row | CSV physical line |
|---|---:|---|---:|
| Academic Block A | 5,600 | 1 / 1 / 27 | 27 |
| Academic Block B | 3,100 | 1 / 1 / 28 | 28 |
| Boys Hostel | 6,200 | 1 / 1 / 29 | 29 |
| Girls Hostel | 5,500 | 1 / 1 / 30 | 30 |
| Library | 1,550 | 1 / 1 / 31 | 31 |

These citations apply to the generated fixture; every upload receives its own extracted references. Show the winner-highlighted chart with value labels. The plain-language interpretation, actual formula and row reference are already visible under the answer. Open **Source readings** only if you need all five comparison candidates; JSON is never shown.

Say: “Gemma chooses a validated operation. Python computes the number. These rows are the evidence.”

## 2:00–2:45 · Period comparison

Ask: **Compare May 2026 and June 2026 electricity consumption.**

```text
May  = 5200 + 3200 + 5800 + 5300 + 1600 = 21100 kWh
June = 5600 + 3100 + 6200 + 5500 + 1550 = 21950 kWh
Absolute change = 21950 - 21100 = 850 kWh
Percentage change = ((21950 - 21100) / 21100) × 100
                  = 4.028436018957346...% (display: 4.03%)
```

Show May/June grouped bars for each building, plus overall change and percentage metric cards. Read the inline formula. Ten source rows contribute. Explain that a zero old value produces an undefined percentage, and unequal building coverage generates a warning.

## 2:45–3:15 · Trend

Ask: **Show the monthly electricity consumption trend.**

| 2026 month | Total kWh |
|---|---:|
| January | 18,800 |
| February | 19,000 |
| March | 19,500 |
| April | 20,150 |
| May | 21,100 |
| June | 21,950 |

Show chronological ordering. Say: “Observed totals increase over this interval; this is not evidence of a cause, waste or statistical significance.”

Other verified fixture results: six-month total **120,500 kWh**; observation mean **4,016.6666… kWh**; monthly-total mean **20,083.3333… kWh**; building-total mean **24,100 kWh**. Always show the denominator.

## 3:15–3:45 · Unavailable information

Ask: **What was the electricity cost in December 2026?**

Expected: unavailable, no guessed number, no chart. This dataset has no cost field/tariff calculation and no December observations. The cost guard explains missing cost data. Ask **What was total electricity consumption in December 2026?** to demonstrate the absent-period check separately.

Optional: **Which building wastes the most electricity?** Consumption alone cannot establish waste.

## 3:45–4:30 · Language and privacy

After passing live tests, try: **June 2026 mein sabse zyada electricity kis building ne use ki?** or **जून 2026 में किस इमारत ने सबसे अधिक बिजली का उपयोग किया?** The ranking remains Boys Hostel, 6,200 kWh.

Say: “Gemma receives the question, schema/category metadata, prior plan for follow-ups and computed facts for explanations, not the whole document. A remote endpoint receives disclosed metadata. A cloud app does not process everything on my laptop.”

Optionally load and confirm the CSV, then repeat the comparison to demonstrate the shared engine.

## Troubleshooting

| Problem | Action |
|---|---|
| Gemini offline badge | Check `GEMINI_API_KEY`, `GEMINI_MODEL=gemma-4-26b-a4b-it`, internet and quota; run `python -m scripts.check_model`. |
| Ollama disconnected | Start/install Ollama, check `OLLAMA_HOST`, run `python -m scripts.check_model`. |
| Model absent | Verify an official Gemma 4 tag, explicitly pull it, set `OLLAMA_MODEL`, restart the app. |
| Catalog blocked | Allow official catalog/registry destinations in environment settings; retry verification. |
| Timeout | Check server load and RAM/VRAM; choose a supported small tag or increase timeout. |
| Invalid model plan | Rephrase with explicit metric/building/month. Do not pretend a backup is AI. |
| Unsupported PDF | Use a searchable grid table or CSV; OCR/cross-page merging is not included. |
| Validation error | Correct mapping, units, periods, missing labels or duplicate building/month records. |
| Replaced file | Confirm the new dataset; old answers are intentionally cleared. |

**Disconnected backup:** load/confirm the PDF, open **Choose a calculation · no AI needed**, select Highest building and June, then Period comparison, Monthly trend and Unavailable cost. The controls change with the analysis. This demonstrates ingestion, math, charts and evidence only. Explicitly state that live Gemma is not demonstrated and the track requirement remains incomplete.


## Optional high-impact extensions

- Ask **Compare kWh per student in June 2026.** Expected: Academic Block A **7**, Academic Block B **5.1666…**, Boys Hostel **15.5**, Girls Hostel **15.7142… kWh/student**. The visible warning says **Library: no occupancy data for one or more selected months, can’t compare.** The missing value is never filled with zero. Multiple months instead use student-months, explicitly labelled.
- Follow the June ranking with **and in May?** Expected Boys Hostel **5,800 kWh**. Click **What about hostels only?** on an answer to scope its own plan. Real language interpretation requires a connected Gemma; offline tests mock that part explicitly.
- Ask **What if the hostels cut usage by 10% in June 2026?** Hostels total **11,700 kWh**; saving **1,170 kWh**; campus total **21,950 − 1,170 = 20,780 kWh**, a **5.33%** campus reduction. The requested 10% applies only to the hostels, not the whole campus. The chart and caveat identify this as conditional.
- Show the **What this means / what could be checked** box. Gemma supplies prose using verified fact references; unverified numerical claims cause a visible fallback. Hindi questions request Hindi explanatory prose. Suggested checks are not established causes.
- Download the one-page PDF, a PNG of the same report, or source CSV directly beneath an answer.
- The bundled smooth series has no anomaly flags. The automated spike fixture proves detection without fabricating an anomaly in the sample; the UI always states “cause unknown” for flags. A flag needs at least three prior valid monthly changes.


## Multi-file / custom theme demo (October 2026)

1. Run `python -m scripts.generate_demo_data`, then launch Streamlit.
2. Use **Load two synthetic samples** and confirm the original and overlap report separately. Both are fictional.
3. Select both in **Sources to use** and ask `Compare both reports by building`; verify the plain-language source scope, grouped bars and calculated changes. Or use **Choose a calculation · no AI needed → Compare reports**.
4. Ask `Trend per file` / `Dono files ka trend dikhao` / `दो रिपोर्ट का मासिक ट्रेंड दिखाओ` for multi-line trends.
5. Upload `campus_electricity_sample_h2.pdf` instead of the overlap report to show nonoverlapping-month caveat.
6. Set **Other → ₹10 per kWh** and re-run a cost comparison. All sources share the rate; taxes, fixed charges and slabs are not included.
7. Download evidence CSV and answer PDF/PNG to show source names, original file/table/page/row citations, and warnings. Do not present synthetic figures as institutional readings.
8. The champagne/rose-gold/dark-cherry UI is a visual theme, not evidence that an AI has passed live tests.

Remote Gemma API responses and Hindi/Hinglish understanding must be demonstrated on an actual reachable model. The offline tests use mocked plans and deterministic calculations; those alone do not establish live inference quality.


## Multi-file live demo (synthetic data only)

1. Click **Load two synthetic samples** and confirm **each pending file**
   separately (select columns, verify units, tick checkbox). Both reports have
   the same months by design, so comparing differences is meaningful.
2. Observe both confirmed source labels and source row counts; rename one
   source to `Revised report`.
3. Under **Sources to use**, keep both selected. In offline manual mode choose
   **Compare reports**. The grouped chart and change table use the two source
   labels; no row from one source overwrites the other.
4. If Gemma is configured and remote consent granted where applicable, ask:
   `Which building used more in the revised report?`; `dono reports compare karo`;
   `दोनों रिपोर्टों की मासिक प्रवृत्ति दिखाओ` (interpretation remains unverified
   until a real model test runs).
5. Inspect **How this was calculated**, then download CSV/PDF evidence.
   Select only the first source and ask a ranking question to show source scope.
6. Remove one report; previous answers disappear. Re-uploading is allowed.
7. Enter one global INR/kWh rate and show estimated, not billed, cost.

If model access is unavailable, do not label manual calculations as Gemma output.
