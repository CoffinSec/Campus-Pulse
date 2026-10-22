# CampusPulse: a 3–5 minute demonstration

Preflight: run `python -m pytest -q`, `python -m scripts.smoke_test`, and `python -m scripts.check_model`. Start `python -m streamlit run app.py`. The first two can pass without AI. Before promising Gemma inference, pass the model check and opt-in live tests in the README. Live inference was unavailable during implementation.

## 0:00–0:30 · Problem

Say: “Campus reports contain useful measurements, but charts can hide missing data and unfair comparisons. CampusPulse lets someone ask a question, see the calculation and inspect the source.”

Show model status and the exact tag. Explain whether inference is local to the app server or remote. Do not call manual analysis AI.

## 0:30–1:15 · Upload and confirm

Upload `data/campus_electricity_sample.pdf` or use **Load synthetic PDF**. This really parses the PDF; it does not read the CSV instead.

Say: “This is SYNTHETIC DEMONSTRATION DATA: fictional buildings, with no official IIMT University data or endorsement.”

Show all three mapped fields, kWh units and page/table/row references. Check the review checkbox and **Confirm dataset**. Expect 30 observations, five buildings, six months and zero missing kWh cells.

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

These citations apply to the generated fixture; every upload receives its own extracted references. Show the bar chart and expand **View calculation**: month filter, grouped sum, descending sort. Expand **View source data**: all five candidates establish the winner.

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

Show the two bars and executed trace. Ten source rows contribute. Explain that a zero old value produces an undefined percentage, and unequal building coverage generates a warning.

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

Say: “Only the question and schema/category metadata go to Gemma, not the whole document. A remote endpoint receives disclosed metadata. A cloud app does not process everything on my laptop.”

Optionally load and confirm the CSV, then repeat the comparison to demonstrate the shared engine.

## Troubleshooting

| Problem | Action |
|---|---|
| Ollama disconnected | Start/install Ollama, check `OLLAMA_HOST`, run `python -m scripts.check_model`. |
| Model absent | Verify an official Gemma 4 tag, explicitly pull it, set `OLLAMA_MODEL`, restart the app. |
| Catalog blocked | Allow official catalog/registry destinations in environment settings; retry verification. |
| Timeout | Check server load and RAM/VRAM; choose a supported small tag or increase timeout. |
| Invalid model plan | Rephrase with explicit metric/building/month. Do not pretend a backup is AI. |
| Unsupported PDF | Use a searchable grid table or CSV; OCR/cross-page merging is not included. |
| Validation error | Correct mapping, units, periods, missing labels or duplicate building/month records. |
| Replaced file | Confirm the new dataset; old answers are intentionally cleared. |

**Disconnected backup:** load/confirm the PDF, open **Manual analysis · no AI**, select Highest building and June, then Period comparison, Monthly trend and Unavailable cost. This demonstrates ingestion, math, charts and evidence only. Explicitly state that live Gemma is not demonstrated and the track requirement remains incomplete.
