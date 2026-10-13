# -*- coding: utf-8 -*-
"""Open QGIS, run the plugin's Demo Mode and LEAVE QGIS OPEN for the user to look at.

    /Applications/QGIS.app/Contents/MacOS/QGIS --nologo --code scripts/qgis_show_demo.py

Adds an OpenStreetMap basemap (needs internet) under the demo result. No API call.
"""
import os

from qgis.PyQt.QtCore import QTimer
from qgis.core import QgsProject, QgsRasterLayer
from qgis.utils import iface, loadPlugin, startPlugin, plugins, active_plugins


def main():
    if "fortyguard_heatmap" not in plugins:
        loadPlugin("fortyguard_heatmap")
    if "fortyguard_heatmap" not in active_plugins:
        startPlugin("fortyguard_heatmap")
    plugin = plugins["fortyguard_heatmap"]

    osm = QgsRasterLayer("type=xyz&url=https://tile.openstreetmap.org/{z}/{x}/{y}.png&zmax=19&zmin=0",
                         "OpenStreetMap", "wms")
    if osm.isValid():
        QgsProject.instance().addMapLayer(osm)

    plugin.run()
    dlg = plugin.dialog
    dlg.demo_check.setChecked(True)
    dlg.demo_aoi_btn.click()
    dlg.filter_combo.setCurrentIndex(2)  # single day -> mean/min/max fixture
    dlg.generate_btn.click()

    def _after():
        if dlg.job is not None and dlg.job.is_active:
            QTimer.singleShot(500, _after)
            return
        # Put the basemap at the bottom and the AOI outline on top.
        root = QgsProject.instance().layerTreeRoot()
        if osm.isValid():
            node = root.findLayer(osm.id())
            if node:
                clone = node.clone(); root.addChildNode(clone); root.removeChildNode(node)
        iface.mapCanvas().refresh()
        iface.messageBar().pushInfo("FortyGuard Heatmap", "Demo heatmap added (synthetic data). "
                                    "Ready for you to explore - nothing was sent to the API.")

    QTimer.singleShot(1000, _after)


QTimer.singleShot(3000, main)
