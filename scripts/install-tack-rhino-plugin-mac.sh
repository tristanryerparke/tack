#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_PATH="$REPO_ROOT/tack.rhproj"
BUILD_PATH="$REPO_ROOT/build"
BUILD_OUTPUT="$BUILD_PATH/rh8"
PLUGIN_FILE="$BUILD_OUTPUT/Tack.rhp"
RUI_FILE="$BUILD_OUTPUT/Tack.rui"
RHINOCODE="${RHINOCODE:-/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode}"
MAC_PLUGINS_DIR="${RHINO_MAC_PLUGINS_DIR:-$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/MacPlugIns}"
INSTALL_DIR="$MAC_PLUGINS_DIR/Tack.rhp"

usage() {
  cat <<'EOF'
Usage: scripts/install-tack-rhino-plugin-mac.sh

Builds tack.rhproj with Rhino 8's rhinocode CLI and installs Tack for the next
Rhino launch.

Environment:
  RHINOCODE               Override the rhinocode executable.
  RHINO_MAC_PLUGINS_DIR   Override Rhino's version-specific MacPlugIns directory.
EOF
}

if [[ $# -gt 0 ]]; then
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
fi

if [[ "$OSTYPE" != darwin* ]]; then
  echo "This installer targets Rhino 8 for macOS (OSTYPE=$OSTYPE)." >&2
  exit 1
fi

if [[ ! -x "$RHINOCODE" ]]; then
  echo "Could not find an executable rhinocode at: $RHINOCODE" >&2
  echo "Set RHINOCODE=/path/to/rhinocode to override it." >&2
  exit 1
fi

echo "Serializing command icons into $PROJECT_PATH..."
uv run "$SCRIPT_DIR/serialize_rhproj_icons.py"

echo "Building $PROJECT_PATH..."
"$RHINOCODE" project build "$PROJECT_PATH" \
  --buildtarget '8.*' \
  --buildpath "$BUILD_PATH"

if [[ ! -f "$PLUGIN_FILE" ]]; then
  echo "Build succeeded, but the plugin was not found: $PLUGIN_FILE" >&2
  exit 1
fi

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp "$PLUGIN_FILE" "$INSTALL_DIR/"

if [[ -f "$RUI_FILE" ]]; then
  cp "$RUI_FILE" "$INSTALL_DIR/"
fi

cat <<EOF
Installed Tack:
  Plugin: $INSTALL_DIR/Tack.rhp
  UI:     $INSTALL_DIR/Tack.rui

Restart Rhino to load this build.
EOF
