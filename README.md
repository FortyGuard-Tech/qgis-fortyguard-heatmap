# FortyGuard Heatmap – QGIS plugin (0.2.0, experimental release candidate)

Install the plugin, click the FortyGuard toolbar icon, enter **your own**
FortyGuard API key, select an area and date, click **Generate Heatmap**, and
receive a styled temperature layer (tcm, °C) in your QGIS project. The plugin
talks directly to the FortyGuard Temperature API, polls the job without
blocking QGIS and saves the GeoJSON tiles. A clearly labelled optional
**Demo Mode** replays synthetic data offline.

End-user guide: `fortyguard_heatmap/README.md` (shipped inside the plugin).
Release notes: `CHANGELOG.md`. Publishing checklist: `docs/PUBLISHING.md`.
Download-page content: `docs/download-page/`.

Tested on QGIS 3.44.15 LTR (Qt 5.15, Python 3.12) on macOS / Apple Silicon.
QGIS 4 (Qt 6) is **not** declared as supported yet because it was not tested.

```
fortyguard_heatmap/        the plugin (this folder is what goes into the ZIP)
  __init__.py              classFactory
  plugin.py                toolbar/menu action, dialog lifecycle, unload cleanup
  metadata.txt             QGIS plugin metadata
  ui/dialog.py             the dialog (built in code, no generated files)
  core/contract.py         verified API constants (endpoints, filters, limits, units)
  core/payload.py          pure payload builder + input validation
  core/responses.py        pure raw-response parsing, terminal states, field detection
  core/polling.py          pure polling policy (deadline, backoff, retry limits)
  core/geometry.py         selected feature -> EPSG:4326 GeoJSON Polygon (holes kept)
  core/api_client.py       async client on QgsNetworkAccessManager (api-key header)
  core/job.py              submit once + QTimer polling, Stop Waiting, Check Again
  core/output.py           save GeoJSON + sidecar, load with OGR, never overwrite
  core/styling.py          graduated blue→red renderer with °C legend labels
  core/credentials.py      key in memory; optional encrypted QGIS auth-store save
  core/demo.py             offline fake client replaying fixtures (same job path)
  fixtures/                SYNTHETIC demo AOI + results (see fixtures/README.md)
tests/                     unit + QGIS-runtime tests
scripts/                   run_tests.sh, package.sh, install_dev.sh, live_check.py,
                           qgis_gui_check.py, make_demo_fixtures.py
docs/API_CONTRACT.md       verified endpoints, schemas, units, limits, open questions
docs/TEST_REPORT.md        what was executed, outcomes, what is still pending
dist/                      built ZIP and in-app check artefacts
```

---

## 1. Install on macOS (QGIS 3.44 LTR)

Two options. Option A is what a normal user does; option B is for development.

### Option A – install the ZIP

1. Build or take the ZIP: `dist/fortyguard_heatmap-0.1.0.zip` (rebuild with `scripts/package.sh`).
2. In QGIS: **Plugins ▸ Manage and Install Plugins… ▸ Install from ZIP**, choose the ZIP, click **Install Plugin**.
3. Go to the **Installed** tab and make sure **FortyGuard Heatmap** is ticked.
4. A toolbar button and **Plugins ▸ FortyGuard Heatmap** menu entry appear.

### Option B – link the source folder (development)

```bash
cd "/Users/mustafahamdy/Downloads/QGIS inetgration"
scripts/install_dev.sh          # symlinks fortyguard_heatmap into the active profile
```
The script reads `~/Library/Application Support/QGIS/QGIS3/profiles/profiles.ini`
to find the active profile (currently `default`). After editing code, use the
*Plugin Reloader* plugin or restart QGIS. Remove with `scripts/install_dev.sh --remove`.

---

## 2. Launch and run the offline demo (no API key, no credits)

1. Open QGIS, click the **FortyGuard Heatmap** toolbar button.
2. Tick **Demo Mode – offline, SYNTHETIC data, no API call, no credits**.
3. Click **Add demo AOI layer (EPSG:3857, synthetic test area)**. A polygon layer
   in Web Mercator is added and its feature is selected (this exercises the
   non‑WGS84 → EPSG:4326 transformation).
