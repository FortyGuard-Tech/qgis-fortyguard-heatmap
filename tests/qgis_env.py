# -*- coding: utf-8 -*-
"""Start a headless QgsApplication once for the QGIS-dependent tests.

Run these tests with the QGIS-bundled interpreter, e.g. on macOS:
    /Applications/QGIS.app/Contents/MacOS/python -m unittest discover -s tests -p "test_qgis_*.py" -t .
"""
import os
import sys
import tempfile

_APP = None


def qgis_available():
    try:
        import qgis.core  # noqa: F401
        return True
    except Exception:
        return False


def start():
    """Return the shared QgsApplication (created on first call)."""
    global _APP
    if _APP is not None:
        return _APP
    # Keep the test run isolated from the user's real profile / auth database.
    tmp = tempfile.mkdtemp(prefix="fg_qgis_test_")
    os.environ.setdefault("QGIS_AUTH_DB_DIR_PATH", tmp)
    os.environ.setdefault("QGIS_AUTH_PASSWORD_FILE", os.path.join(tmp, "master.txt"))
    with open(os.environ["QGIS_AUTH_PASSWORD_FILE"], "w") as fh:
        fh.write("test-master-password\n")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _set_data_dirs()
    from qgis.core import QgsApplication
    prefix = _prefix_path()
    QgsApplication.setPrefixPath(prefix, True)
    plugin_path = os.path.join(os.path.dirname(prefix), "PlugIns", "qgis")  # macOS app bundle layout
    if os.path.isdir(plugin_path):
        QgsApplication.setPluginPath(plugin_path)
    _APP = QgsApplication([], True)
    _APP.initQgis()
    return _APP


def _set_data_dirs():
    """Point PROJ/GDAL at the data bundled with QGIS when running outside the app."""
    prefix = _prefix_path()
    resources = os.path.join(os.path.dirname(prefix), "Resources")
    proj_dir = os.path.join(resources, "qgis", "proj")
    gdal_dir = os.path.join(resources, "qgis", "gdal")
    if not os.path.isdir(proj_dir):
        proj_dir = os.path.join(resources, "proj")
    if not os.path.isdir(gdal_dir):
        gdal_dir = os.path.join(resources, "gdal")
    if os.path.isfile(os.path.join(proj_dir, "proj.db")):
        os.environ.setdefault("PROJ_LIB", proj_dir)
        os.environ.setdefault("PROJ_DATA", proj_dir)
    if os.path.isdir(gdal_dir):
        os.environ.setdefault("GDAL_DATA", gdal_dir)


def _prefix_path():
    import qgis
    # .../Contents/Resources/python3.11/site-packages/qgis -> .../Contents/MacOS
    here = os.path.dirname(os.path.abspath(qgis.__file__))
    for _ in range(5):
        here = os.path.dirname(here)
        candidate = os.path.join(here, "MacOS")
        if os.path.isdir(candidate):
            return candidate
    return os.environ.get("QGIS_PREFIX_PATH", "/usr")
