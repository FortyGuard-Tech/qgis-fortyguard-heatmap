# -*- coding: utf-8 -*-
"""Graduated temperature styling for heatmap tile layers and the smooth surface.

Legend rules (from internal testing, 2026-10-19):
* Label precision follows the data spread. FortyGuard temperature fields often
  span a few tenths of a degree across a site, so one decimal made several
  classes read identically ("21.9 - 21.9 °C").
* Class breaks are computed from the numeric values only. QGIS's
  updateClasses() counts a NULL attribute as 0, which stretched the lowest
  class to "0.0 - 26.3 °C" whenever one tile had no value.
* Zero-width classes produced by the quantile method on data with few distinct
  values are dropped; a uniform result gets exactly one class ("all tiles = 2.0 h").
* QGIS matches a value to the first class whose [lower, upper] contains it,
  with both ends inclusive. The fixed hour-of-day classes therefore end just
  below the next bound so hour 4 lands in "04:00 - 07:59", not "00:00 - 03:59".
* The smooth surface uses a minimum colour span so a 0.2 °C difference is not
  stretched over the whole blue-to-red ramp.
"""
import contextlib

import math

from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsBilinearRasterResampler,
    QgsClassificationQuantile,
    QgsClassificationEqualInterval,
    QgsColorRampShader,
    QgsFeatureRequest,
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


MAX_DECIMALS = 4


def decimals_for_span(span):
    """Starting number of decimals for a data spread (refined by decimals_for_bounds)."""
    span = abs(float(span))
    if span >= 2.0:
        return 1
    if span >= 0.2:
        return 2
    return 3


def decimals_for_bounds(bounds, start=None):
    """Smallest number of decimals (<= MAX_DECIMALS) at which every class label is distinct
    and no label reads "x - x"."""
    if not bounds:
        return 1
    decimals = decimals_for_span(bounds[-1][1] - bounds[0][0]) if start is None else start
    while decimals < MAX_DECIMALS:
        labels = ["%.*f - %.*f" % (decimals, lo, decimals, hi) for lo, hi in bounds]
        collapsed = any("%.*f" % (decimals, lo) == "%.*f" % (decimals, hi) for lo, hi in bounds)
        if len(set(labels)) == len(labels) and not collapsed:
            break
        decimals += 1
    return decimals


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


def numeric_values(layer, idx):
    """Finite numeric values of attribute ``idx``; NULL and non-numeric attributes are skipped."""
    request = QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes([idx])
    values = []
    for feature in layer.getFeatures(request):
        v = feature[idx]
        if v is None or (isinstance(v, QVariant) and v.isNull()):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(fv):
            values.append(fv)
    return values


def class_bounds(values, classes, method="quantile"):
    """(lower, upper) pairs from QGIS's classification methods, zero-width duplicates dropped."""
    calc = QgsClassificationQuantile() if method == "quantile" else QgsClassificationEqualInterval()
    raw = [(float(r.lowerBound()), float(r.upperBound())) for r in calc.classes(list(values), int(classes))]
    out = []
    for i, (lo, hi) in enumerate(raw):
        if lo == hi:
            covered_before = bool(out) and out[-1][1] >= lo
            covered_after = i + 1 < len(raw) and raw[i + 1][0] <= lo <= raw[i + 1][1]
            if covered_before or covered_after:
                continue  # a zero-width class whose value a neighbour already contains (inclusive bounds)
        out.append((lo, hi))
    if not out:
        out = [(min(values), max(values))]
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
        values = numeric_values(layer, idx)
        if not values:
            raise ApiError("Field '%s' has no numeric values to classify." % field_name, kind="malformed")
        vmin, vmax = min(values), max(values)
        if vmin == vmax:
            # A uniform result (common for small areas): one class, one honest label.
            sym = symbol.clone()
            sym.setColor(ramp.color(0.5))
            renderer.addClassRange(QgsRendererRange(vmin, vmax, sym, uniform_label(vmin, unit_kind)))
        else:
            if method is None:
                method = "quantile" if unit_kind == "celsius" else "equal"
            bounds = class_bounds(values, classes, method)
            n = len(bounds)
            decimals = decimals_for_bounds(bounds)
            for i, (lo, hi) in enumerate(bounds):
                sym = symbol.clone()
                sym.setColor(ramp.color(i / float(n - 1) if n > 1 else 0.5))
                renderer.addClassRange(QgsRendererRange(lo, hi, sym, range_label(lo, hi, unit_kind, decimals)))

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
    steps = 6
    decimals = decimals_for_bounds([(lo + (hi - lo) * i / float(steps), lo + (hi - lo) * (i + 1) / float(steps))
                                    for i in range(steps)])
    shader = QgsRasterShader()
    ramp_shader = QgsColorRampShader(lo, hi, ramp, QgsColorRampShader.Interpolated, QgsColorRampShader.Continuous)
    items = []
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
