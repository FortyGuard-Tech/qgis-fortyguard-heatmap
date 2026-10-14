#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local re-implementation of the plugins.qgis.org upload validator.

Mirrors qgis-app/plugins/validator.py from https://github.com/qgis/QGIS-Django
(read 2026-10-13) so the ZIP can be checked before the real upload:

* size <= 25 MB, valid zip, no path traversal, no .pyc, no __MACOSX/.git/__pycache__
* exactly one top-level folder, PEP 8 name ([a-z_][a-z0-9_]*) for a NEW plugin
* <pkg>/__init__.py and <pkg>/metadata.txt with a [general] section
* required metadata: name, description, version, qgisMinimumVersion, author, email,
  about, tracker, repository; booleans experimental/deprecated/server
* icon path (if given) must exist inside the package
* tracker / repository / homepage must be real URLs that answer < 400 to HEAD
* <pkg>/LICENSE must exist; author may not contain '/'
Plus the documented packaging tips: README present, no ui_*.py / resources_rc.py.

Usage: python3 scripts/validate_package.py dist/fortyguard_heatmap-<version>.zip [--offline]
Exit code 0 = would pass the server validator (as far as it can be reproduced).
"""
import configparser
import io
import re
import sys
import urllib.request
import zipfile

MAX_SIZE = 25_000_000
REQUIRED = ("name", "description", "version", "qgisMinimumVersion", "author", "email", "about", "tracker", "repository")
BOOLEANS = ("experimental", "deprecated", "server")
FORBIDDEN_DIRS = ("__MACOSX", ".git", "__pycache__")


def head_ok(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 (validator check)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status < 400, resp.status
    except urllib.error.HTTPError as exc:
        return exc.code < 400, exc.code
    except Exception as exc:
        return False, str(exc)


def main(path, offline=False):
    errors, warnings = [], []
    data = open(path, "rb").read()
    if len(data) > MAX_SIZE:
        errors.append("File is too big (max 25 MB)")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        print("ERROR: could not unzip file"); return 1
    names = zf.namelist()
    for n in names:
        if ".." in n or n.startswith("/"):
            errors.append("path information in zip: %s" % n)
        if ".pyc" in n:
            errors.append(".pyc file in zip: %s" % n)
        parts = n.split("/")
        for fd in FORBIDDEN_DIRS:
            if fd in parts:
                errors.append("forbidden directory %s at %s" % (fd, n))
        base = parts[-1]
        if re.match(r"^ui_.*\.py$", base) or base == "resources_rc.py":
            warnings.append("generated file should be excluded: %s" % n)
    bad = zf.testzip()
    if bad:
        errors.append("bad zip entry: %s" % bad)
    tops = sorted({n.split("/")[0] for n in names})
    if len(tops) != 1:
        errors.append("zip must contain exactly one top-level folder, found %s" % tops)
        pkg = tops[0] if tops else ""
    else:
        pkg = tops[0]
    if not re.match(r"^[a-z_][a-z0-9_]*$", pkg):
        errors.append("top-level folder '%s' is not PEP 8 compliant (new plugins)" % pkg)
    if "plugin" in pkg.lower():
        warnings.append("folder name should not repeat the word 'plugin'")
    init = pkg + "/__init__.py"
    meta = pkg + "/metadata.txt"
    if init not in names:
        errors.append("missing %s" % init)
    if meta not in names:
        errors.append("missing %s" % meta)
        md = {}
    else:
        parser = configparser.ConfigParser()  # default interpolation, exactly like the server ('%' must be '%%')
        try:
            parser.read_file(io.StringIO(zf.read(meta).decode("utf-8")))
        except Exception as exc:
            errors.append("metadata.txt parse error: %s" % exc)
        if not parser.has_section("general"):
            errors.append("metadata.txt has no [general] section")
            md = {}
        else:
            md = dict(parser.items("general"))
    missing = [k for k in REQUIRED if k.lower() not in md]
    if missing:
        errors.append("missing required metadata: %s" % ", ".join(missing))
    for b in BOOLEANS:
        v = md.get(b)
        if v is not None and v.strip().lower() not in ("true", "false", "1", "0"):
            errors.append("boolean metadata %s has invalid value %r" % (b, v))
    if md.get("author") and "/" in md["author"]:
        errors.append("author name cannot contain slashes")
    if md.get("name") and "plugin" in md["name"].lower():
        warnings.append("plugin name should not repeat the word 'plugin'")
    icon = md.get("icon")
    if icon:
        icon_path = icon[2:] if icon.startswith("./") else icon
        if pkg + "/" + icon_path not in names:
            errors.append("icon %s not found in package" % icon)
    if pkg + "/LICENSE" not in names:
        errors.append("missing %s/LICENSE (mandatory since 2024-06-03)" % pkg)
    if not any(n.lower() in (pkg + "/readme.md", pkg + "/readme.txt", pkg + "/readme") for n in names):
        warnings.append("no README in the package (documented tip)")
    from urllib.parse import urlparse
    for key, forbidden in (("tracker", "http://bugs"), ("repository", "http://repo"), ("homepage", "http://homepage")):
        url = md.get(key)
        if url is None:
            continue
        if url == forbidden or not all([urlparse(url).scheme, urlparse(url).netloc]):
            errors.append("invalid URL for %s: %r" % (key, url))
        elif not offline:
            ok, status = head_ok(url)
            if not ok:
                errors.append("%s URL cannot be reached (HEAD -> %s): %s" % (key, status, url))
            else:
                print("  url ok   %-10s %s (%s)" % (key, url, status))
    print("package:", pkg, "| version:", md.get("version"), "| experimental:", md.get("experimental"))
    for w in warnings:
        print("WARNING:", w)
    for e in errors:
        print("ERROR:", e)
    print("RESULT:", "PASS (would be accepted by the upload validator)" if not errors else "FAIL")
    return 0 if not errors else 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(2)
    sys.exit(main(sys.argv[1], offline="--offline" in sys.argv))
