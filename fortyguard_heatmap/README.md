# FortyGuard Heatmap for QGIS – user guide (0.3.2, experimental)

Generate FortyGuard temperature heatmaps (tcm, °C) for a polygon in your QGIS
project and add them as styled layers, using **your own FortyGuard API key**.

Tested on macOS 27 (Apple Silicon) with QGIS 3.44.15 LTR. Windows, Linux and
QGIS 4 (Qt 6) are not yet tested.

## Install

1. QGIS ▸ **Plugins ▸ Manage and Install Plugins… ▸ Install from ZIP** ▸ choose
   `fortyguard_heatmap-<version>.zip` ▸ **Install Plugin**.
2. In the **Installed** tab make sure *FortyGuard Heatmap* is ticked.
3. Click the FortyGuard button in the toolbar (or **Plugins ▸ FortyGuard Heatmap**).

## First heatmap

1. **API key** – paste your key (get one at https://www.fortyguard.com/api-pricing).
   The field is masked; tick *Show* to check it. The key stays in memory only.
   *Save key (encrypted)* stores it in the QGIS Authentication database
   (protected by your QGIS master password); *Load saved key* restores it later.
2. Click **Check key and credits**. You should see your plan, key status and
   remaining credits. If you see "Invalid or unknown API key", check the key.
3. **Area of interest** – choose a polygon layer and select exactly one feature
   on the map (Select Features tool). The dialog shows its CRS and area; the
   area is sent to the API as an EPSG:4326 polygon.
4. **Date and time** – pick a filter type (single hour, range of hours ≤ 23 h,
   single day, range of days ≤ 31 days, calendar month) and the required dates/times.
   Times are the local time of the selected area. Dates must be between
   2019-01-01 and now + 12 h.
5. **Output** – resolution (60 / 80 / 100 m), the measure to style for daily
   outputs (mean / minimum / maximum), the output folder (default
   `Documents/FortyGuard Heatmaps`) and the maximum wait.
6. Click **Generate Heatmap**, read the confirmation and continue. Status and
   the activity ID appear below. When the job completes the GeoJSON is saved
   and a styled layer is added to the project.

**Stop Waiting** only stops the plugin from polling; the FortyGuard job keeps
running on the server. **Check Again** polls the same activity ID later without
sending a new request.

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

## Costs and coverage

Using the plugin requires a FortyGuard API key with an appropriate plan. Each
completed request consumes credits (documented: 3,500 on API Basic/Startup,
4,220 on API Premium; failed tasks are free). Area caps: 10 mi² (Basic/Startup),
50 mi² (Premium). Documented coverage: United States only.

## Demo Mode (optional)

Tick **Demo Mode** to replay synthetic data without any API call. Demo layers
are named `[DEMO - synthetic] …` and are never FortyGuard analyses.

## Errors in plain language

| Message | Meaning |
|---|---|
| Invalid or missing API key (HTTP 401) | The key is wrong, expired, or belongs to a different API environment. |
| HTTP 403 | Your plan does not include this feature, or credits/authorisation are insufficient. |
| HTTP 400/422 + API message | The request was rejected: area above the plan cap, date out of range, polygon outside the covered region, or invalid polygon. |
| Rate limit exceeded (HTTP 429) | Too many requests; the plugin waits longer automatically. |
| Stopped waiting after N minutes | Increase *Max wait* or use *Check Again* later. |
| The request may or may not have reached FortyGuard | A network error happened during submission. The plugin never resubmits by itself; check your credits usage before trying again. |

## Privacy

The key is sent only in the `api-key` header to the selected FortyGuard API
host. It is never written to logs, layer properties, project files or result
files.

Documentation: https://docs-api.fortyguard.com/docs/introduction ·
Support: support@fortyguard.com · Licence: GPL-2.0-or-later (see LICENSE).
