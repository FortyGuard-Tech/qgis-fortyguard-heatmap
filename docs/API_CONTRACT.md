# FortyGuard Temperature API – verified contract for the QGIS plugin

Verified on **2026-10-12** against the sources below and partly **confirmed live
on 2026-10-13** (one real request on the development environment; see
*Live verification*). Where the sources disagree or are silent, the item is
listed under *Unresolved questions* and the plugin takes the conservative option.

## Sources and how they were read

| # | Source | How it was read | Notes |
|---|--------|-----------------|-------|
| S1 | https://docs-api.fortyguard.com/docs/create-heatmap | The site is an Angular single-page app: the HTML is an empty shell. The documentation text was extracted from the served bundle `main.<hash>.js` (the `apiEndpoints` array and compiled page templates). | Authoritative for request/response fields, units, limits. |
| S2 | https://docs-api.fortyguard.com/docs/check-status | Same bundle | Status envelope and example. |
| S3 | https://docs-api.fortyguard.com/docs/authentication | Same bundle | `api-key` header. |
| S4 | https://docs-api.fortyguard.com/docs/introduction, `/docs/quickstart`, `/docs/limitations` (Known Limitations), `/docs/release-notes` | Same bundle | HTTP status table, plan limits, coverage, credits. |
| S5 | https://github.com/FortyGuard-Tech/temperature-api-quickstart | Cloned (MIT). `fortyguard/client.py`, `README.md`, `notebooks/01_create_heatmap.ipynb`, and **cached real responses** in `data/heatmaps/*.json`. | Supporting evidence; the cached files are the only real response samples available. |
| S6 | https://fortyguard.com/api-pricing | WebFetch | Plan names/prices (marketing page). |
| S7 | Internal research PDF `FortyGuard_QGIS_Integration_Research_Only.pdf` (12 Oct 2026) | pypdf text extraction | Consistent with S1–S5. |

QGIS references used for the implementation: PyQGIS cookbook pages on plugins,
loading layers, CRS, tasks (3.44), plus plugins.qgis.org *publish* and
*migrate-qgis4* pages.

## Endpoints

| Item | Verified value | Source |
|------|----------------|--------|
| Base URL (production) | `https://api.fortyguard.com` | S1, S3, S5 |
| Base URL (development) | `https://tos-enterprise-api.dev.app.fortyguard.com` | S5 (`.env.example`); **live-confirmed** |
| Keys are environment-specific | The key supplied for this prototype returns `401 Invalid or unknown API key` on production and works on development. The plugin has an *API environment* selector. | live 2026-10-13 |
| Submit heatmap | `POST /v1/heatmap`, `Content-Type: application/json` | S1, S3 |
| Poll | `GET /v1/status/{activity_id}` | S2, S4 |
| Authentication | request header `api-key: <key>`; no OAuth | S3 |
| Credits usage (not used by plugin) | `POST /v1/system/fetch-api-key-usage`, `POST /v1/system/fetch-api-key-custom-usage` | S4, S5 |
| Cancel a job | **No cancel endpoint is documented.** "Stop Waiting" in the plugin only stops local polling. | S1–S5 |

## Request body (`POST /v1/heatmap`)

```json
{
  "polygon_aoi": {
    "type": "FeatureCollection",
    "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}}]
  },
  "date_time": {"start_date": "YYYY-MM-DD", "filter_type": 1, "start_time": "HH:MM", "end_time": "HH:MM", "end_date": "YYYY-MM-DD"},
  "granularity": 100,
  "analytic_type": "tcm"
}
```

| Field | Rule (verified) | Source |
|-------|-----------------|--------|
| `polygon_aoi` | GeoJSON FeatureCollection with a closed Polygon; coordinates `[longitude, latitude]`, lon in [-180,180], lat in [-90,90]; "During the current release, coordinates must fall within the United States." | S1, S4, S5 |
| `date_time.start_date` | `YYYY-MM-DD`; supported range **2019-01-01 through now + 12 hours** (forecast). Earlier/later dates → 400. | S1, S4 |
| `date_time.filter_type` | `1` single hour (needs `start_time`); `2` range of hours, same day (`start_time`, `end_time`; max 23 h); `3` single day (`start_date` only, covers 00:00–23:59); `4` range of days (`start_date`, `end_date`, "≤ 1 month"). | S1, S4 |
| `date_time.start_time`, `end_time` | `HH:MM` 24-hour. `end_time` auto-calculated for filter 1 (start + 1 h). | S1, S4 |
| `date_time.end_date` | Required for filter 4; auto-populated for 1–3. | S1 |
| `granularity` | one of **60, 80, 100** (metres). | S1, S4, S5 |
| `analytic_type` | `tcm` (default, temperature snapshot, °C), `time_of_measure`, `exceedance`, `persistence`. The plugin only sends `tcm`. | S1, S5 |
| `threshold`, `direction` | Only for exceedance/persistence; not sent by the plugin. | S1 |

