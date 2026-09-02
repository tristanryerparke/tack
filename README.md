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
Rhino plugin. `csharp/TackScriptPlugin` adds the panel, per-user settings, and
startup restoration to that generated plugin. Interactive work runs through
Rhino 8's CPython 3 ScriptRunner command lifecycle.

Relationships are model data stored on their parent and child objects. Display
visibility is document-scoped runtime state; its default is stored in Rhino's
per-user plugin settings rather than document user text. Display conduits are
created per document and reject events from every other document.

## Install on macOS

```bash
scripts/install-tack-rhino-plugin-mac.sh
```

Restart Rhino after installation.

## Interactive development

```bash
uv run rhino-watch demos/analytic_plane_link.py --debug
```
