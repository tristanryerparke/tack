"""JSON access to Tack's generic C# document and user-settings stores."""

import json

DEFAULT_DISPLAY_ENABLED = "default_display_enabled"
SHOW_SELECTED_TACKS_ONLY = "show_selected_tacks_only"
HIGHLIGHT_SELECTED_OBJECTS = "highlight_selected_objects"
DYNAMIC_PREVIEWS_ENABLED = "dynamic_previews_enabled"
ADD_TACK_TRANSLATION = "add_tack_translation"
ADD_TACK_ROTATION = "add_tack_rotation"
ADD_TACK_ATTACH = "add_tack_attach"
ADD_TACK_ALLOW_CHILD_MOVEMENT = "add_tack_allow_child_movement"
ADD_TACK_FLIP_CHILD_PLANE = "add_tack_flip_child_plane"
CROSSHAIR_SIZE = "crosshair_size"
CROSSHAIR_THICKNESS = "crosshair_thickness"


def _bridge():
    """Return Tack's C# bridge when running inside the plug-in."""
    try:
        from TackRhinoPlugin import PluginBridge
    except ImportError:
        return None
    return PluginBridge


def document_data(doc):
    """Return Tack's JSON-compatible document data, or an empty object."""
    bridge = _bridge()
    if bridge is None or doc is None:
        return {}
    try:
        value = json.loads(bridge.GetDocumentDataJson(doc.RuntimeSerialNumber))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def set_document_data(doc, value):
    """Persist a JSON-compatible object in Tack's document archive."""
    bridge = _bridge()
    if bridge is None or doc is None:
        return False
    return bridge.SetDocumentDataJson(
        doc.RuntimeSerialNumber,
        json.dumps(value, separators=(",", ":"), sort_keys=True),
    )


def settings():
    """Return Tack's JSON-compatible per-user settings."""
    bridge = _bridge()
    if bridge is None:
        return {}
    try:
        value = json.loads(bridge.GetSettingsJson())
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def set_settings(value):
    """Persist Tack's JSON-compatible per-user settings."""
    bridge = _bridge()
    if bridge is None:
        return False
    try:
        bridge.SetSettingsJson(json.dumps(value, separators=(",", ":"), sort_keys=True))
    except Exception:
        return False
    return True


def setting(name, default=None):
    return settings().get(name, default)


def set_setting(name, value):
    values = settings()
    values[name] = value
    return set_settings(values)
