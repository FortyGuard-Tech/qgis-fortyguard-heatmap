# -*- coding: utf-8 -*-
"""Persist a heatmap result to disk and load it as a QGIS vector layer.

Main-thread only (touches QgsProject).
"""
import datetime as _dt
import glob
import json
import math
import os
import re

from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from . import contract
from .responses import ApiError

OUTPUT_DIR_SETTING = "fortyguard_heatmap/output_dir"
DEFAULT_OUTPUT_SUBDIR = os.path.join("Documents", "FortyGuard Heatmaps")

# Layer custom properties (never contains the API key).
PROP_PREFIX = "fortyguard/"
PROP_DEMO = PROP_PREFIX + "demo"
PROP_MEASURE = PROP_PREFIX + "measure"
PROP_UNIT = PROP_PREFIX + "unit"
PROP_ACTIVITY = PROP_PREFIX + "activity_id"
PROP_REQUEST = PROP_PREFIX + "request_summary"
PROP_ANALYSIS = PROP_PREFIX + "analytic_type"
PROP_THRESHOLD = PROP_PREFIX + "threshold_c"
PROP_SURFACE = PROP_PREFIX + "smooth_surface"

MAX_STEM_CHARS = 120   # keeps file names well inside every file system's 255-byte limit
SIBLING_SUFFIXES = (".geojson", ".meta.json", "_smooth.tif", "_EMPTY.meta.json")


def default_output_dir():
    return os.path.join(os.path.expanduser("~"), DEFAULT_OUTPUT_SUBDIR)


def ensure_dir(path):
    if not path:
        raise ApiError("No output folder chosen.", kind="invalid_input")
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as exc:
        raise ApiError("Cannot create output folder %s: %s" % (path, exc), kind="invalid_input")
    if not os.access(path, os.W_OK):
        raise ApiError("Output folder %s is not writable." % path, kind="invalid_input")
    return path


