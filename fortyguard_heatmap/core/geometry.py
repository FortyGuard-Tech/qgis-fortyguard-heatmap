# -*- coding: utf-8 -*-
"""QGIS-side geometry preparation: selected feature -> EPSG:4326 GeoJSON Polygon.

Must be called on the main thread (reads layers and features).
"""
import json

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsWkbTypes,
)

from .payload import ValidationError, validate_polygon_geojson

WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")


class AoiInfo(object):
    """Result of preparing an area of interest."""

    def __init__(self, geometry_geojson, source_crs_authid, feature_id, layer_name, area_sq_km):
        self.geometry_geojson = geometry_geojson      # GeoJSON Polygon dict (EPSG:4326)
        self.source_crs_authid = source_crs_authid
        self.feature_id = feature_id
        self.layer_name = layer_name
        self.area_sq_km = area_sq_km

    @property
    def area_sq_mi(self):
        return self.area_sq_km * 0.386102


def selected_polygon_feature(layer):
    """Return exactly one selected feature from a polygon vector layer or raise ValidationError."""
    if layer is None:
        raise ValidationError("Choose a polygon layer first.")
    if not hasattr(layer, "selectedFeatureCount"):
        raise ValidationError("The chosen layer is not a vector layer.")
    if QgsWkbTypes.geometryType(layer.wkbType()) != QgsWkbTypes.PolygonGeometry:
        raise ValidationError("Layer '%s' is not a polygon layer." % layer.name())
    count = layer.selectedFeatureCount()
    if count == 0:
        raise ValidationError("Select exactly one polygon feature in layer '%s' (none selected)." % layer.name())
    if count > 1:
        raise ValidationError(
            "Select exactly one polygon feature in layer '%s' (%d selected). "
            "The API accepts a single Polygon area." % (layer.name(), count))
    return next(layer.getSelectedFeatures())


def geometry_to_wgs84_polygon(geometry, source_crs, project=None):
    """Transform a copy of ``geometry`` to EPSG:4326 and return a GeoJSON Polygon dict.

    Holes are preserved. Coordinates are [longitude, latitude].
    """
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        raise ValidationError("The selected feature has no geometry.")
    if QgsWkbTypes.geometryType(geometry.wkbType()) != QgsWkbTypes.PolygonGeometry:
        raise ValidationError("The selected feature is not a polygon.")
    if geometry.isMultipart():
        parts = geometry.asGeometryCollection()
        parts = [p for p in parts if not p.isEmpty()]
        if len(parts) != 1:
            raise ValidationError(
                "The selected feature is a MultiPolygon with %d parts. The API documents a single Polygon; "
                "please select or create a single-part polygon." % len(parts))
        geometry = parts[0]
    if not geometry.isGeosValid():
        raise ValidationError("The selected polygon geometry is invalid: %s" % geometry.lastError())

    geom = type(geometry)(geometry)  # copy; never mutate the layer's geometry
    if not source_crs.isValid():
        raise ValidationError("The layer has no valid coordinate reference system; set one first.")
    if source_crs != WGS84:
        ctx = (project or QgsProject.instance()).transformContext()
        xform = QgsCoordinateTransform(source_crs, WGS84, ctx)
        try:
            res = geom.transform(xform)
        except Exception as exc:  # QgsCsException
            raise ValidationError("Could not transform the area to EPSG:4326: %s" % exc)
        if res != 0:
            raise ValidationError("Could not transform the area to EPSG:4326 (error code %s)." % res)

    gj = json.loads(geom.asJson(15))
    if gj.get("type") == "MultiPolygon" and len(gj.get("coordinates", [])) == 1:
        gj = {"type": "Polygon", "coordinates": gj["coordinates"][0]}
    return validate_polygon_geojson(gj)


def prepare_aoi(layer, project=None):
    """Validate the selection and return an AoiInfo in EPSG:4326."""
    feature = selected_polygon_feature(layer)
    source_crs = layer.crs()
    polygon = geometry_to_wgs84_polygon(feature.geometry(), source_crs, project)
    area_km2 = _approx_area_sq_km(polygon)
    return AoiInfo(polygon, source_crs.authid() or source_crs.description(), feature.id(), layer.name(), area_km2)


def _approx_area_sq_km(polygon_geojson):
    """Ellipsoidal area via QgsDistanceArea for the WGS84 polygon (informational only)."""
    from qgis.core import QgsDistanceArea, QgsGeometry
    da = QgsDistanceArea()
    da.setSourceCrs(WGS84, QgsProject.instance().transformContext())
    da.setEllipsoid("WGS84")
    geom = QgsGeometry.fromWkt(_polygon_wkt(polygon_geojson))
    try:
        return da.measureArea(geom) / 1_000_000.0
    except Exception:
        return 0.0


def _polygon_wkt(polygon_geojson):
    rings = []
    for ring in polygon_geojson["coordinates"]:
        rings.append("(" + ", ".join("%r %r" % (p[0], p[1]) for p in ring) + ")")
    return "POLYGON(" + ", ".join(rings) + ")"
