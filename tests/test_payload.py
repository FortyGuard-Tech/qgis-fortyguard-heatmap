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
        payload.build_date_time(4, "2024-07-01", end_date="2024-08-01", now=NOW)  # 31 days ok
        with self.assertRaises(ValidationError):
            payload.build_date_time(4, "2024-07-01", end_date="2024-08-02", now=NOW)
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
