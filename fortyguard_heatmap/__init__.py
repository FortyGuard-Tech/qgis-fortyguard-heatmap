# -*- coding: utf-8 -*-
"""FortyGuard Heatmap QGIS plugin entry point."""


def classFactory(iface):  # noqa: N802 (QGIS API name)
    """Load the plugin class. Called by QGIS with the QgisInterface instance."""
    from .plugin import FortyGuardHeatmapPlugin
    return FortyGuardHeatmapPlugin(iface)
