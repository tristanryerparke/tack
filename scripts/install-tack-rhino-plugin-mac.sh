#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RHINOCODE="${RHINOCODE:-/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode}"
RHINO_PROJECT="$REPO_ROOT/tack.rhproj"
GENERATED_ROOT="$REPO_ROOT/build/rh8"
GENERATED_PROJECT="$GENERATED_ROOT/src/Tack/Tack.csproj"
GENERATED_PLUGIN="$GENERATED_ROOT/Tack.rhp"
TEMPLATE_ROOT="${RHINO_PYTHON_PLUGIN_TEMPLATE_ROOT:-$REPO_ROOT/../rhino-python-plugin-template}"
PROJECT_DATA_EXTRACTOR="$TEMPLATE_ROOT/src/ProjectDataExtractor/ProjectDataExtractor.csproj"
PLUGIN_NAME="Tack"
MAC_PLUGINS_DIR="${RHINO_MAC_PLUGINS_DIR:-$HOME/Library/Application Support/McNeel/Rhinoceros/8.0/MacPlugIns}"
INSTALL_DIR="$MAC_PLUGINS_DIR/$PLUGIN_NAME.rhp"
MODE="development"
CONFIGURATION=""

usage() {
  cat <<'EOF'
Usage: scripts/install-tack-rhino-plugin-mac.sh [--mode development|production] [--configuration Debug|Release]

Generates Tack's native Rhino commands, applies its stable C# panel and
persistence extension, and installs one mutually exclusive plug-in bundle.

Development mode reads Tack Python and panel command files from this checkout.
Production mode packages a Tack Python snapshot and uses native commands.

Environment:
  RHINO_PYTHON_PLUGIN_TEMPLATE_ROOT  Template checkout containing the shared extractor.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift 2
      ;;
    --configuration)
      CONFIGURATION="${2:-}"
      shift 2
      ;;
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
done

if [[ "$MODE" != "development" && "$MODE" != "production" ]]; then
  echo "Mode must be development or production." >&2
  exit 2
fi
if [[ "$OSTYPE" != darwin* ]]; then
  echo "This installer targets Rhino 8 for macOS." >&2
  exit 1
fi
if [[ ! -x "$RHINOCODE" ]]; then
  echo "RhinoCode CLI was not found: $RHINOCODE" >&2
  exit 1
fi
if [[ ! -f "$PROJECT_DATA_EXTRACTOR" ]]; then
  echo "Template project-data extractor was not found: $PROJECT_DATA_EXTRACTOR" >&2
  echo "Set RHINO_PYTHON_PLUGIN_TEMPLATE_ROOT to the template checkout." >&2
  exit 1
fi
if [[ -z "$CONFIGURATION" ]]; then
  CONFIGURATION=$([[ "$MODE" == development ]] && echo Debug || echo Release)
fi

PLUGIN_FILE="$GENERATED_ROOT/src/$PLUGIN_NAME/bin/$CONFIGURATION/net48/$PLUGIN_NAME.rhp"

rm -rf "$GENERATED_ROOT"
echo "Generating native Python commands from $RHINO_PROJECT..."
"$RHINOCODE" project build "$RHINO_PROJECT" \
  --buildpath "$REPO_ROOT/build" \
  --buildtarget '8.*'

dotnet run --project "$PROJECT_DATA_EXTRACTOR" -- \
  "$GENERATED_PLUGIN" \
  "$(dirname "$GENERATED_PROJECT")/Plugin.Data.resources"
uv run "$SCRIPT_DIR/prepare-tack-script-plugin.py"

echo "Building $PLUGIN_NAME ($CONFIGURATION)..."
dotnet build "$GENERATED_PROJECT" -c "$CONFIGURATION"
if [[ ! -f "$PLUGIN_FILE" ]]; then
  echo "Build succeeded, but the plug-in was not found: $PLUGIN_FILE" >&2
  exit 1
fi

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp "$PLUGIN_FILE" "$INSTALL_DIR/"

if [[ "$MODE" == development ]]; then
  printf '%s\n' "$REPO_ROOT" > "$INSTALL_DIR/development-python-root.txt"
else
  mkdir -p "$INSTALL_DIR/Python"
  cp -R "$REPO_ROOT/tack" "$INSTALL_DIR/Python/"
  find "$INSTALL_DIR/Python" -type d -name __pycache__ -prune -exec rm -rf {} +
  find "$INSTALL_DIR/Python" -type f -name '*.py[co]' -delete
fi

cat <<EOF
Installed Tack in $MODE mode:
  $INSTALL_DIR

Generated commands:
  TackAdd
  TackShow
  TackHide
  TackClear
  TackSettings

Restart Rhino to load this build or switch modes.
EOF
