# -*- coding: utf-8 -*-
"""Demo Mode: an offline fake client that replays bundled synthetic fixtures.

It implements the same two-method interface as HeatmapApiClient so the job
runner, result handling, saving, loading and styling paths are identical to a
real request. No network access happens. Fixtures are clearly labelled
synthetic and are NOT FortyGuard analyses.
"""
import json
import os

from qgis.PyQt.QtCore import QObject, QTimer

from . import contract
from .responses import StatusResult

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
DEMO_ACTIVITY_PREFIX = "demo-"

FIXTURES = {
    "single_hour": "demo_result_single_hour.geojson",
    "daily": "demo_result_daily.geojson",
}
DEMO_AOI_FILE = "demo_aoi.geojson"


def fixture_for_filter(filter_type):
    return "single_hour" if int(filter_type) in (contract.FILTER_SINGLE_HOUR, contract.FILTER_RANGE_OF_HOURS) else "daily"


def load_fixture(name):
    path = os.path.join(FIXTURE_DIR, FIXTURES[name])
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    # Fixture files carry the FeatureCollection plus a sidecar "demo_stats" member.
    stats = doc.pop("demo_stats", {})
    doc.pop("demo_note", None)
    return doc, stats


def load_demo_aoi():
    """Return the demo AOI as a GeoJSON Feature (EPSG:4326)."""
    with open(os.path.join(FIXTURE_DIR, DEMO_AOI_FILE), "r", encoding="utf-8") as fh:
        return json.load(fh)


class DemoApiClient(QObject):
    """Replays a fixture after a short fake 'Processing' phase. No network."""

    def __init__(self, fixture_name, processing_ticks=2, tick_ms=400, parent=None):
        super().__init__(parent)
        self.fixture_name = fixture_name
        self.processing_ticks = int(processing_ticks)
        self.tick_ms = int(tick_ms)
        self._polls = 0
        self._timers = []
        self._counter = 0

    def has_api_key(self):
        return True

    def _later(self, fn):
        t = QTimer(self)
        t.setSingleShot(True)
        self._timers.append(t)

        def _fire():
            if t in self._timers:
                self._timers.remove(t)
            t.deleteLater()
            fn()

        t.timeout.connect(_fire)
        t.start(self.tick_ms)
        return t

    def submit_heatmap(self, payload, callback):
        self._counter += 1
        activity_id = "%s%s-%d" % (DEMO_ACTIVITY_PREFIX, self.fixture_name, self._counter)
        self._polls = 0
        self.last_payload = payload
        self._later(lambda: callback(activity_id, None))

    def get_status(self, activity_id, callback):
        self._polls += 1
        if self._polls <= self.processing_ticks:
            self._later(lambda: callback(StatusResult(activity_id, "Processing"), None))
            return
        map_data, stats = load_fixture(self.fixture_name)
        result = {"map_data": map_data, "stats_data": stats}
        self._later(lambda: callback(StatusResult(activity_id, "Completed", result=result), None))

    def abort_all(self):
        for t in list(self._timers):
            t.stop()
            t.deleteLater()
        self._timers.clear()
