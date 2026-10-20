# -*- coding: utf-8 -*-
"""Pure parsing of raw FortyGuard HTTP responses.

Documented envelope (Create Heatmap / Check Status pages):

    {"error": false, "status_code": 200, "message": "...",
     "data": {"activity_id": "...", "status": "Completed",
              "result": {"map_data": {...}, "stats_data": {...}}}}

No QGIS imports.
"""
import json
import math

from . import contract
from .payload import recent_data_cutoff


class ApiError(Exception):
    """A problem reported by the API or an unusable response.

    ``kind`` is one of: auth, forbidden, not_found, rate_limited, invalid_input,
    server, network, timeout, malformed, failed, unknown.
    ``retryable`` tells the poller whether a status check may be repeated.
    """

    def __init__(self, message, kind="unknown", http_status=None, retryable=False, details=None):
        super().__init__(message)
        self.kind = kind
        self.http_status = http_status
        self.retryable = retryable
        self.details = details

    def user_message(self):
        return str(self)


# ----------------------------------------------------------------- helpers

def decode_json(body_bytes, retryable=False):
    """Decode a response body to JSON or raise ApiError(kind='malformed').

    ``retryable=True`` marks the error as worth another status check: a body that
    was cut off mid-transfer must not end polling for a paid job.
    """
    if body_bytes is None:
        raise ApiError("Empty response body from the API.", kind="malformed", retryable=retryable)
    if isinstance(body_bytes, (bytes, bytearray)):
        try:
            text = bytes(body_bytes).decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError("Response body is not UTF-8 text.", kind="malformed", retryable=retryable)
    else:
        text = str(body_bytes)
    text = text.strip()
    if not text:
        raise ApiError("Empty response body from the API.", kind="malformed", retryable=retryable)
    try:
        return json.loads(text)
    except ValueError:
        raise ApiError("Response body is not valid JSON (possibly cut off): %s" % text[:200], kind="malformed",
                       retryable=retryable)