def _slug(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "x"


def _taken(directory, stem):
    return any(os.path.exists(os.path.join(directory, stem + suffix)) for suffix in SIBLING_SUFFIXES)


def unique_path(directory, stem, ext=".geojson"):
    """Return a path in ``directory`` whose stem is unused by any result file (never overwrite).

    The GeoJSON, its .meta.json sidecar and the _smooth.tif surface share the
    stem, so all of them are checked, not just the requested extension.
    """
    stem = stem[:MAX_STEM_CHARS].rstrip("_-.")
    candidate_stem = stem
    n = 1
    while _taken(directory, candidate_stem):
        n += 1
        candidate_stem = "%s_%d" % (stem, n)
    return os.path.join(directory, candidate_stem + ext)


def json_safe(value):
    """Return a copy with NaN/Infinity replaced by None so the output is valid JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def unit_label(analytic_type):
    kind = contract.UNIT_KIND.get(analytic_type, "celsius")
    if kind == "celsius":
        return contract.TCM_UNIT
    if kind == "hours":
        return "hours"
    return "hour of day (%s)" % contract.PEAK_TIME_TZ


def _stem(prefix, request_summary, activity_id, when):
    stamp = when.strftime("%Y%m%d_%H%M%S")
    short_id = _slug(str(activity_id))[:8] if activity_id else "noid"
    summary = _slug(request_summary.replace(" | ", "_").replace(" ", ""))[:60]
    return "%s_%s_%s_%s" % (prefix, summary, short_id, stamp)


def _write_json(path, doc):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(json_safe(doc), fh, allow_nan=False, indent=2)


def save_result(directory, map_data, stats_data, request_summary, activity_id, demo=False, when=None,
                analytic_type=contract.ANALYTIC_TYPE_TCM, fingerprint=None, environment=None):
    """Write map_data as GeoJSON plus a sidecar JSON with stats/metadata.

    Returns (geojson_path, sidecar_path). Never overwrites an existing file (the
    sidecar and surface names are checked too). Non-finite numbers become null so
    the files are valid JSON. The API key is never written.
    """
    directory = ensure_dir(directory)
    when = when or _dt.datetime.now()
    prefix = ("fortyguard_DEMO_%s" % analytic_type) if demo else ("fortyguard_%s" % analytic_type)
    geojson_path = unique_path(directory, _stem(prefix, request_summary, activity_id, when), ".geojson")
    sidecar_path = os.path.splitext(geojson_path)[0] + ".meta.json"

    with open(geojson_path, "w", encoding="utf-8") as fh:
        json.dump(json_safe(map_data), fh, allow_nan=False)
    meta = {
        "source": "SYNTHETIC DEMO DATA - not a FortyGuard analysis" if demo else "FortyGuard Temperature API",
        "demo": bool(demo),
        "analytic_type": analytic_type,
        "unit": unit_label(analytic_type),
        "activity_id": None if demo else activity_id,
        "request_summary": request_summary,
        "request_fingerprint": None if demo else fingerprint,
        "environment": None if demo else environment,
        "saved_at": when.isoformat(timespec="seconds"),
        "tiles": len(map_data.get("features") or []),
        "stats_data": stats_data,
    }
    _write_json(sidecar_path, meta)
    return geojson_path, sidecar_path


def save_empty_record(directory, stats_data, request_summary, activity_id, analytic_type, when=None,
                      fingerprint=None, environment=None):
    """Keep a local record of a completed job that returned no tiles (it was probably charged)."""
    directory = ensure_dir(directory)
    when = when or _dt.datetime.now()
    stem = _stem("fortyguard_%s" % analytic_type, request_summary, activity_id, when)
    path = unique_path(directory, stem, "_EMPTY.meta.json")
    _write_json(path, {
        "source": "FortyGuard Temperature API",
        "result": "Completed with 0 tiles (nothing added to the project; credits were most likely charged)",
        "analytic_type": analytic_type,
        "activity_id": activity_id,
        "request_summary": request_summary,
        "request_fingerprint": fingerprint,
        "environment": environment,
        "saved_at": when.isoformat(timespec="seconds"),
        "stats_data": stats_data,
    })
    return path


def find_previous_result(directory, fingerprint):
    """Return the newest sidecar dict (plus 'path') whose request_fingerprint matches, or None."""
    if not fingerprint or not directory or not os.path.isdir(directory):
        return None
    best = None
    for path in glob.glob(os.path.join(directory, "fortyguard_*.meta.json")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(meta, dict) or meta.get("request_fingerprint") != fingerprint:
            continue
        meta["path"] = path
        if best is None or str(meta.get("saved_at", "")) > str(best.get("saved_at", "")):
            best = meta
    return best


def layer_name(measure, request_summary, demo=False, analytic_type=contract.ANALYTIC_TYPE_TCM):
    """e.g. 'FortyGuard Exceedance hours | 2024-07-15 to 2024-07-21 | 100 m | above 35 °C'."""
    if analytic_type == contract.ANALYTIC_TYPE_TCM:
        label = contract.MEASURE_LABELS.get(measure, measure)
        name = "FortyGuard tcm %s %s | %s" % (label, contract.TCM_UNIT, request_summary)
    else:
        name = "FortyGuard %s %s | %s" % (contract.ANALYSIS_LABELS.get(analytic_type, analytic_type),
                                           unit_label(analytic_type), request_summary)
    return ("[DEMO - synthetic] " + name) if demo else name


def load_layer(geojson_path, name, measure, request_summary, activity_id, demo=False, project=None,
               analytic_type=contract.ANALYTIC_TYPE_TCM, threshold=None):
    """Load the saved GeoJSON with the OGR provider and add it to the project."""
    layer = QgsVectorLayer(geojson_path, name, "ogr")
    if not layer.isValid():
        raise ApiError("QGIS could not open the saved GeoJSON: %s" % geojson_path, kind="malformed")
    if layer.featureCount() == 0:
        raise ApiError("The saved heatmap layer has no features.", kind="malformed")
    layer.setCustomProperty(PROP_DEMO, "true" if demo else "false")
    layer.setCustomProperty(PROP_MEASURE, measure)
    layer.setCustomProperty(PROP_UNIT, unit_label(analytic_type))
    layer.setCustomProperty(PROP_ACTIVITY, "" if demo else (activity_id or ""))
    layer.setCustomProperty(PROP_REQUEST, request_summary)
    layer.setCustomProperty(PROP_ANALYSIS, analytic_type)
    layer.setCustomProperty(PROP_THRESHOLD, "" if threshold is None else str(threshold))
    if demo:
        layer.setAbstract("SYNTHETIC DEMO DATA generated by the FortyGuard Heatmap plugin for offline testing. "
                          "Not a FortyGuard analysis.")
    else:
        layer.setAbstract("FortyGuard %s heatmap (%s). Activity %s. %s" % (
            analytic_type, unit_label(analytic_type), activity_id, request_summary))
    (project or QgsProject.instance()).addMapLayer(layer)
    return layer


def surface_layer_name(base_name):
    return base_name + " (smooth surface)"


def load_surface_layer(tif_path, name, measure, request_summary, activity_id, demo=False, project=None,
                       analytic_type=contract.ANALYTIC_TYPE_TCM, threshold=None):
    """Load the smooth-surface GeoTIFF as a raster layer and add it to the project."""
    layer = QgsRasterLayer(tif_path, name, "gdal")
    if not layer.isValid():
        raise ApiError("QGIS could not open the smooth surface raster: %s" % tif_path, kind="malformed")
    layer.setCustomProperty(PROP_DEMO, "true" if demo else "false")
    layer.setCustomProperty(PROP_MEASURE, measure)
    layer.setCustomProperty(PROP_UNIT, unit_label(analytic_type))
    layer.setCustomProperty(PROP_ACTIVITY, "" if demo else (activity_id or ""))
    layer.setCustomProperty(PROP_REQUEST, request_summary)
    layer.setCustomProperty(PROP_ANALYSIS, analytic_type)
    layer.setCustomProperty(PROP_THRESHOLD, "" if threshold is None else str(threshold))
    layer.setCustomProperty(PROP_SURFACE, "true")
    layer.setAbstract(("SYNTHETIC DEMO DATA. " if demo else "") +
                      "Smooth surface interpolated from the FortyGuard %s tiles (presentation only; values between tile "
                      "centres are estimates). Activity %s. %s" % (analytic_type, activity_id or "-", request_summary))
    (project or QgsProject.instance()).addMapLayer(layer)
    return layer
