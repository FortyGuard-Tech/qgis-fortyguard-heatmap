# -*- coding: utf-8 -*-
"""Heatmap job runner: submit once, then poll status with QTimer on the main thread.

Signals (all emitted on the main thread):
    submitted(str activity_id)
    status_changed(str raw_status, str detail)
    progress(str message)
    completed(dict map_data, dict stats_data)
    failed(str message, str kind)
    stopped(str activity_id)     -- user stopped waiting; the server job is NOT cancelled

Rules implemented here:
* A POST is never automatically repeated. If the POST outcome is uncertain the
  user is told so and must decide.
* activity_id is kept after any status failure so polling can be resumed.
"""
import contextlib
import time

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from .polling import Decision, PollingPolicy
from .responses import ApiError, extract_result, validate_map_data


class HeatmapJob(QObject):
    submitted = pyqtSignal(str)
    status_changed = pyqtSignal(str, str)
    progress = pyqtSignal(str)
    completed = pyqtSignal(dict, dict)
    failed = pyqtSignal(str, str)
    stopped = pyqtSignal(str)

    def __init__(self, client, deadline_s=None, policy=None, parent=None):
        super().__init__(parent)
        self.client = client
        self.policy = policy or (PollingPolicy(deadline_s=deadline_s) if deadline_s else PollingPolicy())
        self.activity_id = None
        self.last_error = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._check_status)
        self._active = False
        self._awaiting_submit = False
        self._last_tick = None
        self._generation = 0

    # --------------------------------------------------------------- state

    @property
    def is_active(self):
        return self._active

    @property
    def can_resume(self):
        return bool(self.activity_id) and not self._active

    # -------------------------------------------------------------- public

    def submit(self, payload):
        """Submit once and start polling. Ignored while a request is active."""
        if self._active:
            return False
        self.policy.reset()
        self.activity_id = None
        self.last_error = None
        self._active = True
        self._awaiting_submit = True
        self._generation += 1
        gen = self._generation
        self.progress.emit("Submitting heatmap request...")

        def _cb(activity_id, error):
            if gen != self._generation:
                return  # stopped/unloaded meanwhile
            self._awaiting_submit = False
            if error is not None:
                self._active = False
                self.last_error = error
                if error.kind in ("timeout", "network"):
                    msg = ("%s The request may or may not have reached FortyGuard. It was NOT resubmitted "
                           "automatically to avoid a duplicate charge; check your credits usage before retrying."
                           % error.user_message())
                else:
                    msg = error.user_message()
                self.failed.emit(msg, error.kind)
                return
            self.activity_id = activity_id
            self.submitted.emit(activity_id)
            self.status_changed.emit("Submitted", "Waiting for the first status check")
            self._schedule(self.policy.first_delay())

        self.client.submit_heatmap(payload, _cb)
        return True

    def resume(self, activity_id=None):
        """Poll an existing activity (after Stop Waiting or a status failure)."""
        if self._active:
            return False
        activity_id = (activity_id or self.activity_id or "").strip()
        if not activity_id:
            return False
        self.activity_id = activity_id
        self.policy.reset()
        self.last_error = None
        self._active = True
        self._generation += 1
        self.progress.emit("Checking activity %s..." % activity_id)
        self._schedule(0.0)
        return True

    def stop(self):
        """Stop waiting locally. Does not cancel anything on the server."""
        was_active = self._active
        self._timer.stop()
        self._generation += 1  # invalidates callbacks of in-flight replies
        self._active = False
        self._awaiting_submit = False
        with contextlib.suppress(Exception):
            self.client.abort_all()
        if was_active:
            self.stopped.emit(self.activity_id or "")

    # ------------------------------------------------------------ internal

    def _schedule(self, delay_s):
        self._last_tick = time.monotonic()
        self._timer.start(int(max(0.0, delay_s) * 1000))

    def _check_status(self):
        if not self._active or not self.activity_id:
            return
        if self._last_tick is not None:
            self.policy.advance(time.monotonic() - self._last_tick)
        gen = self._generation
        self.progress.emit("Checking status of %s (elapsed %ds)..." % (self.activity_id, int(self.policy.elapsed_s)))

        def _cb(status_result, error):
            if gen != self._generation:
                return
            if error is not None:
                self._on_status_error(error)
                return
            self._on_status(status_result)

        self.client.get_status(self.activity_id, _cb)

    def _on_status_error(self, error):
        self.last_error = error
        if error.retryable:
            decision = self.policy.on_retryable_error(error.kind)
            self.status_changed.emit("Retrying", error.user_message())
        else:
            decision = self.policy.on_fatal_error(error.kind)
        self._apply(decision, error)

    def _on_status(self, status_result):
        if status_result.is_success:
            self.status_changed.emit(status_result.raw_status, "Result received")
            try:
                map_data, stats_data = extract_result(status_result)
                validate_map_data(map_data)
            except ApiError as exc:
                self._active = False
                self.last_error = exc
                self.failed.emit(exc.user_message(), exc.kind)
                return
            self._active = False
            self.completed.emit(map_data, stats_data)
            return
        if status_result.is_failure:
            self._active = False
            msg = "FortyGuard reported the heatmap job as %s." % status_result.raw_status
            if status_result.message:
                msg += " Message: %s" % status_result.message
            msg += " (Failed tasks do not consume credits, per the documentation.)"
            self.last_error = ApiError(msg, kind="failed")
            self.failed.emit(msg, "failed")
            return
        self.status_changed.emit(status_result.raw_status, "Job still running")
        self._apply(self.policy.on_in_progress(), None)

    def _apply(self, decision, error):
        if decision.action == Decision.CONTINUE:
            self._schedule(decision.delay_s)
            return
        self._active = False
        if decision.reason == "deadline":
            msg = ("Stopped waiting after %d minutes. The job may still finish on the server; "
                   "use 'Check Again' to poll activity %s later." % (int(self.policy.deadline_s // 60), self.activity_id))
            kind = "timeout"
        elif decision.reason == "too_many_failures":
            msg = ("Gave up after %d consecutive failed status checks (last error: %s). The job may still be running; "
                   "use 'Check Again' later for activity %s." % (self.policy.consecutive_failures,
                                                                error.user_message() if error else "unknown",
                                                                self.activity_id))
            kind = error.kind if error else "unknown"
        else:
            msg = error.user_message() if error else "Stopped."
            kind = error.kind if error else "unknown"
        self.failed.emit(msg, kind)
