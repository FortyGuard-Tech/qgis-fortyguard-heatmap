# -*- coding: utf-8 -*-
"""QGIS-runtime tests: saving, loading with OGR, styling, project persistence, demo fixtures."""
import json
import os
import shutil
import tempfile
import unittest

from tests import qgis_env

if qgis_env.qgis_available():
    qgis_env.start()
    from qgis.core import QgsGraduatedSymbolRenderer, QgsProject
    from fortyguard_heatmap.core import demo, output, responses, styling
    from fortyguard_heatmap.core.responses import ApiError


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class OutputStylingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_out_")
        QgsProject.instance().clear()

    def tearDown(self):
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self, fixture, measure):
        map_data, stats = demo.load_fixture(fixture)
        responses.validate_map_data(map_data)
        gpath, mpath = output.save_result(self.tmp, map_data, stats, "2024-07-15 14:00 | 100 m", "demo-x", demo=True)
        layer = output.load_layer(gpath, output.layer_name(measure, "2024-07-15 14:00 | 100 m", demo=True),
                                  measure, "2024-07-15 14:00 | 100 m", "demo-x", demo=True)
        return map_data, stats, gpath, mpath, layer

    def test_fixtures_match_documented_schemas(self):
        md, st = demo.load_fixture("single_hour")
        self.assertEqual(responses.available_measures(md), ["temperature"])
        md, st = demo.load_fixture("daily")
        self.assertEqual(responses.available_measures(md), ["average_temperature", "max_temperature", "min_temperature"])
        self.assertIn("temperature_stats", st)
        self.assertNotIn("demo_stats", md)

    def test_save_load_style_single_hour(self):
        map_data, stats, gpath, mpath, layer = self._load("single_hour", "temperature")
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.featureCount(), len(map_data["features"]))
        self.assertTrue(layer.name().startswith("[DEMO - synthetic]"))
        self.assertIn("°C", layer.name())
        self.assertEqual(layer.customProperty(output.PROP_DEMO), "true")
        self.assertEqual(layer.customProperty(output.PROP_MEASURE), "temperature")
        n = styling.apply_temperature_style(layer, "temperature")
        self.assertGreaterEqual(n, 2)
        r = layer.renderer()
        self.assertIsInstance(r, QgsGraduatedSymbolRenderer)
        self.assertEqual(r.classAttribute(), "temperature")
        self.assertTrue(all("°C" in rng.label() for rng in r.ranges()))
        # sidecar has no key and flags demo
        meta = json.load(open(mpath))
        self.assertTrue(meta["demo"])
        self.assertIsNone(meta["activity_id"])
        self.assertNotIn("api", json.dumps(meta).lower().replace("api_key", "").replace("fortyguard", ""))

    def test_daily_measures_and_restyle(self):
        map_data, stats, gpath, mpath, layer = self._load("daily", "average_temperature")
        for field in ("average_temperature", "min_temperature", "max_temperature"):
            styling.apply_temperature_style(layer, field, classes=5)
            self.assertEqual(layer.renderer().classAttribute(), field)
        with self.assertRaises(ApiError):
            styling.apply_temperature_style(layer, "temperature")  # not in daily schema
        with self.assertRaises(ApiError):
            styling.apply_temperature_style(layer, "tile_id_text_missing")

    def test_never_overwrites(self):
        map_data, stats = demo.load_fixture("daily")
        p1, _ = output.save_result(self.tmp, map_data, stats, "2024-07-15 | 100 m", "abc", demo=False)
        p2, _ = output.save_result(self.tmp, map_data, stats, "2024-07-15 | 100 m", "abc", demo=False)
        self.assertNotEqual(p1, p2)
        self.assertTrue(os.path.exists(p1) and os.path.exists(p2))
        self.assertTrue(os.path.basename(p1).startswith("fortyguard_tcm_"))
        meta = json.load(open(os.path.splitext(p1)[0] + ".meta.json"))
        self.assertEqual(meta["activity_id"], "abc")
        self.assertFalse(meta["demo"])

    def test_unique_path(self):
        a = output.unique_path(self.tmp, "x")
        open(a, "w").close()
        b = output.unique_path(self.tmp, "x")
        self.assertEqual(os.path.basename(b), "x_2.geojson")

    def test_project_roundtrip_keeps_output_file(self):
        map_data, stats, gpath, mpath, layer = self._load("daily", "max_temperature")
        styling.apply_temperature_style(layer, "max_temperature")
        proj_path = os.path.join(self.tmp, "demo_project.qgz")
        self.assertTrue(QgsProject.instance().write(proj_path))
        QgsProject.instance().clear()
        self.assertTrue(QgsProject.instance().read(proj_path))
        layers = list(QgsProject.instance().mapLayers().values())
        self.assertEqual(len(layers), 1)
        lyr = layers[0]
        self.assertTrue(lyr.isValid(), "layer source must resolve after reopening the project")
        self.assertEqual(os.path.realpath(lyr.source().split("|")[0]), os.path.realpath(gpath))
        self.assertIsInstance(lyr.renderer(), QgsGraduatedSymbolRenderer)
        self.assertEqual(lyr.customProperty(output.PROP_MEASURE), "max_temperature")

    def test_bad_output_dir(self):
        with self.assertRaises(ApiError):
            output.ensure_dir("")
        with self.assertRaises(ApiError):
            output.ensure_dir(os.path.join(gpath_that_is_a_file(self.tmp), "sub"))


