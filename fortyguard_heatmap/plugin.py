# -*- coding: utf-8 -*-
"""Plugin lifecycle: toolbar/menu action and dialog management."""
import contextlib
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

PLUGIN_NAME = "FortyGuard Heat Intelligence Layer"


class FortyGuardHeatmapPlugin(object):
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))

    # QGIS calls this after classFactory.
    def initGui(self):  # noqa: N802
        icon = QIcon(os.path.join(self.plugin_dir, "resources", "icon.png"))
        self.action = QAction(icon, PLUGIN_NAME, self.iface.mainWindow())
        self.action.setStatusTip("Generate a FortyGuard temperature heatmap for the selected polygon")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&" + PLUGIN_NAME, self.action)

    def unload(self):
        if self.dialog is not None:
            with contextlib.suppress(Exception):
                self.dialog.shutdown()
                self.dialog.close()
                self.dialog.deleteLater()
            self.dialog = None
        if self.action is not None:
            with contextlib.suppress(Exception):
                self.action.triggered.disconnect(self.run)
            self.iface.removePluginMenu("&" + PLUGIN_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

    def run(self):
        if self.dialog is None:
            from .ui.dialog import HeatmapDialog
            self.dialog = HeatmapDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()
