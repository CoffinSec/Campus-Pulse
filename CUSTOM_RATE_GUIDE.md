# CampusPulse — global electricity rate (INR)

## How to use

1. Upload a PDF or CSV and open **2. Check your data**.
2. In **Electricity cost (INR)** choose **Other — enter a custom ₹/kWh rate**. The input appears immediately.
3. Enter e.g. **10** and confirm the source columns and dataset.
4. All buildings and months have the same estimated rate; ask **What is the total electricity cost?**, **Show monthly cost trend**, or choose **Electricity cost (INR)** under the manual calculator's **Calculate using** selector.
5. Change the active rate later under **Electricity cost (INR) · change global rate**, then click **Apply electricity rate to all data**. Previous calculation history is cleared to avoid mixing rates.

## Calculation and safeguards

For every observation (building × month):

`estimated electricity_cost_inr = electricity_kwh × custom tariff_inr_per_kwh`

- Example at ₹10/kWh: 120,500 kWh across the sample → **₹1,205,000** estimated cost.
- The setting applies consistently to rankings, comparisons, trends, answers, CSV evidence, screenshots and PDF answers generated from those calculations.
- The original uploaded PDF/CSV is not rewritten. Calculated INR values are derived from verified kWh in memory and presented as estimates.
- Cost results show original kWh, global INR/kWh and derived INR in evidence. Missing source kWh remain missing; never replaced with zero.
- A custom flat rate is **not** an actual utility bill: slab tariffs, fixed charges, duties and taxes are not modelled.
- To use the original report's cost values, select its column (rather than Other); or select **From uploaded report** when changing rate later.
- Does not change kWh or occupancy calculations.

## Checks

Offline tests: `python -m pytest -q tests/test_custom_tariff.py`.
Full offline smoke: `python -m scripts.smoke_test`.

The hosted model and interactive Streamlit browser were not exercised in the build environment.


## Multiple files

Each confirmed source retains original kWh and billing fields in memory. Choose **Other — custom rate** under electricity cost to apply the same rate to **every confirmed source**. The combined estimated-cost view includes source ID and label. Changing the global rate rebuilds the dataset from original normalized source data and clears previous answers, preventing stale cost comparisons. Do not add cost totals across overlapping reports without checking duplicate coverage; the UI warns when a building/month exists in multiple sources.


## Multiple confirmed files

The active rate is **one session-global rate**, not a rate per source. After
confirming 2+ files, select `Other — custom rate` in the global rate panel,
enter INR/kWh and click **Apply electricity rate to all data**. Rebuilding from
original validated datasets applies the rate consistently to every source and
clears stale answer history. Source comparison reports estimated INR amounts,
not actual bills. Original tariff/cost data remain in source-specific datasets;
with no global override, only mapped recorded amounts are used.