def gpath_that_is_a_file(tmp):
    p = os.path.join(tmp, "afile")
    open(p, "w").close()
    return p


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class AnalysisStylingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_ana_")
        QgsProject.instance().clear()

    def tearDown(self):
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _load(self, fixture, analytic, threshold=None):
        from fortyguard_heatmap.core import contract
        map_data, stats = demo.load_fixture(fixture)
        responses.validate_map_data(map_data)
        self.assertEqual(responses.result_schema(map_data), "value")
        summary = "2024-07-15 to 2024-07-21 | 100 m" + (" | above %g °C" % threshold if threshold else "")
        gpath, mpath = output.save_result(self.tmp, map_data, stats, summary, "demo-x", demo=True, analytic_type=analytic)
        self.assertTrue(os.path.basename(gpath).startswith("fortyguard_DEMO_%s_" % analytic))
        name = output.layer_name("value", summary, demo=True, analytic_type=analytic)
        layer = output.load_layer(gpath, name, "value", summary, "demo-x", demo=True, analytic_type=analytic, threshold=threshold)
        return map_data, stats, layer

    def test_exceedance_hours_legend_and_zero_in_first_class(self):
        md, st, layer = self._load("exceedance", "exceedance", threshold=35)
        self.assertIn("Exceedance hours", layer.name())
        self.assertIn("above 35 °C", layer.name())
        self.assertEqual(layer.customProperty(output.PROP_ANALYSIS), "exceedance")
        self.assertEqual(layer.customProperty(output.PROP_THRESHOLD), "35")
        n = styling.apply_analysis_style(layer, "value", "hours")
        self.assertGreaterEqual(n, 2)
        ranges = layer.renderer().ranges()
        self.assertTrue(all(r.label().endswith(" h") for r in ranges), [r.label() for r in ranges])
        self.assertEqual(ranges[0].lowerValue(), 0.0, "zero hours is a valid value in the first class")
        d = responses.duration_summary(md)
        self.assertEqual(d["missing"], 1)
        self.assertGreater(d["positive"], 0)
        self.assertEqual(d["count"], 181)

    def test_persistence_legend(self):
        md, st, layer = self._load("persistence", "persistence", threshold=35)
        self.assertIn("Persistence hours", layer.name())
        styling.apply_analysis_style(layer, "value", "hours")
        self.assertTrue(all(" h" in r.label() for r in layer.renderer().ranges()))

    def test_peak_time_fixed_clock_classes(self):
        md, st, layer = self._load("time_of_measure", "time_of_measure")
        self.assertIn("Peak temperature time hour of day (UTC)", layer.name())
        n = styling.apply_analysis_style(layer, "value", "hour_of_day")
        self.assertEqual(n, 6)
        labels = [r.label() for r in layer.renderer().ranges()]
        self.assertEqual(labels[0], "00:00 - 03:59 UTC")
        self.assertEqual(labels[-1], "20:00 - 23:59 UTC")
        self.assertEqual(layer.renderer().ranges()[0].lowerValue(), 0.0, "midnight (0) is a valid peak hour")
        pk = responses.peak_time_summary(md)
        self.assertEqual(pk["missing"], 1)
        self.assertIsNotNone(pk["mode_hour"])
        self.assertIn(0, pk["histogram"])

    def test_temperature_style_unchanged(self):
        map_data, stats = demo.load_fixture("daily")
        gpath, _ = output.save_result(self.tmp, map_data, stats, "2024-07-15 | 100 m", "demo-x", demo=True)
        layer = output.load_layer(gpath, output.layer_name("average_temperature", "2024-07-15 | 100 m", demo=True),
                                  "average_temperature", "2024-07-15 | 100 m", "demo-x", demo=True)
        self.assertEqual(layer.customProperty(output.PROP_ANALYSIS), "tcm")
        styling.apply_temperature_style(layer, "average_temperature")
        self.assertTrue(all("°C" in r.label() for r in layer.renderer().ranges()))


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class SmoothSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_surf_")
        QgsProject.instance().clear()

    def tearDown(self):
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_surface_from_daily_fixture(self):
        from qgis.core import QgsRasterLayer, QgsSingleBandPseudoColorRenderer
        from fortyguard_heatmap.core import surface
        map_data, stats = demo.load_fixture("daily")
        aoi = demo.load_demo_aoi()["geometry"]
        array, gt, st = surface.build_surface(map_data, "average_temperature", aoi_polygon=aoi)
        self.assertGreater(st["valid_pixels"], 1000)
        tile_summary = responses.numeric_summary(map_data, "average_temperature")
        self.assertGreaterEqual(st["min"], tile_summary["min"] - 1e-3)
        self.assertLessEqual(st["max"], tile_summary["max"] + 1e-3)
        tif = surface.write_geotiff(os.path.join(self.tmp, "demo_smooth.tif"), array, gt)
        layer = output.load_surface_layer(tif, "demo surface", "average_temperature", "2024-07-15 | 100 m", "demo-x", demo=True)
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.crs().authid(), "EPSG:4326")
        self.assertEqual(layer.customProperty(output.PROP_SURFACE), "true")
        self.assertEqual(layer.customProperty(output.PROP_DEMO), "true")
        n = styling.apply_surface_style(layer, "celsius", st["min"], st["max"])
        self.assertEqual(n, 7)
        self.assertIsInstance(layer.renderer(), QgsSingleBandPseudoColorRenderer)
        labels = [i.label for i in layer.renderer().shader().rasterShaderFunction().colorRampItemList()]
        self.assertTrue(all("°C" in l for l in labels), labels)
        # pixels outside the AOI are nodata: sample a corner of the raster extent
        prov = layer.dataProvider()
        ext = layer.extent()
        from qgis.core import QgsPointXY
        corner = prov.sample(QgsPointXY(ext.xMinimum() + 1e-6, ext.yMinimum() + 1e-6), 1)
        self.assertFalse(corner[1], "corner pixel outside the AOI must be nodata")
        centre = prov.sample(QgsPointXY(ext.center()), 1)
        self.assertTrue(centre[1])
        self.assertTrue(st["min"] - 1e-3 <= centre[0] <= st["max"] + 1e-3)

    def test_exceedance_surface_hours_legend(self):
        from fortyguard_heatmap.core import surface
        map_data, stats = demo.load_fixture("exceedance")
        array, gt, st = surface.build_surface(map_data, "value")
        self.assertEqual(st["min"], 0.0, "zero hours is a real value and sets the minimum")
        tif = surface.write_geotiff(os.path.join(self.tmp, "exc_smooth.tif"), array, gt)
        layer = output.load_surface_layer(tif, "exc surface", "value", "x", "demo-x", demo=True, analytic_type="exceedance", threshold=35)
        styling.apply_surface_style(layer, "hours", st["min"], st["max"])
        labels = [i.label for i in layer.renderer().shader().rasterShaderFunction().colorRampItemList()]
        self.assertTrue(all(l.endswith(" h") for l in labels), labels)
