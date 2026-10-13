# Changelog – FortyGuard Heatmap (QGIS plugin)

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
