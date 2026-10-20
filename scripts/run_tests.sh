#!/usr/bin/env bash
# Run the offline unit tests and (if QGIS is installed) the QGIS-runtime tests.
#
#   scripts/run_tests.sh            # everything
#   scripts/run_tests.sh --pure     # only the pure-Python tests (any python3)
#
# The QGIS-runtime tests use the Python interpreter bundled with QGIS.app on
# macOS. Override with QGIS_PYTHON=/path/to/python if needed.
set -euo pipefail
cd "$(dirname "$0")/.."

PURE_ONLY=0
[[ "${1:-}" == "--pure" ]] && PURE_ONLY=1

echo "== Pure-Python tests (system python3) =="
python3 -m unittest tests.test_payload tests.test_responses tests.test_polling tests.test_surface tests.test_preflight

if [[ $PURE_ONLY -eq 1 ]]; then exit 0; fi

QGIS_PYTHON="${QGIS_PYTHON:-}"
if [[ -z "$QGIS_PYTHON" ]]; then
  for candidate in /Applications/QGIS.app/Contents/MacOS/python /Applications/QGIS-LTR.app/Contents/MacOS/python; do
    [[ -x "$candidate" ]] && QGIS_PYTHON="$candidate" && break
  done
fi
if [[ -z "$QGIS_PYTHON" ]]; then
  echo "!! QGIS bundled python not found; QGIS-runtime tests skipped. Set QGIS_PYTHON=... to run them."
  exit 0
fi

echo
echo "== QGIS-runtime tests ($QGIS_PYTHON) =="
"$QGIS_PYTHON" -m unittest tests.test_payload tests.test_responses tests.test_polling tests.test_surface \
  tests.test_preflight tests.test_qgis_geometry tests.test_qgis_output_styling tests.test_qgis_credentials \
  tests.test_qgis_job tests.test_qgis_dialog_demo
