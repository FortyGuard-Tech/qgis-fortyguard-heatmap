# -*- coding: utf-8 -*-
"""Offline tests for the polling policy (deadline, backoff, retry limits)."""
import unittest

from fortyguard_heatmap.core.polling import Decision, PollingPolicy


class PollingPolicyTests(unittest.TestCase):
    def test_in_progress_keeps_fixed_interval(self):
        p = PollingPolicy(deadline_s=60, initial_interval_s=3)
        self.assertEqual(p.first_delay(), 3)
        for _ in range(5):
            p.advance(3)
            d = p.on_in_progress()
            self.assertEqual(d.action, Decision.CONTINUE)
            self.assertEqual(d.delay_s, 3)

    def test_deadline_stops(self):
        p = PollingPolicy(deadline_s=10, initial_interval_s=3)
        p.advance(3); self.assertEqual(p.on_in_progress().action, Decision.CONTINUE)
        p.advance(3); self.assertEqual(p.on_in_progress().action, Decision.CONTINUE)
        p.advance(3)
        d = p.on_in_progress()
        self.assertEqual(d.action, Decision.CONTINUE)
        self.assertAlmostEqual(d.delay_s, 1.0)  # clipped to the remaining second
        p.advance(1)
        d = p.on_in_progress()
        self.assertEqual(d.action, Decision.STOP)
        self.assertEqual(d.reason, "deadline")

    def test_backoff_on_retryable_errors(self):
        p = PollingPolicy(deadline_s=1000, initial_interval_s=2, max_interval_s=10, backoff_factor=2)
        delays = []
        for _ in range(5):
            d = p.on_retryable_error("not_found")
            self.assertEqual(d.action, Decision.CONTINUE)
            delays.append(d.delay_s)
        self.assertEqual(delays, [4, 8, 10, 10, 10])
        # success resets the interval
        d = p.on_in_progress()
        self.assertEqual(d.delay_s, 2)
        self.assertEqual(p.consecutive_failures, 0)

    def test_rate_limit_jumps_to_max_interval(self):
        p = PollingPolicy(deadline_s=1000, initial_interval_s=3, max_interval_s=30)
        d = p.on_retryable_error("rate_limited")
        self.assertEqual(d.delay_s, 30)

    def test_too_many_consecutive_failures(self):
        p = PollingPolicy(deadline_s=1000, max_consecutive_failures=3)
        self.assertEqual(p.on_retryable_error("server").action, Decision.CONTINUE)
        self.assertEqual(p.on_retryable_error("server").action, Decision.CONTINUE)
        d = p.on_retryable_error("server")
        self.assertEqual(d.action, Decision.STOP)
        self.assertEqual(d.reason, "too_many_failures")

    def test_fatal_stops_immediately(self):
        p = PollingPolicy()
        d = p.on_fatal_error("auth")
        self.assertEqual(d.action, Decision.STOP)
        self.assertEqual(d.reason, "fatal:auth")

    def test_reset(self):
        p = PollingPolicy(deadline_s=10)
        p.advance(9); p.on_retryable_error("x")
        p.reset()
        self.assertEqual(p.elapsed_s, 0)
        self.assertEqual(p.consecutive_failures, 0)
        self.assertEqual(p.first_delay(), p.initial_interval_s)


if __name__ == "__main__":
    unittest.main()
