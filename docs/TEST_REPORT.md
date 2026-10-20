# Test report – FortyGuard Temperature Intelligence Layer 0.5.0

## 0. Internal testing round (2026-10-19) and the fixes in 0.5.0

Nine FortyGuard colleagues tested plugin 0.4.2 from plugins.qgis.org on macOS
26.6.2 / 27 (QGIS 3.44.15), Windows 11 (QGIS 3.44) and Ubuntu 26 (QGIS 3.40.15)
against the production API, and recorded 34 rows in the sheet "FortyGuard QGIS
Plugin Internal Testing". Install, open, reload, Demo Mode, the direct API
comparison of all four analyses (0 differences) and "Generate ignored while a
job is running" passed. Every reported failure is listed below with its root
cause and the change in 0.5.0; `docs/API_CONTRACT.md` → *Observed behaviour*
records the API facts behind them.

| # | Reported by | Issue | Root cause | Fix in 0.5.0 | Test |
|---|-------------|-------|------------|--------------|------|
| 1 | Fares, Arpit, Inji, Aashan | Default date (yesterday) and any date in the last ~5 days fail with HTTP 400 "Temperature data is unavailable"; message not explained | The plugin trusted the documented "now + 12 h" limit; the API has no data for recent days | Default date today − 7, latency warning in the confirmation, `no_data` error kind with a plain explanation and "nothing was charged" | `test_payload.RecentDataTests`, `test_responses.test_no_data_400…`, `test_qgis_dialog_demo.test_default_dates…` |
| 2 | Aashan | Calendar month for the current month always fails | `month_range` clipped to now + 12 h | Clip to today − 7 and tell the user; early in a month the option explains that no day is available yet | `test_payload.MonthRangeTests` |
| 3 | Fares | Range of days defaults confusing / invalid | start = end = yesterday | Switching to Range of days sets a valid 7-day window ending a week ago | `test_default_dates…` |
| 4 | Aashan | 32 inclusive days accepted; API ran 7 min and failed without a reason | `(end − start).days > 31` ignores the inclusive end date | `+ 1` in the rule; message names the day count and the Calendar month option | `test_range_of_days_bounds` |
| 5 | Aashan | "Check key and credits" never moves (13,338,180) while 37,980 credits were billed | `cycle_remaining_credits` read first; that field is frozen after the cycle ends | Read `total_remaining_credits`, keep cycle as fallback; low-credit warning uses the live figure | `test_frozen_cycle_balance_is_not_used`, `test_fetch_usage_posts_key_and_parses` |
| 6 | Aashan, Fawad, Rohit | Paris / London / ocean / 64 m² / 10 m polygons complete with 0 tiles, charged 4,220 each; plugin says "malformed", no mention of coverage or credits, no local record | No client-side coverage or size check; empty collection treated as a parsing error | Coverage outline check blocks fully-outside areas and warns on partial overlap; tile-size warning; `empty` error kind stating the charge and the activity; `*_EMPTY.meta.json` record | `test_preflight.CoverageTests/AreaTests`, `test_empty_map_data_is_reported_as_charged_empty_result`, `test_preflight_blocks_outside_coverage_and_huge_areas`, `test_empty_record_and_previous_result_lookup` |
| 7 | Arpit, Fawad | Huge polygons (1,300 and 11,472 mi²) accepted, charged, status 504 forever; no warning | No area check; 5xx retried until the limit with a generic message | Block above 500 mi², warn above the plan allowance (plan from the credits check) or 50 mi²; give-up message explains the pattern | `test_preflight.AreaTests`, `test_repeated_504_mentions_large_areas` |
| 8 | Aashan | Identical request re-run is charged again | Only "Generate while active" was guarded | Fingerprint of body + host stored in the sidecar; warning when it was completed in this session or found in the output folder | `test_preflight.FingerprintTests`, `test_identical_request_is_detected_from_the_output_folder` |
| 9 | Fawad | Stop during submit may lose the paid job's ID (static review) | `stop()` bumped the generation and aborted the POST | Stop while awaiting the answer keeps the reply alive, records the activity ID, then stops | `test_stop_during_submit_keeps_the_activity_id` |
| 10 | Fawad | New Generate after a timeout orphans the earlier job | Dialog disposed the job silently | The previous unfinished activity is pointed out in the confirmation | code path in `_on_generate` |
| 11 | Fawad | Status body cut off mid-transfer stops polling for a paid job | JSON decode error was a fatal `malformed`; transport errors with an HTTP status were parsed | Decode errors on status are retryable; Qt network-layer errors are retryable regardless of HTTP status | `test_cut_off_body_on_status_is_retryable`, `test_cut_off_status_body_is_retried` |
| 12 | Akhilesh | Old activity 404 shown as "just submitted", 8 retries | Same 404 text and retry policy for submit and resume | On resume, 404 stops after 3 checks with a specific message; 404 wording reworded | `test_resume_of_unknown_activity_stops_after_a_few_404s` |
| 13 | Aashan | "Message: Failed" repeats the status | Message appended whenever present | Appended only when it adds information; otherwise "The API gave no reason." | `test_failed_status_without_reason_says_so` |
| 14 | Fawad | Transient HTTP 500 on submit; user not told it was free | Generic server message | Submit 500 says no job was created and nothing was charged | `test_submit_500_says_nothing_was_charged` |
| 15 | Aashan, Fawad | Legend labels collapse ("21.9 - 21.9 °C" three times); uniform results show 7 identical classes | One-decimal labels; quantile method on few distinct values | Decimals follow the spread; zero-width classes dropped; uniform result → one class "all tiles = 2.0 h" | `test_small_spread_gets_distinct_labels`, `test_uniform_result_gets_a_single_honest_class`, `test_few_distinct_values_no_duplicate_classes` |
| 16 | Fawad | Peak-time hours 4, 8, 12, 16, 20 painted in the previous class | QGIS matches both class bounds inclusively; bounds were 0-4, 4-8 … | Upper bound = next bound − 1e-6; labels built from the bounds | `test_peak_hour_bins_exact_bounds` |
| 17 | Aashan | Surface legend "Band 1 (Gray)"; 0.21 °C stretched over the whole ramp | No band description; ramp spanned min–max | Band description "FortyGuard mean temperature (°C)"; minimum colour span 1 °C / 1 h; spread shown in statistics and log | `test_surface_from_daily_fixture`, `test_surface_minimum_colour_span`, `test_surface_legend_uses_two_decimals_for_small_spread` |
| 18 | Fawad | NaN written as literal `NaN` (invalid JSON) | `json.dump` default | Non-finite numbers → `null`, `allow_nan=False` | `test_nan_values_become_null` |
| 19 | Fawad | 400-character summary → OSError; sidecar overwritten | Unbounded stem; only `.geojson` checked | Stem capped; `.geojson`, `.meta.json` and `_smooth.tif` all checked | `test_long_request_summary…`, `test_unique_path_checks_sidecar_and_surface_too` |
| 20 | Sarang | Orphan "Start date" label in Calendar month mode | Label added as plain text, never hidden | Label is a widget toggled with the field | `test_calendar_month_builds_filter_4` |
| 21 | Sarang | Demo stop says "server job not cancelled", "Check Again" (disabled) | One stop handler for demo and live | Demo-specific message: nothing sent, generate again | `test_demo_stop_does_not_mention_a_server_job` |
| 22 | Sarang | Getting-started steps run together | Steps separated by spaces | One step per line | `test_getting_started_steps_on_separate_lines` |
| 23 | Aashan | Analysis settings not restored after restart | Only measure, appearance, max wait, folder were saved | Analysis, time option, threshold, resolution, times remembered; dates stay relative | `test_analysis_settings_are_restored_after_restart` |
| 24 | Akhilesh | Credits / selected-feature / status text and buttons cropped at ~560 px | Fixed-width form rows | Rows wrap, labels wrap, "Check key and credits" on its own row | visual |
| 25 | Akhilesh | Hackathon plan: no cost in the confirmation | Only documented plans quoted | Cost text uses the checked plan; unknown plans state the observed 4,220 and the remaining balance | `test_preflight.CostTextTests` |
| 26 | Fares | Install needed "Show also experimental plugins" | `experimental=True` while only macOS was tested | Windows and Linux now tested; `experimental=False` | metadata |

