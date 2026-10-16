# -*- coding: utf-8 -*-
"""QGIS-runtime end-to-end test of the dialog in Demo Mode (offscreen GUI).

Drives the real widgets: adds the EPSG:3857 demo AOI layer, enables Demo Mode,
clicks Generate, waits for the job, and checks that a styled, clearly labelled
layer was added and saved. Also checks plugin initGui/unload with a fake iface.
"""
import os
import shutil
import tempfile
import unittest

from tests import qgis_env

if qgis_env.qgis_available():
    qgis_env.start()
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from qgis.PyQt.QtWidgets import QMainWindow, QToolBar
    from qgis.core import QgsGraduatedSymbolRenderer, QgsProject
    from qgis.gui import QgsMapCanvas, QgsMessageBar
    from fortyguard_heatmap import classFactory
    from fortyguard_heatmap.core import contract, output
    from fortyguard_heatmap.ui.dialog import HeatmapDialog


class FakeIface(object):
    """Minimal stand-in for QgisInterface used by the plugin and dialog."""

    def __init__(self):
        self._win = QMainWindow()
        self._canvas = QgsMapCanvas(self._win)
        self._bar = QgsMessageBar(self._win)
        self._toolbar = QToolBar(self._win)
        self.menu_actions = []
        self.toolbar_actions = []

    def mainWindow(self):
        return self._win

    def mapCanvas(self):
        return self._canvas

    def messageBar(self):
        return self._bar

    def addToolBarIcon(self, action):
        self.toolbar_actions.append(action); self._toolbar.addAction(action)

    def removeToolBarIcon(self, action):
        self.toolbar_actions.remove(action); self._toolbar.removeAction(action)

    def addPluginToMenu(self, name, action):
        self.menu_actions.append((name, action))

    def removePluginMenu(self, name, action):
        self.menu_actions.remove((name, action))


