#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload a plugin ZIP to plugins.qgis.org through its XML-RPC API (plugin.upload).

This is the same mechanism qgis-plugin-ci uses. It needs an OSGeo ID
(https://id.osgeo.org) with plugin-upload rights. Credentials are read from a
local file so they never appear in a chat or shell history:

    umask 077; mkdir -p ~/.config/fortyguard
    printf 'OSGEO_USERNAME\\nOSGEO_PASSWORD\\n' > ~/.config/fortyguard/osgeo_credentials

Usage:
    python3 scripts/upload_to_qgis_repo.py dist/fortyguard_heatmap-0.2.0.zip [--auto-approve]

Uploading is a SUBMISSION only. The version then goes through the automatic
security scan and manual approval before it is visible in the QGIS Plugin
Manager (see docs/SUBMISSION.md). --auto-approve only works for accounts that
already have the can_approve permission.
"""
import os
import stat
import sys
import xmlrpc.client
from base64 import b64encode

RPC_URL = "https://{user}:{password}@plugins.qgis.org/plugins/RPC2/"


def read_credentials():
    path = os.path.expanduser("~/.config/fortyguard/osgeo_credentials")
    if not os.path.isfile(path):
        sys.exit("Credentials file not found: %s" % path)
    if stat.S_IMODE(os.stat(path).st_mode) & 0o077:
        sys.exit("Refusing: %s is readable by other users. Run: chmod 600 %s" % (path, path))
    with open(path, "r", encoding="utf-8") as fh:
        lines = [l.strip() for l in fh.read().splitlines() if l.strip()]
    if len(lines) < 2:
        sys.exit("Credentials file must contain the OSGeo username on line 1 and the password on line 2.")
    return lines[0], lines[1]


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    zip_path = sys.argv[1]
    auto = "--auto-approve" in sys.argv
    user, password = read_credentials()
    with open(zip_path, "rb") as fh:
        payload = b64encode(fh.read()).decode("ascii")
    from urllib.parse import quote
    server = xmlrpc.client.ServerProxy(RPC_URL.format(user=quote(user, safe=""), password=quote(password, safe="")),
                                       verbose=False)
    print("Uploading %s as %s ..." % (os.path.basename(zip_path), user))
    try:
        result = server.plugin.upload(payload, auto) if auto else server.plugin.upload(payload)
    except xmlrpc.client.Fault as fault:
        sys.exit("Upload rejected by plugins.qgis.org: %s" % fault.faultString)
    except xmlrpc.client.ProtocolError as err:
        sys.exit("HTTP error %s from plugins.qgis.org: %s" % (err.errcode, err.errmsg))
    print("Submitted. Server returned:", result)
    print("Next: watch for the confirmation and security-scan e-mails, then wait for manual approval.")


if __name__ == "__main__":
    main()
