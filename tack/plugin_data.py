"""Tack's JSON convenience wrapper around the generic C# document store."""

import json


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
    """Persist a JSON-compatible object with Rhino undo support."""
    bridge = _bridge()
    if bridge is None or doc is None:
        return False
    return bridge.SetDocumentDataJson(
        doc.RuntimeSerialNumber,
        json.dumps(value, separators=(",", ":"), sort_keys=True),
    )
