# -*- coding: utf-8 -*-
"""Graduated temperature styling for heatmap tile layers."""
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsBilinearRasterResampler,
    QgsClassificationQuantile,
    QgsClassificationEqualInterval,
    QgsColorRampShader,
    QgsFillSymbol,
    QgsGradientColorRamp,
    QgsGradientStop,
    QgsGraduatedSymbolRenderer,
    QgsRasterShader,
    QgsRendererRange,
    QgsSingleBandPseudoColorRenderer,
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


def hours_ramp():
    """Pale -> deep orange for durations (hours)."""
    ramp = QgsGradientColorRamp(QColor(255, 247, 236), QColor(127, 39, 4))
    ramp.setStops([QgsGradientStop(0.35, QColor(253, 187, 132)), QgsGradientStop(0.7, QColor(239, 101, 72))])
    return ramp


def hour_of_day_ramp():
    """Night (deep blue) -> midday (yellow) -> evening (purple) for peak hour."""
    ramp = QgsGradientColorRamp(QColor(37, 52, 148), QColor(84, 39, 143))
    ramp.setStops([QgsGradientStop(0.25, QColor(65, 182, 196)), QgsGradientStop(0.5, QColor(253, 224, 61)),
                   QgsGradientStop(0.75, QColor(240, 96, 96))])
    return ramp


def range_label(lower, upper, unit_kind):
    if unit_kind == "celsius":
        return "%.1f - %.1f %s" % (lower, upper, contract.TCM_UNIT)
    if unit_kind == "hours":
        return "%.1f - %.1f %s" % (lower, upper, contract.HOURS_UNIT)
    if unit_kind == "hour_of_day":
        lo = int(lower)
        hi = int(upper) - 1 if upper > lower else int(upper)
        return "%02d:00 - %02d:59 %s" % (lo, max(lo, hi), contract.PEAK_TIME_TZ)
    return "%.2f - %.2f" % (lower, upper)


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
    """Graduated °C renderer (kept for the temperature snapshot)."""
    return apply_analysis_style(layer, field_name, "celsius", classes=classes, method=method)


def apply_analysis_style(layer, field_name, unit_kind, classes=7, method=None):
    """Apply a graduated renderer on ``field_name`` with legend labels in the right unit.

    unit_kind: 'celsius' (quantile classes), 'hours' (equal-interval classes; 0 is a
    valid value and sits in the first class) or 'hour_of_day' (six fixed 4-hour
    classes with clock labels, time zone stated).
    Returns the number of classes. Raises ApiError if the field is missing/non-numeric.
    Features with NULL values are not rendered.
    """
    idx = numeric_field_index(layer, field_name)
    symbol = QgsFillSymbol.createSimple({"outline_style": "no", "outline_width": "0"})
    symbol.setOpacity(0.8)
    renderer = QgsGraduatedSymbolRenderer(field_name)
    renderer.setSourceSymbol(symbol)
    ramp = {"celsius": temperature_ramp, "hours": hours_ramp, "hour_of_day": hour_of_day_ramp}.get(unit_kind, temperature_ramp)()
    renderer.setSourceColorRamp(ramp)

    if unit_kind == "hour_of_day":
        bounds = [0, 4, 8, 12, 16, 20, 24]
        n = len(bounds) - 1
        for i in range(n):
            sym = symbol.clone()
            sym.setColor(ramp.color(i / float(n - 1)))
            renderer.addClassRange(QgsRendererRange(float(bounds[i]), float(bounds[i + 1]), sym,
                                                    range_label(bounds[i], bounds[i + 1], unit_kind)))
    else:
        if method is None:
            method = "quantile" if unit_kind == "celsius" else "equal"
        renderer.setClassificationMethod(
            QgsClassificationQuantile() if method == "quantile" else QgsClassificationEqualInterval())
        renderer.updateClasses(layer, classes)
        if len(renderer.ranges()) == 0:
            vmin, vmax = layer.minimumValue(idx), layer.maximumValue(idx)
            if vmin is None or vmax is None:
                raise ApiError("Field '%s' has no numeric values to classify." % field_name, kind="malformed")
            renderer.addClassRange(QgsRendererRange(float(vmin), float(vmax), symbol.clone(), "%s" % vmin))
            renderer.updateColorRamp(ramp)
        for i, rng in enumerate(renderer.ranges()):  # ranges() returns copies -> update by index
            renderer.updateRangeLabel(i, range_label(rng.lowerValue(), rng.upperValue(), unit_kind))

    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return len(renderer.ranges())


def apply_surface_style(layer, unit_kind, vmin, vmax, opacity=0.75):
    """Continuous colour ramp for the smooth-surface raster (same ramps as the tiles).

    Returns the number of legend entries. NODATA stays transparent; bilinear
    resampling keeps the surface smooth when zooming in.
    """
    if vmax <= vmin:
        vmax = vmin + 1e-6
    ramp = {"celsius": temperature_ramp, "hours": hours_ramp, "hour_of_day": hour_of_day_ramp}.get(unit_kind, temperature_ramp)()
    unit = {"celsius": contract.TCM_UNIT, "hours": contract.HOURS_UNIT}.get(unit_kind, "")
    shader = QgsRasterShader()
    ramp_shader = QgsColorRampShader(vmin, vmax, ramp, QgsColorRampShader.Interpolated, QgsColorRampShader.Continuous)
    items = []
    steps = 6
    for i in range(steps + 1):
        v = vmin + (vmax - vmin) * i / float(steps)
        items.append(QgsColorRampShader.ColorRampItem(v, ramp.color(i / float(steps)), "%.1f %s" % (v, unit)))
    ramp_shader.setColorRampItemList(items)
    ramp_shader.setClip(False)
    try:  # tidy legend: one decimal and the unit next to the colour bar
        from qgis.core import QgsBasicNumericFormat, QgsColorRampLegendNodeSettings
        legend = QgsColorRampLegendNodeSettings()
        fmt = QgsBasicNumericFormat()
        fmt.setNumberDecimalPlaces(1)
        legend.setNumericFormat(fmt)
        legend.setSuffix(" " + unit if unit else "")
        ramp_shader.setLegendSettings(legend)
    except Exception:
        pass
    shader.setRasterShaderFunction(ramp_shader)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    renderer.setClassificationMin(vmin)
    renderer.setClassificationMax(vmax)
    renderer.setOpacity(opacity)
    layer.setRenderer(renderer)
    layer.resampleFilter().setZoomedInResampler(QgsBilinearRasterResampler())
    layer.resampleFilter().setZoomedOutResampler(QgsBilinearRasterResampler())
    layer.triggerRepaint()
    return len(items)
