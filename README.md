# Tack

Tack links analytic planes on two Rhino objects. Moving or rotating the parent
updates the child, with a live constrained preview during native transforms.

## Rhino commands

- `TackAdd`
- `TackShow`
- `TackHide`
- `TackClear`

The same actions are available at the top of the per-document Tack dockable
panel.

## Architecture

The Script Editor project generates the native Python commands and combined
Rhino plug-in. `csharp/TackScriptPlugin` provides the stable panel host,
generic JSON document storage, and per-user settings. `tack/plugin_data.py`
owns Tack's document-data convenience wrapper and link schema.

In development, panel buttons run their `commands/*.py` entry files directly
from this checkout. In production, the same buttons invoke generated native
`Tack*` commands. Typed commands are generated native commands in both modes.

Relationships and display visibility are stored in Tack's plug-in-owned
document data. The default display visibility, crosshair size, and crosshair
line width are stored in per-user plug-in settings. Display conduits are
created per document and reject events from every other document.

## Install on macOS

```bash
scripts/install-tack-rhino-plugin-mac.sh --mode development
```

Development mode reads Python and panel command files from this checkout.
Production snapshots the `tack/` package into the plug-in bundle:

```bash
scripts/install-tack-rhino-plugin-mac.sh --mode production
```

Restart Rhino after installation or a mode change. In development, reload the
panel after editing `tack/panel.py`:

```bash
uv run in-rhino scripts/reload-panel.py
```

## Interactive development

```bash
uv run rhino-watch demos/analytic_plane_link.py --debug
```