4. Choose a filter type (hourly filters use the `temperature` fixture, day
   filters use the `average/min/max_temperature` fixture).
5. Click **Generate DEMO Heatmap (synthetic)**. The status goes
   Submitted → Processing → Completed in ~10 s and a layer named
   `[DEMO - synthetic] FortyGuard tcm … °C | …` is added with a 7‑class
   blue→red graduated style. Statistics appear in the dialog.
6. For daily outputs, change **Measure (daily outputs)** and click
   **Restyle last layer** to switch between mean / minimum / maximum.

Demo results are saved as `fortyguard_DEMO_*.geojson` + `.meta.json` in the
output folder (default `~/Documents/FortyGuard Heatmaps`). They are synthetic
and are never presented as a FortyGuard analysis.

---

## 2b. Analysis modes (0.3.0)

The **Analysis** box offers the four modes of the FortyGuard Forma extension.
Each mode is one API request; the API computes the result.

| Mode | `analytic_type` | Result per tile | Legend |
|------|-----------------|-----------------|--------|
| Temperature / Snapshot | `tcm` | temperature (°C); mean/min/max for daily windows | °C |
| Exceedance | `exceedance` | total hours above the threshold in the period | hours (`h`) |
| Persistence | `persistence` | longest continuous run of hours above the threshold | hours (`h`) |
| Peak temperature time | `time_of_measure` | hour of day (0–23) of the tile's peak | clock classes, labelled **UTC** |

* **Threshold (°C)** appears only for Exceedance and Persistence (default 35 °C,
  sent with `direction: above`). Exceedance = total hours (may be spread out);
  Persistence = the longest unbroken stretch.
* **Single hour** is not available for the three analyses; the dialog switches
  to Single day and tells you.
* **Calendar month** submits the month's first and last day as a range of days
  (leap years handled; the current month is clipped to now + 12 h).
* Every result becomes its own layer named with the analysis, dates, resolution
  and threshold. Zero hours and 00:00 are shown as real values, not gaps.
* The summary shows valid tile counts, the share of valid **tiles** (not area)
  with more than 0 h and the maximum duration, or the most common peak hour.

## 3. Run a real request

Before the first live request read `docs/API_CONTRACT.md` → *Plans, credits,
limits, coverage*: a completed request costs credits (documented 3,500 on
API Basic/Startup, 4,220 on API Premium), coverage is **United States only**,
area caps are 10 mi² (Basic/Startup) or 50 mi² (Premium).

1. Paste your API key (use **Show** to check it). The key stays in memory only.
   Click **Check key and credits** to see your plan, key status and remaining
   credits before spending anything. The plugin always starts on the
   production API (`api.fortyguard.com`). FortyGuard developers with a
   development key can expand **Developer settings** and pick the development
   environment; switching clears the key field and the choice is not saved.
   Keys are environment-specific: a development key is rejected with HTTP 401
   by production. Optionally click **Save key (encrypted)** to store it in the
   QGIS Authentication database (you will be asked for the QGIS master
   password); **Load saved key** restores it next time, **Forget saved key**
   deletes it.
2. Choose the polygon layer and select exactly one polygon feature on the map.
   The dialog shows the feature id, source CRS and approximate area.
3. Pick the filter type and the required date/time fields. Dates must be
   between 2019‑01‑01 and now + 12 h. Range of hours ≤ 23 h; range of days ≤ 31 days.
4. Pick the resolution (60 / 80 / 100 m), output folder and maximum wait.
5. Click **Generate Heatmap**, read the confirmation (area, request, credit
   note) and confirm.
6. Watch **Status** and **Activity ID**. **Stop Waiting** stops local polling only
   (the server job continues and will still be charged if it completes);
   **Check Again** polls the same activity id without resubmitting.
7. When completed, the GeoJSON is saved as `fortyguard_tcm_<request>_<id>_<time>.geojson`
   with a `.meta.json` sidecar (stats, request summary, no key) and the styled
   layer is added. Existing files are never overwritten.

