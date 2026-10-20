# -*- coding: utf-8 -*-
"""Smooth surface rendering: turn the API's tiles into an interpolated raster.

This is a PRESENTATION step on top of the same API data (like the FortyGuard
dashboard look): the tile values are painted onto a fine pixel grid, blurred
with a nodata-aware Gaussian kernel, clipped to the area of interest and saved
as a GeoTIFF next to the GeoJSON. Values between tile centres are estimates;
the original tile layer stays the source of exact numbers.

Only numpy and GDAL, both bundled with QGIS, are used. The pure numpy parts
(``build_grid``, ``gaussian_blur_nodata``) have no QGIS dependency.
"""
import math
import os

import numpy as np

from . import contract
from .responses import ApiError, _is_number

NODATA = -9999.0
PIXELS_PER_TILE = 8          # pixel size = tile size / 8  (100 m tiles -> 12.5 m pixels)
BLUR_SIGMA_TILES = 0.45      # Gaussian sigma in tile units
MIN_WEIGHT = 0.15            # a pixel is valid only if >= 15 percent of its kernel weight comes from real tiles
MAX_PIXELS = 2500 * 2500     # above this the pixel density is halved (memory on 8 GB laptops)


def _tile_bbox(feature):
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates") or []
    if geom.get("type") == "Polygon":
        rings = coords
    elif geom.get("type") == "MultiPolygon":
        rings = [r for poly in coords for r in poly]
    else:
        return None
    xs = [p[0] for ring in rings for p in ring]
    ys = [p[1] for ring in rings for p in ring]
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def tile_size(map_data):
    """Median tile width/height in map units (degrees for EPSG:4326 results)."""
    ws, hs = [], []
    for f in (map_data.get("features") or [])[:500]:
        bb = _tile_bbox(f)
        if bb:
            ws.append(bb[2] - bb[0]); hs.append(bb[3] - bb[1])
    if not ws:
        raise ApiError("No polygon tiles to build a surface from.", kind="malformed")
    return float(np.median(ws)), float(np.median(hs))


def build_grid(map_data, field, pixels_per_tile=PIXELS_PER_TILE):
    """Paint tile values onto a pixel grid.

    Returns (values, mask, geotransform) where values is a float32 array
    (rows x cols, north-up), mask is True where a tile with a numeric value
    covers the pixel, and geotransform is the GDAL 6-tuple.
    Zero is a valid value; only null/non-numeric tiles are left unpainted.
    """
    feats = map_data.get("features") or []
    tw, th = tile_size(map_data)
    px = tw / float(pixels_per_tile)
    py = th / float(pixels_per_tile)
    boxes = []
    for f in feats:
        props = f.get("properties") or {}
        v = props.get(field)
        bb = _tile_bbox(f)
        if bb is None or not _is_number(v):
            continue
        boxes.append((bb, float(v)))
    if not boxes:
        raise ApiError("No tiles with a numeric '%s' value." % field, kind="malformed")
    minx = min(b[0][0] for b in boxes) - tw / 2.0
    maxx = max(b[0][2] for b in boxes) + tw / 2.0
    miny = min(b[0][1] for b in boxes) - th / 2.0
    maxy = max(b[0][3] for b in boxes) + th / 2.0
    cols = int(math.ceil((maxx - minx) / px))
    rows = int(math.ceil((maxy - miny) / py))
    while cols * rows > MAX_PIXELS and pixels_per_tile > 1:
        # very large areas: coarser pixels rather than a failure or hundreds of megabytes
        pixels_per_tile = max(1, pixels_per_tile // 2)
        px, py = tw / float(pixels_per_tile), th / float(pixels_per_tile)
        cols = int(math.ceil((maxx - minx) / px))
        rows = int(math.ceil((maxy - miny) / py))
    if cols * rows > MAX_PIXELS:
        raise ApiError("The area is too large for a smooth surface (%d x %d pixels)." % (cols, rows), kind="invalid_input")
    values = np.zeros((rows, cols), dtype=np.float32)
    mask = np.zeros((rows, cols), dtype=bool)
    for (x0, y0, x1, y1), v in boxes:
        c0 = max(0, int(math.floor((x0 - minx) / px)))
        c1 = min(cols, int(math.ceil((x1 - minx) / px)))
        r0 = max(0, int(math.floor((maxy - y1) / py)))
        r1 = min(rows, int(math.ceil((maxy - y0) / py)))
        if c1 > c0 and r1 > r0:
            values[r0:r1, c0:c1] = v
            mask[r0:r1, c0:c1] = True
    geotransform = (minx, px, 0.0, maxy, 0.0, -py)
    return values, mask, geotransform


def _gaussian_kernel(sigma):
    radius = max(1, int(math.ceil(3 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-(x ** 2) / (2 * sigma ** 2))
    return k / k.sum()


def _convolve_separable(a, k):
    """Separable 2-D convolution with edge padding (pure numpy)."""
    r = (len(k) - 1) // 2
    pad = np.pad(a, ((r, r), (r, r)), mode="edge")
    tmp = np.zeros_like(pad)
    for i, w in enumerate(k):
        tmp += w * np.roll(pad, i - r, axis=1)
    out = np.zeros_like(pad)
    for i, w in enumerate(k):
        out += w * np.roll(tmp, i - r, axis=0)
    return out[r:-r, r:-r]


def gaussian_blur_nodata(values, mask, sigma_px):
    """Nodata-aware Gaussian blur: blur(values*mask) / blur(mask).

    Pixels without any tile influence stay NODATA. Zero values are preserved as
    real values (they contribute 0, not 'missing').
    """
    if sigma_px <= 0:
        out = np.where(mask, values, NODATA).astype(np.float32)
        return out, mask.copy()
    k = _gaussian_kernel(sigma_px).astype(np.float32)
    v = values.astype(np.float32) * mask
    m = mask.astype(np.float32)
    num = _convolve_separable(v, k)
    den = _convolve_separable(m, k)
    valid = den >= MIN_WEIGHT
    out = np.full(values.shape, NODATA, dtype=np.float32)
    out[valid] = (num[valid] / den[valid]).astype(np.float32)
    return out, valid


def clip_to_polygon(values, valid, geotransform, polygon_geojson):
    """Set pixels outside the GeoJSON Polygon (EPSG:4326) to NODATA using GDAL rasterisation."""
    from osgeo import gdal, ogr, osr
    rows, cols = values.shape
    drv = gdal.GetDriverByName("MEM")
    ds = drv.Create("", cols, rows, 1, gdal.GDT_Byte)
    ds.SetGeoTransform(geotransform)
    srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1); band.Fill(0)
    vds = ogr.GetDriverByName("Memory").CreateDataSource("aoi")
    lyr = vds.CreateLayer("aoi", srs, ogr.wkbPolygon)
    feat = ogr.Feature(lyr.GetLayerDefn())
    rings = ["(" + ", ".join("%r %r" % (p[0], p[1]) for p in ring) + ")" for ring in polygon_geojson["coordinates"]]
    feat.SetGeometry(ogr.CreateGeometryFromWkt("POLYGON(" + ", ".join(rings) + ")"))
    lyr.CreateFeature(feat)
    gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1], options=["ALL_TOUCHED=TRUE"])
    inside = band.ReadAsArray().astype(bool)
    out = values.copy()
    out[~inside] = NODATA
    return out, valid & inside


