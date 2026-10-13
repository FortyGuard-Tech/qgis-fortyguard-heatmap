# -*- coding: utf-8 -*-
"""Verified FortyGuard Temperature API contract constants.

Every value here was checked against the official documentation text served by
https://docs-api.fortyguard.com (read from the site's JavaScript bundle on
2026-10-12) and the public quickstart repository
https://github.com/FortyGuard-Tech/temperature-api-quickstart.
See docs/API_CONTRACT.md for sources and unresolved questions.

This module is pure Python (no QGIS imports) so it can be unit-tested anywhere.
"""

DEFAULT_BASE_URL = "https://api.fortyguard.com"
# Development environment documented in the official quickstart (.env.example).
DEV_BASE_URL = "https://tos-enterprise-api.dev.app.fortyguard.com"
BASE_URL_CHOICES = (
    ("Production - api.fortyguard.com", DEFAULT_BASE_URL),
    ("Development - tos-enterprise-api.dev.app.fortyguard.com", DEV_BASE_URL),
)
HEATMAP_PATH = "/v1/heatmap"
STATUS_PATH_TEMPLATE = "/v1/status/{activity_id}"
# Documented "Check API Credits Usage"; the server accepts POST with {"api_key": ...} (GET -> 405).
USAGE_PATH = "/v1/system/fetch-api-key-usage"

# Verified public links (HTTP 200 on 2026-10-13).
URL_DOCS = "https://docs-api.fortyguard.com/docs/introduction"
URL_DOCS_HEATMAP = "https://docs-api.fortyguard.com/docs/create-heatmap"
URL_DOCS_AUTH = "https://docs-api.fortyguard.com/docs/authentication"
URL_DOCS_LIMITS = "https://docs-api.fortyguard.com/docs/limitations"
URL_DOCS_CREDITS = "https://docs-api.fortyguard.com/docs/credits-usage"
URL_API_PLANS = "https://www.fortyguard.com/api-pricing"
URL_CONTACT = "https://www.fortyguard.com/contact-us"
SUPPORT_EMAIL = "support@fortyguard.com"  # published on the Known Limitations page

AUTH_HEADER = "api-key"
CONTENT_TYPE_JSON = "application/json"

# analytic_type values (Create Heatmap page, verified 2026-10-12):
#   tcm             - Temperature snapshot; value is temperature (°C) per tile
#   time_of_measure - hour of day (0-23, UTC) at which the peak temperature occurs
#   exceedance      - number of hours the temperature passes the threshold
#   persistence     - longest continuous run of hours past the threshold
# "time_of_measure, exceedance and persistence return values in hours (stats_data.units = "hour"); tcm returns °C."
ANALYTIC_TYPE_TCM = "tcm"
ANALYTIC_TYPE_EXCEEDANCE = "exceedance"
ANALYTIC_TYPE_PERSISTENCE = "persistence"
ANALYTIC_TYPE_TIME_OF_MEASURE = "time_of_measure"
ANALYTIC_TYPES = (ANALYTIC_TYPE_TCM, ANALYTIC_TYPE_EXCEEDANCE, ANALYTIC_TYPE_PERSISTENCE, ANALYTIC_TYPE_TIME_OF_MEASURE)
THRESHOLD_TYPES = frozenset({ANALYTIC_TYPE_EXCEEDANCE, ANALYTIC_TYPE_PERSISTENCE})
ANALYSIS_LABELS = {
    ANALYTIC_TYPE_TCM: "Temperature / Snapshot",
    ANALYTIC_TYPE_EXCEEDANCE: "Exceedance",
    ANALYTIC_TYPE_PERSISTENCE: "Persistence",
    ANALYTIC_TYPE_TIME_OF_MEASURE: "Peak temperature time",
}
ANALYSIS_EXPLANATIONS = {
    ANALYTIC_TYPE_TCM: "Temperature across the selected period (°C).",
    ANALYTIC_TYPE_EXCEEDANCE: "Total hours above the selected temperature threshold.",
    ANALYTIC_TYPE_PERSISTENCE: "Longest continuous period (hours) above the threshold.",
    ANALYTIC_TYPE_TIME_OF_MEASURE: "Hour of day when each tile reaches its highest temperature (reported in UTC).",
}
TCM_UNIT = "°C"  # documented: "tcm — Temperature snapshot; value is temperature (°C) per tile"
HOURS_UNIT = "h"
PEAK_TIME_TZ = "UTC"  # documented "hour of day (0–23, UTC)"; confirmed by the FortyGuard API team 2026-10-13
INPUT_TIME_ZONE_NOTE = "local time of the area"  # start_time/end_time: confirmed by the FortyGuard API team 2026-10-13
UNIT_KIND = {  # how to label legends and summaries
    ANALYTIC_TYPE_TCM: "celsius",
    ANALYTIC_TYPE_EXCEEDANCE: "hours",
    ANALYTIC_TYPE_PERSISTENCE: "hours",
    ANALYTIC_TYPE_TIME_OF_MEASURE: "hour_of_day",
}
# threshold: "Temperature threshold in °C for exceedance / persistence. Defaults to 30 °C."
# direction: "'above' (default) counts hours above the threshold, 'below' counts hours below it."
DIRECTION_ABOVE = "above"
DEFAULT_THRESHOLD_C = 35.0      # UI starting value requested for this plugin (API default is 30)
THRESHOLD_MIN_C = -40.0
THRESHOLD_MAX_C = 70.0
# Quickstart README: analysis types are computed "over a multi-hour or multi-day window
# (filter_type 2 or 4)"; the Forma extension disables Single hour for them.
ANALYSIS_FILTER_TYPES = (2, 3, 4)

