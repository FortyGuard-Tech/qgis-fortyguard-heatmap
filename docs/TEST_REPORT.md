# Test report – FortyGuard Heatmap QGIS plugin 0.3.1 (code identical to 0.3.0 except dialog text)

Environment actually used: macOS 27 (Darwin 27.0.0, Apple Silicon), QGIS
3.44.15-Solothurn (`/Applications/QGIS.app`), Qt 5.15.19, PyQt 5.15.10,
QGIS-bundled Python 3.12.11. System Python 3.9.6 for the pure tests.
Dates: 2026-10-12 and 2026-10-13. **No other operating system or QGIS version
was tested.**

## 1. Automated tests – executed

Command: `scripts/run_tests.sh` (last run 2026-10-13 after the 0.3.0 changes).
Result: **131 tests, 130 passed, 1 skipped, 0 failed** (70 of them also pass
on plain system Python without QGIS).

| Suite | Covers | Tests |
|-------|--------|-------|
| `test_payload.py` | tcm payload per filter type, date/time formats and documented bounds, granularity, polygon validation; **analysis payloads: threshold + direction only for exceedance/persistence, omitted for tcm/time_of_measure, threshold required/bounded/numeric, only "above", single hour rejected for analyses, request summary with threshold; calendar month: leap years (2024-02-29, 2023-02-28, 2100-02-28), 31-day month passes the ≤ 31-day rule, current month clipped to now + 12 h, future months rejected, months before 2019 rejected, single-available-day case** | 46 |
| `test_responses.py` | envelopes, HTTP classification, `details.message`, terminal states, result extraction, measures, NULL values, stats keys, usage endpoint; **schema detection (temperature / aggregate / value / none), real cached exceedance + persistence samples (`tests/fixtures/real_*_sample.json`, MIT), zero duration counted as valid, all-missing case, midnight (0) peak hour valid and tie-breaking, out-of-range hours flagged, analysis stats tolerant of junk** | 31 |
| `test_polling.py` | polling policy | 7 |
| `test_qgis_geometry.py` | selection rules, EPSG:3857→4326 with holes, MultiPolygon, invalid geometry | 6 |
| `test_qgis_output_styling.py` | tcm save/load/style/restyle/persistence; **exceedance legend in `h` with 0 in the first class and threshold in the layer name and custom properties, persistence legend, peak-time six fixed clock classes `00:00 - 03:59 UTC` … `20:00 - 23:59 UTC`, file prefixes per analysis, temperature style unchanged** | 11 |
| `test_qgis_job.py` | real `QgsNetworkAccessManager` against a scripted server, usage endpoint, demo client | 16 |
| `test_qgis_dialog_demo.py` | plugin lifecycle, tcm Demo Mode (single hour + daily), defaults, environment switch, credits check; **four analysis choices with explanations, threshold shown only for exceedance/persistence (default 35 °C), measure combo disabled for analyses, Single hour disabled for analyses with an explanation and automatic switch to Single day, calendar month → `filter_type 4` with first/last day, exceedance demo layer + summary (% of valid tiles, maximum, valid count), peak-time demo layer + UTC summary, three results become three separate layers** | 15 |
| `test_qgis_credentials.py` | `mask()`; encrypted store (opt-in, **skipped** headless) | 2 |

## 2. Checks inside the real QGIS application – executed

| Script | What it proved | Evidence |
|--------|----------------|----------|
| `scripts/qgis_gui_check.py` (Demo Mode, 0.3.0 dialog) | install/load, toolbar icon, dialog, EPSG:3857 demo AOI, tcm demo layer styled, screenshot, project save/clear/reopen, **exceedance demo pass: threshold visible, layer "Exceedance hours … above 35 °C", legend in h, summary "31.5% of valid tiles (57) have more than 0 h above 35 °C; maximum 34.8 h; 1 missing"**, clean unload | `dist/gui_check_report.json`, `dist/gui_check_canvas.png` |
| `scripts/qgis_live_dialog_check.py` (0.2.0, real tcm request through the dialog) | confirmation box, submission, polling, 150 real tiles, styling, file without key, project reopen | `dist/live_dialog_report.json`, `dist/live_dialog_screenshot.png` |
| `scripts/qgis_render_result.py` | **real live exceedance result** loads and styles through the plugin's output/styling code: 7 classes `1.0 - 1.7 h … 5.3 - 6.0 h`, API stats shown | `dist/render_result_report.json`, `dist/render_result_exceedance_canvas.png` |

## 3. Real API validation – executed (development environment, dev key)

| Request | Result |
|---------|--------|
| tcm, filter 3 (single day), 2024-07-15, 100 m – headless client | Completed, 150 tiles, aggregate fields, °C (0.2.0) |
| tcm, filter 1 (single hour 14:00) – **through the dialog** | Completed, 150 tiles, aggregate fields (no `temperature` field), °C (0.2.0) |
| **exceedance**, filter 4 2024-07-15…21, threshold 35 °C above – plugin client (`scripts/live_check.py`) | **Completed** (`d0439dfd-…`), 150 Polygon tiles, schema `value`, 0.98–6.03 h, mean 2.46, `stats_data.units = hour`, saved as `fortyguard_exceedance_…_above35_C_….geojson`; rendered in QGIS (see §2) |
| **persistence**, same window and threshold – plugin client | **Completed** (`c9836df7-…`), 150 tiles, `value` 0.87–1.50 h, `units = hour` |
| **time_of_measure**, same window – plugin client | **Completed** (`a6f5d9ef-…`), 150 tiles, `value` = 14 for every tile, `units = hour`; summary "most common peak hour 14:00 UTC (150 of 150)". Whether 14 is UTC or local cannot be decided from this sample (open question 8 in `docs/API_CONTRACT.md`). |
| Credits | 5 completed requests so far on the dev key (Premium rate 4,220 each) |

The three analyses were verified through the plugin's client/job/output code
(`scripts/live_check.py`), **not through the dialog click path** (only the tcm
request used the dialog live). The dialog path for analyses was exercised with
synthetic fixtures in the offscreen suite and the in-app check.

## 4. Pending / not executed

| Item | Why | How |
|------|-----|-----|
| Analyses through the dialog click path live | Not authorised (each request costs credits); same code path verified with fixtures and the tcm live dialog run. | `FG_ENV=dev FG_FILTER=4 …` extension of `scripts/qgis_live_dialog_check.py` or a manual run. |
| Filter type 2 (range of hours) and filter 3 with an analysis; calendar month live | Not authorised. | `scripts/live_check.py --analytic exceedance --filter 2 …` |
| Peak-time time zone (UTC vs local) | Needs FortyGuard confirmation; uniform live sample. | Ask the API team; if local, change `contract.PEAK_TIME_TZ` and labels. |
| Production environment | Development key only. | Production key. |
| Windows, Linux, QGIS 4 | Not available. | Install the ZIP there and run `scripts/run_tests.sh` + the in-app checks. |
| Encrypted key storage headless | Skipped (keychain); guarded code. | In QGIS: Save key → restart → Load saved key. |
| plugins.qgis.org upload, scan, approval | No OSGeo ID yet. | See `docs/SUBMISSION.md`. |
