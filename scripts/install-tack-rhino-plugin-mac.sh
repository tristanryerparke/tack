#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RHINOCODE="${RHINOCODE:-/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode}"
BUILD_CONFIGURATION="${BUILD_CONFIGURATION:-Debug}"
GENERATED_PROJECT="$REPO_ROOT/build/rh8/src/Tack/Tack.csproj"
GENERATED_PLUGIN="$REPO_ROOT/build/rh8/Tack.rhp"
PROJECT_DATA_EXTRACTOR="$REPO_ROOT/csharp/TackScriptPlugin/ProjectDataExtractor/ProjectDataExtractor.csproj"
PLUGIN_FILE="$REPO_ROOT/build/rh8/src/Tack/bin/$BUILD_CONFIGURATION/net48/Tack.rhp"
MAC_PLUGINS_DIR="${RHINO_MAC_PLUGINS_DIR:-$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/MacPlugIns}"
INSTALL_DIR="$MAC_PLUGINS_DIR/Tack.rhp"
LEGACY_INSTALL_DIR="$MAC_PLUGINS_DIR/TackPanelHost.rhp"
LEGACY_RUI_SETTINGS="$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/settings/Scheme__Default/Tack_e59443d4-ab7b-4e21-8aa3-66a7ced1ae27.xml"

usage() {
  cat <<'EOF'
Usage: scripts/install-tack-rhino-plugin-mac.sh

Builds Tack's Python Script Editor project, applies its C# startup/panel
extension, and installs the combined plugin for the next Rhino launch.

Environment:
  BUILD_CONFIGURATION    dotnet configuration. Default: Debug.
  RHINOCODE              RhinoCode CLI path.
  RHINO_MAC_PLUGINS_DIR  Override Rhino's MacPlugIns directory.
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
  echo "RhinoCode CLI was not found: $RHINOCODE" >&2
  exit 1
fi

echo "Generating $REPO_ROOT/tack.rhproj..."
"$RHINOCODE" project build "$REPO_ROOT/tack.rhproj"
dotnet run --project "$PROJECT_DATA_EXTRACTOR" -- \
  "$GENERATED_PLUGIN" "$(dirname "$GENERATED_PROJECT")/Plugin.Data.resources"
uv run "$REPO_ROOT/scripts/prepare-tack-script-plugin.py"

echo "Building $GENERATED_PROJECT ($BUILD_CONFIGURATION)..."
dotnet build "$GENERATED_PROJECT" -c "$BUILD_CONFIGURATION"

if [[ ! -f "$PLUGIN_FILE" ]]; then
  echo "Build succeeded, but the plugin was not found: $PLUGIN_FILE" >&2
  exit 1
fi

rm -rf "$INSTALL_DIR" "$LEGACY_INSTALL_DIR"
rm -f "$LEGACY_RUI_SETTINGS"
mkdir -p "$INSTALL_DIR/Python"
cp "$PLUGIN_FILE" "$INSTALL_DIR/"
cp -R "$REPO_ROOT/tack" "$INSTALL_DIR/Python/"

cat <<EOF
Installed Tack:
  Plugin: $INSTALL_DIR/Tack.rhp
  Python: $INSTALL_DIR/Python/tack

The generated Python commands own TackAdd, TackShow, TackHide, and TackClear.
Restart Rhino to load this build.
EOF