The plugin sends **only** the fields required by the chosen filter type plus
`granularity` and `analytic_type`. No time-zone field exists in the
documentation and none is sent.

## Responses

### Submission (HTTP 200)

```json
{"error": false, "status_code": 200, "message": "Heatmap Submitted Successfully",
 "data": {"activity_id": "f52d2453-6a59-4b31-afa3-8fe3bb1ac5df"}}
```
`activity_id` is read from `data.activity_id` (S1, S5 client).

### Status (HTTP 200)

```json
{"error": false, "status_code": 200, "message": "Processing",
 "data": {"activity_id": "...", "status": "Processing"}}
```
Completed:
```json
{"error": false, "status_code": 200, "message": "Completed",
 "data": {"activity_id": "...", "status": "Completed",
          "result": {"map_data": {...GeoJSON FeatureCollection...}, "stats_data": {...}}}}
```

| Item | Verified value | Source |
|------|----------------|--------|
| Status location | `data.status` | S2 |
| Result location | `data.result.map_data`, `data.result.stats_data` | S1, S2 |
| Documented statuses | `Processing` (continue bounded polling), `Completed` (retrieve result), `Failed` (stop polling, record activity id) | S4 |
| Extra statuses accepted | `succeeded` (success) and `error` (failure), case-insensitive, as in the official quickstart example and the public client | S4, S5 |
| Error flag | top-level `error: true` with `message` | S1, S5 |

Note: the quickstart client returns `{"activity_id", "result"}` – a wrapper it
builds itself. The raw HTTP envelope is the one above. The cached response files
in S5 contain only the `result` part (`map_data` + `stats_data`).

### HTTP status meanings (Quickstart table, S4)

| HTTP | Meaning | Plugin behaviour |
|------|---------|------------------|
| 400 / 422 | Invalid request or validation error | stop, show API message |
| 401 | Missing or invalid API key | stop, keep activity id |
| 403 | Insufficient plan access or authorization | stop (may also indicate credit problems) |
| 404 | Activity not found or temporarily unavailable immediately after submission | retry with backoff (status only) |
| 429 | Rate limit exceeded | retry after the maximum interval |
| 500 | Server-side processing error | retry (status only), bounded |

### `map_data` tile schema

| Filter | Tile `properties` | Evidence |
|--------|-------------------|----------|
| 1, 2 (hourly) | Documented: `tile_id`, `temperature` (°C) (S1, S5 notebook). **Observed live (dev, filter 1): `average_temperature` = `min_temperature` = `max_temperature` per tile, no `temperature` field.** |
| 3, 4 (daily) | `tile_id`, `average_temperature`, `min_temperature`, `max_temperature` (°C) | S5 notebook **and two cached real responses** (`heatmap_parcel_diridon_san_jose_2024-07-15_tcm.json`: 329 Polygon tiles; `heatmap_parcel_portfolio_san_jose_2026-08-03_tcm.json`: 2224 tiles). All geometries are `Polygon` with 5-point rings; features carry `"id"`. |

The plugin detects which numeric field exists at runtime (`temperature` first,
then `average_temperature`, `max_temperature`, `min_temperature`) and refuses
to style if none is numeric.

### `stats_data` (tcm)

Documented (S1) with capitalised keys: `Temperature_stats` {Minimum, Maximum,
Mean, Standard_deviation}, `Overall_temperature_distribution`,
`Normal_temperature_distribution` {x_axis, y_axis}, `Temperature_frequency`.
**Real responses (S5) use lower-case keys**: `temperature_stats` {minimum,
maximum, mean, standard_deviation}, `overall_temperature_distribution`,
`normal_temperature_distribution`, `temperature_frequency`. The plugin matches
keys case-insensitively.

## Units

