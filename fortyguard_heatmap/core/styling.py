# -*- coding: utf-8 -*-
"""Graduated temperature styling for heatmap tile layers and the smooth surface.

Legend rules (from internal testing, 2026-10-19):
* Label precision follows the data spread. FortyGuard temperature fields often
  span a few tenths of a degree across a site, so one decimal made several
  classes read identically ("21.9 - 21.9 °C").
* Zero-width classes produced by the quantile method on data with few distinct
  values are dropped; a uniform result gets exactly one class ("all tiles = 2.0 h").
* QGIS matches a value to the first class whose [lower, upper] contains it,
  with both ends inclusive. The fixed hour-of-day classes therefore end just
  below the next bound so hour 4 lands in "04:00 - 07:59", not "00:00 - 03:59".
* The smooth surface uses a minimum colour span so a 0.2 °C difference is not
  stretched over the whole blue-to-red ramp.
"""
import contextlib

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

HOUR_BOUNDS = (0, 4, 8, 12, 16, 20, 24)
HOUR_EPSILON = 1e-6                     # class upper bound = next bound - epsilon (inclusive matching in QGIS)
MIN_SURFACE_SPAN = {"celsius": 1.0, "hours": 1.0}   # smallest range the full colour ramp is stretched over
UNITS = {"celsius": contract.TCM_UNIT, "hours": contract.HOURS_UNIT}


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


def _ramp_for(unit_kind):
    return {"celsius": temperature_ramp, "hours": hours_ramp, "hour_of_day": hour_of_day_ramp}.get(unit_kind, temperature_ramp)()


def decimals_for_span(span):
    """Number of decimals so that neighbouring class labels stay distinct."""
    span = abs(float(span))
    if span >= 2.0:
        return 1
    if span >= 0.2:
        return 2
    return 3


def format_value(value, unit_kind, decimals=1):
    unit = UNITS.get(unit_kind, "")
    text = "%.*f" % (decimals, value)
    return (text + " " + unit) if unit else text


def range_label(lower, upper, unit_kind, decimals=None):
    """Legend label for one class. ``decimals`` defaults to a value derived from the class width."""
    if unit_kind == "hour_of_day":
        return hour_class_label(lower, upper)
    if decimals is None:
        decimals = decimals_for_span(upper - lower) if upper != lower else 1
    unit = UNITS.get(unit_kind, "")
    text = "%.*f - %.*f" % (decimals, lower, decimals, upper)
    return (text + " " + unit) if unit else text


def uniform_label(value, unit_kind, decimals=1):
    return "all tiles = %s" % format_value(value, unit_kind, decimals)


def hour_class_label(lower, upper):
    """'04:00 - 07:59 UTC' for the class starting at hour 4."""
    lo = int(round(lower))
    nxt = int(round(upper + HOUR_EPSILON))     # upper is next_bound - epsilon
    hi = max(lo, nxt - 1)
    return "%02d:00 - %02d:59 %s" % (lo, min(hi, 23), contract.PEAK_TIME_TZ)


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


