# -*- coding: utf-8 -*-
"""Asynchronous FortyGuard API client built on QgsNetworkAccessManager.

Every call returns immediately; results arrive through the ``callback`` given
to the method, invoked on the main thread with ``(result, error)`` where
exactly one of the two is not None. ``error`` is an ``ApiError``.

The API key is sent only as the documented ``api-key`` request header. It is
never logged, never placed in a URL and never stored by this class beyond the
in-memory attribute.
"""
import contextlib
from qgis.PyQt.QtCore import QByteArray, QObject, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager

import json

from . import contract
from .responses import ApiError, parse_status_response, parse_submit_response, parse_usage_response

try:  # QGIS >= 3.x exposes these attributes; fall back gracefully otherwise.
    _ATTR_FOLLOW = QNetworkRequest.FollowRedirectsAttribute
except AttributeError:  # pragma: no cover
    _ATTR_FOLLOW = None


class HeatmapApiClient(QObject):
    """Thin async adapter. UI code must not build requests itself."""

    def __init__(self, api_key, base_url=contract.DEFAULT_BASE_URL, timeout_ms=contract.HTTP_TIMEOUT_MS, parent=None):
        super().__init__(parent)
        self._api_key = (api_key or "").strip()
        self.base_url = (base_url or contract.DEFAULT_BASE_URL).rstrip("/")
        self.timeout_ms = int(timeout_ms)
        self._replies = set()

    # ------------------------------------------------------------- public

    def submit_heatmap(self, payload, callback):
        """POST /v1/heatmap. callback(activity_id, error)."""
        url = QUrl(self.base_url + contract.HEATMAP_PATH)
        request = self._request(url)
        request.setHeader(QNetworkRequest.ContentTypeHeader, contract.CONTENT_TYPE_JSON)
        body = QByteArray(json.dumps(payload).encode("utf-8"))
        reply = QgsNetworkAccessManager.instance().post(request, body)
        self._track(reply, callback, parse_submit_response, "submit")
        return reply

    def get_status(self, activity_id, callback):
        """GET /v1/status/{activity_id}. callback(StatusResult, error)."""
        path = contract.STATUS_PATH_TEMPLATE.format(activity_id=QUrl.toPercentEncoding(activity_id).data().decode("ascii"))
        request = self._request(QUrl(self.base_url + path))
        reply = QgsNetworkAccessManager.instance().get(request)
        self._track(reply, callback, parse_status_response, "status")
        return reply

    def fetch_usage(self, callback):
        """POST /v1/system/fetch-api-key-usage. callback(UsageInfo, error).

        The documented request body carries the key as well; it goes only to the
        configured base URL, like every other call.
        """
        request = self._request(QUrl(self.base_url + contract.USAGE_PATH))
        request.setHeader(QNetworkRequest.ContentTypeHeader, contract.CONTENT_TYPE_JSON)
        body = QByteArray(json.dumps({"api_key": self._api_key}).encode("utf-8"))
        reply = QgsNetworkAccessManager.instance().post(request, body)
        self._track(reply, callback, parse_usage_response, "usage")
        return reply

    def abort_all(self):
        """Abort in-flight replies (used on Stop / unload). Callbacks are not invoked."""
        for reply in list(self._replies):
            with contextlib.suppress(Exception):
                reply.finished.disconnect()
            with contextlib.suppress(Exception):
                reply.abort()
            reply.deleteLater()
        self._replies.clear()

    def has_api_key(self):
        return bool(self._api_key)

    # ------------------------------------------------------------ internal

    def _request(self, url):
        request = QNetworkRequest(url)
        request.setRawHeader(contract.AUTH_HEADER.encode("ascii"), self._api_key.encode("utf-8"))
        request.setRawHeader(b"Accept", contract.CONTENT_TYPE_JSON.encode("ascii"))
        request.setRawHeader(b"User-Agent", b"FortyGuard-Heatmap-QGIS-Plugin/0.1")
        if _ATTR_FOLLOW is not None:
            request.setAttribute(_ATTR_FOLLOW, False)  # never forward the key to another host
        # QGIS's network manager has a disk cache; API responses must never come from it.
        request.setAttribute(QNetworkRequest.CacheLoadControlAttribute, QNetworkRequest.AlwaysNetwork)
        request.setAttribute(QNetworkRequest.CacheSaveControlAttribute, False)
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(self.timeout_ms)
        return request

    def _track(self, reply, callback, parser, context):
        self._replies.add(reply)

        def _finished():
            self._replies.discard(reply)
            try:
                result, error = self._handle(reply, parser, context)
            finally:
                reply.deleteLater()
            callback(result, error)

        reply.finished.connect(_finished)

    def _handle(self, reply, parser, context):
        http_status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        net_error = reply.error()

        if net_error != QNetworkReply.NoError and http_status is None:
            # Pure transport failure (DNS, TLS, timeout, offline...). No HTTP status to interpret.
            if net_error in (QNetworkReply.TimeoutError, QNetworkReply.OperationCanceledError):
                return None, ApiError("The request timed out before FortyGuard answered.", kind="timeout",
                                      retryable=(context == "status"))
            if net_error == QNetworkReply.AuthenticationRequiredError:
                return None, ApiError("Authentication was rejected (HTTP 401).", kind="auth", http_status=401)
            return None, ApiError("Network error while contacting FortyGuard: %s" % reply.errorString(),
                                  kind="network", retryable=(context == "status"))
        try:
            return parser(http_status, body), None
        except ApiError as exc:
            return None, exc
        except Exception as exc:  # defensive: never let a parser bug kill the event loop
            return None, ApiError("Unexpected error while reading the API response: %s" % exc, kind="malformed")