def _api_message(body):
    """Best-effort human message from an envelope.

    Observed live (2026-10-13): errors look like
    {"error": true, "status_code": 401, "details": {"message": "Invalid or unknown API key."}}
    so ``details.message`` is checked first; documented success envelopes use top-level ``message``.
    """
    if isinstance(body, dict):
        details = body.get("details")
        if isinstance(details, dict):
            for key in ("message", "detail", "error"):
                val = details.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        elif isinstance(details, str) and details.strip():
            return details.strip()
        for key in ("message", "detail", "error_message", "error"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
        data = body.get("data")
        if isinstance(data, dict):
            for key in ("message", "error", "reason"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    return ""


def error_for_http_status(http_status, body=None, context="request"):
    """Map an HTTP status (and optional decoded body) to an ApiError."""
    api_msg = _api_message(body)
    documented = contract.HTTP_MEANINGS.get(http_status, "")
    suffix = (" API message: %s" % api_msg) if api_msg else ""

    if http_status == 401:
        return ApiError("Invalid or missing API key (HTTP 401). Check the key and try again." + suffix,
                        kind="auth", http_status=401)
    if http_status == 403:
        return ApiError("The API key is not allowed to use this feature or plan (HTTP 403). "
                        "This can also indicate insufficient credits." + suffix,
                        kind="forbidden", http_status=403)
    if http_status == 402:
        return ApiError("Insufficient credits (HTTP 402)." + suffix, kind="forbidden", http_status=402)
    if http_status == 404:
        return ApiError("Activity not found or not visible yet (HTTP 404). %s" % documented + suffix,
                        kind="not_found", http_status=404, retryable=(context == "status"))
    if http_status == 429:
        return ApiError("Rate limit exceeded (HTTP 429). Waiting longer before the next check." + suffix,
                        kind="rate_limited", http_status=429, retryable=True)
    if http_status in (400, 422):
        if any(marker in api_msg.lower() for marker in contract.NO_DATA_MESSAGE_MARKERS):
            return ApiError(
                "FortyGuard has no temperature data yet for part of the selected period (HTTP %d). Data for the "
                "most recent days usually appears about %d days later, so choose dates ending on or before %s. "
                "Nothing was charged: the API rejected the request before creating a job. API message: %s"
                % (http_status, contract.DATA_LATENCY_DAYS, recent_data_cutoff().isoformat(), api_msg),
                kind="no_data", http_status=http_status)
        return ApiError("The API rejected the input (HTTP %d). %s" % (http_status, documented) + suffix,
                        kind="invalid_input", http_status=http_status)
    if http_status is not None and http_status >= 500:
        if context == "submit":
            return ApiError("FortyGuard service error while submitting (HTTP %d). No job was created and nothing was "
                            "charged; try again in a moment." % http_status + suffix,
                            kind="server", http_status=http_status)
        return ApiError("FortyGuard service error (HTTP %d). %s" % (http_status, documented) + suffix,
                        kind="server", http_status=http_status, retryable=(context == "status"))
    return ApiError("Unexpected HTTP status %s from the API." % http_status + suffix,
                    kind="unknown", http_status=http_status)


def _check_envelope_error(body):
    if not isinstance(body, dict):
        raise ApiError("Unexpected response shape (not a JSON object).", kind="malformed")
    if body.get("error") in (True, "true", "True"):
        msg = _api_message(body) or "The API reported an error."
        raise ApiError(msg, kind="failed", details=body)


# ------------------------------------------------------------- submission

def parse_submit_response(http_status, body_bytes):
    """Return the activity_id from a POST /v1/heatmap response or raise ApiError."""
    body = None
    try:
        body = decode_json(body_bytes)
    except ApiError:
        if http_status is not None and http_status != 200:
            raise error_for_http_status(http_status, None, context="submit")
        raise
    if http_status is not None and http_status != 200:
        raise error_for_http_status(http_status, body, context="submit")
    _check_envelope_error(body)
    data = body.get("data")
    if not isinstance(data, dict) or not data.get("activity_id"):
        raise ApiError("Submission response did not contain data.activity_id.", kind="malformed", details=body)
    activity_id = str(data["activity_id"]).strip()
    if not activity_id:
        raise ApiError("Submission response contained an empty activity_id.", kind="malformed")
    return activity_id


# ----------------------------------------------------------------- status

class StatusResult(object):
    """Normalised view of a GET /v1/status/{id} response."""

    __slots__ = ("activity_id", "status", "raw_status", "result", "message", "is_success", "is_failure")

    def __init__(self, activity_id, raw_status, result=None, message=""):
        self.activity_id = activity_id
        self.raw_status = raw_status or ""
        self.status = self.raw_status.strip().lower()
        self.result = result
        self.message = message
        self.is_success = self.status in contract.TERMINAL_SUCCESS
        self.is_failure = self.status in contract.TERMINAL_FAILURE

    @property
    def is_terminal(self):
        return self.is_success or self.is_failure


def parse_status_response(http_status, body_bytes):
    """Parse a status response. Raises ApiError for HTTP/JSON problems.

    404 is returned as a retryable ApiError (documented: "temporarily unavailable
    immediately after submission").
    """
    body = None
    try:
        body = decode_json(body_bytes, retryable=True)  # a cut-off body is a transient problem, not a verdict
    except ApiError:
        if http_status is not None and http_status != 200:
            raise error_for_http_status(http_status, None, context="status")
        raise
    if http_status is not None and http_status != 200:
        raise error_for_http_status(http_status, body, context="status")
    _check_envelope_error(body)
    data = body.get("data")
    if not isinstance(data, dict):
        raise ApiError("Status response did not contain a data object.", kind="malformed", details=body)
    raw_status = data.get("status")
    if not isinstance(raw_status, str) or not raw_status.strip():
        raise ApiError("Status response did not contain data.status.", kind="malformed", details=body)
    return StatusResult(
        activity_id=str(data.get("activity_id") or ""),
        raw_status=raw_status,
        result=data.get("result"),
        message=_api_message(body),
    )


# ----------------------------------------------------------------- result

def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def extract_result(status_result):
    """Return (map_data, stats_data) from a completed StatusResult or raise ApiError."""
    if not status_result.is_success:
        raise ApiError("Activity is not completed (status: %s)." % status_result.raw_status, kind="failed")
    result = status_result.result
    if not isinstance(result, dict):
        raise ApiError("Completed status did not include a result object.", kind="malformed")
    map_data = result.get("map_data")
    stats_data = result.get("stats_data")
    if not isinstance(stats_data, dict):
        stats_data = {}
    return map_data, stats_data


def validate_map_data(map_data):
    """Validate that map_data is a usable GeoJSON FeatureCollection of polygons.

    Returns the FeatureCollection. Raises ApiError(kind='malformed') otherwise,
    including for an empty collection (we never invent data).
    """
    if not isinstance(map_data, dict) or map_data.get("type") != "FeatureCollection":
        raise ApiError("map_data is not a GeoJSON FeatureCollection.", kind="malformed")
    feats = map_data.get("features")
    if not isinstance(feats, list):
        raise ApiError("map_data.features is missing.", kind="malformed")
    if not feats:
        raise ApiError(
            "The job completed but FortyGuard returned an empty heatmap (0 tiles). This happens when the area lies outside "
            "the documented coverage (United States) or is smaller than one tile. Because the job completed, credits "
            "were most likely charged. Nothing was added to the project.", kind="empty")
    bad = 0
    for f in feats:
        geom = f.get("geometry") if isinstance(f, dict) else None
        if not isinstance(geom, dict) or geom.get("type") not in ("Polygon", "MultiPolygon"):
            bad += 1
    if bad == len(feats):
        raise ApiError("map_data contains no polygon features.", kind="malformed")
    return map_data


def available_measures(map_data):
    """Return the ordered list of documented numeric temperature fields present.

    A field counts as available when at least one feature has a finite numeric
    value for it. Order follows contract.MEASURE_PRIORITY.
    """
    feats = map_data.get("features") or []
    found = set()
    for f in feats:
        props = f.get("properties") if isinstance(f, dict) else None
        if not isinstance(props, dict):
            continue
        for name in contract.MEASURE_PRIORITY:
            if name not in found and _is_number(props.get(name)):
                found.add(name)
        if len(found) == len(contract.MEASURE_PRIORITY):
            break
    return [m for m in contract.MEASURE_PRIORITY if m in found]


def result_schema(map_data):
    """Classify the tile schema: 'temperature', 'aggregate', 'value' or None.

    Checked on the actual features, never assumed from the request.
    """
    feats = map_data.get("features") or []
    has = {"value": False, "temperature": False, "aggregate": False}
    for f in feats:
        props = f.get("properties") if isinstance(f, dict) else None
        if not isinstance(props, dict):
            continue
        if _is_number(props.get(contract.FIELD_VALUE)):
            has["value"] = True
        if _is_number(props.get(contract.FIELD_TEMPERATURE)):
            has["temperature"] = True
        if any(_is_number(props.get(k)) for k in (contract.FIELD_AVERAGE, contract.FIELD_MIN, contract.FIELD_MAX)):
            has["aggregate"] = True
        if all(has.values()):
            break
    if has["value"] and not (has["temperature"] or has["aggregate"]):
        return "value"
    if has["temperature"]:
        return "temperature"
    if has["aggregate"]:
        return "aggregate"
    if has["value"]:
        return "value"
    return None


def analysis_stats(stats_data):
    """Return documented analysis stats {analytic_type, units, n_cells, min, max, mean} (lower-case keys)."""
    if not isinstance(stats_data, dict):
        return {}
    out = {}
    for k, v in stats_data.items():
        if not isinstance(k, str):
            continue
        lk = k.lower()
        if lk in ("analytic_type", "units") and isinstance(v, str):
            out[lk] = v
        elif lk in ("n_cells", "min", "max", "mean") and _is_number(v):
            out[lk] = float(v) if lk != "n_cells" else int(v)
    return out


def duration_summary(map_data, field=contract.FIELD_VALUE):
    """Summary for exceedance/persistence: valid tiles, tiles with a positive duration, max.

    Zero is a valid result (no hours above the threshold), not missing data.
    Percentages are of valid TILES, not of geographic area.
    """
    base = numeric_summary(map_data, field)
    feats = map_data.get("features") or []
    positive = 0
    for f in feats:
        props = f.get("properties") if isinstance(f, dict) else {}
        v = props.get(field) if isinstance(props, dict) else None
        if _is_number(v) and v > 0:
            positive += 1
    base["positive"] = positive
    base["positive_pct_of_valid_tiles"] = (100.0 * positive / base["count"]) if base["count"] else None
    return base


def peak_time_summary(map_data, field=contract.FIELD_VALUE):
    """Summary for time_of_measure: valid tiles and the most common peak hour (0-23).

    00:00 (value 0) is a valid peak hour. Values are rounded to the nearest whole
    hour for the histogram; out-of-range values are reported as invalid.
    """
    feats = map_data.get("features") or []
    counts = {}
    missing = 0
    invalid = 0
    for f in feats:
        props = f.get("properties") if isinstance(f, dict) else {}
        v = props.get(field) if isinstance(props, dict) else None
        if not _is_number(v):
            missing += 1
            continue
        h = int(round(float(v)))
        if 0 <= h <= 23:
            counts[h] = counts.get(h, 0) + 1
        else:
            invalid += 1
    valid = sum(counts.values())
    mode_hour = None
    if counts:
        best = max(counts.values())
        mode_hour = min(h for h, c in counts.items() if c == best)  # earliest hour on ties
    return {"count": valid, "missing": missing, "invalid": invalid, "mode_hour": mode_hour,
            "mode_count": counts.get(mode_hour, 0) if mode_hour is not None else 0, "histogram": counts}


def format_hour_of_day(hour):
    return "%02d:00 %s" % (int(hour), contract.PEAK_TIME_TZ)


def numeric_summary(map_data, field):
    """Return dict(count, missing, min, max, mean) for a field, counting nonnumeric as missing."""
    feats = map_data.get("features") or []
    vals = []
    missing = 0
    for f in feats:
        props = f.get("properties") if isinstance(f, dict) else {}
        v = props.get(field) if isinstance(props, dict) else None
        if _is_number(v):
            vals.append(float(v))
        else:
            missing += 1
    if not vals:
        return {"count": 0, "missing": missing, "min": None, "max": None, "mean": None}
    return {"count": len(vals), "missing": missing, "min": min(vals), "max": max(vals),
            "mean": sum(vals) / len(vals)}


def temperature_stats(stats_data):
    """Return {'minimum','maximum','mean','standard_deviation'} from stats_data if present.

    Keys are matched case-insensitively because the docs show 'Temperature_stats'
    while real responses use 'temperature_stats'.
    """
    if not isinstance(stats_data, dict):
        return {}
    block = None
    for k, v in stats_data.items():
        if isinstance(k, str) and k.lower() == "temperature_stats" and isinstance(v, dict):
            block = v
            break
    if block is None:
        return {}
    out = {}
    for k, v in block.items():
        if isinstance(k, str) and _is_number(v):
            out[k.lower()] = float(v)
    return out


# ------------------------------------------------------------------ usage

class UsageInfo(object):
    """Normalised credits/plan report from POST /v1/system/fetch-api-key-usage."""

    __slots__ = ("plan_type", "cycle_type", "active", "key_status", "key_valid", "expiry_date",
                 "remaining_credits", "cycle_remaining_credits", "total_credits", "used_credits", "raw")

    def __init__(self, **kw):
        for name in self.__slots__:
            setattr(self, name, kw.get(name))

    def summary(self):
        parts = []
        if self.plan_type:
            parts.append("Plan: %s%s" % (self.plan_type, (" (%s)" % self.cycle_type) if self.cycle_type else ""))
        if self.key_status:
            parts.append("Key: %s" % self.key_status)
        if self.remaining_credits is not None:
            parts.append("Credits remaining: {:,}".format(int(self.remaining_credits)))
        if self.total_credits is not None:
            parts.append("of {:,}".format(int(self.total_credits)))
        if self.expiry_date:
            parts.append("Key expires: %s" % self.expiry_date)
        return " | ".join(parts) if parts else "Usage report received (no recognised fields)."


def parse_usage_response(http_status, body_bytes):
    """Parse the usage endpoint. Shape observed live (2026-10-13):
    {"plan_details": {"plan_type", "cycle_type", "active"}, "api_key_details": {"status", "valid", "expiry_date"},
     "credit_summary": {"total_available_credits", "cycle_remaining_credits", "total_remaining_credits", ...}}
    Errors: {"error": true, "message": "Unable to fetch API key usage."} with HTTP 500.
    """
    body = None
    try:
        body = decode_json(body_bytes)
    except ApiError:
        if http_status is not None and http_status != 200:
            raise error_for_http_status(http_status, None, context="usage")
        raise
    if http_status is not None and http_status != 200:
        if http_status >= 500:
            raise ApiError("FortyGuard could not report usage for this key (HTTP %d). This also happens when the key "
                           "does not belong to the selected API environment.%s"
                           % (http_status, (" API message: %s" % _api_message(body)) if _api_message(body) else ""),
                           kind="server", http_status=http_status)
        raise error_for_http_status(http_status, body, context="usage")
    _check_envelope_error(body)
    plan = body.get("plan_details") if isinstance(body.get("plan_details"), dict) else {}
    key = body.get("api_key_details") if isinstance(body.get("api_key_details"), dict) else {}
    credits = body.get("credit_summary") if isinstance(body.get("credit_summary"), dict) else {}
    # total_remaining_credits is the live balance: it dropped by 4,220 per completed request in testing,
    # while cycle_remaining_credits stayed frozen on a key whose billing cycle had ended (2026-10-19).
    cycle_remaining = credits.get("cycle_remaining_credits")
    remaining = credits.get("total_remaining_credits")
    if not _is_number(remaining):
        remaining = cycle_remaining
    total = credits.get("total_available_credits")
    used = credits.get("cycle_credits_used")
    if not plan and not key and not credits:
        raise ApiError("Usage response did not contain plan, key or credit details.", kind="malformed", details=body)
    return UsageInfo(
        plan_type=plan.get("plan_type"), cycle_type=plan.get("cycle_type"), active=plan.get("active"),
        key_status=key.get("status"), key_valid=key.get("valid"), expiry_date=key.get("expiry_date"),
        remaining_credits=remaining if _is_number(remaining) else None,
        cycle_remaining_credits=cycle_remaining if _is_number(cycle_remaining) else None,
        total_credits=total if _is_number(total) else None,
        used_credits=used if _is_number(used) else None,
        raw=body,
    )
