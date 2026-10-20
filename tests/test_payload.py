# -*- coding: utf-8 -*-
"""Offline tests for payload construction and input validation (no QGIS needed)."""
import datetime as dt
import unittest

from fortyguard_heatmap.core import contract, payload
from fortyguard_heatmap.core.payload import ValidationError

SQUARE = {
    "type": "Polygon",
    "coordinates": [[[-74.017, 40.705], [-74.003, 40.705], [-74.003, 40.718],
                     [-74.017, 40.718], [-74.017, 40.705]]],
}
WITH_HOLE = {
    "type": "Polygon",
    "coordinates": [
        [[-74.02, 40.70], [-74.00, 40.70], [-74.00, 40.72], [-74.02, 40.72], [-74.02, 40.70]],
        [[-74.015, 40.705], [-74.005, 40.705], [-74.005, 40.715], [-74.015, 40.715], [-74.015, 40.705]],
    ],
}
NOW = dt.datetime(2026, 10, 12, 15, 0, 0)


class BuildPayloadTests(unittest.TestCase):
    def test_single_hour_sends_only_required_fields(self):
        p = payload.build_payload(SQUARE, 1, "2024-07-15", 100, start_time="14:00", now=NOW)
        self.assertEqual(p["date_time"], {"start_date": "2024-07-15", "filter_type": 1, "start_time": "14:00"})
        self.assertEqual(p["granularity"], 100)
        self.assertEqual(p["analytic_type"], "tcm")
        self.assertEqual(set(p.keys()), {"polygon_aoi", "date_time", "granularity", "analytic_type"})
        self.assertNotIn("timezone", p)
        self.assertNotIn("timezone", p["date_time"])

    def test_single_hour_ignores_end_fields(self):
        p = payload.build_payload(SQUARE, 1, "2024-07-15", 60, start_time="09:30",
                                  end_time="17:00", end_date="2024-07-20", now=NOW)
        self.assertNotIn("end_time", p["date_time"])
        self.assertNotIn("end_date", p["date_time"])

    def test_range_of_hours(self):
        p = payload.build_payload(SQUARE, 2, "2024-07-15", 80, start_time="12:00", end_time="17:00", now=NOW)
        self.assertEqual(p["date_time"], {"start_date": "2024-07-15", "filter_type": 2,
                                          "start_time": "12:00", "end_time": "17:00"})

    def test_range_of_hours_rejects_reversed_or_too_long(self):
        with self.assertRaises(ValidationError):
            payload.build_date_time(2, "2024-07-15", "17:00", "12:00", now=NOW)
        with self.assertRaises(ValidationError):
            payload.build_date_time(2, "2024-07-15", "12:00", "12:00", now=NOW)
        # 23 h is the documented maximum: 00:00-23:00 is fine, 00:00-23:30 is not.
        payload.build_date_time(2, "2024-07-15", "00:00", "23:00", now=NOW)
        with self.assertRaises(ValidationError):
            payload.build_date_time(2, "2024-07-15", "00:00", "23:30", now=NOW)

    def test_single_day_only_start_date(self):
        p = payload.build_payload(SQUARE, 3, "2024-07-15", 100, start_time="14:00", now=NOW)
        self.assertEqual(p["date_time"], {"start_date": "2024-07-15", "filter_type": 3})

    def test_range_of_days(self):
        p = payload.build_payload(SQUARE, 4, "2024-07-15", 100, end_date="2024-07-21", now=NOW)
        self.assertEqual(p["date_time"], {"start_date": "2024-07-15", "filter_type": 4, "end_date": "2024-07-21"})

    def test_range_of_days_bounds(self):
        with self.assertRaises(ValidationError):
            payload.build_date_time(4, "2024-07-15", end_date="2024-07-15", now=NOW)
        with self.assertRaises(ValidationError):
            payload.build_date_time(4, "2024-07-15", end_date="2024-07-10", now=NOW)
        payload.build_date_time(4, "2024-07-01", end_date="2024-07-31", now=NOW)  # 31 inclusive days ok
        # 1st to 1st of the next month is 32 inclusive days: the API ran it for 7 minutes and then failed it
        with self.assertRaises(ValidationError) as cm:
            payload.build_date_time(4, "2024-07-01", end_date="2024-08-01", now=NOW)
        self.assertIn("32 days", str(cm.exception))
        self.assertIn("Calendar month", str(cm.exception))
        with self.assertRaises(ValidationError):
            payload.build_date_time(4, "2024-07-01", now=NOW)

    def test_date_bounds(self):
        with self.assertRaises(ValidationError):
            payload.build_date_time(3, "2018-12-31", now=NOW)
        payload.build_date_time(3, "2019-01-01", now=NOW)
        # now = 2026-10-12 15:00 -> now + 12h is still 2026-10-13 03:00 -> 13th allowed, 14th not
        payload.build_date_time(3, "2026-10-13", now=NOW)
        with self.assertRaises(ValidationError):
            payload.build_date_time(3, "2026-10-14", now=NOW)

    def test_bad_formats(self):
        for bad in ("15/07/2024", "2024-7-15", "2024-02-30", "", None, 20240715):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                payload.build_date_time(3, bad, now=NOW)
        for bad in ("2 pm", "24:00", "14:60", "14", "14:00:00"):
            with self.assertRaises(ValidationError, msg=repr(bad)):
                payload.build_date_time(1, "2024-07-15", start_time=bad, now=NOW)

    def test_filter_type_validation(self):
        for bad in (0, 5, "x", None):
            with self.assertRaises(ValidationError):
                payload.build_date_time(bad, "2024-07-15", now=NOW)
        # strings of digits are accepted (combo boxes often hand back text)
        self.assertEqual(payload.build_date_time("3", "2024-07-15", now=NOW)["filter_type"], 3)

    def test_granularity_restricted(self):
        for g in contract.GRANULARITY_OPTIONS:
            payload.build_payload(SQUARE, 3, "2024-07-15", g, now=NOW)
        for bad in (20, 50, 120, "abc", None):
            with self.assertRaises(ValidationError):
                payload.build_payload(SQUARE, 3, "2024-07-15", bad, now=NOW)