Automated result for 0.5.0 (2026-10-20, macOS 27, QGIS 3.44.15): `scripts/run_tests.sh`
→ **95 pure-Python tests and 90 QGIS-runtime tests, 0 failed** (1 keychain test skipped headless).

---

# Earlier report – 0.3.1 (kept for history)

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

### 2c. Install from the official QGIS Plugin Repository – **passed** (2026-10-15)

Inside QGIS 3.44.15, with the development symlink removed, a `--code` script used
the Plugin Manager API (`pyplugin_installer`) with *Show also experimental plugins*
enabled: the official repository lists **FortyGuard Heatmap 0.3.3 (experimental)**,
`installPlugin(..., stable=False)` installed it into the default profile, the plugin
loaded and started, `metadata.txt` reports 0.3.3, and the dialog opened.
Evidence: `dist/pm_install_report.json`. The ZIP served by plugins.qgis.org is
byte-identical to `dist/fortyguard_heatmap-0.3.3.zip`.

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
| Windows, Linux | Done by the FortyGuard team on 2026-10-19 (Windows 11 / QGIS 3.44, Ubuntu / QGIS 3.40.15), see section 0. | – |
| QGIS 4 | Not available. | Install the ZIP there and run `scripts/run_tests.sh` + the in-app checks. |
| Encrypted key storage headless | Skipped (keychain); guarded code. | In QGIS: Save key → restart → Load saved key. |
| plugins.qgis.org upload, scan, approval | No OSGeo ID yet. | See `docs/SUBMISSION.md`. |
