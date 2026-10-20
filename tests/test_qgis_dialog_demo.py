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
        qgis_env.reset_plugin_settings()
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
        self.assertEqual(self.iface.toolbar_actions[0].text(), "FortyGuard Temperature Intelligence Layer")
        plugin.run()
        self.assertIsNotNone(plugin.dialog)
        self.assertTrue(plugin.dialog.isVisible())
        plugin.unload()
        self.assertEqual(self.iface.toolbar_actions, [])
        self.assertEqual(self.iface.menu_actions, [])
        self.assertIsNone(plugin.dialog)
        self.assertIsNone(plugin.action)

    def _run_demo(self, filter_index, measure_field=None):
        from fortyguard_heatmap.ui.dialog import APPEARANCE_TILES
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        dlg.appearance_combo.setCurrentIndex(dlg.appearance_combo.findData(APPEARANCE_TILES))  # one layer per result
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

    def test_getting_started_steps_on_separate_lines(self):
        dlg = HeatmapDialog(self.iface)
        intro = dlg.findChildren(type(dlg.selection_label))[0].text()
        for step in ("1. ", "2. ", "3. ", "4. "):
            self.assertIn(step, intro)
        # every step except the first is preceded by a line break
        self.assertIn("<br>2. ", intro); self.assertIn("<br>3. ", intro); self.assertIn("<br>4. ", intro)

    def test_default_dates_avoid_the_data_latency(self):
        from qgis.PyQt.QtCore import QDate
        dlg = HeatmapDialog(self.iface)
        expected = QDate.currentDate().addDays(-contract.DATA_LATENCY_DAYS)
        self.assertEqual(dlg.start_date.date(), expected, "default date is not 'yesterday' (rejected by the API)")
        self.assertEqual(dlg.end_date.date(), expected)
        self.assertIn("not available yet", dlg.findChildren(type(dlg.selection_label))[0].text())
        # switching to Range of days yields a valid 7-day window instead of start == end
        dlg.filter_combo.setCurrentIndex(dlg.filter_combo.findData(contract.FILTER_RANGE_OF_DAYS))
        self.assertEqual(dlg.start_date.date(), expected.addDays(-6))
        self.assertEqual(dlg.end_date.date(), expected)
        self.assertEqual(dlg.month_edit.date().day(), 1)

    def test_analysis_settings_are_restored_after_restart(self):
        dlg = HeatmapDialog(self.iface)
        dlg.analysis_combo.setCurrentIndex(dlg.analysis_combo.findData("persistence"))
        dlg.filter_combo.setCurrentIndex(dlg.filter_combo.findData(contract.FILTER_RANGE_OF_DAYS))
        dlg.threshold_spin.setValue(33.0)
        dlg.granularity_combo.setCurrentIndex(dlg.granularity_combo.findData(60))
        dlg.start_time.setTime(dlg.start_time.time().addSecs(3600))
        dlg.shutdown()
        again = HeatmapDialog(self.iface)   # "restart"
        self.assertEqual(again.analysis_combo.currentData(), "persistence")
        self.assertEqual(again.filter_combo.currentData(), contract.FILTER_RANGE_OF_DAYS)
        self.assertEqual(again.threshold_spin.value(), 33.0)
        self.assertEqual(again.granularity_combo.currentData(), 60)
        self.assertEqual(again.start_time.time().hour(), 15)
        self.assertTrue(again.threshold_spin.isVisibleTo(again))
        qgis_env.reset_plugin_settings()
        fresh = HeatmapDialog(self.iface)
        self.assertEqual(fresh.analysis_combo.currentData(), "tcm")

    def test_demo_stop_does_not_mention_a_server_job(self):
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        dlg.demo_check.setChecked(True)
        dlg.demo_aoi_btn.click()
        done = {"done": False}
        dlg.generate_btn.click()
        sub = {"done": False}
        dlg.job.submitted.connect(lambda a: sub.__setitem__("done", True))
        self.assertTrue(pump(sub))
        dlg.job.stopped.connect(lambda a: done.__setitem__("done", True))
        dlg.stop_btn.click()
        self.assertTrue(pump(done))
        pump({"done": False}, 100)
        self.assertEqual(dlg.status_label.text(), "Demo stopped")
        log = dlg.log.toPlainText()
        self.assertIn("No request was sent", log)
        self.assertNotIn("Check Again", log)
        self.assertNotIn("server", log.split("Demo replay stopped")[-1])
        self.assertFalse(dlg.resume_btn.isEnabled())
        self.assertTrue(dlg.generate_btn.isEnabled())

    def test_preflight_blocks_outside_coverage_and_huge_areas(self):
        from fortyguard_heatmap.core.geometry import AoiInfo
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        body = {"polygon_aoi": {}, "date_time": {"start_date": "2026-08-01", "filter_type": 3}, "granularity": 100,
                "analytic_type": "tcm"}
        paris = {"type": "Polygon", "coordinates": [[[2.32, 48.85], [2.36, 48.85], [2.36, 48.87], [2.32, 48.87], [2.32, 48.85]]]}
        block, warnings = dlg._preflight(body, AoiInfo(paris, "EPSG:4326", 1, "paris", 6.53))
        self.assertIsNotNone(block)
        self.assertIn("outside the documented FortyGuard coverage", block)
        self.assertIn("charged", block)
        phoenix_big = {"type": "Polygon", "coordinates": [[[-112.5, 33.0], [-112.0, 33.0], [-112.0, 33.5], [-112.5, 33.5], [-112.5, 33.0]]]}
        block, warnings = dlg._preflight(body, AoiInfo(phoenix_big, "EPSG:4326", 1, "big", 1300 / 0.386102))
        self.assertIsNotNone(block)
        self.assertIn("504", block)
        tiny = {"type": "Polygon", "coordinates": [[[-74.006, 40.7128], [-74.005904, 40.7128], [-74.005904, 40.712872],
                                                     [-74.006, 40.712872], [-74.006, 40.7128]]]}
        block, warnings = dlg._preflight(body, AoiInfo(tiny, "EPSG:4326", 1, "tiny", 64e-6))
        self.assertIsNone(block)
        self.assertTrue(any("smaller than one" in w for w in warnings), warnings)
        # recent dates are warned about, not blocked
        from qgis.PyQt.QtCore import QDate
        recent = dict(body, date_time={"start_date": QDate.currentDate().addDays(-1).toString("yyyy-MM-dd"), "filter_type": 3})
        manhattan = {"type": "Polygon", "coordinates": [[[-74.017, 40.705], [-74.003, 40.705], [-74.003, 40.718], [-74.017, 40.718], [-74.017, 40.705]]]}
        block, warnings = dlg._preflight(recent, AoiInfo(manhattan, "EPSG:4326", 1, "m", 1.7))
        self.assertIsNone(block)
        self.assertTrue(any("not available yet" in w for w in warnings), warnings)
        # the developer switch bypasses everything
        dlg.skip_checks_check.setChecked(True)
        block, warnings = dlg._preflight(body, AoiInfo(paris, "EPSG:4326", 1, "paris", 6.53))
        self.assertIsNone(block)
        self.assertIn("skipped", warnings[0])

    def test_identical_request_is_detected_from_the_output_folder(self):
        from fortyguard_heatmap.core import output, preflight
        dlg = HeatmapDialog(self.iface)
        dlg.output_dir.setFilePath(self.tmp)
        body = {"polygon_aoi": {"x": 1}, "date_time": {"start_date": "2026-07-15", "filter_type": 3}, "granularity": 100,
                "analytic_type": "exceedance", "threshold": 30.0, "direction": "above"}
        self.assertIsNone(dlg._previous_identical(body))
        fp = preflight.request_fingerprint(body, dlg.base_url)
        md = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {"value": 1},
                                                        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}}]}
        output.save_result(self.tmp, md, {}, "2026-07-15 | 100 m | above 30 °C", "9dfaa62a-first", analytic_type="exceedance",
                           fingerprint=fp, environment=dlg.base_url)
        text = dlg._previous_identical(body)
        self.assertIsNotNone(text)
        self.assertIn("9dfaa62a-first", text)
        self.assertIn("charged again", text)
        self.assertIsNone(dlg._previous_identical(dict(body, threshold=31.0)))

    def test_demo_single_hour(self):
        dlg, lyr = self._run_demo(0)
        self.assertTrue(lyr.name().startswith("[DEMO - synthetic]"))
        # the fixture has one NULL tile: the lowest class must start at the data minimum, not at 0
        self.assertAlmostEqual(lyr.renderer().ranges()[0].lowerValue(), 24.8051, places=3)
        # the status log does not repeat the same "Processing" line on every poll
        self.assertEqual(dlg.log.toPlainText().count("Status: Processing (Job still running)"), 1)
        self.assertIn("activity_id = demo-", dlg.log.toPlainText())
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

    def test_environment_selector_hidden_in_public_build(self):
        dlg = HeatmapDialog(self.iface)
        self.assertFalse(dlg.base_url_combo.isVisibleTo(dlg))
        self.assertFalse(dlg.base_url_label.isVisibleTo(dlg))
        self.assertEqual(dlg.base_url, contract.DEFAULT_BASE_URL)
        self.assertNotIn("dashboard", dlg.appearance_combo.itemText(0).lower())
        self.assertNotIn("Developer", dlg.dev_group.title())

    def test_environment_switch_clears_key(self):
        os.environ["FORTYGUARD_DEV_ENVIRONMENT"] = "1"
        try:
            dlg = HeatmapDialog(self.iface)
        finally:
            os.environ.pop("FORTYGUARD_DEV_ENVIRONMENT", None)
        self.assertTrue(dlg.base_url_combo.isVisibleTo(dlg))
        dlg.key_edit.setText("SECRET-KEY-prod")
        dlg.base_url_combo.setCurrentIndex(dlg.base_url_combo.findData(contract.DEV_BASE_URL))
        self.assertEqual(dlg.key_edit.text(), "")
        self.assertEqual(dlg.base_url, contract.DEV_BASE_URL)
        self.assertNotIn("SECRET-KEY", dlg.log.toPlainText())
        self.assertIn("cleared", dlg.log.toPlainText())

    def test_check_again_with_pasted_activity_requires_key_and_not_demo(self):
        dlg = HeatmapDialog(self.iface)
        shown = []
        dlg._show_error = lambda text: shown.append(text)
        self.assertFalse(dlg.resume_btn.isEnabled())
        dlg.activity_label.setText("4f35f470-ee05-4dfb-ba56-c61393b0a5eb")
        self.assertTrue(dlg.resume_btn.isEnabled(), "a pasted activity ID enables Check Again")
        dlg.resume_btn.click()
        self.assertEqual(len(shown), 1); self.assertIn("API key", shown[0])
        dlg.key_edit.setText("k"); dlg.demo_check.setChecked(True)
        self.assertFalse(dlg.resume_btn.isEnabled())
        dlg.demo_check.setChecked(False)
        dlg.key_edit.setText("some-key")
        dlg.resume_btn.click()   # builds a job on the typed id (network call to production is aborted on shutdown)
        self.assertIsNotNone(dlg.job)
        self.assertTrue(dlg.job.is_active)
        self.assertTrue(dlg._foreign_activity)
        self.assertIn("no new submission", dlg.log.toPlainText())
        dlg.shutdown()

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
        qgis_env.reset_plugin_settings()
        QgsProject.instance().clear()
        self.iface = FakeIface()
        self.dlg = HeatmapDialog(self.iface)
        self.dlg.output_dir.setFilePath(self.tmp)
        from fortyguard_heatmap.ui.dialog import APPEARANCE_TILES
        self.dlg.appearance_combo.setCurrentIndex(self.dlg.appearance_combo.findData(APPEARANCE_TILES))
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
        self.assertFalse(self.dlg.start_date_label.isVisibleTo(self.dlg), "no orphan 'Start date' label in month mode")
        self.dlg.filter_combo.setCurrentIndex(self.dlg.filter_combo.findData(contract.FILTER_SINGLE_DAY))
        self.assertTrue(self.dlg.start_date_label.isVisibleTo(self.dlg))
        self.dlg.filter_combo.setCurrentIndex(self.dlg.filter_combo.findData("month"))
        self.dlg.month_edit.setDate(QDate(2024, 2, 10))
        self._select("exceedance")
        body, aoi, notes = self.dlg._collect_inputs()
        self.assertEqual(notes, [])
        self.assertEqual(body["date_time"], {"start_date": "2024-02-01", "filter_type": 4, "end_date": "2024-02-29"})
        self.assertEqual(body["analytic_type"], "exceedance")
        self.assertEqual(body["threshold"], 35.0)
        self.assertEqual(body["direction"], "above")

    def test_legend_classes_option(self):
        self.assertEqual(self.dlg.classes_spin.value(), 10)
        self.dlg.classes_spin.setValue(16)
        self._select("tcm")
        lyr = self._run()
        n = len(lyr.renderer().ranges())
        self.assertGreater(n, 7); self.assertLessEqual(n, 16)
        self.dlg.classes_spin.setValue(4)
        self.dlg.restyle_btn.click()
        self.assertLessEqual(len(lyr.renderer().ranges()), 4)
        again = HeatmapDialog(self.iface)   # remembered
        self.assertEqual(again.classes_spin.value(), 4)
        again.shutdown()

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
        qgis_env.reset_plugin_settings()
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


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class DialogLiveFlowTests(unittest.TestCase):
    """The dialog against the scripted local API server (no FortyGuard call): Check Again across requests."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import HTTPServer
        from tests.test_qgis_job import FakeApi, make_handler
        cls.api = FakeApi()
        cls.server = HTTPServer(("127.0.0.1", 0), make_handler(cls.api))
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fg_dialog_live_")
        qgis_env.reset_plugin_settings()
        QgsProject.instance().clear()
        self.iface = FakeIface()
        os.environ["FORTYGUARD_DEV_ENVIRONMENT"] = "1"
        try:
            self.dlg = HeatmapDialog(self.iface)
        finally:
            os.environ.pop("FORTYGUARD_DEV_ENVIRONMENT", None)
        self.dlg.base_url_combo.addItem("local test server", self.base_url)
        self.dlg.base_url_combo.setCurrentIndex(self.dlg.base_url_combo.findData(self.base_url))
        self.dlg.key_edit.setText("TEST-KEY")
        self.dlg.output_dir.setFilePath(self.tmp)
        from fortyguard_heatmap.ui.dialog import APPEARANCE_TILES
        self.dlg.appearance_combo.setCurrentIndex(self.dlg.appearance_combo.findData(APPEARANCE_TILES))
        self.dlg.skip_checks_check.setChecked(True)
        self.dlg._confirm = lambda title, text: True
        self.dlg.demo_aoi_btn.click()
        self.dlg.start_date.setDate(self.dlg.start_date.date().addDays(-30))
        self.api.requests.clear()

    def tearDown(self):
        self.dlg.shutdown()
        QgsProject.instance().clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _completed(activity, kind):
        from tests.test_qgis_job import COMPLETED
        import json as _json
        body = _json.loads(_json.dumps(COMPLETED))
        body["data"]["activity_id"] = activity
        geom = {"type": "Polygon", "coordinates": [[[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71], [-74.01, 40.71], [-74.01, 40.70]]]}
        if kind == "exceedance":
            body["data"]["result"]["map_data"]["features"] = [
                {"type": "Feature", "properties": {"tile_id": i, "value": float(i)}, "geometry": geom} for i in range(4)]
            body["data"]["result"]["stats_data"] = {"analytic_type": "exceedance", "units": "hour", "n_cells": 4,
                                                    "min": 0, "max": 3, "mean": 1.5}
        else:
            body["data"]["result"]["map_data"]["features"] = [
                {"type": "Feature", "properties": {"tile_id": i, "average_temperature": 20.0 + i}, "geometry": geom} for i in range(4)]
        return body

    def _wait(self, signal_names, timeout=15000, click=None):
        """Connect to the job signals first (some are emitted synchronously), then click, then pump."""
        done = {"done": False}
        if click is not None and self.dlg.job is None:
            click()  # the click creates the job
            click = None
        for name in signal_names:
            getattr(self.dlg.job, name).connect(lambda *a: done.__setitem__("done", True))
        if click is not None:
            click()
        self.assertTrue(pump(done, timeout), self.dlg.log.toPlainText()[-1500:])
        pump({"done": False}, 250)

    def test_check_again_on_an_earlier_activity_restores_its_own_context(self):
        # 1. exceedance request A, server keeps it Processing; user stops waiting
        self.api.submit_response = (200, {"error": False, "data": {"activity_id": "act-A"}})
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-A", "status": "Processing"}})]
        self.dlg.analysis_combo.setCurrentIndex(self.dlg.analysis_combo.findData("exceedance"))
        self.dlg.threshold_spin.setValue(33.0)
        self.dlg.generate_btn.click()
        self._wait(["submitted"])
        self.assertEqual(self.dlg.activity_label.text(), "act-A")
        self._wait(["stopped"], click=self.dlg.stop_btn.click)
        self.assertIn("act-A", self.dlg._session_activities)
        # 2. a temperature request B completes
        self.api.submit_response = (200, {"error": False, "data": {"activity_id": "act-B"}})
        self.api.status_script = [(200, self._completed("act-B", "tcm"))]
        self.dlg.analysis_combo.setCurrentIndex(self.dlg.analysis_combo.findData("tcm"))
        before = set(QgsProject.instance().mapLayers())
        self.dlg.generate_btn.click()
        self._wait(["completed", "failed"])
        new_b = [QgsProject.instance().mapLayer(i) for i in set(QgsProject.instance().mapLayers()) - before]
        self.assertEqual(len(new_b), 1); self.assertIn("tcm mean", new_b[0].name())
        # 3. paste A's id and Check Again: the exceedance context (threshold, type) must come back
        self.api.status_script = [(200, self._completed("act-A", "exceedance"))]
        self.dlg.activity_label.setText("act-A")
        self.assertTrue(self.dlg.resume_btn.isEnabled())
        before = set(QgsProject.instance().mapLayers())
        self.dlg.resume_btn.click()
        self._wait(["completed", "failed"])
        new_a = [QgsProject.instance().mapLayer(i) for i in set(QgsProject.instance().mapLayers()) - before]
        self.assertEqual(len(new_a), 1, self.dlg.log.toPlainText()[-1200:])
        self.assertIn("Exceedance hours", new_a[0].name())
        self.assertIn("above 33 °C", new_a[0].name())
        self.assertEqual(len([r for r in self.api.requests if r[0] == "POST"]), 2, "no new submission")
        self.assertIn("act-A", self.dlg.log.toPlainText())
        self.assertIsNone(self.dlg._unfinished_activity, "A is no longer unfinished after its result was fetched")

    def test_cancelled_confirmation_keeps_the_previous_job_context(self):
        self.api.submit_response = (200, {"error": False, "data": {"activity_id": "act-A"}})
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-A", "status": "Processing"}})]
        self.dlg.analysis_combo.setCurrentIndex(self.dlg.analysis_combo.findData("persistence"))
        self.dlg.generate_btn.click()
        self._wait(["submitted"])
        self._wait(["stopped"], click=self.dlg.stop_btn.click)
        self.dlg.analysis_combo.setCurrentIndex(self.dlg.analysis_combo.findData("tcm"))
        self.dlg._confirm = lambda title, text: False
        self.dlg.generate_btn.click()
        self.assertEqual(self.dlg.last_analytic_type, "persistence", "a cancelled request must not replace the context")
        self.assertIn("cancelled", self.dlg.log.toPlainText())
        self.assertEqual(len([r for r in self.api.requests if r[0] == "POST"]), 1)

    def test_unknown_activity_takes_its_type_from_the_result(self):
        self.api.status_script = [(200, self._completed("4f35f470-foreign", "exceedance"))]
        self.dlg.activity_label.setText("4f35f470-foreign")
        before = set(QgsProject.instance().mapLayers())
        self.dlg.resume_btn.click()
        self._wait(["completed", "failed"])
        new = [QgsProject.instance().mapLayer(i) for i in set(QgsProject.instance().mapLayers()) - before]
        self.assertEqual(len(new), 1, self.dlg.log.toPlainText()[-1200:])
        self.assertIn("Exceedance hours", new[0].name())
        self.assertIn("activity 4f35f470", new[0].name())
        self.assertFalse(any(r[0] == "POST" for r in self.api.requests))

    def test_restyle_after_layer_removed_and_rebuilds_surface(self):
        from qgis.core import QgsRasterLayer
        from fortyguard_heatmap.ui.dialog import APPEARANCE_SMOOTH
        self.dlg.appearance_combo.setCurrentIndex(self.dlg.appearance_combo.findData(APPEARANCE_SMOOTH))
        self.api.submit_response = (200, {"error": False, "data": {"activity_id": "act-S"}})
        self.api.status_script = [(200, self._completed("act-S", "tcm"))]
        self.dlg.generate_btn.click()
        self._wait(["completed", "failed"])
        surface_before = self.dlg.last_surface_layer
        self.assertIsInstance(surface_before, QgsRasterLayer)
        self.assertIn("mean", surface_before.name())
        self.dlg.measure_combo.setCurrentIndex(self.dlg.measure_combo.findData(contract.FIELD_AVERAGE))
        self.dlg.restyle_btn.click()
        self.assertIsNot(self.dlg.last_surface_layer, surface_before, "surface rebuilt on restyle")
        self.assertEqual(len([l for l in QgsProject.instance().mapLayers().values() if isinstance(l, QgsRasterLayer)]), 1)
        QgsProject.instance().removeMapLayer(self.dlg.last_layer.id())
        shown = []
        self.dlg._show_error = lambda text: shown.append(text)
        self.dlg.restyle_btn.click()      # must not raise RuntimeError
        self.assertEqual(len(shown), 1); self.assertIn("removed", shown[0])
        self.assertFalse(self.dlg.restyle_btn.isEnabled())

    def test_buttons_are_not_default_buttons(self):
        for b in (self.dlg.generate_btn, self.dlg.resume_btn, self.dlg.stop_btn, self.dlg.check_key_btn):
            self.assertFalse(b.autoDefault()); self.assertFalse(b.isDefault())
        from qgis.PyQt.QtCore import QDate
        self.assertEqual(self.dlg.start_date.maximumDate(), QDate.currentDate())
