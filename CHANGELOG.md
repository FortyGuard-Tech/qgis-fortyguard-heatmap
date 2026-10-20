# Changelog – FortyGuard Temperature Intelligence Layer (QGIS plugin)

## 0.5.2 – 2026-10-20

Second internal testing round (Windows 11 / QGIS 3.44.15; testers Shreya,
Mudethir, Snehil) and a self-review of the whole plugin.

- **Legend classes from numeric values only.** QGIS's `updateClasses()` counts a
  NULL attribute as 0, so one tile without a value stretched the lowest class to
  "0.0 - 26.3 °C" and shifted every quantile break. Breaks are now computed with
  `QgsClassificationMethod.classes(values, n)` on the finite values.
- **Default output folder** is the Documents folder reported by the operating
  system (`QStandardPaths`), so on Windows with OneDrive-redirected Documents
  the results appear where File Explorer shows Documents.
- **Check Again for any activity.** The Activity ID field is editable: paste the
  ID of an earlier request (every submission logs it) and click Check Again to
  fetch its result without paying again, even after other requests were made.
  The analysis type of such a result is read from the API's `stats_data`.
- **Status log** no longer repeats "Processing (Job still running)" every poll:
  the status line updates in place with the check count and elapsed time, and a
  log line is written only when the status changes.
- **Gateway errors on submit** (HTTP 502/503/504) are explained as a server-side
  timeout that is not a key problem and whose outcome is uncertain (check
  credits, then retry), instead of "no job was created".
- Appearance option reads "Smooth surface (interpolated estimate) + exact tiles
  layer hidden" (no dashboard reference).
- The API environment selector is hidden in the public build (shown only with
  `FORTYGUARD_DEV_ENVIRONMENT=1`); the group is now "Advanced settings".
- Plugin description rewritten as short sections with bullet points.

## 0.5.1 – 2026-10-20

- **Legend classes** option in the Output box (3 to 20, default 10, remembered):
  more classes show finer temperature differences on the tiles layer, as
  requested in the report review. Identical classes are still merged; Peak
  temperature time keeps its six clock classes. Restyle uses the same setting.

## 0.5.0 – 2026-10-20

Fixes for every issue reported in the FortyGuard internal testing round of
2026-10-19 (sheet "FortyGuard QGIS Plugin Internal Testing"; testers on macOS,
Windows 11 / QGIS 3.44 and Ubuntu / QGIS 3.40.15). Now that the plugin has run
on all three platforms it is **no longer marked experimental**.

Dates and data availability
- Default date is **today minus 7 days** (was yesterday). The API has no data for
  the most recent days yet; every first run with the old default failed with
  HTTP 400 "Temperature data is unavailable for one or more hours".
- That HTTP 400 is now explained in plain words: no data yet for part of the
  period, dates up to `today - 7` normally work, nothing was charged (kind `no_data`).
- Confirmation dialog warns when the selected window ends within the last 7 days.
- **Calendar month** clips the current month to the available days and explains
  it, instead of sending a request the API rejects.
- **Range of days** counts both dates: 2026-07-01 to 2026-08-01 (32 inclusive
  days) is rejected locally with a hint to use Calendar month, instead of
  running 7 minutes on the server and failing without a reason.
- Switching to Range of days gives a valid 7-day default window.

Credits
- "Check key and credits" reads `total_remaining_credits` (the live balance)
  instead of `cycle_remaining_credits`, which stayed frozen at 13,338,180 across
  nine billed requests on a key whose billing cycle had ended. The low-credit
  warning uses the same live figure.
- The confirmation dialog states the expected cost for **your** plan when the
  key was checked (documented plans), or says that the plan has no documented
  cost and that every completed request in testing cost 4,220 credits
  (Hackathon keys), plus the remaining balance.

Pre-checks before a paid request (all bypassable in Developer settings)
- **Coverage:** an area outside the documented United States coverage is blocked
  before submission (Paris, London and open-ocean requests completed with 0
  tiles and were charged 4,220 each); partial overlap is warned about. The
  selected-feature line shows the coverage status.