* `tcm` tile values and `stats_data` temperatures are **°C** (S1, S5 README and
  notebook: "the Enterprise API delivers tile temperatures in °C – no
  conversion needed").
* The docstring of `create_heatmap` in `fortyguard/client.py` says "tiles in
  °F". This **contradicts** the current documentation and the repository's own
  README/notebook. The plugin uses °C and performs no conversion. The cached
  real responses (San Jose, July) show values of 16–37 which are consistent with
  °C.

## Plans, credits, limits, coverage (documented 2026-10-12)

| Item | API Basic | API Startup | API Premium | Source |
|------|-----------|-------------|-------------|--------|
| Credits per heatmap request | 3,500 | 3,500 | 4,220 | S1, S4 |
| Heatmap max area | 10 mi² | 10 mi² | 50 mi² | S1, S4 |
| Monthly credits | 1,000,000 | 1,000,000 one-time (6 months) | 5,000,000 | S4 |
| Regional coverage | United States only | United States only | United States only | S4, S5 |
| Credits charged | only when status reaches `Completed`; failed tasks are free | | | S4, S5 |

The marketing page (S6) calls the tiers "Basic" and "Pro"; the API docs use
"API Basic / API Startup / API Premium". Which plan a given key has must be
checked with the Credits Usage page or endpoint. **No free test allowance is
documented anywhere.**

## Live verification (2026-10-13, development environment)

One approved request was sent through the plugin's own client/job code
(`scripts/live_check.py`, key read from `~/.config/fortyguard/api_key`):

| Item | Observed |
|------|----------|
| Request | demo AOI (lower Manhattan rectangle, ~1.71 km² / 0.66 mi²), `filter_type 3`, `start_date 2024-07-15`, `granularity 100`, `analytic_type tcm` |
| Submission | HTTP 200, `data.activity_id = dcdb57e7-6d8e-4291-9449-4b4c47deb674` |
| Polling | `Processing` for ~23 s (7 checks at 3 s), then `Completed` with `data.result` |
| `map_data` | FeatureCollection, **150 `Polygon` tiles**, properties exactly `tile_id`, `average_temperature`, `min_temperature`, `max_temperature` |
| Value ranges | mean 28.84–29.75, min 24.51–24.61, max 33.47–34.41 (consistent with °C for New York, 15 July 2024) |
| `stats_data` keys | `temperature_stats` {minimum, maximum, mean, standard_deviation}, `overall_temperature_distribution`, `normal_temperature_distribution`, `temperature_frequency` (**lower-case**, as in S5, not capitalised as in S1) |
| Credits | usage endpoint afterwards: `Heatmap Generation` 4,220 credits, count 1 → the key is on the **Premium** rate |
| Error envelope (observed) | `{"error": true, "status_code": 401, "details": {"message": "Invalid or unknown API key."}}` and `{"error": true, "status_code": 404, "details": {"message": "No activity found for the provided activity_id."}}`; missing header → 401 `"Missing required 'api-key' header…"`. The message lives under `details.message` (the plugin reads it). |
| Usage endpoint | `POST /v1/system/fetch-api-key-usage` with `{"api_key": ...}` works on development (HTTP 200: `plan_details.plan_type = "Premium"`, `cycle_type = "One-Time"`, `credit_summary.total_available_credits = 1000000`, `api_key_details.expiry_date = 2026-10-19T14:36:30Z`). On production it returned **HTTP 500 `Unable to fetch API key usage.`** for this key (same for the custom-range variant); GET is `405 Method Not Allowed`. |

### Second live request (2026-10-13, through the plugin dialog, development environment)

| Item | Observed |
|------|----------|
| Request | same AOI, `filter_type 1`, `start_date 2024-07-15`, `start_time 14:00`, `granularity 100` |
| Activity | `69a66823-c9b8-400c-8400-d7a7a67c0c6f`, Processing ~20 s, then Completed |
| `map_data` | 150 `Polygon` tiles; properties **`tile_id`, `average_temperature`, `min_temperature`, `max_temperature`** with identical values per tile (31.89–33.14 °C). **The documented hourly field `temperature` was not present.** The plugin auto-detects fields, so it styled `average_temperature`. |
| Usage endpoint (dev) before the request | HTTP 200: Premium (One-Time), key active, 995,780 of 1,000,000 credits, expiry 2026-10-19T14:36:30Z |

Still **not** live-verified: filter types 2 and 4; the production environment;
60 m / 80 m requests; rate limiting (429); whether production ever returns a
`temperature` field for hourly requests.

## Unresolved questions (need FortyGuard / API team)

1. **Time zone of `start_time` / `end_time`.** Not stated in any source. Only the
   `time_of_measure` output is documented as UTC. The plugin sends the time
   exactly as typed and shows a warning. Please confirm whether times are UTC or
   local to the AOI.
2. **`filter_type = 4`.** The Create Heatmap page documents it (≤ 1 month); the
   Known Limitations page lists only filter types 1–3 for heatmaps. The plugin
   offers it (max 31 days) but it is unverified live.
3. **Hourly (`filter_type` 1/2) tile field name.** Docs/notebook say `temperature`;
   the live filter-1 result on the development environment carried the
   aggregate fields instead (all three equal). The plugin auto-detects either
   shape; FortyGuard should confirm which one production returns.
4. **Exact error payloads** for 401/403/429 and the "insufficient credits" case
   (402 is handled defensively but is not documented).
5. **Production key.** The supplied key is a development-environment key
   (Premium, one-time 1,000,000 credits, expires 2026-10-19). A production key is
   needed to verify `api.fortyguard.com` itself, and the production usage
   endpoint returned HTTP 500 for this key – worth reporting to FortyGuard.
6. MultiPolygon or multiple-feature AOIs are **not documented**; the plugin
   rejects them (one Polygon only, holes preserved).
7. Response/`map_data` CRS is assumed EPSG:4326 (GeoJSON default; S5 samples are
   lon/lat). The plugin loads the file as-is through OGR.
