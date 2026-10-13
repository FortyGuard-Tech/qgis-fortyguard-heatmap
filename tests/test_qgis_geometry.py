# -*- coding: utf-8 -*-
"""QGIS-runtime tests: selection validation and EPSG:4326 transformation."""
import unittest

from tests import qgis_env

if qgis_env.qgis_available():
    qgis_env.start()
    from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry,
                           QgsPointXY, QgsProject, QgsVectorLayer)
    from fortyguard_heatmap.core import geometry
    from fortyguard_heatmap.core.payload import ValidationError


def _layer(crs="EPSG:4326", wkb="Polygon"):
    return QgsVectorLayer("%s?crs=%s" % (wkb, crs), "test", "memory")


def _add(layer, wkt):
    """Add a feature and return its provider-assigned id."""
    f = QgsFeature(layer.fields())
    f.setGeometry(QgsGeometry.fromWkt(wkt))
    ok, added = layer.dataProvider().addFeatures([f])
    layer.updateExtents()
    return added[0].id()


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class GeometryTests(unittest.TestCase):
    def test_requires_exactly_one_selected_feature(self):
        lyr = _layer()
        small_id = _add(lyr, "POLYGON((-74.017 40.705, -74.003 40.705, -74.003 40.718, -74.017 40.718, -74.017 40.705))")
        _add(lyr, "POLYGON((-73.9 40.7, -73.8 40.7, -73.8 40.8, -73.9 40.8, -73.9 40.7))")  # ~94 km2
        with self.assertRaises(ValidationError) as cm:
            geometry.prepare_aoi(lyr)
        self.assertIn("none selected", str(cm.exception))
        lyr.selectAll()
        with self.assertRaises(ValidationError) as cm:
            geometry.prepare_aoi(lyr)
        self.assertIn("2 selected", str(cm.exception))
        lyr.selectByIds([small_id])
        info = geometry.prepare_aoi(lyr)
        self.assertEqual(info.geometry_geojson["type"], "Polygon")
        self.assertEqual(info.source_crs_authid, "EPSG:4326")
        self.assertEqual(info.feature_id, small_id)
        self.assertAlmostEqual(info.area_sq_km, 1.708, places=2)  # ellipsoidal (WGS84) area

    def test_rejects_non_polygon_layer(self):
        lyr = _layer(wkb="Point")
        with self.assertRaises(ValidationError):
            geometry.prepare_aoi(lyr)
        with self.assertRaises(ValidationError):
            geometry.prepare_aoi(None)

    def test_transforms_web_mercator_to_wgs84_and_keeps_hole(self):
        lyr = _layer("EPSG:3857")
        # Build the geometry in 4326 then forward-transform to 3857 so we know the expected answer.
        src = QgsGeometry.fromWkt(
            "POLYGON((-74.017 40.705, -74.003 40.705, -74.003 40.718, -74.017 40.718, -74.017 40.705),"
            "(-74.012 40.709, -74.008 40.709, -74.008 40.713, -74.012 40.713, -74.012 40.709))")
        xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                       QgsCoordinateReferenceSystem("EPSG:3857"), QgsProject.instance())
        src.transform(xform)
        _add(lyr, src.asWkt())
        lyr.selectAll()
        info = geometry.prepare_aoi(lyr)
        gj = info.geometry_geojson
        self.assertEqual(gj["type"], "Polygon")
        self.assertEqual(len(gj["coordinates"]), 2, "hole must be preserved")
        outer = gj["coordinates"][0]
        lons = [p[0] for p in outer]
        lats = [p[1] for p in outer]
        self.assertAlmostEqual(min(lons), -74.017, places=5)
        self.assertAlmostEqual(max(lons), -74.003, places=5)
        self.assertAlmostEqual(min(lats), 40.705, places=5)
        self.assertAlmostEqual(max(lats), 40.718, places=5)
        self.assertEqual(outer[0], outer[-1])
        self.assertEqual(info.source_crs_authid, "EPSG:3857")
        # Original layer geometry must be untouched (still projected metres).
        orig = next(lyr.getFeatures()).geometry().asPolygon()[0][0]
        self.assertGreater(abs(orig.x()), 1000)

    def test_rejects_multipolygon_with_two_parts(self):
        lyr = _layer(wkb="MultiPolygon")
        _add(lyr, "MULTIPOLYGON(((-74.01 40.70, -74.00 40.70, -74.00 40.71, -74.01 40.70)),"
                  "((-73.99 40.70, -73.98 40.70, -73.98 40.71, -73.99 40.70)))")
        lyr.selectAll()
        with self.assertRaises(ValidationError) as cm:
            geometry.prepare_aoi(lyr)
        self.assertIn("MultiPolygon", str(cm.exception))

    def test_single_part_multipolygon_is_accepted_as_polygon(self):
        lyr = _layer(wkb="MultiPolygon")
        _add(lyr, "MULTIPOLYGON(((-74.01 40.70, -74.00 40.70, -74.00 40.71, -74.01 40.71, -74.01 40.70)))")
        lyr.selectAll()
        info = geometry.prepare_aoi(lyr)
        self.assertEqual(info.geometry_geojson["type"], "Polygon")

    def test_rejects_invalid_and_empty_geometry(self):
        lyr = _layer()
        _add(lyr, "POLYGON((0 0, 1 1, 1 0, 0 1, 0 0))")  # self-intersecting bow-tie
        lyr.selectAll()
        with self.assertRaises(ValidationError) as cm:
            geometry.prepare_aoi(lyr)
        self.assertIn("invalid", str(cm.exception).lower())
        with self.assertRaises(ValidationError):
            geometry.geometry_to_wgs84_polygon(QgsGeometry(), QgsCoordinateReferenceSystem("EPSG:4326"))


if __name__ == "__main__":
    unittest.main()