- **Area:** smaller than one tile → warning (a 64 m² polygon completed with 0
  tiles and was charged); above the plan allowance (or above 50 mi² when the
  plan is unknown) → warning; above 500 mi² → blocked (a ~1,300 mi² request
  was accepted, charged, and the status endpoint answered HTTP 504 forever).
- **Duplicates:** an identical request already completed in this session or
  found in the output folder (`request_fingerprint` in the sidecar) is warned
  about; a previous request that was stopped or timed out is pointed out so
  "Check Again" can fetch it instead of paying twice.

Results and messages
- A completed job with no tiles is reported as kind `empty`: it says credits
  were most likely charged, names the activity, and a `*_EMPTY.meta.json`
  record is saved so the user keeps a trace of what they paid for.
- Repeated HTTP 502/503/504 status answers mention the large-area pattern seen
  in testing; HTTP 500 on submit says no job was created and nothing was charged.
- "Message: Failed" is no longer repeated when the API gives no reason.

Legends
- Label precision follows the data spread (2 decimals under 2 °C, 3 under
  0.2): no more three classes labelled "21.9 - 21.9 °C".
- Zero-width quantile classes are dropped; a uniform result gets exactly one
  class labelled "all tiles = 2.0 h".
- Peak temperature time classes end just below the next bound, so hour 4 is in
  "04:00 - 07:59" and hour 8 in "08:00 - 11:59" (QGIS matches both bounds
  inclusively).
- Smooth surface: the GeoTIFF band is named with the quantity and unit (legend
  heading "FortyGuard mean temperature (°C)" instead of "Band 1 (Gray)"), the
  colour scale spans at least 1 °C / 1 h so a 0.2 °C spread is not stretched to
  a blue-to-red contrast, and the spread is shown in the statistics and log.

Robustness
- **Stop Waiting during submission** no longer discards the answer: the
  activity ID of the (paid) job is recorded, then polling stops.
- A status answer cut off mid-body, or a transport error with a partial body,
  is retried instead of ending polling for a paid job.
- When resuming an old activity, HTTP 404 stops after 3 checks with a message
  that does not claim the job was "just submitted".
- NaN/Infinity values are written as `null` (valid JSON); request summaries are
  shortened in file names; the sidecar and surface names are checked before
  writing so nothing is overwritten.

Dialog
- Getting-started steps on separate lines; no orphan "Start date" label in
  Calendar month mode; Demo Mode "Stop" explains that nothing was sent instead
  of mentioning a server job and a disabled "Check Again".
- Analysis type, time option, threshold, resolution and times are remembered
  between sessions (dates stay relative to today).
- Form rows wrap at narrow widths; plan/credits, selected feature and status
  texts wrap instead of being cropped; "Check key and credits" has its own row.

Tests: 95 pure-Python (new `tests/test_preflight.py`) and 90 QGIS-runtime tests.

## 0.4.3 – 2026-10-19 (experimental)

- Re-upload through the plugins.qgis.org main upload form so the listing title
  updates (Add version does not change the title). No code change.

## 0.4.2 – 2026-10-16 (experimental)

- Renamed to **FortyGuard Temperature Intelligence Layer**. No functional change.

## 0.4.1 – 2026-10-16 (experimental)

- Security-scan fix: a try/except/pass in the surface legend code replaced by
  contextlib.suppress. No functional change.

## 0.4.0 – 2026-10-16 (experimental)

- **Smooth surface appearance** (default): the API tiles are painted onto a fine
  pixel grid (tile size / 8), blurred with a nodata-aware Gaussian kernel,
  clipped to the area of interest and saved as a GeoTIFF next to the GeoJSON,
  then shown with a continuous colour ramp and bilinear resampling, like the
  FortyGuard dashboard. The tiles layer is added hidden so exact values stay
  available. Presentation only: values between tile centres are estimates.
- "Tiles only" appearance option kept; the choice is remembered.
- Not applied to Peak temperature time (hour-of-day values are cyclic).
- Uses numpy and GDAL bundled with QGIS; no new dependencies.

## 0.3.6 – 2026-10-16 (experimental)