# Documented granularity options (metres).
GRANULARITY_OPTIONS = (60, 80, 100)
DEFAULT_GRANULARITY = 100

# Documented date_time.filter_type values.
FILTER_SINGLE_HOUR = 1
FILTER_RANGE_OF_HOURS = 2
FILTER_SINGLE_DAY = 3
FILTER_RANGE_OF_DAYS = 4

FILTER_TYPE_LABELS = {
    FILTER_SINGLE_HOUR: "Single hour",
    FILTER_RANGE_OF_HOURS: "Range of hours (same day)",
    FILTER_SINGLE_DAY: "Single day (daily aggregates)",
    FILTER_RANGE_OF_DAYS: "Range of days (aggregates, max 31 days)",
}

# Documented bounds.
MIN_DATE_ISO = "2019-01-01"           # "Supported range: 2019-01-01 through 12 hours past the current time."
FORECAST_HOURS_AHEAD = 12
MAX_RANGE_OF_HOURS = 23               # Known Limitations: "Max supported range for filter_type = 2 — 23Hrs"
MAX_RANGE_OF_DAYS = 31                # Create Heatmap page: "Range of Days — week / month, ≤ 1 month"

# Plan limits (documented 2026-10-12). Enforced server-side; shown to the user only.
AREA_CAP_SQ_MI = {"API Basic": 10, "API Startup": 10, "API Premium": 50}
CREDITS_PER_REQUEST = {"API Basic": 3500, "API Startup": 3500, "API Premium": 4220}
COVERAGE_NOTE = "United States only (documented regional coverage for all plans)."

# Status strings. Documented: "Processing", "Completed", "Failed".
# The official quickstart example also accepts lower-case variants plus
# "succeeded" / "error". Comparison is case-insensitive.
TERMINAL_SUCCESS = frozenset({"completed", "succeeded"})
TERMINAL_FAILURE = frozenset({"failed", "error"})

# Result field names.
# tcm, documented: hourly -> properties.temperature; daily -> average/min/max_temperature.
# Observed live (dev, 2026-10-13): an hourly tcm request also returned the aggregate fields.
# Analysis types (exceedance/persistence/time_of_measure): properties.value, stats_data.units = "hour".
FIELD_VALUE = "value"
FIELD_TEMPERATURE = "temperature"
FIELD_AVERAGE = "average_temperature"
FIELD_MIN = "min_temperature"
FIELD_MAX = "max_temperature"
FIELD_TILE_ID = "tile_id"

MEASURE_LABELS = {
    FIELD_TEMPERATURE: "temperature",
    FIELD_AVERAGE: "mean",
    FIELD_MIN: "minimum",
    FIELD_MAX: "maximum",
}
# Preferred order when offering a default measure.
MEASURE_PRIORITY = (FIELD_TEMPERATURE, FIELD_AVERAGE, FIELD_MAX, FIELD_MIN)

# Documented HTTP status meanings (Quickstart "response and status guide").
HTTP_MEANINGS = {
    400: "Invalid request or validation error.",
    422: "Invalid request or validation error.",
    401: "Missing or invalid API key.",
    403: "Insufficient plan access or authorization.",
    404: "Activity not found or temporarily unavailable immediately after submission.",
    429: "Rate limit exceeded.",
    500: "Server-side processing error.",
}

# Polling defaults (client-side policy; the API documents only "continue bounded polling").
POLL_INITIAL_INTERVAL_S = 3.0
POLL_MAX_INTERVAL_S = 30.0
POLL_BACKOFF_FACTOR = 1.5
POLL_DEFAULT_DEADLINE_S = 15 * 60
POLL_MAX_CONSECUTIVE_FAILURES = 8
HTTP_TIMEOUT_MS = 60_000