def _distinct_ranges(ranges):
    """Drop zero-width duplicates created by the quantile method; keep order."""
    out = []
    for rng in ranges:
        if rng.lowerValue() == rng.upperValue() and out and out[-1].upperValue() >= rng.lowerValue():
            continue  # the value is already covered by the previous class (inclusive upper bound)
        out.append(rng)
    return out


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
    ramp = _ramp_for(unit_kind)
    renderer.setSourceColorRamp(ramp)

    if unit_kind == "hour_of_day":
        n = len(HOUR_BOUNDS) - 1
        for i in range(n):
            sym = symbol.clone()
            sym.setColor(ramp.color(i / float(n - 1)))
            lower = float(HOUR_BOUNDS[i])
            upper = float(HOUR_BOUNDS[i + 1]) - (HOUR_EPSILON if i < n - 1 else 0.0)
            renderer.addClassRange(QgsRendererRange(lower, upper, sym, hour_class_label(lower, upper)))
    else:
        vmin, vmax = layer.minimumValue(idx), layer.maximumValue(idx)
        if vmin is None or vmax is None:
            raise ApiError("Field '%s' has no numeric values to classify." % field_name, kind="malformed")
        vmin, vmax = float(vmin), float(vmax)
        if vmin == vmax:
            # A uniform result (common for small areas): one class, one honest label.
            sym = symbol.clone()
            sym.setColor(ramp.color(0.5))
            renderer.addClassRange(QgsRendererRange(vmin, vmax, sym, uniform_label(vmin, unit_kind)))
        else:
            if method is None:
                method = "quantile" if unit_kind == "celsius" else "equal"
            renderer.setClassificationMethod(
                QgsClassificationQuantile() if method == "quantile" else QgsClassificationEqualInterval())
            renderer.updateClasses(layer, classes)
            kept = _distinct_ranges(renderer.ranges())
            if len(kept) != len(renderer.ranges()):
                renderer.deleteAllClasses()
                for rng in kept:
                    renderer.addClassRange(QgsRendererRange(rng.lowerValue(), rng.upperValue(), rng.symbol().clone(), ""))
                renderer.updateColorRamp(ramp)
            decimals = decimals_for_span(vmax - vmin)
            for i, rng in enumerate(renderer.ranges()):  # ranges() returns copies -> update by index
                renderer.updateRangeLabel(i, range_label(rng.lowerValue(), rng.upperValue(), unit_kind, decimals))

    layer.setRenderer(renderer)
    layer.triggerRepaint()
    return len(renderer.ranges())


def surface_colour_span(unit_kind, vmin, vmax):
    """(lo, hi, widened) colour-scale bounds: at least MIN_SURFACE_SPAN wide, centred on the data."""
    vmin, vmax = float(vmin), float(vmax)
    min_span = MIN_SURFACE_SPAN.get(unit_kind, 0.0)
    span = vmax - vmin
    if span >= min_span and span > 0:
        return vmin, vmax, False
    mid = (vmin + vmax) / 2.0
    half = max(min_span, 1e-6) / 2.0
    lo, hi = mid - half, mid + half
    if unit_kind == "hours" and lo < 0:   # durations cannot be negative; keep zero at the bottom
        lo, hi = 0.0, max(hi - lo, min_span)
    return lo, hi, True


def apply_surface_style(layer, unit_kind, vmin, vmax, opacity=0.75):
    """Continuous colour ramp for the smooth-surface raster (same ramps as the tiles).

    The ramp spans at least MIN_SURFACE_SPAN so tiny differences are not shown as
    a strong hot/cold contrast. Returns the number of legend entries. NODATA stays
    transparent; bilinear resampling keeps the surface smooth when zooming in.
    """
    lo, hi, _widened = surface_colour_span(unit_kind, vmin, vmax)
    ramp = _ramp_for(unit_kind)
    unit = UNITS.get(unit_kind, "")
    decimals = decimals_for_span(hi - lo)
    shader = QgsRasterShader()
    ramp_shader = QgsColorRampShader(lo, hi, ramp, QgsColorRampShader.Interpolated, QgsColorRampShader.Continuous)
    items = []
    steps = 6
    for i in range(steps + 1):
        v = lo + (hi - lo) * i / float(steps)
        items.append(QgsColorRampShader.ColorRampItem(v, ramp.color(i / float(steps)), format_value(v, unit_kind, decimals)))
    ramp_shader.setColorRampItemList(items)
    ramp_shader.setClip(False)
    with contextlib.suppress(Exception):  # tidy legend: matching decimals and the unit next to the colour bar
        from qgis.core import QgsBasicNumericFormat, QgsColorRampLegendNodeSettings
        legend = QgsColorRampLegendNodeSettings()
        fmt = QgsBasicNumericFormat()
        fmt.setNumberDecimalPlaces(decimals)
        legend.setNumericFormat(fmt)
        legend.setSuffix(" " + unit if unit else "")
        ramp_shader.setLegendSettings(legend)
    shader.setRasterShaderFunction(ramp_shader)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
    renderer.setClassificationMin(lo)
    renderer.setClassificationMax(hi)
    renderer.setOpacity(opacity)
    layer.setRenderer(renderer)
    layer.resampleFilter().setZoomedInResampler(QgsBilinearRasterResampler())
    layer.resampleFilter().setZoomedOutResampler(QgsBilinearRasterResampler())
    layer.triggerRepaint()
    return len(items)
