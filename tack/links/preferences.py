"""Persist per-document and per-user Tack display preferences."""

from tack.core import plugin_data


def _document_state(display_enabled=None):
    payload = {}
    if isinstance(display_enabled, bool):
        payload["display_enabled"] = display_enabled
    return payload


def display_enabled(doc, default_enabled=True):
    """Return this document's saved Tack visibility, or its initial default."""
    value = plugin_data.document_data(doc).get("display_enabled")
    return bool(default_enabled) if not isinstance(value, bool) else value


def set_display_enabled(doc, enabled):
    """Persist this document's Tack visibility outside the relationship graph."""
    return bool(
        plugin_data.set_document_data(
            doc,
            _document_state(bool(enabled)),
        )
    )
