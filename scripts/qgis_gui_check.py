# -*- coding: utf-8 -*-
"""Automated in-app check, executed INSIDE the real QGIS application.

    /Applications/QGIS.app/Contents/MacOS/QGIS --nologo --code scripts/qgis_gui_check.py

What it does (all through the installed plugin, no shortcuts):
  1. loads + starts the 'fortyguard_heatmap' plugin via qgis.utils (install/load check)
  2. opens the dialog, adds the EPSG:3857 demo AOI, enables Demo Mode, clicks Generate
  3. waits for the result layer, saves a canvas screenshot, saves a .qgz project,
     reopens the project to verify the layer source still resolves
  4. unloads the plugin (toolbar/menu cleanup check) and writes a JSON report to
     dist/gui_check_report.json, then quits QGIS.

The script never touches the API: Demo Mode only.
"""
import json
import os
import sys
import time
import traceback

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsProject, QgsGraduatedSymbolRenderer, QgsSettings
from qgis.utils import iface, loadPlugin, startPlugin, unloadPlugin, plugins, active_plugins

# QGIS's --code runner executes the file without defining __file__; locate the project
# through the installed plugin package (a symlink or copy of <project>/fortyguard_heatmap).
def _project_root():
    env = os.environ.get("FG_PROJECT_ROOT")
    if env:
        return env
    try:
        import fortyguard_heatmap
        return os.path.dirname(os.path.dirname(os.path.realpath(fortyguard_heatmap.__file__)))
    except Exception:
        return os.getcwd()


ROOT = _project_root()
DIST = os.path.join(ROOT, "dist")
REPORT = {"steps": [], "ok": False, "started": time.strftime("%Y-%m-%d %H:%M:%S")}


def step(name, ok=True, **info):
    REPORT["steps"].append(dict(name=name, ok=ok, **info))
    print("[gui-check] %s: %s %s" % ("OK " if ok else "FAIL", name, info if info else ""))


SAVED_OUTPUT_DIR = None


def finish(ok):
    if SAVED_OUTPUT_DIR is not None:
        if SAVED_OUTPUT_DIR:
            QgsSettings().setValue("fortyguard_heatmap/output_dir", SAVED_OUTPUT_DIR)
        else:
            QgsSettings().remove("fortyguard_heatmap/output_dir")
    REPORT["ok"] = ok
    REPORT["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    os.makedirs(DIST, exist_ok=True)
    with open(os.path.join(DIST, "gui_check_report.json"), "w") as fh:
        json.dump(REPORT, fh, indent=2)
    print("[gui-check] report written; quitting QGIS in 2 s")
    QTimer.singleShot(2000, iface.mainWindow().close)
    QTimer.singleShot(4000, lambda: os._exit(0 if ok else 1))


def main():
    try:
        from qgis.core import Qgis
        REPORT["qgis_version"] = Qgis.QGIS_VERSION
        step("qgis_version", version=Qgis.QGIS_VERSION)

        if "fortyguard_heatmap" not in plugins:
            ok = loadPlugin("fortyguard_heatmap")
            step("loadPlugin", ok)
            if not ok:
                return finish(False)
        if "fortyguard_heatmap" not in active_plugins:
            ok = startPlugin("fortyguard_heatmap")
            step("startPlugin", ok)
            if not ok:
                return finish(False)
        plugin = plugins["fortyguard_heatmap"]
        global SAVED_OUTPUT_DIR
        SAVED_OUTPUT_DIR = QgsSettings().value("fortyguard_heatmap/output_dir", "")
        step("toolbar_action_present", plugin.action is not None, text=plugin.action.text(),
             icon_loaded=not plugin.action.icon().isNull())

        plugin.run()
        dlg = plugin.dialog
        step("dialog_shown", dlg is not None and dlg.isVisible())

        out_dir = os.path.join(DIST, "gui_check_output")
        os.makedirs(out_dir, exist_ok=True)
        dlg.output_dir.setFilePath(out_dir)
        dlg.demo_check.setChecked(True)
        dlg.demo_aoi_btn.click()
        lyr = dlg.layer_combo.currentLayer()
        step("demo_aoi_layer", lyr is not None and lyr.crs().authid() == "EPSG:3857" and lyr.selectedFeatureCount() == 1,
             selection_text=dlg.selection_label.text())
        dlg.filter_combo.setCurrentIndex(2)  # single day -> daily aggregate fixture
        before = set(QgsProject.instance().mapLayers())
        dlg.generate_btn.click()
        step("generate_clicked_job_active", dlg.job is not None and dlg.job.is_active,
             generate_enabled=dlg.generate_btn.isEnabled(), stop_enabled=dlg.stop_btn.isEnabled())

        def _after_result():
            try:
                new = set(QgsProject.instance().mapLayers()) - before
                if not new:
                    step("result_layer_added", False, status=dlg.status_label.text(), log=dlg.log.toPlainText()[-800:])
                    return finish(False)
                result = QgsProject.instance().mapLayer(new.pop())
                step("result_layer_added", True, layer_name=result.name(), features=result.featureCount(),
                     crs=result.crs().authid(), source=result.source())
                step("styled_graduated", isinstance(result.renderer(), QgsGraduatedSymbolRenderer),
                     attribute=result.renderer().classAttribute() if isinstance(result.renderer(), QgsGraduatedSymbolRenderer) else None,
                     classes=len(result.renderer().ranges()) if isinstance(result.renderer(), QgsGraduatedSymbolRenderer) else 0)
                step("demo_labelled", result.name().startswith("[DEMO - synthetic]") and result.customProperty("fortyguard/demo") == "true")
                step("stats_shown", "SYNTHETIC" in dlg.stats_label.text(), text=dlg.stats_label.text())

                iface.mapCanvas().refreshAllLayers()
                shot = os.path.join(DIST, "gui_check_canvas.png")

                def _snapshot_and_persist():
                    try:
                        iface.mapCanvas().saveAsImage(shot)
                        step("canvas_screenshot", os.path.exists(shot), path=shot)
                        proj_path = os.path.join(out_dir, "gui_check_project.qgz")
                        ok = QgsProject.instance().write(proj_path)
                        step("project_saved", ok, path=proj_path)
                        src = result.source()
                        QgsProject.instance().clear()
                        ok = QgsProject.instance().read(proj_path)
                        layers = [l for l in QgsProject.instance().mapLayers().values() if l.source() == src]
                        step("project_reopened_layer_resolves", ok and len(layers) == 1 and layers[0].isValid(),
                             valid=[l.isValid() for l in layers])
                        unloadPlugin("fortyguard_heatmap")
                        step("unload", "fortyguard_heatmap" not in active_plugins and plugin.action is None)
                        finish(all(s["ok"] for s in REPORT["steps"]))
                    except Exception:
                        step("exception", False, trace=traceback.format_exc())
                        finish(False)

                QTimer.singleShot(1500, _snapshot_and_persist)
            except Exception:
                step("exception", False, trace=traceback.format_exc())
                finish(False)

        waited = {"t": 0}

        def _poll():
            waited["t"] += 1
            if dlg.job is not None and not dlg.job.is_active:
                QTimer.singleShot(500, _after_result)
            elif waited["t"] > 120:
                step("timeout_waiting_for_demo_job", False, status=dlg.status_label.text())
                finish(False)
            else:
                QTimer.singleShot(500, _poll)

        QTimer.singleShot(500, _poll)
    except Exception:
        step("exception", False, trace=traceback.format_exc())
        finish(False)


# QGIS runs --code scripts right after startup; defer a little so the GUI is fully up.
QTimer.singleShot(3000, main)
