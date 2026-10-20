# -*- coding: utf-8 -*-
"""Client-side checks run before a paid request is submitted.

All findings come from internal testing against the production API (2026-10-19):
areas outside the documented coverage and areas smaller than one tile complete
with 0 tiles and are charged; very large areas are accepted, never finish
(HTTP 504 on every status check) and are charged; an identical request repeated
after completion is charged again. None of this is enforced by the API before
the charge, so the plugin checks it first. The API remains the final authority;
every check here can be bypassed from the Developer settings.

Pure Python (no QGIS imports).
"""
import hashlib
import json

from . import contract

COVERAGE_INSIDE = "inside"
COVERAGE_PARTIAL = "partial"
COVERAGE_OUTSIDE = "outside"


def polygon_bbox(polygon_geojson):
    """(lon_min, lat_min, lon_max, lat_max) of a GeoJSON Polygon (outer ring)."""
    ring = polygon_geojson["coordinates"][0]
    lons = [float(p[0]) for p in ring]
    lats = [float(p[1]) for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def point_in_ring(lon, lat, ring):
    """Even-odd ray casting test for a (lon, lat) point against a closed ring."""
    inside = False
    n = len(ring)
    for i in range(n - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        if (y0 > lat) != (y1 > lat):
            x_cross = x0 + (lat - y0) * (x1 - x0) / (y1 - y0)
            if x_cross > lon:
                inside = not inside
    return inside


def _ring_bbox(ring):
    return min(p[0] for p in ring), min(p[1] for p in ring), max(p[0] for p in ring), max(p[1] for p in ring)


def _intersects(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def coverage_status(polygon_geojson):
    """Return (status, region_names) against the documented coverage outlines.

    The corners of the area's bounding box, its centre and its outer-ring vertices
    are tested against each coverage outline:
    inside  - every sample point lies in one outline
    partial - some sample points lie in an outline, others do not (or the area
              is so large that it surrounds an outline)
    outside - no sample point lies in any outline; the API returns 0 tiles and charges
    """
    bb = polygon_bbox(polygon_geojson)
    cx, cy = (bb[0] + bb[2]) / 2.0, (bb[1] + bb[3]) / 2.0
    samples = [(bb[0], bb[1]), (bb[2], bb[1]), (bb[2], bb[3]), (bb[0], bb[3]), (cx, cy)]
    samples += [(float(p[0]), float(p[1])) for p in polygon_geojson["coordinates"][0]]
    touched = []
    for name, ring in contract.COVERAGE_OUTLINES:
        hits = sum(1 for lon, lat in samples if point_in_ring(lon, lat, ring))
        if hits == len(samples):
            return COVERAGE_INSIDE, [name]
        if hits or _intersects(bb, _ring_bbox(ring)):
            touched.append(name)
    if touched:
        return COVERAGE_PARTIAL, touched
    return COVERAGE_OUTSIDE, []


def tile_area_sq_km(granularity_m):
    return (float(granularity_m) / 1000.0) ** 2


def area_assessment(area_sq_km, granularity_m, plan_type=None):
    """Return {'block': str|None, 'warnings': [str]} for the area of interest.

    Rules (see module docstring for the evidence):
    * smaller than one tile          -> warning (0 tiles likely, still charged)
    * above the plan cap (if known)  -> warning
    * above the largest documented cap -> warning
    * above AREA_BLOCK_SQ_MI         -> block (never finished in testing, charged)
    """
    area_sq_mi = area_sq_km * 0.386102
    warnings = []
    block = None
    tile_km2 = tile_area_sq_km(granularity_m)
    if area_sq_km < tile_km2:
        warnings.append(
            "The area (%.0f m²) is smaller than one %d m tile (%.0f m²). In testing such areas completed with "
            "0 tiles and were still charged. Use a larger polygon."
            % (area_sq_km * 1e6, int(granularity_m), tile_km2 * 1e6))
    if area_sq_mi > contract.AREA_BLOCK_SQ_MI:
        block = ("The area (~%.0f mi²) is far above every documented plan allowance (%d mi² on API Premium). In testing, "
                 "requests above ~%d mi² were accepted, charged, and then never finished (the status service "
                 "answered HTTP 504 on every check). Split the area into smaller polygons."
                 % (area_sq_mi, contract.AREA_WARN_SQ_MI, contract.AREA_BLOCK_SQ_MI))
        return {"block": block, "warnings": warnings, "area_sq_mi": area_sq_mi}
    cap = None
    if plan_type:
        for name, value in contract.AREA_CAP_SQ_MI.items():
            if name.lower().replace("api ", "") in str(plan_type).lower():
                cap = (name, value)
                break
    if cap and area_sq_mi > cap[1]:
        warnings.append("The area (~%.2f mi²) is above the documented %d mi² allowance of your plan (%s). The API may "
                        "reject it or charge for it; the documentation does not say which." % (area_sq_mi, cap[1], cap[0]))
    elif not cap and area_sq_mi > contract.AREA_WARN_SQ_MI:
        warnings.append("The area (~%.0f mi²) is above the largest documented plan allowance (%d mi² on API Premium). "
                        "Large areas take long to process and cost the same credits as small ones."
                        % (area_sq_mi, contract.AREA_WARN_SQ_MI))
    return {"block": block, "warnings": warnings, "area_sq_mi": area_sq_mi}


def request_fingerprint(payload, base_url=""):
    """Stable SHA-256 of the request body plus the API host (never includes the key)."""
    canon = json.dumps({"base_url": (base_url or "").rstrip("/"), "payload": payload},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def expected_cost_text(plan_type=None, remaining_credits=None):
    """Plain-language credit cost for the confirmation dialog."""
    cost = None
    if plan_type:
        for name, value in contract.CREDITS_PER_REQUEST.items():
            if name.lower().replace("api ", "") in str(plan_type).lower():
                cost = (name, value)
                break
    if cost:
        text = "Expected cost on your plan (%s): %s credits per completed request (documented)." % (
            cost[0], "{:,}".format(cost[1]))
    elif plan_type:
        text = ("Your plan (%s) has no documented per-request cost. In internal testing every completed request "
                "cost %s credits regardless of plan, area or resolution." % (plan_type, "{:,}".format(contract.CREDITS_PER_REQUEST_OBSERVED)))
    else:
        text = ("Documented cost: 3,500 credits per completed request on API Basic/Startup, 4,220 on API Premium. "
                "Click 'Check key and credits' first to see the figure for your plan.")
    if remaining_credits is not None:
        text += " Credits remaining at the last check: {:,}.".format(int(remaining_credits))
    return text
