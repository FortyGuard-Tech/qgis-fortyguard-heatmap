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
