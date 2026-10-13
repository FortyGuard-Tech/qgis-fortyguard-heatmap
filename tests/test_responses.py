# -*- coding: utf-8 -*-
"""Offline tests for raw response parsing (no QGIS needed)."""
import json
import unittest

from fortyguard_heatmap.core import responses
from fortyguard_heatmap.core.responses import ApiError


def _b(obj):
    return json.dumps(obj).encode("utf-8")


SUBMIT_OK = {"error": False, "status_code": 200, "message": "Heatmap Submitted Successfully",
             "data": {"activity_id": "f52d2453-6a59-4b31-afa3-8fe3bb1ac5df"}}

PROCESSING = {"error": False, "status_code": 200, "message": "Processing",
              "data": {"activity_id": "abc", "status": "Processing"}}

TILE = {"type": "Feature", "id": "0",
        "properties": {"tile_id": 0, "average_temperature": 20.86, "min_temperature": 16.35, "max_temperature": 27.60},
        "geometry": {"type": "Polygon", "coordinates": [[[-121.906, 37.3256], [-121.9056, 37.3256],
                                                         [-121.9056, 37.3262], [-121.906, 37.3262],
                                                         [-121.906, 37.3256]]]}}
COMPLETED = {"error": False, "status_code": 200, "message": "Completed",
             "data": {"activity_id": "abc", "status": "Completed",
                      "result": {"map_data": {"type": "FeatureCollection", "features": [TILE]},
                                 "stats_data": {"temperature_stats": {"minimum": 20.4, "maximum": 20.9,
                                                                      "mean": 20.7, "standard_deviation": 0.13}}}}}


