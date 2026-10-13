# -*- coding: utf-8 -*-
"""Graduated temperature styling for heatmap tile layers."""
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsClassificationQuantile,
    QgsClassificationEqualInterval,
    QgsFillSymbol,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsRendererRange,
)

from . import contract
from .responses import ApiError


def temperature_ramp():
    """Blue -> yellow -> red gradient (cool to hot). Self-contained; no style DB lookup."""
    ramp = QgsGradientColorRamp(QColor(49, 54, 149), QColor(165, 0, 38))
    ramp.setStops([
        QgsGradientStop(0.25, QColor(116, 173, 209)),
        QgsGradientStop(0.5, QColor(255, 255, 191)),
        QgsGradientStop(0.75, QColor(253, 174, 97)),
    ])
    return ramp


def numeric_field_index(layer, field_name):
    idx = layer.fields().indexOf(field_name)
    if idx < 0:
        raise ApiError("Field '%s' does not exist in the layer." % field_name, kind="malformed")
    ftype = layer.fields().at(idx).type()
    if ftype not in (QVariant.Double, QVariant.Int, QVariant.LongLong, QVariant.UInt, QVariant.ULongLong):
        raise ApiError("Field '%s' is not numeric (type %s); cannot apply a temperature ramp."
                       % (field_name, layer.fields().at(idx).typeName()), kind="malformed")
    return idx


def apply_temperature_style(layer, field_name, classes=7, method="quantile"):
    """Apply a graduated renderer on ``field_name`` with unit-labelled legend classes.

    Returns the number of classes created. Raises ApiError if the field is missing
    or non-numeric. Features with NULL values are simply not rendered by QGIS.
    """
    numeric_field_index(layer, field_name)

    symbol = QgsFillSymbol.createSimple({"outline_style": "no", "outline_width": "0"})
    symbol.setOpacity(0.8)
    renderer = QgsGraduatedSymbolRenderer(field_name)
    renderer.setSourceSymbol(symbol)
    renderer.setSourceColorRamp(temperature_ramp())
    renderer.setClassificationMethod(
        QgsClassificationQuantile() if method == "quantile" else QgsClassificationEqualInterval())
    renderer.updateClasses(layer, classes)

    # If every value is identical (or quantiles collapse), make sure at least one class exists.
    if len(renderer.ranges()) == 0:
        vmin, vmax = layer.minimumValue(layer.fields().indexOf(field_name)), layer.maximumValue(layer.fields().indexOf(field_name))
        if vmin is None or vmax is None:
            raise ApiError("Field '%s' has no numeric values to classify." % field_name, kind="malformed")
        renderer.addClassRange(QgsRendererRange(float(vmin), float(vmax), symbol.clone(), "%s" % vmin))
        renderer.updateColorRamp(temperature_ramp())

    unit = contract.TCM_UNIT
    # ranges() returns copies, so update labels by index.
    for i, rng in enumerate(renderer.ranges()):
        renderer.updateRangeLabel(i, "%.1f - %.1f %s" % (rng.lowerValue(), rng.upperValue(), unit))

    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return len(renderer.ranges())
