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
        self.assertEqual(self.iface.toolbar_actions[0].text(), "FortyGuard Heatmap")
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
