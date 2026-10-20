# -*- coding: utf-8 -*-
"""Capture review screenshots of a saved Phoenix result inside the real QGIS window.

    FG_RESULT=/path/to/fortyguard_tcm_*.geojson FG_AOI=/path/to/aoi.geojson FG_OUT=/path/to/folder \
    /Applications/QGIS.app/Contents/MacOS/QGIS --nologo --code scripts/qgis_capture_phoenix.py

Produces, through the plugin's own output/styling/surface code and no API call:
  09_tiles_12_classes_phoenix.png   tiles layer with 12 legend classes over OpenStreetMap
  10_smooth_surface_phoenix.png     smooth surface (band-named legend, bounded colour span)
  11_smooth_surface_zoom_phoenix.png the same surface zoomed in on the hottest blocks
With FG_FULL_STRETCH=1 the surface uses the exact data range instead of the 1 degree minimum span
(files get a _full_contrast suffix) so both looks can be compared.
Optional: FG_PLACE (file-name suffix, default phoenix), FG_LABEL (AOI layer name), FG_CLASSES (default 12),
FG_MEASURE (average_temperature, min_temperature or max_temperature).
Needs internet for the OpenStreetMap tiles. QGIS quits when done.
"""
import json
import os
import traceback

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsProject, QgsRasterLayer, QgsRectangle, QgsVectorLayer, QgsFillSymbol
from qgis.utils import iface

LOG = []


def log(msg):
    LOG.append(msg)
    print("[capture]", msg)


def finish(ok):
    with open(os.path.join(os.environ.get("FG_OUT", "."), "capture_phoenix_log.txt"), "w") as fh:
        fh.write("\n".join(LOG) + "\n")
    QTimer.singleShot(1000, iface.mainWindow().close)
    QTimer.singleShot(3000, lambda: os._exit(0 if ok else 1))


def grab(name):
    out = os.environ.get("FG_OUT", ".")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name)
    iface.mainWindow().grab().save(path)
    log("saved %s" % path)


def main():
    try:
        from fortyguard_heatmap.core import output, responses, styling, surface
        full = os.environ.get("FG_FULL_STRETCH") == "1"   # comparison: colour ramp over the exact data range
        if full:
            styling.MIN_SURFACE_SPAN.clear()
        tag = "_full_contrast" if full else ""
        place = os.environ.get("FG_PLACE", "phoenix")            # file-name suffix
        label = os.environ.get("FG_LABEL", "Downtown Phoenix (2 km square)")
        n_classes = int(os.environ.get("FG_CLASSES", "12"))
        result = os.environ["FG_RESULT"]
        aoi_path = os.environ["FG_AOI"]
        win = iface.mainWindow()
        win.resize(1600, 1000)
        with open(result, "r", encoding="utf-8") as fh:
            map_data = json.load(fh)
        responses.validate_map_data(map_data)
        meta = json.load(open(os.path.splitext(result)[0] + ".meta.json"))
        summary = meta.get("request_summary", "")
        activity = meta.get("activity_id", "")

        osm = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
                             "OpenStreetMap", "wms")
        QgsProject.instance().addMapLayer(osm)
        aoi = QgsVectorLayer(aoi_path, label, "ogr")
        aoi.setRenderer(aoi.renderer().clone())
        aoi.renderer().setSymbol(QgsFillSymbol.createSimple({"color": "0,0,0,0", "outline_color": "#15232e",
                                                             "outline_width": "0.6"}))
        QgsProject.instance().addMapLayer(aoi)

        measure = os.environ.get("FG_MEASURE", "average_temperature")
        name = output.layer_name(measure, summary, analytic_type="tcm")
        tiles = output.load_layer(result, name, measure, summary, activity, analytic_type="tcm")
        n = styling.apply_analysis_style(tiles, measure, "celsius", classes=n_classes)
        log("tiles styled with %d classes: %s" % (n, [r.label() for r in tiles.renderer().ranges()]))
        root = QgsProject.instance().layerTreeRoot()
        # order: AOI outline, tiles, basemap
        for lyr in (aoi, tiles):
            node = root.findLayer(lyr.id()); clone = node.clone(); root.insertChildNode(0, clone); root.removeChildNode(node)
        node = root.findLayer(osm.id()); clone = node.clone(); root.addChildNode(clone); root.removeChildNode(node)
        iface.layerTreeView().expandAllNodes()

        canvas = iface.mapCanvas()
        ext = canvas.mapSettings().layerExtentToOutputExtent(tiles, tiles.extent())
        ext.scale(1.25)
        canvas.setExtent(ext)
        canvas.refresh()

        state = {}

        def shot_tiles():
            if not full:
                grab("09_tiles_%d_classes_%s.png" % (n_classes, place))
            # smooth surface from the same tiles
            with open(aoi_path, "r", encoding="utf-8") as fh:
                poly = json.load(fh)["features"][0]["geometry"]
            array, gt, st = surface.build_surface(map_data, measure, aoi_polygon=poly)
            tif = surface.write_geotiff(os.path.join(os.environ.get("FG_OUT", "."), "%s_review_smooth.tif" % place),
                                        array, gt, description=surface.band_description("tcm", measure))
            rl = output.load_surface_layer(tif, output.surface_layer_name(name), measure, summary, activity, analytic_type="tcm")
            styling.apply_surface_style(rl, "celsius", st["min"], st["max"])
            lo, hi, widened = styling.surface_colour_span("celsius", st["min"], st["max"])
            log("surface %s colour span %.2f..%.2f widened=%s" % (st, lo, hi, widened))
            node = root.findLayer(rl.id()); clone = node.clone(); root.insertChildNode(1, clone); root.removeChildNode(node)
            root.findLayer(tiles.id()).setItemVisibilityChecked(False)
            iface.layerTreeView().expandAllNodes()
            canvas.refresh()
            state["rl"] = rl
            QTimer.singleShot(6000, shot_surface)

        def shot_surface():
            grab("10_smooth_surface%s_%s.png" % (tag, place))
            e = canvas.extent()
            c = e.center()
            zoom = QgsRectangle(c.x() + e.width() * 0.05, c.y() - e.height() * 0.22,
                                c.x() + e.width() * 0.45, c.y() + e.height() * 0.10)
            canvas.setExtent(zoom)
            canvas.refresh()
            QTimer.singleShot(7000, shot_zoom)

        def shot_zoom():
            grab("11_smooth_surface_zoom%s_%s.png" % (tag, place))
            proj = os.path.join(os.environ.get("FG_OUT", "."), "%s_review_project.qgz" % place)
            QgsProject.instance().write(proj)
            log("project saved %s" % proj)
            finish(True)

        QTimer.singleShot(8000, shot_tiles)   # let the OSM tiles arrive
    except Exception:
        log(traceback.format_exc())
        finish(False)


QTimer.singleShot(3000, main)
