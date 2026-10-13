# -*- coding: utf-8 -*-
"""Pure payload construction and input validation for POST /v1/heatmap.

No QGIS imports. Geometry arrives as an already-serialised GeoJSON Polygon
dict in EPSG:4326 (see core/geometry.py for the QGIS side).
"""
import datetime as _dt
import re

from . import contract

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ValidationError(ValueError):
    """Raised for user-facing input problems. Message is safe to display."""


# ---------------------------------------------------------------- dates/times

def parse_date(value):
    """Return a datetime.date for a YYYY-MM-DD string or raise ValidationError."""
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValidationError("Date must use the format YYYY-MM-DD (got %r)." % (value,))
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError("Date %r is not a real calendar date." % (value,))


def parse_time(value):
    """Return a datetime.time for an HH:MM 24-hour string or raise ValidationError."""
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise ValidationError("Time must use the 24-hour format HH:MM (got %r)." % (value,))
    hh, mm = value.split(":")
    return _dt.time(int(hh), int(mm))


def latest_allowed_date(now=None):
    """Latest start_date the API accepts: 'now + 12 hours' (documented).

    The documentation does not say which time zone the API applies to this
    check. We therefore use the local calendar date of (now + 12 h), which is
    the most permissive reading; the API remains the final authority.
    """
    now = now or _dt.datetime.now()
    return (now + _dt.timedelta(hours=contract.FORECAST_HOURS_AHEAD)).date()


def check_date_bounds(day, now=None):
    min_day = _dt.date.fromisoformat(contract.MIN_DATE_ISO)
    if day < min_day:
        raise ValidationError(
            "Dates before %s are not supported by the FortyGuard API." % contract.MIN_DATE_ISO)
    max_day = latest_allowed_date(now)
    if day > max_day:
        raise ValidationError(
            "The API only supports dates up to %d hours ahead of now (latest date: %s)."
            % (contract.FORECAST_HOURS_AHEAD, max_day.isoformat()))


# ------------------------------------------------------------------ geometry

def validate_polygon_geojson(geometry):
    """Validate a GeoJSON Polygon geometry dict (lon/lat ordering, closed rings).

    Only 'Polygon' is accepted; the API documents a single Polygon AOI and
    MultiPolygon support is not documented.
    """
    if not isinstance(geometry, dict):
        raise ValidationError("AOI geometry must be a GeoJSON geometry object.")
    gtype = geometry.get("type")
    if gtype != "Polygon":
        raise ValidationError(
            "Only a single Polygon area is supported (got %s). "
            "MultiPolygon or other geometry types are not documented by the API." % gtype)
    rings = geometry.get("coordinates")
    if not isinstance(rings, list) or not rings:
        raise ValidationError("AOI polygon has no coordinate rings.")
    for idx, ring in enumerate(rings):
        if not isinstance(ring, list) or len(ring) < 4:
            raise ValidationError("AOI polygon ring %d needs at least 4 positions." % idx)
        for pos in ring:
            if (not isinstance(pos, (list, tuple)) or len(pos) < 2
                    or not all(isinstance(c, (int, float)) for c in pos[:2])):
                raise ValidationError("AOI polygon contains a malformed coordinate.")
            lon, lat = float(pos[0]), float(pos[1])
            if not (-180.0 <= lon <= 180.0) or not (-90.0 <= lat <= 90.0):
                raise ValidationError(
                    "AOI coordinate (%s, %s) is outside longitude/latitude bounds. "
                    "The area must be transformed to EPSG:4326 first." % (lon, lat))
        if list(ring[0][:2]) != list(ring[-1][:2]):
            raise ValidationError("AOI polygon ring %d is not closed (first and last positions differ)." % idx)
    return geometry


def build_polygon_aoi(geometry):
    """Wrap a validated Polygon geometry in the documented FeatureCollection."""
    validate_polygon_geojson(geometry)
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": geometry}
        ],
    }


# ------------------------------------------------------------------- payload

