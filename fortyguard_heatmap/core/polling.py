# -*- coding: utf-8 -*-
"""Pure polling policy: bounded deadline, backoff, retry limits.

The QGIS job runner (core/job.py) asks this object what to do after every
status check. Keeping the decisions here makes them unit-testable without Qt.
"""
from . import contract


class Decision(object):
    """What the runner should do next."""
    __slots__ = ("action", "delay_s", "reason")

    CONTINUE = "continue"   # schedule another status check after delay_s
    STOP = "stop"           # give up (deadline / too many failures / fatal error)

    def __init__(self, action, delay_s=0.0, reason=""):
        self.action = action
        self.delay_s = delay_s
        self.reason = reason

    def __repr__(self):
        return "Decision(%s, %.1fs, %r)" % (self.action, self.delay_s, self.reason)


class PollingPolicy(object):
    def __init__(self, deadline_s=contract.POLL_DEFAULT_DEADLINE_S,
                 initial_interval_s=contract.POLL_INITIAL_INTERVAL_S,
                 max_interval_s=contract.POLL_MAX_INTERVAL_S,
                 backoff_factor=contract.POLL_BACKOFF_FACTOR,
                 max_consecutive_failures=contract.POLL_MAX_CONSECUTIVE_FAILURES):
        self.deadline_s = float(deadline_s)
        self.initial_interval_s = float(initial_interval_s)
        self.max_interval_s = float(max_interval_s)
        self.backoff_factor = float(backoff_factor)
        self.max_consecutive_failures = int(max_consecutive_failures)
        self.reset()

    def reset(self):
        self.elapsed_s = 0.0
        self.consecutive_failures = 0
        self.checks = 0
        self._interval = self.initial_interval_s

    def _bounded(self, delay):
        remaining = self.deadline_s - self.elapsed_s
        return max(0.0, min(delay, remaining))

    def _deadline_reached(self):
        return self.elapsed_s >= self.deadline_s

    def first_delay(self):
        """Delay before the very first status check after submission."""
        return self._bounded(self.initial_interval_s)

    def advance(self, seconds):
        """Record that wall-clock time passed (called by the runner)."""
        self.elapsed_s += max(0.0, float(seconds))

    def on_in_progress(self):
        """Status check succeeded but the job is still running."""
        self.checks += 1
        self.consecutive_failures = 0
        self._interval = self.initial_interval_s
        if self._deadline_reached():
            return Decision(Decision.STOP, reason="deadline")
        return Decision(Decision.CONTINUE, self._bounded(self._interval), "in_progress")

    def on_retryable_error(self, kind=""):
        """Status check failed in a way that may clear up (404 right after submit,
        5xx, network hiccup, 429)."""
        self.checks += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            return Decision(Decision.STOP, reason="too_many_failures")
        if self._deadline_reached():
            return Decision(Decision.STOP, reason="deadline")
        if kind == "rate_limited":
            self._interval = self.max_interval_s
        else:
            self._interval = min(self._interval * self.backoff_factor, self.max_interval_s)
        return Decision(Decision.CONTINUE, self._bounded(self._interval), "retry:%s" % kind)

    def on_fatal_error(self, kind=""):
        """Status check failed permanently (401/403/400, malformed)."""
        self.checks += 1
        return Decision(Decision.STOP, reason="fatal:%s" % kind)
