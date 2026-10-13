# Test report – FortyGuard Heatmap QGIS plugin 0.2.0

Environment actually used: macOS 27 (Darwin 27.0.0, Apple Silicon), QGIS
3.44.15-Solothurn (`/Applications/QGIS.app`), Qt 5.15.19, PyQt 5.15.10,
QGIS-bundled Python 3.12.11. System Python 3.9.6 for the pure tests.
Dates: 2026-10-12 and 2026-10-13. **No other operating system or QGIS version
was tested.**

## 1. Automated tests – executed

Command: `scripts/run_tests.sh` (last run 2026-10-13 after the 0.2.0 changes).
Result: **100 tests, 99 passed, 1 skipped, 0 failed** (49 of them also pass on
plain system Python without QGIS).

| Suite | Covers | Tests |
|-------|--------|-------|
| `test_payload.py` | payload per filter type, date/time formats and documented bounds, granularity restriction, polygon validation (holes, lon/lat order, closed rings, MultiPolygon/Point/projected coordinates rejected) | 24 |
| `test_responses.py` | submit/status envelopes, HTTP 400/401/403/404/422/429/5xx classification, `details.message` (live shape), terminal states case-insensitive, result extraction, empty/non-polygon `map_data`, measure detection, NULL values, stats keys, **usage endpoint parsing (live shape, 500 explanation, 401, malformed)** | 25 |
| `test_polling.py` | fixed interval, deadline, backoff, rate-limit interval, consecutive-failure limit, fatal stop, reset | 7 |
| `test_qgis_geometry.py` | one-selection rule, non-polygon layer, EPSG:3857→4326 with hole kept and source untouched, MultiPolygon handling, invalid/empty geometry, ellipsoidal area | 6 |
| `test_qgis_output_styling.py` | fixtures vs documented schemas, save + OGR load + °C graduated style, restyle, non-numeric field rejected, never overwrite, sidecar without key, project save/reopen keeps the layer | 7 |
| `test_qgis_job.py` | real `QgsNetworkAccessManager` against a scripted local server: headers/body, single POST, 404 retry, Failed terminal, 401 keeps activity id, submit errors never retried, deadline then resume without new POST, 5xx give-up, Stop Waiting, double submit ignored, empty result, network error warning, **usage endpoint POST + parsing, usage 500**, demo client | 16 |
| `test_qgis_dialog_demo.py` | offscreen GUI: plugin initGui/run/unload, Demo Mode end to end (single hour + daily), restyle, validation without selection, key required in live mode, **new-installation defaults (no key, masked field, production, developer group collapsed, default output folder)**, **environment switch clears the key**, credits check requires key, shutdown cleanup | 9 |
| `test_qgis_credentials.py` | `mask()` never reveals the key (pass); encrypted store/load/forget (**skipped** unless `FG_TEST_AUTH_STORE=1`, because the headless run blocks on the macOS keychain) | 2 |

## 2. Checks inside the real QGIS application – executed

| Script | What it proved | Evidence |
|--------|----------------|----------|
| `scripts/qgis_gui_check.py` (Demo Mode only) | install/load via `qgis.utils`, toolbar action with icon, dialog, EPSG:3857 demo AOI, Generate disabled while active, demo layer labelled `[DEMO - synthetic]`, 7-class °C style, screenshot, project save/clear/reopen resolves the layer, clean unload | `dist/gui_check_report.json`, `dist/gui_check_canvas.png` (run after the 0.1.0 changes; rerun pending for 0.2.0 UI, see §4) |
| `scripts/qgis_render_result.py` | the first live result (150 tiles) loads and styles through the plugin's output/styling modules | `dist/render_result_report.json`, `dist/render_result_canvas.png` |
| **`scripts/qgis_live_dialog_check.py` – real request through the dialog** (2026-10-13 10:00) | see §3 | `dist/live_dialog_report.json`, `dist/live_dialog_screenshot.png`, `dist/live_dialog_canvas.png` |

## 3. Real API validation – executed

Authorisation: Mustafa approved one single-day request on 2026-10-13 and then
instructed completion of the dialog test with the same development key. Key
source: `~/.config/fortyguard/api_key` (owner-only), never printed.

| Check | Result |
|-------|--------|
| Environment / key match | The supplied key is a **development** key: production `api.fortyguard.com` answers `401 Invalid or unknown API key`; `tos-enterprise-api.dev.app.fortyguard.com` accepts it. Both live runs used the development environment. **Production was not exercised with a valid key.** |
| Credits check through the dialog (`Check key and credits`) | HTTP 200: Plan Premium (One-Time), key active, 995,780 of 1,000,000 credits remaining, key expires 2026-10-19T14:36:30Z |
| Request 1 – headless `scripts/live_check.py`, filter 3 (single day), 2024-07-15, 100 m | Completed in ~23 s, activity `dcdb57e7-…`, 150 Polygon tiles, `average/min/max_temperature` 24.5–34.4 °C, stats keys lower-case, 4,220 credits charged |
| Request 2 – **through the plugin dialog**, filter 1 (single hour 14:00), 2024-07-15, 100 m | Confirmation box shown and accepted; submission → activity `69a66823-…`; status polling Processing ×6 then Completed (~20 s); real GeoJSON saved to `~/Documents/FortyGuard Heatmaps/fortyguard_tcm_2024-07-1514_00_100m_69a66823_20261013_100034.geojson` + `.meta.json` (no key, `demo=false`); layer added, **not** labelled demo; field `average_temperature` type Real, 31.887–33.142; graduated renderer 7 classes with °C labels; API stats shown (min 31.89, max 33.14, mean 32.26, sd 0.41); key absent from log and status; project saved, cleared and reopened with the layer valid |
| Schema note | The hourly request returned `average_temperature = min_temperature = max_temperature` per tile and **no `temperature` field**, contrary to the documentation. The plugin's field auto-detection handled it. |
| Production usage endpoint | HTTP 500 `Unable to fetch API key usage.` for the development key (expected for a key unknown to production, but the status code is unhelpful; reported in `docs/API_CONTRACT.md`). |

Demo Mode success is **not** counted as API validation; the two requests above are.

## 4. Pending / not executed

| Item | Why | How |
|------|-----|-----|
| Production environment end to end | No production key available. | Obtain a production key, run `scripts/qgis_live_dialog_check.py` with `FG_ENV=prod` (spends credits). |
| Filter types 2 and 4, 60 m / 80 m, 429 behaviour | Not authorised (each completed request costs credits). | `scripts/live_check.py --filter 2 …` etc. |
| Windows and Linux | No machine available. | Install the ZIP on each, run `scripts/run_tests.sh` and the in-app Demo check. |
| QGIS 4 / Qt 6 | Not installed; `qgisMaximumVersion=3.99` on purpose. | Install a QGIS 4 build, run tests, then raise the maximum version. |
| Encrypted key storage (auth DB) | Headless test skipped; code is guarded. | In QGIS: Save key → restart → Load saved key (master-password prompt). |
| 0.2.0 UI re-run of `qgis_gui_check.py` | The 0.2.0 dialog was exercised by the offscreen suite (9 tests) and by the real dialog run; the Demo-only in-app script was last run on 0.1.0. | `QGIS --code scripts/qgis_gui_check.py` |
| plugins.qgis.org security scan and approval | Not uploaded (publisher details and public repository missing, see `docs/PUBLISHING.md`). | After upload, read the Security tab and the approval e-mail. |