def build_date_time(filter_type, start_date, start_time=None, end_time=None, end_date=None, now=None):
    """Build the date_time object with only the fields the selected filter needs.

    Raises ValidationError on missing/invalid input or documented bound violations.
    """
    try:
        filter_type = int(filter_type)
    except (TypeError, ValueError):
        raise ValidationError("filter_type must be an integer 1-4.")
    if filter_type not in contract.FILTER_TYPE_LABELS:
        raise ValidationError("filter_type must be 1, 2, 3 or 4 (got %r)." % (filter_type,))

    start_day = parse_date(start_date)
    check_date_bounds(start_day, now)
    date_time = {"start_date": start_day.isoformat(), "filter_type": filter_type}

    if filter_type == contract.FILTER_SINGLE_HOUR:
        if not start_time:
            raise ValidationError("Single hour requires a start time.")
        date_time["start_time"] = parse_time(start_time).strftime("%H:%M")

    elif filter_type == contract.FILTER_RANGE_OF_HOURS:
        if not start_time or not end_time:
            raise ValidationError("Range of hours requires a start time and an end time.")
        t0 = parse_time(start_time)
        t1 = parse_time(end_time)
        if t1 <= t0:
            raise ValidationError("End time must be later than start time (same day).")
        span_minutes = (t1.hour * 60 + t1.minute) - (t0.hour * 60 + t0.minute)
        if span_minutes > contract.MAX_RANGE_OF_HOURS * 60:
            raise ValidationError(
                "Range of hours may not exceed %d hours." % contract.MAX_RANGE_OF_HOURS)
        date_time["start_time"] = t0.strftime("%H:%M")
        date_time["end_time"] = t1.strftime("%H:%M")

    elif filter_type == contract.FILTER_SINGLE_DAY:
        pass  # only start_date

    elif filter_type == contract.FILTER_RANGE_OF_DAYS:
        if not end_date:
            raise ValidationError("Range of days requires an end date.")
        end_day = parse_date(end_date)
        check_date_bounds(end_day, now)
        if end_day <= start_day:
            raise ValidationError("End date must be after the start date.")
        if (end_day - start_day).days > contract.MAX_RANGE_OF_DAYS:
            raise ValidationError(
                "Range of days may not exceed %d days." % contract.MAX_RANGE_OF_DAYS)
        date_time["end_date"] = end_day.isoformat()

    return date_time


def build_payload(polygon_geometry, filter_type, start_date, granularity,
                  start_time=None, end_time=None, end_date=None, now=None):
    """Build the full POST /v1/heatmap JSON body for a tcm heatmap.

    Only documented fields are sent. No time-zone field is added because the
    documentation does not define one.
    """
    try:
        granularity = int(granularity)
    except (TypeError, ValueError):
        raise ValidationError("Resolution must be one of %s metres." % (contract.GRANULARITY_OPTIONS,))
    if granularity not in contract.GRANULARITY_OPTIONS:
        raise ValidationError(
            "Resolution %s m is not supported. Documented options: %s metres."
            % (granularity, ", ".join(str(g) for g in contract.GRANULARITY_OPTIONS)))

    return {
        "polygon_aoi": build_polygon_aoi(polygon_geometry),
        "date_time": build_date_time(filter_type, start_date, start_time, end_time, end_date, now=now),
        "granularity": granularity,
        "analytic_type": contract.ANALYTIC_TYPE_TCM,
    }


def describe_request(payload):
    """Short human-readable summary for the layer name/legend (no secrets)."""
    dt = payload["date_time"]
    ft = dt["filter_type"]
    if ft == contract.FILTER_SINGLE_HOUR:
        when = "%s %s" % (dt["start_date"], dt["start_time"])
    elif ft == contract.FILTER_RANGE_OF_HOURS:
        when = "%s %s-%s" % (dt["start_date"], dt["start_time"], dt["end_time"])
    elif ft == contract.FILTER_SINGLE_DAY:
        when = dt["start_date"]
    else:
        when = "%s to %s" % (dt["start_date"], dt["end_date"])
    return "%s | %d m" % (when, payload["granularity"])
