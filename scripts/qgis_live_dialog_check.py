# -*- coding: utf-8 -*-
"""REAL request through the plugin dialog, executed INSIDE the real QGIS application.

    FG_ENV=dev FG_FILTER=1 FG_START_TIME=14:00 \
    /Applications/QGIS.app/Contents/MacOS/QGIS --nologo --code scripts/qgis_live_dialog_check.py

What it does (through the installed plugin's own widgets):
  1. loads the plugin, opens the dialog, reads the key from ~/.config/fortyguard/api_key
     (never printed), selects the API environment (FG_ENV=prod|dev; default prod)
  2. clicks "Check key and credits" and records plan/credits
  3. adds the demo AOI (EPSG:3857), sets date 2024-07-15 and the requested filter,
     clicks Generate Heatmap and auto-answers the confirmation box with Yes
  4. waits for the job, verifies the result layer (numeric field, graduated style,
     file saved, project save/reopen), screenshots the dialog and the canvas
  5. restores the user's output-folder setting, writes dist/live_dialog_report.json, quits

THIS SPENDS CREDITS when the job completes. Run only with authorisation.
"""
import json
import os
import time
import traceback

from qgis.PyQt.QtCore import QDate, QTime, QTimer
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsGraduatedSymbolRenderer, QgsProject, QgsSettings
from qgis.utils import iface, loadPlugin, startPlugin, plugins, active_plugins


def _root():
    """Repository root: FG_ROOT, else the working directory (the plugin may be a copy inside the QGIS profile)."""
    root = os.environ.get("FG_ROOT") or os.getcwd()
    if os.path.isdir(os.path.join(root, "scripts")):
        return root
    import fortyguard_heatmap
    return os.path.dirname(os.path.dirname(os.path.realpath(fortyguard_heatmap.__file__)))


REPORT = {"steps": [], "ok": False, "started": time.strftime("%Y-%m-%d %H:%M:%S")}
SAVED_SETTINGS = {}


def step(name, ok=True, **info):
    REPORT["steps"].append(dict(name=name, ok=ok, **info))
    print("[live-dialog] %s %s %s" % ("OK " if ok else "FAIL", name, info))


