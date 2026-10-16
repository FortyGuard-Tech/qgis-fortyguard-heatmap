#!/usr/bin/env bash
# Build the installable plugin ZIP: dist/fortyguard_heatmap-<version>.zip
# The archive contains exactly one top-level folder named "fortyguard_heatmap"
# (the folder name QGIS uses as the plugin id). Caches, tests, dev files and
# anything that could hold a key are excluded.
set -euo pipefail
cd "$(dirname "$0")/.."

PLUGIN_DIR="fortyguard_heatmap"
VERSION="$(sed -n 's/^version=//p' "$PLUGIN_DIR/metadata.txt" | tr -d '[:space:]')"
[[ -n "$VERSION" ]] || { echo "version not found in metadata.txt"; exit 1; }

mkdir -p dist
OUT="dist/${PLUGIN_DIR}-${VERSION}.zip"
rm -f "$OUT"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
rsync -a "$PLUGIN_DIR/" "$STAGE/$PLUGIN_DIR/" \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '*.pyo' \
  --exclude '.DS_Store' --exclude '.git*' --exclude '*.env' --exclude '.env*' \
  --exclude '*.key' --exclude 'api_key*' --exclude 'tests' --exclude '*.orig' --exclude '*.swp'

# Safety net: the same Bandit scan plugins.qgis.org runs (blocks on any finding) - when bandit is installed.
if python3 -m bandit --version >/dev/null 2>&1; then
  if ! python3 -m bandit -r "$STAGE/$PLUGIN_DIR" -q >/dev/null 2>&1; then
    echo "!! Refusing to package: Bandit reported findings (plugins.qgis.org would block this version):"
    python3 -m bandit -r "$STAGE/$PLUGIN_DIR" -q 2>/dev/null | grep -E "Issue|Location" || true
    exit 1
  fi
  echo "Bandit: clean"
fi

# Safety net: refuse to package anything that looks like a live key.
if grep -rIE 'fg_live_[A-Za-z0-9]{8,}' "$STAGE" >/dev/null 2>&1; then
  echo "!! Refusing to package: a string that looks like a live API key was found."; exit 1
fi

( cd "$STAGE" && zip -qr -X "$OLDPWD/$OUT" "$PLUGIN_DIR" -x '*/__MACOSX/*' )
echo "Built $OUT"
unzip -l "$OUT" | awk 'NR>3 {print $4}' | grep -v '^$' | sed '$d' | sed '$d' | awk -F/ '{print $1}' | sort -u | sed 's/^/top-level: /'
du -h "$OUT"