def pump(holder, timeout_ms=20000):
    loop = QEventLoop()
    t = QTimer(); t.setSingleShot(True); t.timeout.connect(loop.quit); t.start(timeout_ms)
    while not holder.get("done") and t.isActive():
        loop.processEvents(QEventLoop.AllEvents, 50)
    return bool(holder.get("done"))


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class DialogDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_dialog_")
        QgsProject.instance().clear()
        self.iface = FakeIface()

    def tearDown(self):
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_plugin_init_and_unload(self):
        plugin = classFactory(self.iface)
        plugin.initGui()
        self.assertEqual(len(self.iface.toolbar_actions), 1)
        self.assertEqual(len(self.iface.menu_actions), 1)
        self.assertEqual(self.iface.toolbar_actions[0].text(), "FortyGuard Heat Intelligence Layer")
        plugin.run()
        self.assertIsNotNone(plugin.dialog)
        self.assertTrue(plugin.dialog.isVisible())
        plugin.unload()
        self.assertEqual(self.iface.toolbar_actions, [])
        self.assertEqual(self.iface.menu_actions, [])
        self.assertIsNone(plugin.dialog)
        self.assertIsNone(plugin.action)

    def _run_demo(self, filter_index, measure_field=None):
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        dlg.key_edit.setText("SECRET-KEY-must-never-appear-in-logs")
        dlg.demo_check.setChecked(True)
        self.assertFalse(dlg.key_edit.isEnabled())
        self.assertIn("DEMO", dlg.generate_btn.text())
        dlg.demo_aoi_btn.click()
        layer = dlg.layer_combo.currentLayer()
        self.assertIsNotNone(layer)
        self.assertEqual(layer.crs().authid(), "EPSG:3857")
        self.assertEqual(layer.selectedFeatureCount(), 1)
        self.assertIn("EPSG:3857", dlg.selection_label.text())
        dlg.filter_combo.setCurrentIndex(filter_index)
        if measure_field:
            dlg.measure_combo.setCurrentIndex(dlg.measure_combo.findData(measure_field))
        before = set(QgsProject.instance().mapLayers().keys())
        done = {"done": False}

        def _finished(*a):
            done["done"] = True

        dlg.generate_btn.click()
        self.assertTrue(dlg.job is not None and dlg.job.is_active)
        self.assertFalse(dlg.generate_btn.isEnabled(), "Generate disabled while active")
        self.assertTrue(dlg.stop_btn.isEnabled())
        dlg.job.completed.connect(_finished)
        dlg.job.failed.connect(_finished)
        self.assertTrue(pump(done), "demo job did not finish")
        # let _on_completed run (same signal, connected earlier) - pump a little more
        pump({"done": False}, 200)
        after = set(QgsProject.instance().mapLayers().keys()) - before
        self.assertEqual(len(after), 1, "exactly one result layer added")
        result_layer = QgsProject.instance().mapLayer(after.pop())
        self.assertTrue(dlg.generate_btn.isEnabled())
        self.assertFalse(dlg.stop_btn.isEnabled())
        return dlg, result_layer

    def test_demo_single_hour(self):
        dlg, lyr = self._run_demo(0)
        self.assertTrue(lyr.name().startswith("[DEMO - synthetic]"))
        self.assertIn("temperature °C", lyr.name())
        self.assertEqual(lyr.customProperty(output.PROP_DEMO), "true")
        self.assertEqual(lyr.customProperty(output.PROP_MEASURE), "temperature")
        self.assertIsInstance(lyr.renderer(), QgsGraduatedSymbolRenderer)
        self.assertEqual(lyr.renderer().classAttribute(), "temperature")
        self.assertEqual(lyr.crs().authid(), "EPSG:4326")
        files = [f for f in os.listdir(self.tmp) if f.endswith(".geojson")]
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].startswith("fortyguard_DEMO_"))
        self.assertIn("SYNTHETIC", dlg.stats_label.text())
        self.assertIn("1 missing", dlg.stats_label.text())
        self.assertTrue(dlg.activity_label.text().startswith("demo-"))
        self.assertIn("Completed", dlg.status_label.text())
        self.assertNotIn("SECRET-KEY", dlg.log.toPlainText())

    def test_demo_daily_uses_preferred_measure_and_restyle(self):
        dlg, lyr = self._run_demo(2, measure_field=contract.FIELD_MAX)
        self.assertEqual(lyr.renderer().classAttribute(), "max_temperature")
        self.assertIn("maximum °C", lyr.name())
        dlg.measure_combo.setCurrentIndex(dlg.measure_combo.findData(contract.FIELD_MIN))
        dlg.restyle_btn.click()
        self.assertEqual(lyr.renderer().classAttribute(), "min_temperature")
        self.assertIn("minimum °C", lyr.name())
        self.assertEqual(lyr.customProperty(output.PROP_MEASURE), "min_temperature")

    def test_generate_without_selection_shows_validation(self):
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        dlg.demo_check.setChecked(True)
        # patch the modal error box so the test does not block
        shown = []
        dlg._show_error = lambda text: shown.append(text)
        dlg.generate_btn.click()
        self.assertEqual(len(shown), 1)
        self.assertIn("polygon layer", shown[0].lower())
        self.assertIsNone(dlg.job)

    def test_live_mode_requires_key(self):
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        dlg.demo_aoi_btn.click()
        shown = []
        dlg._show_error = lambda text: shown.append(text)
        dlg.key_edit.setText("")
        dlg.generate_btn.click()
        self.assertEqual(len(shown), 1)
        self.assertIn("API key", shown[0])
        self.assertIsNone(dlg.job)

    def test_defaults_for_new_installation(self):
        dlg = HeatmapDialog(self.iface)
        self.assertEqual(dlg.key_edit.text(), "", "a new installation starts without a key")
        self.assertEqual(dlg.key_edit.echoMode(), dlg.key_edit.Password)
        self.assertEqual(dlg.base_url, contract.DEFAULT_BASE_URL, "production by default")
        self.assertTrue(dlg.dev_group.isCollapsed())
        self.assertFalse(dlg.demo_check.isChecked())
        self.assertEqual(dlg.filter_combo.currentData(), contract.FILTER_SINGLE_DAY)
        self.assertTrue(dlg.output_dir.filePath().endswith(os.path.join("Documents", "FortyGuard Heatmaps"))
                        or os.path.isdir(dlg.output_dir.filePath()))
        self.assertIn("api-pricing", dlg.findChildren(type(dlg.selection_label))[0].text())

    def test_environment_switch_clears_key(self):
        dlg = HeatmapDialog(self.iface)
        dlg.key_edit.setText("SECRET-KEY-prod")
        dlg.base_url_combo.setCurrentIndex(dlg.base_url_combo.findData(contract.DEV_BASE_URL))
        self.assertEqual(dlg.key_edit.text(), "")
        self.assertEqual(dlg.base_url, contract.DEV_BASE_URL)
        self.assertNotIn("SECRET-KEY", dlg.log.toPlainText())
        self.assertIn("cleared", dlg.log.toPlainText())

    def test_check_credits_requires_key(self):
        dlg = HeatmapDialog(self.iface)
        shown = []
        dlg._show_error = lambda text: shown.append(text)
        dlg.check_key_btn.click()
        self.assertEqual(len(shown), 1)
        self.assertIsNone(dlg.usage_client)

    def test_shutdown_cleans_up(self):
        dlg, lyr = self._run_demo(0)
        dlg.key_edit.setText("not-a-real-key")
        dlg.shutdown()
        self.assertEqual(dlg.key_edit.text(), "")
        self.assertIsNone(dlg.job)
        self.assertIsNone(dlg.client)


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class DialogAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_dialog_ana_")
        QgsProject.instance().clear()
        self.iface = FakeIface()
        self.dlg = HeatmapDialog(self.iface)
        self.dlg.output_dir.setFilePath(self.tmp)
        self.dlg.demo_check.setChecked(True)
        self.dlg.demo_aoi_btn.click()

    def tearDown(self):
        self.dlg.shutdown()
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _select(self, analytic):
        self.dlg.analysis_combo.setCurrentIndex(self.dlg.analysis_combo.findData(analytic))

    def _run(self):
        before = set(QgsProject.instance().mapLayers())
        done = {"done": False}
        self.dlg.generate_btn.click()
        self.assertTrue(self.dlg.job is not None and self.dlg.job.is_active)
        self.dlg.job.completed.connect(lambda *a: done.__setitem__("done", True))
        self.dlg.job.failed.connect(lambda *a: done.__setitem__("done", True))
        self.assertTrue(pump(done), "demo job did not finish")
        pump({"done": False}, 200)
        new = set(QgsProject.instance().mapLayers()) - before
        self.assertEqual(len(new), 1, self.dlg.log.toPlainText()[-800:])
        return QgsProject.instance().mapLayer(new.pop())

    def test_four_choices_with_explanations_and_conditional_threshold(self):
        self.assertEqual([self.dlg.analysis_combo.itemData(i) for i in range(self.dlg.analysis_combo.count())],
                         ["tcm", "exceedance", "persistence", "time_of_measure"])
        self.assertFalse(self.dlg.threshold_spin.isVisibleTo(self.dlg))
        self.assertIn("Temperature across", self.dlg.analysis_help.text())
        self._select("exceedance")
        self.assertTrue(self.dlg.threshold_spin.isVisibleTo(self.dlg))
        self.assertEqual(self.dlg.threshold_spin.value(), 35.0)
        self.assertIn("Total hours above", self.dlg.analysis_help.text())
        self.assertIn("longest unbroken", self.dlg.threshold_help.text())
        self._select("time_of_measure")
        self.assertFalse(self.dlg.threshold_spin.isVisibleTo(self.dlg))
        self.assertIn("UTC", self.dlg.analysis_help.text())
        self.assertFalse(self.dlg.measure_combo.isEnabled())
        self._select("tcm")
        self.assertTrue(self.dlg.measure_combo.isEnabled())

    def test_single_hour_disabled_for_analyses_with_explanation(self):
        self.dlg.filter_combo.setCurrentIndex(self.dlg.filter_combo.findData(contract.FILTER_SINGLE_HOUR))
        self._select("persistence")
        self.assertEqual(self.dlg.filter_combo.currentData(), contract.FILTER_SINGLE_DAY)
        self.assertIn("changed from 'Single hour' to 'Single day'", self.dlg.log.toPlainText())
        model = self.dlg.filter_combo.model()
        self.assertFalse(model.item(self.dlg.filter_combo.findData(contract.FILTER_SINGLE_HOUR)).isEnabled())
        self._select("tcm")
        self.assertTrue(model.item(self.dlg.filter_combo.findData(contract.FILTER_SINGLE_HOUR)).isEnabled())

    def test_calendar_month_builds_filter_4(self):
        from qgis.PyQt.QtCore import QDate
        self.dlg.filter_combo.setCurrentIndex(self.dlg.filter_combo.findData("month"))
        self.assertTrue(self.dlg.month_edit.isVisibleTo(self.dlg))
        self.assertFalse(self.dlg.start_date.isVisibleTo(self.dlg))
        self.dlg.month_edit.setDate(QDate(2024, 2, 10))
        self._select("exceedance")
        body, aoi = self.dlg._collect_inputs()
        self.assertEqual(body["date_time"], {"start_date": "2024-02-01", "filter_type": 4, "end_date": "2024-02-29"})
        self.assertEqual(body["analytic_type"], "exceedance")
        self.assertEqual(body["threshold"], 35.0)
        self.assertEqual(body["direction"], "above")

    def test_exceedance_demo_layer_and_summary(self):
        self._select("exceedance")
        self.dlg.threshold_spin.setValue(35.0)
        lyr = self._run()
        self.assertTrue(lyr.name().startswith("[DEMO - synthetic] FortyGuard Exceedance hours"))
        self.assertIn("above 35 °C", lyr.name())
        self.assertEqual(lyr.renderer().classAttribute(), "value")
        self.assertTrue(all(r.label().endswith(" h") for r in lyr.renderer().ranges()))
        text = self.dlg.stats_label.text()
        self.assertIn("% of valid tiles", text)
        self.assertIn("maximum", text)
        self.assertIn("181 valid tiles", text)
        self.assertIn("SYNTHETIC", text)
        self.assertIn("Exceedance (hours)", self.dlg.log.toPlainText())
        files = [f for f in os.listdir(self.tmp) if f.endswith(".geojson")]
        self.assertTrue(files[0].startswith("fortyguard_DEMO_exceedance_"))

    def test_peak_time_demo_layer_and_summary(self):
        self._select("time_of_measure")
        self.dlg.filter_combo.setCurrentIndex(self.dlg.filter_combo.findData(contract.FILTER_RANGE_OF_DAYS))
        self.dlg.start_date.setDate(self.dlg.start_date.date().addDays(-7))
        lyr = self._run()
        self.assertIn("Peak temperature time hour of day (UTC)", lyr.name())
        labels = [r.label() for r in lyr.renderer().ranges()]
        self.assertEqual(labels[0], "00:00 - 03:59 UTC")
        text = self.dlg.stats_label.text()
        self.assertIn("most common peak hour", text)
        self.assertIn("UTC", text)
        self.assertIn("not converted", text)

    def test_results_are_separate_layers(self):
        self._select("exceedance")
        a = self._run()
        self._select("persistence")
        b = self._run()
        self._select("tcm")
        c = self._run()
        self.assertEqual(len({a.id(), b.id(), c.id()}), 3)
        self.assertEqual(len(QgsProject.instance().mapLayers()), 4)  # 3 results + demo AOI
        self.assertIn("Persistence hours", b.name())
        self.assertIn("tcm", c.name())


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class DialogSmoothSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_dialog_surf_")
        QgsProject.instance().clear()
        self.iface = FakeIface()
        self.dlg = HeatmapDialog(self.iface)
        self.dlg.output_dir.setFilePath(self.tmp)
        self.dlg.demo_check.setChecked(True)
        self.dlg.demo_aoi_btn.click()

    def tearDown(self):
        self.dlg.shutdown()
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        before = set(QgsProject.instance().mapLayers())
        done = {"done": False}
        self.dlg.generate_btn.click()
        self.dlg.job.completed.connect(lambda *a: done.__setitem__("done", True))
        self.dlg.job.failed.connect(lambda *a: done.__setitem__("done", True))
        self.assertTrue(pump(done)); pump({"done": False}, 300)
        return [QgsProject.instance().mapLayer(i) for i in set(QgsProject.instance().mapLayers()) - before]

    def test_smooth_surface_default_adds_raster_and_hides_tiles(self):
        from qgis.core import QgsRasterLayer, QgsVectorLayer
        from fortyguard_heatmap.ui.dialog import APPEARANCE_SMOOTH
        self.dlg.appearance_combo.setCurrentIndex(self.dlg.appearance_combo.findData(APPEARANCE_SMOOTH))
        new = self._run()
        rasters = [l for l in new if isinstance(l, QgsRasterLayer)]
        vectors = [l for l in new if isinstance(l, QgsVectorLayer)]
        self.assertEqual(len(rasters), 1); self.assertEqual(len(vectors), 1)
        self.assertTrue(rasters[0].name().endswith("(smooth surface)"))
        self.assertTrue(rasters[0].name().startswith("[DEMO - synthetic]"))
        root = QgsProject.instance().layerTreeRoot()
        self.assertFalse(root.findLayer(vectors[0].id()).isVisible(), "tiles layer added hidden")
        self.assertTrue(root.findLayer(rasters[0].id()).isVisible())
        files = os.listdir(self.tmp)
        self.assertTrue(any(f.endswith("_smooth.tif") for f in files), files)
        self.assertIn("smooth surface", self.dlg.log.toPlainText())
        self.assertIs(self.dlg.last_surface_layer, rasters[0])

    def test_tiles_only_option(self):
        from qgis.core import QgsRasterLayer
        from fortyguard_heatmap.ui.dialog import APPEARANCE_TILES
        self.dlg.appearance_combo.setCurrentIndex(self.dlg.appearance_combo.findData(APPEARANCE_TILES))
        new = self._run()
        self.assertFalse(any(isinstance(l, QgsRasterLayer) for l in new))
        self.assertIsNone(self.dlg.last_surface_layer)

    def test_peak_time_has_no_surface(self):
        from qgis.core import QgsRasterLayer
        from fortyguard_heatmap.ui.dialog import APPEARANCE_SMOOTH
        self.dlg.appearance_combo.setCurrentIndex(self.dlg.appearance_combo.findData(APPEARANCE_SMOOTH))
        self.dlg.analysis_combo.setCurrentIndex(self.dlg.analysis_combo.findData("time_of_measure"))
        new = self._run()
        self.assertFalse(any(isinstance(l, QgsRasterLayer) for l in new))
        self.assertIn("cyclic", self.dlg.log.toPlainText())
        vec = new[0]
        self.assertTrue(QgsProject.instance().layerTreeRoot().findLayer(vec.id()).isVisible())
