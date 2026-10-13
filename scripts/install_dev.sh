#!/usr/bin/env bash
# Link (or copy) the plugin folder into the active QGIS profile for development.
#
#   scripts/install_dev.sh          # symlink (edits are live; reload plugin in QGIS)
#   scripts/install_dev.sh --copy   # copy instead of symlink
#   scripts/install_dev.sh --remove # remove the link/copy
#
# Profile path is detected from ~/Library/Application Support/QGIS/QGIS3/profiles/profiles.ini
set -euo pipefail
cd "$(dirname "$0")/.."

PROFILES_DIR="$HOME/Library/Application Support/QGIS/QGIS3/profiles"
PROFILE="default"
if [[ -f "$PROFILES_DIR/profiles.ini" ]]; then
  last="$(sed -n 's/^lastProfile=//p' "$PROFILES_DIR/profiles.ini" | tr -d '[:space:]')"
  [[ -n "$last" ]] && PROFILE="$last"
fi
PLUGINS_DIR="$PROFILES_DIR/$PROFILE/python/plugins"
TARGET="$PLUGINS_DIR/fortyguard_heatmap"
SRC="$(pwd)/fortyguard_heatmap"

case "${1:-}" in
  --remove)
    rm -rf "$TARGET"; echo "Removed $TARGET"; exit 0 ;;
  --copy)
    mkdir -p "$PLUGINS_DIR"; rm -rf "$TARGET"
    rsync -a --exclude '__pycache__' "$SRC/" "$TARGET/"; echo "Copied to $TARGET" ;;
  *)
    mkdir -p "$PLUGINS_DIR"
    if [[ -e "$TARGET" && ! -L "$TARGET" ]]; then echo "!! $TARGET exists and is not a symlink; use --remove first"; exit 1; fi
    ln -sfn "$SRC" "$TARGET"; echo "Linked $TARGET -> $SRC" ;;
esac
echo "Profile: $PROFILE"
echo "Now start QGIS, open Plugins > Manage and Install Plugins > Installed, and enable 'FortyGuard Heatmap'."
