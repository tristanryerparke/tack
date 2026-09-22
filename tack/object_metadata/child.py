"""Persist Tack IDs on child Rhino objects."""

import json

from tack.links.schema import valid_link_id

KEY = "Tack.LinkRef"


def _raw_link_ids(obj):
    if obj is None or not obj.Attributes.UserDictionary.ContainsKey(KEY):
        return []
    try:
        value = json.loads(str(obj.Attributes.UserDictionary[KEY]))
    except Exception:  # noqa: BLE001 - malformed .NET user data is ignored
        return []
    return value if isinstance(value, list) else []


def link_ids(obj):
    """Return valid Tack IDs owned by ``obj``."""
    return {str(link_id) for link_id in _raw_link_ids(obj) if valid_link_id(link_id)}


def has_link_ids(obj):
    return bool(obj is not None and obj.Attributes.UserDictionary.ContainsKey(KEY))


def set_link_ids(attributes, link_ids):
    if link_ids:
        attributes.UserDictionary.Set(
            KEY,
            json.dumps(sorted(link_ids), separators=(",", ":")),
        )
    else:
        attributes.UserDictionary.Remove(KEY)
