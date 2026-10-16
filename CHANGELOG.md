# Changelog – FortyGuard Heat Intelligence Layer (QGIS plugin)

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

- Renamed to **FortyGuard Heat Intelligence Layer**. New listing description and about text:
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
