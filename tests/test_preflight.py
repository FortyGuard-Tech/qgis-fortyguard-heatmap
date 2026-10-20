# -*- coding: utf-8 -*-
"""Offline tests for the pre-submission checks (coverage, area, duplicates, cost text)."""
import unittest

from fortyguard_heatmap.core import contract, preflight


def _box(lon0, lat0, lon1, lat1):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


MANHATTAN = _box(-74.017, 40.705, -74.003, 40.718)
PARIS = _box(2.32, 48.85, 2.36, 48.87)
LONDON = _box(-0.15, 51.48, -0.05, 51.53)
OCEAN = _box(-40.1, 29.9, -39.9, 30.1)
ONTARIO_TO_NY = _box(-77.2, 44.0, -73.5, 46.0)     # Arpit's polygon: Canada with a small part in New York state
HONOLULU = _box(-157.9, 21.28, -157.8, 21.33)
ANCHORAGE = _box(-149.95, 61.18, -149.85, 61.23)
SAN_JUAN = _box(-66.12, 18.42, -66.05, 18.47)


class CoverageTests(unittest.TestCase):
    def test_us_areas_inside(self):
        for poly, region in ((MANHATTAN, "contiguous"), (HONOLULU, "Hawaii"), (ANCHORAGE, "Alaska"), (SAN_JUAN, "Puerto Rico")):
            status, regions = preflight.coverage_status(poly)
            self.assertEqual(status, preflight.COVERAGE_INSIDE, poly)
            self.assertIn(region, regions[0])

    def test_outside_areas_from_the_test_sheet(self):
        for poly in (PARIS, LONDON, OCEAN):
            status, regions = preflight.coverage_status(poly)
            self.assertEqual(status, preflight.COVERAGE_OUTSIDE, poly)
            self.assertEqual(regions, [])

    def test_partial_overlap(self):
        status, regions = preflight.coverage_status(ONTARIO_TO_NY)
        self.assertEqual(status, preflight.COVERAGE_PARTIAL)
        self.assertIn("contiguous United States", regions)


class AreaTests(unittest.TestCase):
    def test_tiny_area_warns(self):
        a = preflight.area_assessment(64e-6, 100)   # Rohit's 64 m2 polygon: completed with 0 tiles, charged
        self.assertIsNone(a["block"])
        self.assertTrue(any("smaller than one" in w for w in a["warnings"]), a)
        self.assertTrue(any("charged" in w for w in a["warnings"]))

    def test_normal_area_silent(self):
        a = preflight.area_assessment(1.71, 100)
        self.assertIsNone(a["block"])
        self.assertEqual(a["warnings"], [])

    def test_above_largest_documented_cap_warns(self):
        a = preflight.area_assessment(55 / 0.386102, 100)   # 55 mi2
        self.assertIsNone(a["block"])
        self.assertTrue(any("largest documented plan allowance" in w for w in a["warnings"]), a)

    def test_plan_cap_used_when_plan_known(self):
        a = preflight.area_assessment(12 / 0.386102, 100, plan_type="Basic")
        self.assertTrue(any("10 mi²" in w and "your plan" in w for w in a["warnings"]), a)
        a = preflight.area_assessment(12 / 0.386102, 100, plan_type="Premium")
        self.assertEqual(a["warnings"], [], "12 mi2 is within the 50 mi2 Premium allowance")

    def test_huge_area_blocked(self):
        for sq_mi in (1300, 11472):   # Fawad's Phoenix bbox, Arpit's Ontario/Quebec polygon
            a = preflight.area_assessment(sq_mi / 0.386102, 100)
            self.assertIsNotNone(a["block"])
            self.assertIn("504", a["block"])
        a = preflight.area_assessment(400 / 0.386102, 100)
        self.assertIsNone(a["block"], "400 mi2 completed in testing and is only warned about")
        self.assertTrue(a["warnings"])


class FingerprintTests(unittest.TestCase):
    def test_fingerprint_is_stable_and_sensitive(self):
        body = {"polygon_aoi": {"a": 1}, "date_time": {"start_date": "2026-07-15", "filter_type": 3},
                "granularity": 100, "analytic_type": "exceedance", "threshold": 30.0, "direction": "above"}
        same = dict(reversed(list(body.items())))
        self.assertEqual(preflight.request_fingerprint(body, "https://api.fortyguard.com"),
                         preflight.request_fingerprint(same, "https://api.fortyguard.com/"))
        other = dict(body, threshold=31.0)
        self.assertNotEqual(preflight.request_fingerprint(body, "x"), preflight.request_fingerprint(other, "x"))
        self.assertNotEqual(preflight.request_fingerprint(body, contract.DEFAULT_BASE_URL),
                            preflight.request_fingerprint(body, contract.DEV_BASE_URL))
        self.assertEqual(len(preflight.request_fingerprint(body)), 64)


class CostTextTests(unittest.TestCase):
    def test_known_plan(self):
        t = preflight.expected_cost_text("Premium", 9365500)
        self.assertIn("4,220", t); self.assertIn("9,365,500", t); self.assertIn("API Premium", t)
        self.assertIn("3,500", preflight.expected_cost_text("Startup"))

    def test_unknown_plan_states_observed_cost(self):
        t = preflight.expected_cost_text("Hackathon")
        self.assertIn("Hackathon", t)
        self.assertIn("no documented per-request cost", t)
        self.assertIn("4,220", t)

    def test_no_check_yet(self):
        t = preflight.expected_cost_text(None)
        self.assertIn("Check key and credits", t)
