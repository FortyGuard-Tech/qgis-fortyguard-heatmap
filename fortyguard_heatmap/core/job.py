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
* Stop Waiting while the POST is in flight does not abort the POST: the answer
  is awaited so the activity_id (a paid job) is recorded, then polling stops.
* An empty "Completed" result is reported as kind "empty" (credits were most
  likely charged) and its stats are kept in ``last_stats``.
* When resuming an older activity, HTTP 404 is retried only a few times: it is
  not "just submitted" any more.
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
        self._stop_after_submit = False
        self._resumed = False
        self._last_tick = None
        self._generation = 0
        self.last_stats = None
        self.max_not_found_on_resume = 3

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
        self.last_stats = None
        self._active = True
        self._awaiting_submit = True
        self._stop_after_submit = False
        self._resumed = False
        self._generation += 1
        gen = self._generation
        self.progress.emit("Submitting heatmap request...")

        def _cb(activity_id, error):
            if gen != self._generation:
                return  # unloaded meanwhile
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
            if self._stop_after_submit:
                # The user clicked Stop while the POST was in flight: the job exists (and is paid),
                # so keep its id and stop polling instead of pretending nothing was sent.
                self._stop_after_submit = False
                self._active = False
                self.stopped.emit(activity_id)
                return
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
        self._resumed = True
        self._generation += 1
        self.progress.emit("Checking activity %s..." % activity_id)
        self._schedule(0.0)
        return True

    def stop(self):
        """Stop waiting locally. Does not cancel anything on the server.

        While the submission POST is still in flight the reply is NOT aborted:
        the server may already have created (and charged) the job, so the
        activity_id must be recorded. ``stopped`` is emitted once it arrives.
        """
        was_active = self._active
        self._timer.stop()
        if was_active and self._awaiting_submit:
            self._stop_after_submit = True
            self.progress.emit("Stop requested; waiting for the submission answer so the activity ID is not lost...")
            return
        self._generation += 1  # invalidates callbacks of in-flight replies
        self._active = False
        self._awaiting_submit = False
        with contextlib.suppress(Exception):
            self.client.abort_all()
        if was_active:
            self.stopped.emit(self.activity_id or "")

    def abandon(self):
        """Hard stop used on unload: abort everything, emit nothing."""
        self._timer.stop()
        self._generation += 1
        self._active = False
        self._awaiting_submit = False
        self._stop_after_submit = False
        with contextlib.suppress(Exception):
            self.client.abort_all()

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
            if (error.kind == "not_found" and self._resumed
                    and self.policy.consecutive_failures >= self.max_not_found_on_resume
                    and decision.action == Decision.CONTINUE):
                decision = self.policy.on_fatal_error(error.kind)
                error = ApiError(
                    "Activity %s was not found after %d checks (HTTP 404). It is not a freshly submitted job, so "
                    "the ID is unknown to this API environment, belongs to another account, or was mistyped."
                    % (self.activity_id, self.policy.consecutive_failures), kind="not_found", http_status=404)
                self.last_error = error
            else:
                self.status_changed.emit("Retrying", error.user_message())
        else:
            decision = self.policy.on_fatal_error(error.kind)
        self._apply(decision, error)

    def _on_status(self, status_result):
        if status_result.is_success:
            self.status_changed.emit(status_result.raw_status, "Result received")
            try:
                map_data, stats_data = extract_result(status_result)
                self.last_stats = stats_data
                validate_map_data(map_data)
            except ApiError as exc:
                self._active = False
                self.last_error = exc
                msg = exc.user_message()
                if exc.kind == "empty":
                    msg += " Activity %s." % self.activity_id
                self.failed.emit(msg, exc.kind)
                return
            self._active = False
            self.completed.emit(map_data, stats_data)
            return
        if status_result.is_failure:
            self._active = False
            msg = "FortyGuard reported the heatmap job as %s." % status_result.raw_status
            detail = (status_result.message or "").strip()
            if detail and detail.lower() != status_result.status:
                msg += " Message: %s" % detail
            else:
                msg += " The API gave no reason."
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
            if error is not None and error.http_status in (502, 503, 504):
                msg += (" In internal testing, repeated HTTP %d answers happened with very large areas (hundreds of "
                        "square miles): those jobs never finished although credits were charged. If 'Check Again' "
                        "keeps failing, contact support with the activity ID." % error.http_status)
            kind = error.kind if error else "unknown"
        else:
            msg = error.user_message() if error else "Stopped."
            kind = error.kind if error else "unknown"
        self.failed.emit(msg, kind)