### Headless live check (for automated verification)

```bash
umask 077; mkdir -p ~/.config/fortyguard
printf '%s' 'YOUR_KEY' > ~/.config/fortyguard/api_key     # or export FORTYGUARD_API_KEY
/Applications/QGIS.app/Contents/MacOS/python scripts/live_check.py \
   --aoi fortyguard_heatmap/fixtures/demo_aoi.geojson --date 2024-07-15 --filter 3 \
   --granularity 100 --out "$HOME/Documents/FortyGuard Heatmaps" --confirm \
   --base-url https://tos-enterprise-api.dev.app.fortyguard.com   # omit for production
```
It uses the plugin's own client/job code, prints every status, saves the result
and a `.live_check.json` schema report, and never prints the key.

---

## 4. Tests

```bash
scripts/run_tests.sh --pure      # 44 pure-Python tests, any python3
scripts/run_tests.sh             # + QGIS-runtime tests with QGIS's bundled Python
```
In‑app automated check (opens QGIS, runs the demo, saves a screenshot and a
project, unloads the plugin, quits):
```bash
scripts/install_dev.sh
/Applications/QGIS.app/Contents/MacOS/QGIS --nologo --code "$(pwd)/scripts/qgis_gui_check.py"
cat dist/gui_check_report.json
```
See `docs/TEST_REPORT.md` for results.

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Plugin not listed after install | The ZIP must contain one top‑level folder `fortyguard_heatmap`; rebuild with `scripts/package.sh`. Check **Plugins ▸ Manage ▸ Settings ▸ Show also experimental plugins** (this version is marked experimental). |
| "Select exactly one polygon feature" | Use the Select Features tool on the chosen layer; multi‑selection and MultiPolygon features with several parts are rejected (the API documents one Polygon). |
| "Invalid or missing API key (HTTP 401) … Invalid or unknown API key." | Wrong key **or wrong environment** (a development key on production, or vice versa). Switch *API environment*. Keys can also expire even if the subscription is active (docs). |
| "HTTP 403" | Plan does not allow the feature, or credits/authorization problem. Check the Credits Usage page on docs‑api.fortyguard.com. |
| "HTTP 400/422 … API message" | Input rejected: area over the plan cap, date outside 2019‑01‑01…now+12 h, polygon outside the United States, invalid polygon. |
| "Rate limit exceeded (HTTP 429)" | The plugin backs off to 30 s between checks automatically. |
| "Stopped waiting after N minutes" | Raise **Max wait** or click **Check Again** later; the server job may still finish. |
| "The request may or may not have reached FortyGuard" | Network error during submission. The plugin never resubmits automatically; check credits usage before retrying. |
| Layer missing after reopening a project | The GeoJSON file was moved/deleted from the output folder. Keep results in a stable folder (the default is `~/Documents/FortyGuard Heatmaps`). |
| Save key does nothing | QGIS authentication system disabled or master password cancelled; the key still works in memory. |
| Times/time zone | The API docs do not define the time zone of `start_time`; the plugin sends what you type. Confirm with FortyGuard. |

Logs: **View ▸ Panels ▸ Log Messages ▸ "FortyGuard Heatmap"**. The key is never logged.

---

## 6. Security notes

* The key is only sent as the documented `api-key` request header to the API
  base URL; redirects are not followed; responses are never cached.
* The key is never written to files, logs, layer properties, project files or
  the ZIP. `scripts/package.sh` refuses to package anything resembling a key.
* Optional persistence uses `QgsAuthManager.storeAuthSetting(..., encrypt=True)`
  (QGIS master‑password protected).

## 7. License and attribution

GPL‑2.0‑or‑later (see `fortyguard_heatmap/LICENSE`). Publisher: FortyGuard,
support@fortyguard.com. Source: https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap.
Schema knowledge verified against the FortyGuard API documentation and the
MIT‑licensed FortyGuard‑Tech/temperature‑api‑quickstart repository; no code
copied. Demo tile values are synthetic.
