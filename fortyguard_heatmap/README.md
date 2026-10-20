# FortyGuard Temperature Intelligence Layer for QGIS – user guide (0.5.3)

Generate FortyGuard temperature heatmaps (tcm, °C) for a polygon in your QGIS
project and add them as styled layers, using **your own FortyGuard API key**.

Tested by the FortyGuard team on macOS (QGIS 3.44.15 LTR), Windows (QGIS 3.44)
and Ubuntu Linux (QGIS 3.40.15). QGIS 4 (Qt 6) is not supported yet.

## Install

1. QGIS ▸ **Plugins ▸ Manage and Install Plugins…** ▸ **All** ▸ search "FortyGuard"
   ▸ **Install Plugin**. (Versions before 0.5.0 were marked experimental and
   needed *Settings ▸ Show also experimental plugins*; 0.5.0 does not.)
   (Offline: **Install from ZIP** with `fortyguard_heatmap-<version>.zip`.)
2. In the **Installed** tab make sure *FortyGuard Temperature Intelligence Layer* is ticked.
3. Click the FortyGuard button in the toolbar (or **Plugins ▸ FortyGuard Temperature Intelligence Layer**).

## First heatmap

1. **API key** – paste your key (get one at https://www.fortyguard.com/api-pricing).
   The field is masked; tick *Show* to check it. The key stays in memory only.
   *Save key (encrypted)* stores it in the QGIS Authentication database
   (protected by your QGIS master password); *Load saved key* restores it later.
2. Click **Check key and credits**. You should see your plan, key status and
   remaining credits (the live balance, `total_remaining_credits`). If you see
   "Invalid or unknown API key", check the key. Checking first also lets the
   confirmation dialog state the cost for your plan.
3. **Area of interest** – choose a polygon layer and select exactly one feature
   on the map (Select Features tool). The dialog shows its CRS, area and whether
   it lies inside the documented coverage (United States); the area is sent to
   the API as an EPSG:4326 polygon.
4. **Date and time** – pick a filter type (single hour, range of hours ≤ 23 h,
   single day, range of days ≤ 31 days counting both dates, calendar month) and
   the required dates/times. Times are the local time of the selected area.
   The API documents dates from 2019-01-01, but **data for the most recent days
   (about the last 7) is usually not available yet**: the API then answers
   "Temperature data is unavailable" (free of charge). The dialog therefore
   defaults to one week ago and warns about more recent windows.
5. **Output** – resolution (60 / 80 / 100 m), the measure to style for daily
   outputs (mean / minimum / maximum), the appearance, the number of **legend
   classes** (3 to 20, default 10; more classes show finer differences), the
   output folder (default: the `FortyGuard Heatmaps` folder inside your
   Documents folder as the system reports it, e.g. under OneDrive on Windows)
   and the maximum wait.
6. Click **Generate Heatmap**, read the confirmation and continue. Before a
   paid request the plugin checks the area (coverage, size), the dates and
   whether the identical request was already completed, and either warns or
   blocks (see *Pre-checks*). Status and the activity ID appear below. When
   the job completes the GeoJSON is saved and a styled layer is added.

**Stop Waiting** only stops the plugin from polling; the FortyGuard job keeps
running on the server (if you stop while the request is being submitted, the
plugin still waits for the activity ID so the paid job is not lost). **Check
Again** polls the activity ID shown in the field without sending a new request.
The field is editable: every submission logs its activity ID, so you can paste
an earlier ID there and fetch that result later, even after other requests.

## Pre-checks before a paid request

The API charges for some requests that return nothing useful, so the plugin
checks first (the API remains the authority; *Advanced settings ▸ Skip the
pre-checks* bypasses them):

| Check | Result |
|---|---|
| Area outside the United States coverage | Blocked. Such requests completed with 0 tiles and were charged in testing. |
| Area partly outside the coverage | Warning. |
| Area smaller than one tile | Warning (0 tiles likely, still charged). |
| Area above your plan allowance (10 mi² Basic/Startup, 50 mi² Premium) | Warning. |
| Area above 500 mi² | Blocked. Such jobs were accepted, charged and never finished (HTTP 504). |
| Window ends within the last 7 days | Warning (data usually not available yet; a rejection is free). |
| Identical request already completed (this session or a file in the output folder) | Warning: it is charged again and returns the same tiles. |
| A previous request was stopped or timed out | Warning: use *Check Again* before paying for a new one. |

If a job completes with **0 tiles**, the plugin says so, states that credits
were most likely charged, and keeps a `*_EMPTY.meta.json` record with the
activity ID in the output folder.

## Analysis modes

| Mode | What each tile shows | Legend |
|---|---|---|
| Temperature / Snapshot | temperature in the period (°C); mean / min / max for daily windows | °C |
| Exceedance | total hours above your threshold (hours may be spread out) | h |
| Persistence | longest unbroken run of hours above your threshold | h |
| Peak temperature time | hour of day when the tile reaches its highest temperature | clock classes in UTC (confirmed by FortyGuard) |

The **Threshold (°C)** box appears only for Exceedance and Persistence (default
35 °C, always "above"). Single hour is not offered for these three analyses;
pick a range of hours, a day, a range of days or a calendar month. Each result
is added as its own layer; zero hours and 00:00 are real values, not gaps.

Legend labels use as many decimals as the data spread needs (FortyGuard fields
often differ by tenths of a degree across a site); a uniform result shows one
class ("all tiles = 2.0 h").

## Appearance: smooth surface or tiles

By default the plugin shows a **smooth surface**: the same API tiles painted
onto a fine grid, blurred and clipped to your area, with a continuous colour
ramp. The exact tiles layer is added hidden
underneath; tick it in the Layers panel to read exact values. Choose
**Tiles only** in the Appearance box to skip the surface. The surface is a
presentation layer: values between tile centres are estimates. Its colour
scale spans at least 1 °C (or 1 h), so a spread of a few tenths of a degree
is not stretched into a strong hot/cold contrast; the actual spread is shown
in the statistics. It is not created for Peak temperature time, because hours
of the day are cyclic.

## Costs and coverage

Using the plugin requires a FortyGuard API key with an appropriate plan. Each
completed request consumes credits (documented: 3,500 on API Basic/Startup,
4,220 on API Premium; rejected and failed tasks are free; a completed job with
0 tiles is charged). In internal testing every completed request cost 4,220
credits regardless of area or resolution. Area caps: 10 mi² (Basic/Startup),
50 mi² (Premium). Documented coverage: United States only.

## Demo Mode (optional)

Tick **Demo Mode** to replay synthetic data without any API call. Demo layers
are named `[DEMO - synthetic] …` and are never FortyGuard analyses.

## Errors in plain language

| Message | Meaning |
|---|---|
| Invalid or missing API key (HTTP 401) | The key is wrong or expired. |
| The FortyGuard gateway did not answer in time while submitting (HTTP 502/503/504) | A server-side timeout, not a key problem. The job may or may not exist: check your credits, then retry the same request in a minute. |
| HTTP 403 | Your plan does not include this feature, or credits/authorisation are insufficient. |
| FortyGuard has no temperature data yet for part of the selected period (HTTP 400) | The most recent days are not available yet; choose dates up to about a week ago. Nothing was charged. |
| HTTP 400/422 + API message | The request was rejected: area above the plan cap, date out of range, polygon outside the covered region, or invalid polygon. Nothing was charged. |
| The job completed but FortyGuard returned an empty heatmap (0 tiles) | Area outside the coverage or smaller than one tile. Credits were most likely charged; a record file was saved. |
| Gave up after N consecutive failed status checks (HTTP 504) | Seen with very large areas; use *Check Again* later or contact support with the activity ID. |
| Activity … was not found after 3 checks (HTTP 404) | An old activity ID unknown to this environment or account. |
| Rate limit exceeded (HTTP 429) | Too many requests; the plugin waits longer automatically. |
| Stopped waiting after N minutes | Increase *Max wait* or use *Check Again* later. |
| The request may or may not have reached FortyGuard | A network error happened during submission. The plugin never resubmits by itself; check your credits usage before trying again. |

## Privacy

The key is sent only in the `api-key` header to the selected FortyGuard API
host. It is never written to logs, layer properties, project files or result
files.

Documentation: https://docs-api.fortyguard.com/docs/introduction ·
Support: support@fortyguard.com · Licence: GPL-2.0-or-later (see LICENSE).
