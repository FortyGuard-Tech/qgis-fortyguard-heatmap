# -*- coding: utf-8 -*-
"""Render a saved FortyGuard result inside the real QGIS app through the plugin's
output/styling code, save a screenshot + project, then quit.

    FG_RESULT=/path/to/fortyguard_tcm_*.geojson \
    /Applications/QGIS.app/Contents/MacOS/QGIS --nologo --code scripts/qgis_render_result.py

Writes dist/render_result_report.json and dist/render_result_canvas.png.
No API call is made.
"""
import json
import os
import time
import traceback

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsGraduatedSymbolRenderer, QgsProject
from qgis.utils import iface

REPORT = {"steps": [], "ok": False}


def _root():
    """Repository root: FG_ROOT, else the working directory (the plugin may be a copy inside the QGIS profile)."""
    root = os.environ.get("FG_ROOT") or os.getcwd()
    if os.path.isdir(os.path.join(root, "scripts")):
        return root
    import fortyguard_heatmap
    return os.path.dirname(os.path.dirname(os.path.realpath(fortyguard_heatmap.__file__)))


def step(name, ok=True, **info):
    REPORT["steps"].append(dict(name=name, ok=ok, **info))
    print("[render] %s %s %s" % ("OK " if ok else "FAIL", name, info))


def finish(ok):
    REPORT["ok"] = ok
    dist = os.path.join(_root(), "dist")
    os.makedirs(dist, exist_ok=True)
    with open(os.path.join(dist, "render_result_report.json"), "w") as fh:
        json.dump(REPORT, fh, indent=2)
    QTimer.singleShot(1500, iface.mainWindow().close)
    QTimer.singleShot(3500, lambda: os._exit(0 if ok else 1))


def main():
    try:
        from fortyguard_heatmap.core import contract, output, responses, styling
        path = os.environ.get("FG_RESULT")
        if not path or not os.path.isfile(path):
            step("result_file", False, path=path)
            return finish(False)
        with open(path, "r", encoding="utf-8") as fh:
            map_data = json.load(fh)
        responses.validate_map_data(map_data)
        meta_path = os.path.splitext(path)[0] + ".meta.json"
        meta = json.load(open(meta_path)) if os.path.exists(meta_path) else {}
        analytic = meta.get("analytic_type", "tcm")
        schema = responses.result_schema(map_data)
        measures = responses.available_measures(map_data)
        step("validated", True, features=len(map_data["features"]), measures=measures, schema=schema, analytic=analytic)
        summary = meta.get("request_summary", "live result")
        activity = meta.get("activity_id") or ""
        measure = measures[0] if analytic == "tcm" else "value"
        layer = output.load_layer(path, output.layer_name(measure, summary, analytic_type=analytic), measure, summary,
                                  activity, demo=False, analytic_type=analytic)
        n = styling.apply_analysis_style(layer, measure, contract.UNIT_KIND.get(analytic, "celsius"))
        step("layer_loaded_styled", isinstance(layer.renderer(), QgsGraduatedSymbolRenderer),
             layer_name=layer.name(), classes=n, crs=layer.crs().authid(), features=layer.featureCount(),
             labels=[r.label() for r in layer.renderer().ranges()])
        ts = responses.temperature_stats(meta.get("stats_data", {})) or responses.analysis_stats(meta.get("stats_data", {}))
        step("stats", bool(ts), stats=ts)
        iface.mapCanvas().setExtent(iface.mapCanvas().mapSettings().layerExtentToOutputExtent(layer, layer.extent()))
        iface.mapCanvas().refresh()

        def _shot():
            try:
                dist = os.path.join(_root(), "dist")
                os.makedirs(dist, exist_ok=True)
                shot = os.path.join(dist, "render_result_%s_canvas.png" % analytic)
                iface.mapCanvas().saveAsImage(shot)
                step("screenshot", os.path.exists(shot), path=shot)
                proj = os.path.join(os.path.dirname(path), "live_result_%s_project.qgz" % analytic)
                step("project_saved", QgsProject.instance().write(proj), path=proj)
                finish(all(s["ok"] for s in REPORT["steps"]))
            except Exception:
                step("exception", False, trace=traceback.format_exc())
                finish(False)

        QTimer.singleShot(2500, _shot)
    except Exception:
        step("exception", False, trace=traceback.format_exc())
        finish(False)


QTimer.singleShot(3000, main)
