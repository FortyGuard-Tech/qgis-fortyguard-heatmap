# -*- coding: utf-8 -*-
"""QGIS-runtime test of the optional encrypted key storage (QgsAuthManager settings).

qgis_env points QGIS_AUTH_DB_DIR_PATH at a temp folder and supplies a master
password file, so this never touches the user's real authentication database.
"""
import os
import unittest

from tests import qgis_env

if qgis_env.qgis_available():
    qgis_env.start()
    from qgis.core import QgsApplication
    from fortyguard_heatmap.core import credentials


@unittest.skipUnless(qgis_env.qgis_available(), "QGIS runtime not available")
class CredentialTests(unittest.TestCase):
    def test_store_load_forget(self):
        # Opt-in: with the real auth-method plugins loaded, setMasterPassword() talks to the
        # OS keychain and can block a headless run. Run inside QGIS or set FG_TEST_AUTH_STORE=1.
        if os.environ.get("FG_TEST_AUTH_STORE") != "1":
            self.skipTest("set FG_TEST_AUTH_STORE=1 to exercise the QGIS auth store (may prompt for the master password)")
        if not credentials.auth_available():
            self.skipTest("QGIS auth manager disabled in this runtime")
        mgr = QgsApplication.authManager()
        if not mgr.setMasterPassword(True):
            self.skipTest("could not set a master password in the headless test runtime")
        self.assertTrue(credentials.store_key("fg_test_key_ABC123"))
        self.assertTrue(credentials.has_stored_key())
        self.assertEqual(credentials.load_key(), "fg_test_key_ABC123")
        self.assertTrue(credentials.forget_key())
        self.assertFalse(credentials.has_stored_key())
        self.assertEqual(credentials.load_key(), "")

    def test_mask_never_reveals(self):
        self.assertEqual(credentials.mask(""), "(none)")
        m = credentials.mask("fg_live_secret")
        self.assertNotIn("secret", m)
        self.assertIn("14", m)


if __name__ == "__main__":
    unittest.main()
