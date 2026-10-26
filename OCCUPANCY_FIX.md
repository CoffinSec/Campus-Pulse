# Occupancy correction

- Monthly occupancy is a headcount. For generic occupancy totals/rankings/building comparisons the calculation now uses the most recent selected month only (e.g. June 2026), not the sum across 6 months. Explicit monthly trends, period comparisons and averages retain their requested periods.
- For the included sample PDF/CSV the Library occupancy values are genuinely empty for all 6 months. No value has been invented. The result displays Library: unavailable.
- The repeated optional occupancy missing-values warning is not shown in the dashboard/chat; the source data and underlying caveats remain unchanged. Non-occupancy missing-data warnings continue.
- Report-wide summaries no longer repeat the optional occupancy missing-data warning.
- Run with `streamlit run app.py`; reload/reconfirm the PDF after upgrading.
