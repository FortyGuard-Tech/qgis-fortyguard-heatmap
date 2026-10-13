# -*- coding: utf-8 -*-
"""QGIS-runtime tests for the async client + job runner against a local HTTP server.

A tiny http.server runs in a thread and plays the FortyGuard API: it records the
headers/body it received and returns scripted responses. This exercises the real
QgsNetworkAccessManager path, the api-key header, the retry-on-404 behaviour,
terminal states, deadline handling and Stop Waiting.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests import qgis_env

if qgis_env.qgis_available():
    qgis_env.start()
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from fortyguard_heatmap.core import contract
    from fortyguard_heatmap.core.api_client import HeatmapApiClient
    from fortyguard_heatmap.core.demo import DemoApiClient
    from fortyguard_heatmap.core.job import HeatmapJob
    from fortyguard_heatmap.core.polling import PollingPolicy

TILE = {"type": "Feature", "properties": {"tile_id": 0, "temperature": 30.5},
        "geometry": {"type": "Polygon", "coordinates": [[[-74.01, 40.70], [-74.00, 40.70], [-74.00, 40.71],
                                                         [-74.01, 40.71], [-74.01, 40.70]]]}}
COMPLETED = {"error": False, "status_code": 200, "message": "Completed",
             "data": {"activity_id": "act-1", "status": "Completed",
                      "result": {"map_data": {"type": "FeatureCollection", "features": [TILE]},
                                 "stats_data": {"temperature_stats": {"minimum": 30.5, "maximum": 30.5, "mean": 30.5}}}}}


class FakeApi(object):
    """Scripted server state shared with the handler."""

    def __init__(self):
        self.requests = []           # (method, path, headers dict, body)
        self.submit_response = (200, {"error": False, "status_code": 200, "message": "Heatmap Submitted Successfully",
                                      "data": {"activity_id": "act-1"}})
        self.status_script = []      # list of (http_status, body) consumed in order; last repeats
        self.usage_response = (500, {"error": True, "message": "Unable to fetch API key usage."})
        self.lock = threading.Lock()

    def next_status(self):
        with self.lock:
            if len(self.status_script) > 1:
                return self.status_script.pop(0)
            return self.status_script[0]


def make_handler(api):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silence
            pass

        def _send(self, code, body):
            data = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            api.requests.append(("POST", self.path, dict(self.headers), body))
            if self.path.endswith("fetch-api-key-usage"):
                code, resp = api.usage_response
            else:
                code, resp = api.submit_response
            self._send(code, resp)

        def do_GET(self):
            api.requests.append(("GET", self.path, dict(self.headers), b""))
            code, resp = api.next_status()
            self._send(code, resp)
    return Handler


def wait_for(signal_holder, timeout_ms=15000):
    """Run the Qt event loop until ``signal_holder['done']`` becomes True."""
    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    while not signal_holder.get("done") and timer.isActive():
        loop.processEvents(QEventLoop.AllEvents, 50)
    return bool(signal_holder.get("done"))


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class LiveLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = FakeApi()
        cls.server = HTTPServer(("127.0.0.1", 0), make_handler(cls.api))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self._drain()
        self.api.requests.clear()
        self.api.submit_response = (200, {"error": False, "data": {"activity_id": "act-1"}})
        self.api.status_script = [(200, COMPLETED)]
        self.events = []
        self._jobs = []

    def tearDown(self):
        for job in self._jobs:
            job.stop()
        self._drain()

    def _drain(self, ms=250):
        """Let any in-flight socket traffic from a previous test reach the server."""
        wait_for({"done": False}, ms)

    def _job(self, deadline_s=30, **policy_kwargs):
        client = HeatmapApiClient("TEST-KEY-123", base_url=self.base_url, timeout_ms=5000)
        policy = PollingPolicy(deadline_s=deadline_s, initial_interval_s=0.05, max_interval_s=0.2,
                               backoff_factor=2.0, **policy_kwargs)
        job = HeatmapJob(client, policy=policy)
        holder = {"done": False}
        job.submitted.connect(lambda a: self.events.append(("submitted", a)))
        job.status_changed.connect(lambda s, d: self.events.append(("status", s)))
        job.completed.connect(lambda m, s: (self.events.append(("completed", m, s)), holder.__setitem__("done", True)))
        job.failed.connect(lambda m, k: (self.events.append(("failed", m, k)), holder.__setitem__("done", True)))
        job.stopped.connect(lambda a: (self.events.append(("stopped", a)), holder.__setitem__("done", True)))
        self._jobs.append(job)
        return job, holder, client

    def _payload(self):
        return {"polygon_aoi": {"type": "FeatureCollection", "features": []},
                "date_time": {"start_date": "2024-07-15", "filter_type": 3}, "granularity": 100, "analytic_type": "tcm"}

    def test_submit_poll_complete_sends_documented_headers(self):
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-1", "status": "Processing"}}),
                                  (200, COMPLETED)]
        job, holder, client = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        kinds = [e[0] for e in self.events]
        self.assertIn("submitted", kinds)
        self.assertEqual(kinds[-1], "completed")
        post = [r for r in self.api.requests if r[0] == "POST"]
        self.assertEqual(len(post), 1, "exactly one submission")
        method, path, headers, body = post[0]
        self.assertEqual(path, contract.HEATMAP_PATH)
        self.assertEqual(headers.get("api-key"), "TEST-KEY-123")
        self.assertTrue(headers.get("Content-Type", "").startswith("application/json"))
        self.assertEqual(json.loads(body.decode())["analytic_type"], "tcm")
        gets = [r for r in self.api.requests if r[0] == "GET"]
        self.assertGreaterEqual(len(gets), 2)
        self.assertEqual(gets[0][1], "/v1/status/act-1")
        self.assertEqual(gets[0][2].get("api-key"), "TEST-KEY-123")
        self.assertEqual(job.activity_id, "act-1")
        self.assertFalse(job.is_active)
        statuses = [e[1] for e in self.events if e[0] == "status"]
        self.assertIn("Processing", statuses)
        self.assertIn("Completed", statuses)

    def test_404_then_completed_is_retried(self):
        self.api.status_script = [(404, {"error": True, "message": "not found"}),
                                  (404, {"error": True, "message": "not found"}),
                                  (200, COMPLETED)]
        job, holder, _ = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "completed")
        self.assertIn("Retrying", [e[1] for e in self.events if e[0] == "status"])

    def test_failed_status_is_terminal(self):
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-1", "status": "Failed"}})]
        job, holder, _ = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "failed")
        self.assertEqual(self.events[-1][2], "failed")
        self.assertIn("Failed", self.events[-1][1])
        self.assertEqual(len([r for r in self.api.requests if r[0] == "GET"]), 1)
        self.assertEqual(job.activity_id, "act-1", "activity id kept for later checks")

    def test_401_on_status_stops_and_keeps_activity_id(self):
        self.api.status_script = [(401, {"error": True, "message": "invalid key"})]
        job, holder, _ = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "failed")
        self.assertEqual(self.events[-1][2], "auth")
        self.assertEqual(job.activity_id, "act-1")
        self.assertTrue(job.can_resume)

    def test_submit_401_never_retries(self):
        self.api.submit_response = (401, {"error": True, "message": "Missing or invalid API key."})
        job, holder, _ = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "failed")
        self.assertEqual(self.events[-1][2], "auth")
        self.assertEqual(len(self.api.requests), 1)
        self.assertIsNone(job.activity_id)

    def test_submit_400_reports_api_message(self):
        self.api.submit_response = (400, {"error": True, "message": "Polygon area exceeds plan limit"})
        job, holder, _ = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][2], "invalid_input")
        self.assertIn("Polygon area exceeds plan limit", self.events[-1][1])

    def test_deadline_stops_polling_and_allows_resume(self):
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-1", "status": "Processing"}})]
        job, holder, _ = self._job(deadline_s=0.4)
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "failed")
        self.assertEqual(self.events[-1][2], "timeout")
        self.assertIn("act-1", self.events[-1][1])
        self.assertTrue(job.can_resume)
        # Now the server finishes; resume picks up the result without a new POST.
        self.api.status_script = [(200, COMPLETED)]
        holder["done"] = False
        self.assertTrue(job.resume())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "completed")
        self.assertEqual(len([r for r in self.api.requests if r[0] == "POST"]), 1)

    def test_too_many_server_errors(self):
        self.api.status_script = [(500, {"error": True, "message": "boom"})]
        job, holder, _ = self._job(max_consecutive_failures=3)
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "failed")
        self.assertIn("3 consecutive", self.events[-1][1])
        self.assertEqual(len([r for r in self.api.requests if r[0] == "GET"]), 3)

    def test_stop_waiting_keeps_activity_and_does_not_resubmit(self):
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-1", "status": "Processing"}})]
        job, holder, _ = self._job()
        job.submit(self._payload())
        sub = {"done": False}
        job.submitted.connect(lambda a: sub.__setitem__("done", True))
        self.assertTrue(wait_for(sub))
        job.stop()
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "stopped")
        self.assertEqual(self.events[-1][1], "act-1")
        self.assertFalse(job.is_active)
        self.assertTrue(job.can_resume)
        n_gets = len([r for r in self.api.requests if r[0] == "GET"])
        # let time pass; no further polling must happen
        idle = {"done": False}
        wait_for(idle, 300)
        self.assertEqual(len([r for r in self.api.requests if r[0] == "GET"]), n_gets)

    def test_submit_ignored_while_active(self):
        self.api.status_script = [(200, {"error": False, "data": {"activity_id": "act-1", "status": "Processing"}})]
        job, holder, _ = self._job()
        self.assertTrue(job.submit(self._payload()))
        self.assertFalse(job.submit(self._payload()), "second submit while the POST is in flight is ignored")
        sub = {"done": False}
        job.submitted.connect(lambda a: sub.__setitem__("done", True))
        self.assertTrue(wait_for(sub))
        self.assertFalse(job.submit(self._payload()), "submit while polling is ignored")
        job.stop()
        wait_for(holder)
        self._drain()
        self.assertEqual(len([r for r in self.api.requests if r[0] == "POST"]), 1)

    def test_empty_map_data_is_rejected(self):
        empty = json.loads(json.dumps(COMPLETED))
        empty["data"]["result"]["map_data"]["features"] = []
        self.api.status_script = [(200, empty)]
        job, holder, _ = self._job()
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][0], "failed")
        self.assertIn("empty", self.events[-1][1].lower())

    def test_network_error_on_submit_warns_about_uncertain_outcome(self):
        client = HeatmapApiClient("K", base_url="http://127.0.0.1:1", timeout_ms=2000)  # nothing listens
        job = HeatmapJob(client, policy=PollingPolicy(deadline_s=5, initial_interval_s=0.05))
        holder = {"done": False}
        job.failed.connect(lambda m, k: (self.events.append(("failed", m, k)), holder.__setitem__("done", True)))
        job.submit(self._payload())
        self.assertTrue(wait_for(holder))
        self.assertEqual(self.events[-1][2], "network")
        self.assertIn("NOT resubmitted", self.events[-1][1])


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class UsageEndpointTests(LiveLoopTests):
    """Reuses the scripted server; only the usage endpoint is exercised."""

    def test_fetch_usage_posts_key_and_parses(self):
        self.api.usage_response = (200, {"plan_details": {"plan_type": "Premium", "cycle_type": "One-Time"},
                                         "api_key_details": {"status": "active", "valid": True},
                                         "credit_summary": {"total_available_credits": 1000000,
                                                            "cycle_remaining_credits": 995780}})
        client = HeatmapApiClient("TEST-KEY-123", base_url=self.base_url, timeout_ms=5000)
        got = {}
        holder = {"done": False}
        client.fetch_usage(lambda info, err: (got.update(info=info, err=err), holder.__setitem__("done", True)))
        self.assertTrue(wait_for(holder))
        self.assertIsNone(got["err"])
        self.assertEqual(got["info"].plan_type, "Premium")
        self.assertEqual(got["info"].remaining_credits, 995780)
        posts = [r for r in self.api.requests if r[0] == "POST"]
        self.assertEqual(posts[-1][1], contract.USAGE_PATH)
        self.assertEqual(posts[-1][2].get("api-key"), "TEST-KEY-123")
        self.assertEqual(json.loads(posts[-1][3].decode())["api_key"], "TEST-KEY-123")

    def test_fetch_usage_500(self):
        self.api.usage_response = (500, {"error": True, "message": "Unable to fetch API key usage."})
        client = HeatmapApiClient("K", base_url=self.base_url, timeout_ms=5000)
        got = {}
        holder = {"done": False}
        client.fetch_usage(lambda info, err: (got.update(info=info, err=err), holder.__setitem__("done", True)))
        self.assertTrue(wait_for(holder))
        self.assertEqual(got["err"].kind, "server")
        self.assertIn("environment", str(got["err"]))


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class DemoClientTests(unittest.TestCase):
    def test_demo_client_runs_same_job_path(self):
        client = DemoApiClient("daily", processing_ticks=2, tick_ms=20)
        job = HeatmapJob(client, policy=PollingPolicy(deadline_s=10, initial_interval_s=0.02))
        events = []
        holder = {"done": False}
        job.submitted.connect(lambda a: events.append(("submitted", a)))
        job.status_changed.connect(lambda s, d: events.append(("status", s)))
        job.completed.connect(lambda m, s: (events.append(("completed", m, s)), holder.__setitem__("done", True)))
        job.failed.connect(lambda m, k: (events.append(("failed", m, k)), holder.__setitem__("done", True)))
        job.submit({"x": 1})
        self.assertTrue(wait_for(holder))
        self.assertEqual(events[-1][0], "completed")
        self.assertTrue(events[0][1].startswith("demo-"))
        self.assertEqual([e[1] for e in events if e[0] == "status"].count("Processing"), 2)
        self.assertGreater(len(events[-1][1]["features"]), 100)


if __name__ == "__main__":
    unittest.main()