def finish(ok):
    for k, v in SAVED_SETTINGS.items():
        if v is None or v == "":
            QgsSettings().remove(k)
        else:
            QgsSettings().setValue(k, v)
    REPORT["ok"] = ok
    REPORT["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    dist = os.path.join(_root(), "dist")
    os.makedirs(dist, exist_ok=True)
    with open(os.path.join(dist, "live_dialog_report.json"), "w") as fh:
        json.dump(REPORT, fh, indent=2)
    QTimer.singleShot(1500, iface.mainWindow().close)
    QTimer.singleShot(3500, lambda: os._exit(0 if ok else 1))


def read_key():
    path = os.path.expanduser("~/.config/fortyguard/api_key")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip()


def main():
    try:
        from fortyguard_heatmap.core import contract, output
        from fortyguard_heatmap.ui import dialog as dialog_mod

        SAVED_SETTINGS[output.OUTPUT_DIR_SETTING] = QgsSettings().value(output.OUTPUT_DIR_SETTING, "")

        if "fortyguard_heatmap" not in plugins:
            step("loadPlugin", loadPlugin("fortyguard_heatmap"))
        if "fortyguard_heatmap" not in active_plugins:
            step("startPlugin", startPlugin("fortyguard_heatmap"))
        plugin = plugins["fortyguard_heatmap"]
        plugin.run()
        dlg = plugin.dialog
        step("dialog_shown", dlg.isVisible())

        env = os.environ.get("FG_ENV", "prod")
        want = contract.DEV_BASE_URL if env == "dev" else contract.DEFAULT_BASE_URL
        if env == "dev":
            dlg.base_url_combo.setCurrentIndex(dlg.base_url_combo.findData(want))
        step("environment_selected", dlg.base_url == want, base_url=want,
             developer_group_collapsed=dlg.dev_group.isCollapsed())

        key = read_key()
        dlg.key_edit.setText(key)
        step("key_entered", bool(key), key_length=len(key), masked=dlg.key_edit.echoMode() != dlg.key_edit.Normal)

        out_dir = os.path.join(os.path.expanduser("~"), "Documents", "FortyGuard Heatmaps")
        dlg.output_dir.setFilePath(out_dir)

        # --- credits check
        dlg.check_key_btn.click()
        waited = {"t": 0}

        def _after_usage():
            waited["t"] += 1
            if dlg.usage_label.text() == "Checking..." and waited["t"] < 60:
                QTimer.singleShot(500, _after_usage)
                return
            usage_text = dlg.usage_label.text()
            step("credits_check", "Plan:" in usage_text or "Credits" in usage_text, text=usage_text)
            _generate()

        def _generate():
            dlg.demo_check.setChecked(False)
            dlg.demo_aoi_btn.click()
            lyr = dlg.layer_combo.currentLayer()
            step("aoi_selected", lyr is not None and lyr.selectedFeatureCount() == 1, crs=lyr.crs().authid(),
                 selection_text=dlg.selection_label.text())
            filter_type = int(os.environ.get("FG_FILTER", "3"))
            dlg.filter_combo.setCurrentIndex(dlg.filter_combo.findData(filter_type))
            fg_date = os.environ.get("FG_DATE")   # default: the dialog's own default date (today - latency)
            if fg_date:
                dlg.start_date.setDate(QDate.fromString(fg_date, "yyyy-MM-dd"))
            step("date_used", True, date=dlg.start_date.date().toString("yyyy-MM-dd"))
            st = os.environ.get("FG_START_TIME", "14:00")
            dlg.start_time.setTime(QTime.fromString(st, "HH:mm"))
            dlg.granularity_combo.setCurrentIndex(dlg.granularity_combo.findData(100))

            # Auto-answer the confirmation box (the real box is modal).
            confirmations = []

            def _auto_confirm(title, text):
                confirmations.append(text)
                return True

            dlg._confirm = _auto_confirm
            before = set(QgsProject.instance().mapLayers())
            dlg.generate_btn.click()
            step("confirmation_shown_and_accepted", len(confirmations) == 1,
                 text=(confirmations[0] if confirmations else "")[:400])
            step("job_active", dlg.job is not None and dlg.job.is_active, generate_enabled=dlg.generate_btn.isEnabled(),
                 stop_enabled=dlg.stop_btn.isEnabled(), status=dlg.status_label.text())

            dshot = os.path.join(_root(), "dist", "live_dialog_screenshot.png")

            def _poll():
                if dlg.job is not None and dlg.job.is_active:
                    waited["t"] += 1
                    if waited["t"] > 2400:
                        step("timeout", False, status=dlg.status_label.text())
                        return finish(False)
                    QTimer.singleShot(500, _poll)
                    return
                QTimer.singleShot(800, lambda: _verify(before, dshot))

            QTimer.singleShot(500, _poll)

        def _verify(before, dshot):
            try:
                log_text = dlg.log.toPlainText()
                step("key_not_in_log", key not in log_text and key not in dlg.status_label.text())
                step("activity_id", bool(dlg.activity_label.text()), activity_id=dlg.activity_label.text())
                statuses = [l for l in log_text.splitlines() if "Status:" in l]
                step("status_polling_seen", any("Processing" in s or "Submitted" in s for s in statuses),
                     statuses=statuses[-6:])
                new = set(QgsProject.instance().mapLayers()) - before
                if not new:
                    step("result_layer_added", False, status=dlg.status_label.text(), log=log_text[-1500:])
                    dlg.grab().save(dshot)
                    return finish(False)
                result = QgsProject.instance().mapLayer(new.pop())
                r = result.renderer()
                styled = isinstance(r, QgsGraduatedSymbolRenderer)
                step("result_layer_added", True, layer_name=result.name(), features=result.featureCount(),
                     crs=result.crs().authid(), source=result.source(), demo_flag=result.customProperty("fortyguard/demo"))
                step("not_labelled_demo", not result.name().startswith("[DEMO") and result.customProperty("fortyguard/demo") == "false")
                step("styled_graduated", styled, attribute=r.classAttribute() if styled else None,
                     classes=len(r.ranges()) if styled else 0, labels=[x.label() for x in r.ranges()] if styled else [])
                idx = result.fields().indexOf(r.classAttribute()) if styled else -1
                step("numeric_field", idx >= 0 and result.fields().at(idx).typeName() in ("double", "Real", "Integer64", "integer", "Integer"),
                     type=result.fields().at(idx).typeName() if idx >= 0 else None,
                     min=result.minimumValue(idx) if idx >= 0 else None, max=result.maximumValue(idx) if idx >= 0 else None)
                step("stats_shown", "API stats_data" in dlg.stats_label.text(), text=dlg.stats_label.text())
                src = result.source().split("|")[0]
                step("file_saved", os.path.isfile(src) and os.path.isfile(os.path.splitext(src)[0] + ".meta.json"), path=src)
                meta = json.load(open(os.path.splitext(src)[0] + ".meta.json"))
                step("meta_has_no_key", key not in json.dumps(meta) and meta.get("demo") is False, activity=meta.get("activity_id"))
                dlg.grab().save(dshot)
                step("dialog_screenshot", os.path.exists(dshot), path=dshot)
                iface.mapCanvas().setExtent(iface.mapCanvas().mapSettings().layerExtentToOutputExtent(result, result.extent()))
                iface.mapCanvas().refresh()

                def _persist():
                    try:
                        shot = os.path.join(_root(), "dist", "live_dialog_canvas.png")
                        iface.mapCanvas().saveAsImage(shot)
                        step("canvas_screenshot", os.path.exists(shot), path=shot)
                        proj = os.path.join(os.path.dirname(src), "live_dialog_project.qgz")
                        step("project_saved", QgsProject.instance().write(proj), path=proj)
                        QgsProject.instance().clear()
                        ok = QgsProject.instance().read(proj)
                        layers = [l for l in QgsProject.instance().mapLayers().values() if l.source().split("|")[0] == src]
                        step("project_reopened_layer_resolves", ok and len(layers) == 1 and layers[0].isValid())
                        finish(all(s["ok"] for s in REPORT["steps"]))
                    except Exception:
                        step("exception", False, trace=traceback.format_exc())
                        finish(False)

                QTimer.singleShot(2000, _persist)
            except Exception:
                step("exception", False, trace=traceback.format_exc())
                finish(False)

        QTimer.singleShot(500, _after_usage)
    except Exception:
        step("exception", False, trace=traceback.format_exc())
        finish(False)


QTimer.singleShot(3000, main)
