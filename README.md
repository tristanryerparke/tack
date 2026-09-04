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

The Script Editor project generates the four Python commands and the combined
Rhino plugin. `csharp/TackScriptPlugin` hosts the per-document panel, stores
per-user settings, and restores saved links. `tack/panel.py` owns the panel's
Eto control tree; its buttons dispatch the generated Python commands through
the ScriptRunner lifecycle.

Relationships and display visibility are stored in Tack's plug-in-owned
document data. The default display visibility, crosshair size, and
crosshair line width are stored in per-user plug-in settings. Display conduits
are created per document and
reject events from every other document.

## Install on macOS

```bash
scripts/install-tack-rhino-plugin-mac.sh
```

Restart Rhino after installation.

## Interactive development

```bash
uv run rhino-watch demos/analytic_plane_link.py --debug
```
