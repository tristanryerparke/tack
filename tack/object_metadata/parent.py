"""Persist full Tack Links on parent Rhino objects."""

import json

from tack.core.objects import same_id
from tack.links.schema import from_data

KEY = "Tack.Link"


def _raw_links(obj):
    if obj is None or not obj.Attributes.UserDictionary.ContainsKey(KEY):
        return {}
    try:
        value = json.loads(str(obj.Attributes.UserDictionary[KEY]))
    except Exception:  # noqa: BLE001 - malformed .NET user data is ignored
        return {}
    return value if isinstance(value, dict) else {}


def links(obj):
    """Return valid Links owned by ``obj``."""
    result = {}
    for link_id, data in _raw_links(obj).items():
        link = from_data(data, expected_link_id=link_id)
        if link is not None and same_id(obj.Id, link.parent_id):
            result[link.link_id] = link
    return result


def has_links(obj):
    return bool(obj is not None and obj.Attributes.UserDictionary.ContainsKey(KEY))


def set_links(attributes, links):
    if links:
        attributes.UserDictionary.Set(
            KEY,
            json.dumps(
                {link_id: link.to_data() for link_id, link in links.items()},
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
    else:
        attributes.UserDictionary.Remove(KEY)