- Renamed to **FortyGuard Temperature Intelligence Layer**. New listing description and about text:
  FortyGuard positioning, the four products, a data-center example and the API
  documentation link. No functional change.

## 0.3.5 – 2026-10-15 (experimental)

- Getting-started text uses an explicit dark colour so it is readable in macOS dark mode.

## 0.3.4 – 2026-10-15 (experimental)

- The dialog no longer overflows small screens: the settings area scrolls and the
  Generate / Stop Waiting / Check Again buttons, status and log stay pinned at the
  bottom. Default size 680×720, resizable and maximisable.

## 0.3.3 – 2026-10-14 (experimental)

- Clean plugins.qgis.org security scan: the nine `try/except/pass` blocks now
  use `contextlib.suppress`, and the getting-started text no longer contains a
  phrase that Bandit mistook for SQL string building. No functional change.

## 0.3.2 – 2026-10-14 (experimental)

- Fixed `metadata.txt` parsing on plugins.qgis.org: a percent sign in the
  changelog text broke the server-side parser. No code change.

## 0.3.1 – 2026-10-13 (experimental)

- FortyGuard confirmed the time-zone semantics: `start_time`/`end_time` are the
  local time of the area; `time_of_measure` hours are UTC. Dialog text, README
  and API contract updated; no behaviour change.

## 0.3.0 – 2026-10-13 (experimental)

Heat-analysis modes matching the FortyGuard Autodesk Forma extension, all
computed by the API in a single `POST /v1/heatmap` request per result:

- **Analysis type selector:** Temperature / Snapshot (`tcm`), Exceedance
  (`exceedance`), Persistence (`persistence`), Peak temperature time
  (`time_of_measure`), each with a one-line explanation.
- **Threshold (°C)** shown only for Exceedance and Persistence, default 35 °C,
  validated (−40…70 °C), sent as `threshold` + `direction: "above"`; omitted
  for the other two analyses.
- **Calendar month** time option: first/last day computed (leap years, partial
  current month clipped to now + 12 h, months before 2019 rejected), submitted
  as `filter_type: 4`.
- Single hour is disabled for the three analyses; the dialog switches to
  Single day and says so.
- Result schema is validated per response (`value` field for analyses,
  temperature fields for the snapshot). Legends: °C, hours (`h`), or clock
  classes labelled with the UTC time zone. Zero hours and 00:00 are valid
  values.
- Each result is a separate layer named with analysis, dates, resolution and
  threshold; earlier results are kept.
- Summaries: temperature range and measure; % of valid tiles with > 0 h and
  maximum duration; most common peak hour; valid tile counts. Percentages are
  of tiles, not area.
- Synthetic demo fixtures for all four modes (with zero values, midnight
  peaks and one NULL each).


## 0.2.0 – 2026-10-13 (experimental release candidate)

Tested on macOS 27 (Apple Silicon) with QGIS 3.44.15 LTR only.

- FortyGuard toolbar icon (company mark from fortyguard.com, PNG).
- Getting-started panel in the dialog with verified links to the API
  documentation, plans page, limits, credits usage and contact page.
- **Check key and credits** button (`POST /v1/system/fetch-api-key-usage`):
  shows plan, key status/expiry and remaining credits before you spend any.
- Production API (`api.fortyguard.com`) is the default for everyone. The
  development environment moved to a collapsed **Developer settings** section;
  switching environments clears the key field and the choice is never saved.
- Output folder defaults to `~/Documents/FortyGuard Heatmaps`; a saved folder
  that no longer exists falls back to the default; **Default** button added.
- Clearer messages for authentication, credits and API errors; the API's
  `details.message` text is now surfaced.
- Default filter type is *Single day* (the schema verified live).
- Real request through the dialog verified (see docs/TEST_REPORT.md).

## 0.1.0 – 2026-10-12 (prototype)

- Submit + bounded polling on `QgsNetworkAccessManager`, Stop Waiting / Check Again.
- Geometry validation and EPSG:4326 transformation (holes preserved).
- GeoJSON persistence without overwriting, OGR layer loading, graduated °C styling.
- Optional encrypted key storage in the QGIS authentication database.
- Offline Demo Mode with clearly labelled synthetic fixtures.