class SubmitParsingTests(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(responses.parse_submit_response(200, _b(SUBMIT_OK)), "f52d2453-6a59-4b31-afa3-8fe3bb1ac5df")

    def test_http_errors_are_classified(self):
        cases = {401: "auth", 403: "forbidden", 400: "invalid_input", 422: "invalid_input",
                 429: "rate_limited", 500: "server", 503: "server"}
        for code, kind in cases.items():
            with self.assertRaises(ApiError) as cm:
                responses.parse_submit_response(code, b'{"error": true, "message": "nope"}')
            self.assertEqual(cm.exception.kind, kind, code)
            self.assertEqual(cm.exception.http_status, code)
            self.assertIn("nope", str(cm.exception))

    def test_live_error_envelope_details_message(self):
        # Shape observed from the real API on 2026-10-13.
        body = b'{"error":true,"status_code":401,"details":{"message":"Invalid or unknown API key."}}'
        with self.assertRaises(ApiError) as cm:
            responses.parse_submit_response(401, body)
        self.assertEqual(cm.exception.kind, "auth")
        self.assertIn("Invalid or unknown API key.", str(cm.exception))
        body = b'{"error":true,"status_code":404,"details":{"message":"No activity found for the provided activity_id."}}'
        with self.assertRaises(ApiError) as cm:
            responses.parse_status_response(404, body)
        self.assertTrue(cm.exception.retryable)
        self.assertIn("No activity found", str(cm.exception))

    def test_http_error_without_json_body(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_submit_response(502, b"<html>Bad gateway</html>")
        self.assertEqual(cm.exception.kind, "server")

    def test_envelope_error_flag(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_submit_response(200, _b({"error": True, "message": "Area too large", "data": None}))
        self.assertEqual(cm.exception.kind, "failed")
        self.assertIn("Area too large", str(cm.exception))

    def test_missing_activity_id(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_submit_response(200, _b({"error": False, "data": {}}))
        self.assertEqual(cm.exception.kind, "malformed")

    def test_malformed_json(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_submit_response(200, b"not json")
        self.assertEqual(cm.exception.kind, "malformed")
        with self.assertRaises(ApiError):
            responses.parse_submit_response(200, b"")
        with self.assertRaises(ApiError):
            responses.parse_submit_response(200, None)


class StatusParsingTests(unittest.TestCase):
    def test_processing(self):
        s = responses.parse_status_response(200, _b(PROCESSING))
        self.assertEqual(s.status, "processing")
        self.assertFalse(s.is_terminal)
        self.assertIsNone(s.result)

    def test_terminal_states_case_insensitive(self):
        for raw, ok, fail in (("Completed", True, False), ("completed", True, False), ("SUCCEEDED", True, False),
                              ("Failed", False, True), ("error", False, True), ("Pending", False, False),
                              ("Queued", False, False)):
            body = {"error": False, "data": {"activity_id": "x", "status": raw}}
            s = responses.parse_status_response(200, _b(body))
            self.assertEqual(s.is_success, ok, raw)
            self.assertEqual(s.is_failure, fail, raw)

    def test_404_is_retryable(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_status_response(404, b'{"error": true, "message": "not found"}')
        self.assertEqual(cm.exception.kind, "not_found")
        self.assertTrue(cm.exception.retryable)

    def test_401_not_retryable(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_status_response(401, b"{}")
        self.assertEqual(cm.exception.kind, "auth")
        self.assertFalse(cm.exception.retryable)

    def test_server_error_retryable_on_status(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_status_response(500, b"")
        self.assertTrue(cm.exception.retryable)

    def test_missing_status(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_status_response(200, _b({"error": False, "data": {"activity_id": "x"}}))
        self.assertEqual(cm.exception.kind, "malformed")


class ResultTests(unittest.TestCase):
    def test_extract_and_validate(self):
        s = responses.parse_status_response(200, _b(COMPLETED))
        map_data, stats = responses.extract_result(s)
        responses.validate_map_data(map_data)
        self.assertEqual(responses.available_measures(map_data),
                         ["average_temperature", "max_temperature", "min_temperature"])
        ts = responses.temperature_stats(stats)
        self.assertAlmostEqual(ts["mean"], 20.7)

    def test_stats_keys_case_insensitive(self):
        ts = responses.temperature_stats({"Temperature_stats": {"Minimum": 1, "Maximum": 2.5, "Mean": 2, "Standard_deviation": 0.1}})
        self.assertEqual(ts, {"minimum": 1.0, "maximum": 2.5, "mean": 2.0, "standard_deviation": 0.1})
        self.assertEqual(responses.temperature_stats({}), {})
        self.assertEqual(responses.temperature_stats(None), {})

    def test_single_hour_schema(self):
        tile = dict(TILE, properties={"tile_id": 1, "temperature": 31.2})
        md = {"type": "FeatureCollection", "features": [tile]}
        self.assertEqual(responses.available_measures(md), ["temperature"])

    def test_missing_and_nonnumeric_values(self):
        t1 = dict(TILE, properties={"tile_id": 1, "temperature": 31.2})
        t2 = dict(TILE, properties={"tile_id": 2, "temperature": None})
        t3 = dict(TILE, properties={"tile_id": 3, "temperature": "n/a"})
        t4 = dict(TILE, properties={"tile_id": 4})
        md = {"type": "FeatureCollection", "features": [t1, t2, t3, t4]}
        self.assertEqual(responses.available_measures(md), ["temperature"])
        summ = responses.numeric_summary(md, "temperature")
        self.assertEqual(summ["count"], 1)
        self.assertEqual(summ["missing"], 3)
        all_missing = {"type": "FeatureCollection", "features": [t2, t3, t4]}
        self.assertEqual(responses.available_measures(all_missing), [])

    def test_empty_output_rejected(self):
        with self.assertRaises(ApiError) as cm:
            responses.validate_map_data({"type": "FeatureCollection", "features": []})
        self.assertIn("empty", str(cm.exception).lower())
        with self.assertRaises(ApiError):
            responses.validate_map_data({"type": "Feature"})
        with self.assertRaises(ApiError):
            responses.validate_map_data(None)
        pts = {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                                                          "geometry": {"type": "Point", "coordinates": [0, 0]}}]}
        with self.assertRaises(ApiError):
            responses.validate_map_data(pts)

    def test_completed_without_result(self):
        body = {"error": False, "data": {"activity_id": "x", "status": "Completed"}}
        s = responses.parse_status_response(200, _b(body))
        with self.assertRaises(ApiError) as cm:
            responses.extract_result(s)
        self.assertEqual(cm.exception.kind, "malformed")

    def test_extract_requires_success(self):
        s = responses.parse_status_response(200, _b(PROCESSING))
        with self.assertRaises(ApiError):
            responses.extract_result(s)


if __name__ == "__main__":
    unittest.main()


USAGE_LIVE = {"api_key": None, "subscription_id": "sub_x",
              "plan_details": {"plan_type": "Premium", "cycle_type": "One-Time", "active": True},
              "api_key_details": {"status": "active", "valid": True, "expiry_date": "2026-10-19T14:36:30Z",
                                  "api_access_available": True},
              "credit_summary": {"total_available_credits": 1000000, "cycle_credits_used": 4220,
                                 "cycle_remaining_credits": 995780, "total_remaining_credits": 995780}}


class UsageParsingTests(unittest.TestCase):
    def test_live_shape(self):
        info = responses.parse_usage_response(200, _b(USAGE_LIVE))
        self.assertEqual(info.plan_type, "Premium")
        self.assertEqual(info.remaining_credits, 995780)
        self.assertEqual(info.total_credits, 1000000)
        self.assertEqual(info.key_status, "active")
        s = info.summary()
        self.assertIn("Premium", s); self.assertIn("995,780", s); self.assertIn("2026-10-19", s)

    def test_server_error_explains_environment(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_usage_response(500, b'{"error": true, "message": "Unable to fetch API key usage."}')
        self.assertEqual(cm.exception.kind, "server")
        self.assertIn("environment", str(cm.exception))
        self.assertIn("Unable to fetch API key usage.", str(cm.exception))

    def test_401(self):
        with self.assertRaises(ApiError) as cm:
            responses.parse_usage_response(401, b'{"error":true,"status_code":401,"details":{"message":"Invalid or unknown API key."}}')
        self.assertEqual(cm.exception.kind, "auth")

    def test_malformed(self):
        with self.assertRaises(ApiError):
            responses.parse_usage_response(200, b'{"hello": 1}')