def build_surface(map_data, field, aoi_polygon=None, pixels_per_tile=PIXELS_PER_TILE,
                  sigma_tiles=BLUR_SIGMA_TILES):
    """Full pipeline: grid -> blur -> clip. Returns (array, geotransform, stats dict)."""
    values, mask, gt = build_grid(map_data, field, pixels_per_tile)
    # pixels per tile may have been reduced for very large areas; derive it from the grid itself
    tw, _th = tile_size(map_data)
    effective_ppt = max(1.0, tw / gt[1])
    out, valid = gaussian_blur_nodata(values, mask, sigma_tiles * effective_ppt)
    if aoi_polygon is not None:
        out, valid = clip_to_polygon(out, valid, gt, aoi_polygon)
    if not valid.any():
        raise ApiError("The smooth surface has no valid pixels inside the area.", kind="malformed")
    vals = out[valid]
    stats = {"min": float(vals.min()), "max": float(vals.max()), "mean": float(vals.mean()),
             "rows": int(out.shape[0]), "cols": int(out.shape[1]), "valid_pixels": int(valid.sum()),
             "pixel_size": (gt[1], -gt[5])}
    return out, gt, stats


def write_geotiff(path, array, geotransform, description=None):
    """Write a float32 GeoTIFF (EPSG:4326, NODATA) with GDAL.

    ``description`` becomes the band description, which QGIS shows as the legend
    heading instead of "Band 1 (Gray)".
    """
    from osgeo import gdal, osr
    drv = gdal.GetDriverByName("GTiff")
    rows, cols = array.shape
    ds = drv.Create(path, cols, rows, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform(geotransform)
    srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    if description:
        band.SetDescription(str(description))
        band.SetMetadataItem("DESCRIPTION", str(description))
    band.WriteArray(array)
    band.FlushCache()
    ds = None
    return path


def band_description(analytic_type, measure):
    """Legend heading for the surface band, e.g. 'FortyGuard mean temperature (°C)'."""
    kind = contract.UNIT_KIND.get(analytic_type, "celsius")
    if kind == "celsius":
        return "FortyGuard %s temperature (%s)" % (contract.MEASURE_LABELS.get(measure, measure), contract.TCM_UNIT)
    if kind == "hours":
        return "FortyGuard %s (hours)" % contract.ANALYSIS_LABELS.get(analytic_type, analytic_type)
    return "FortyGuard %s" % contract.ANALYSIS_LABELS.get(analytic_type, analytic_type)


def surface_path_for(geojson_path):
    return os.path.splitext(geojson_path)[0] + "_smooth.tif"


def supports_surface(analytic_type):
    """Hour-of-day values are cyclic (23 and 0 are neighbours); averaging them is wrong, so no surface."""
    return analytic_type != contract.ANALYTIC_TYPE_TIME_OF_MEASURE
