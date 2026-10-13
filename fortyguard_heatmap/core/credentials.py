# -*- coding: utf-8 -*-
"""API key handling.

Default: the key lives only in memory (the dialog's password field).
Optional: store/load it through the QGIS Authentication Manager's encrypted
settings store (``QgsAuthManager.storeAuthSetting``), which is protected by the
QGIS master password. Nothing here ever logs or prints the key.
"""
from qgis.core import QgsApplication

AUTH_SETTING_KEY = "fortyguard_heatmap/api_key"


def _manager():
    mgr = QgsApplication.authManager()
    if mgr is None or mgr.isDisabled():
        return None
    return mgr


def auth_available():
    return _manager() is not None


def store_key(api_key):
    """Encrypt and store the key. Returns True on success. May prompt for the master password."""
    mgr = _manager()
    if mgr is None or not api_key:
        return False
    try:
        if not mgr.setMasterPassword(True):
            return False
        return bool(mgr.storeAuthSetting(AUTH_SETTING_KEY, api_key, True))
    except Exception:
        return False


def load_key():
    """Return the stored key or '' (prompts for the master password if needed)."""
    mgr = _manager()
    if mgr is None:
        return ""
    try:
        if not mgr.existsAuthSetting(AUTH_SETTING_KEY):
            return ""
        if not mgr.setMasterPassword(True):
            return ""
        value = mgr.authSetting(AUTH_SETTING_KEY, "", True)
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def has_stored_key():
    mgr = _manager()
    if mgr is None:
        return False
    try:
        return bool(mgr.existsAuthSetting(AUTH_SETTING_KEY))
    except Exception:
        return False


def forget_key():
    mgr = _manager()
    if mgr is None:
        return False
    try:
        if not mgr.existsAuthSetting(AUTH_SETTING_KEY):
            return True
        if not mgr.setMasterPassword(True):
            return False
        return bool(mgr.removeAuthSetting(AUTH_SETTING_KEY))
    except Exception:
        return False


def mask(api_key):
    """Safe representation for status messages: never reveals the key."""
    if not api_key:
        return "(none)"
    return "set (%d characters)" % len(api_key)