class GeometryValidationTests(unittest.TestCase):
    def test_feature_collection_wrapper(self):
        fc = payload.build_polygon_aoi(SQUARE)
        self.assertEqual(fc["type"], "FeatureCollection")
        self.assertEqual(len(fc["features"]), 1)
        self.assertEqual(fc["features"][0]["geometry"], SQUARE)
        self.assertEqual(fc["features"][0]["properties"], {})

    def test_holes_preserved(self):
        fc = payload.build_polygon_aoi(WITH_HOLE)
        self.assertEqual(len(fc["features"][0]["geometry"]["coordinates"]), 2)

    def test_rejects_multipolygon_and_others(self):
        for gtype in ("MultiPolygon", "Point", "LineString", None):
            with self.assertRaises(ValidationError):
                payload.validate_polygon_geojson({"type": gtype, "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]})

    def test_rejects_unclosed_or_tiny_rings(self):
        with self.assertRaises(ValidationError):
            payload.validate_polygon_geojson({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]})
        with self.assertRaises(ValidationError):
            payload.validate_polygon_geojson({"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [0, 0]]]})
        with self.assertRaises(ValidationError):
            payload.validate_polygon_geojson({"type": "Polygon", "coordinates": []})

    def test_rejects_projected_coordinates(self):
        projected = {"type": "Polygon", "coordinates": [[[-8238000, 4969000], [-8237000, 4969000],
                                                         [-8237000, 4970000], [-8238000, 4969000]]]}
        with self.assertRaises(ValidationError) as cm:
            payload.validate_polygon_geojson(projected)
        self.assertIn("EPSG:4326", str(cm.exception))

    def test_lon_lat_order_is_kept(self):
        fc = payload.build_polygon_aoi(SQUARE)
        first = fc["features"][0]["geometry"]["coordinates"][0][0]
        self.assertEqual(first, [-74.017, 40.705])  # longitude first


class DescribeTests(unittest.TestCase):
    def test_describe(self):
        p = payload.build_payload(SQUARE, 2, "2024-07-15", 80, start_time="12:00", end_time="17:00", now=NOW)
        self.assertEqual(payload.describe_request(p), "2024-07-15 12:00-17:00 | 80 m")
        p = payload.build_payload(SQUARE, 4, "2024-07-15", 60, end_date="2024-07-21", now=NOW)
        self.assertEqual(payload.describe_request(p), "2024-07-15 to 2024-07-21 | 60 m")


if __name__ == "__main__":
    unittest.main()


class AnalysisPayloadTests(unittest.TestCase):
    def _p(self, analytic, ft=3, **kw):
        kw.setdefault("end_date", "2024-07-21" if ft == 4 else None)
        kw.setdefault("start_time", "12:00" if ft in (1, 2) else None)
        kw.setdefault("end_time", "17:00" if ft == 2 else None)
        return payload.build_payload(SQUARE, ft, "2024-07-15", 100, now=NOW, analytic_type=analytic, **kw)

    def test_tcm_omits_threshold_even_if_given(self):
        p = self._p("tcm", threshold=35, direction="above")
        self.assertEqual(p["analytic_type"], "tcm")
        self.assertNotIn("threshold", p)
        self.assertNotIn("direction", p)

    def test_exceedance_and_persistence_send_threshold_above(self):
        for at in ("exceedance", "persistence"):
            p = self._p(at, threshold=35)
            self.assertEqual(p["analytic_type"], at)
            self.assertEqual(p["threshold"], 35.0)
            self.assertEqual(p["direction"], "above")
            self.assertEqual(set(p), {"polygon_aoi", "date_time", "granularity", "analytic_type", "threshold", "direction"})

    def test_time_of_measure_omits_threshold(self):
        p = self._p("time_of_measure", ft=4, threshold=35)
        self.assertEqual(p["analytic_type"], "time_of_measure")
        self.assertNotIn("threshold", p)
        self.assertNotIn("direction", p)

    def test_threshold_required_and_bounded(self):
        with self.assertRaises(ValidationError):
            self._p("exceedance")
        with self.assertRaises(ValidationError):
            self._p("persistence", threshold="hot")
        with self.assertRaises(ValidationError):
            self._p("exceedance", threshold=120)
        with self.assertRaises(ValidationError):
            self._p("exceedance", threshold=float("nan"))
        self.assertEqual(self._p("exceedance", threshold="35.5")["threshold"], 35.5)

    def test_only_above_direction(self):
        with self.assertRaises(ValidationError):
            self._p("exceedance", threshold=35, direction="below")

    def test_single_hour_rejected_for_analyses(self):
        for at in ("exceedance", "persistence", "time_of_measure"):
            with self.assertRaises(ValidationError) as cm:
                self._p(at, ft=1, threshold=35)
            self.assertIn("single hour", str(cm.exception).lower())
        self._p("tcm", ft=1)  # snapshot still allows single hour
        for ft in (2, 3, 4):
            self._p("exceedance", ft=ft, threshold=35)

    def test_unknown_analysis(self):
        with self.assertRaises(ValidationError):
            self._p("heat_index")

    def test_describe_includes_threshold(self):
        p = self._p("exceedance", ft=4, threshold=35)
        self.assertEqual(payload.describe_request(p), "2024-07-15 to 2024-07-21 | 100 m | above 35 °C")
        self.assertNotIn("above", payload.describe_request(self._p("tcm")))


class MonthRangeTests(unittest.TestCase):
    def test_full_past_months_and_leap_year(self):
        self.assertEqual(payload.month_range(2024, 2, now=NOW), ("2024-02-01", "2024-02-29"))
        self.assertEqual(payload.month_range(2023, 2, now=NOW), ("2023-02-01", "2023-02-28"))
        self.assertEqual(payload.month_range(2100, 2, now=dt.datetime(2100, 6, 1)), ("2100-02-01", "2100-02-28"))
        self.assertEqual(payload.month_range(2024, 7, now=NOW), ("2024-07-01", "2024-07-31"))
        self.assertEqual(payload.month_range(2024, 12, now=NOW), ("2024-12-01", "2024-12-31"))

    def test_month_fits_documented_maximum_range(self):
        first, last = payload.month_range(2024, 7, now=NOW)
        payload.build_date_time(4, first, end_date=last, now=NOW)  # 31-day month passes the <= 31 day rule

    def test_current_month_is_clipped_to_recent_data_cutoff(self):
        # NOW = 2026-10-12 -> data normally available up to 2026-10-05 (7-day latency observed in testing)
        self.assertEqual(payload.month_range(2026, 10, now=NOW), ("2026-10-01", "2026-10-05"))
        self.assertTrue(payload.month_was_clipped(2026, 10, "2026-10-01", "2026-10-05"))
        self.assertFalse(payload.month_was_clipped(2024, 7, "2024-07-01", "2024-07-31"))
        # a custom latency is honoured
        self.assertEqual(payload.month_range(2026, 10, now=NOW, latency_days=1), ("2026-10-01", "2026-10-11"))

    def test_future_month_rejected_with_latency_explanation(self):
        with self.assertRaises(ValidationError) as cm:
            payload.month_range(2026, 11, now=NOW)
        self.assertIn("no available data yet", str(cm.exception))
        with self.assertRaises(ValidationError):
            payload.month_range(2027, 1, now=NOW)
        # early in a month the whole month is still unavailable (NOW - 7 days is in September)
        with self.assertRaises(ValidationError) as cm:
            payload.month_range(2026, 10, now=dt.datetime(2026, 10, 3, 1, 0))
        self.assertIn("2026-09-26", str(cm.exception))

    def test_month_before_api_start_rejected_and_partial_first_month(self):
        with self.assertRaises(ValidationError):
            payload.month_range(2018, 12, now=NOW)
        self.assertEqual(payload.month_range(2019, 1, now=NOW), ("2019-01-01", "2019-01-31"))

    def test_month_with_a_single_available_day(self):
        now = dt.datetime(2026, 10, 8, 1, 0)  # cutoff = 2026-10-01: only one day of October available
        with self.assertRaises(ValidationError) as cm:
            payload.month_range(2026, 10, now=now)
        self.assertIn("Single day", str(cm.exception))


class RecentDataTests(unittest.TestCase):
    def test_cutoff_and_warning(self):
        self.assertEqual(payload.recent_data_cutoff(NOW), dt.date(2026, 10, 5))
        self.assertIsNone(payload.recent_data_warning("2026-10-05", now=NOW))
        self.assertIsNone(payload.recent_data_warning("2026-09-01", "2026-09-30", now=NOW))
        w = payload.recent_data_warning("2026-10-11", now=NOW)   # "yesterday": rejected by the API in testing
        self.assertIn("2026-10-05", w)
        self.assertIn("not available yet", w)
        w = payload.recent_data_warning("2026-10-01", "2026-10-08", now=NOW)
        self.assertIn("2026-10-08", w)

    def test_latest_allowed_date_still_documented_bound(self):
        # the documented limit (now + 12 h) is still the hard validation bound; latency is a warning only
        payload.build_date_time(3, "2026-10-13", now=NOW)
        with self.assertRaises(ValidationError):
            payload.build_date_time(3, "2026-10-14", now=NOW)

    def test_invalid_month(self):
        with self.assertRaises(ValidationError):
            payload.month_range(2024, 13, now=NOW)
        with self.assertRaises(ValidationError):
            payload.month_range("x", 1, now=NOW)
