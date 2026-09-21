"""Read and write Tack metadata on Rhino object attributes."""

import json

from tack.core.objects import find_object, same_id
from tack.links.schema import valid_link_id, validate

LINKS_KEY = "Tack.Link"
LINK_REFS_KEY = "Tack.LinkRef"


def _raw_links(obj):
    if obj is None or not obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY):
        return {}
    try:
        value = json.loads(str(obj.Attributes.UserDictionary[LINKS_KEY]))
    except Exception:  # noqa: BLE001 - malformed .NET user data is ignored
        return {}
    return value if isinstance(value, dict) else {}


def _raw_link_refs(obj):
    if obj is None or not obj.Attributes.UserDictionary.ContainsKey(LINK_REFS_KEY):
        return []
    try:
        value = json.loads(str(obj.Attributes.UserDictionary[LINK_REFS_KEY]))
    except Exception:  # noqa: BLE001 - malformed .NET user data is ignored
        return []
    return value if isinstance(value, list) else []


def read_links(obj):
    """Return valid full links whose saved endpoint IDs include ``obj``."""
    result = {}
    for link_id, link in _raw_links(obj).items():
        if not validate(link, expected_link_id=link_id):
            continue
        if not (
            same_id(obj.Id, link["parent_id"]) or same_id(obj.Id, link["child_id"])
        ):
            continue
        result[str(link_id)] = link
    return result


def read_parent_links(obj):
    """Return full links owned by their parent object."""
    return {
        link_id: link
        for link_id, link in read_links(obj).items()
        if same_id(obj.Id, link["parent_id"])
    }


def read_link_refs(obj):
    """Return child-side link IDs, including the legacy full-link format."""
    refs = {str(link_id) for link_id in _raw_link_refs(obj) if valid_link_id(link_id)}
    refs.update(
        link_id
        for link_id, link in read_links(obj).items()
        if same_id(obj.Id, link["child_id"])
    )
    return refs


def has_metadata(obj):
    return bool(
        obj is not None
        and (
            obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY)
            or obj.Attributes.UserDictionary.ContainsKey(LINK_REFS_KEY)
        )
    )


def _set_object_metadata(doc, obj, parent_links, child_refs):
    if obj is None:
        return False
    has_parent_links = obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY)
    has_child_refs = obj.Attributes.UserDictionary.ContainsKey(LINK_REFS_KEY)
    if (
        not parent_links
        and not child_refs
        and not has_parent_links
        and not has_child_refs
    ):
        return True

    attributes = obj.Attributes.Duplicate()
    if parent_links:
        attributes.UserDictionary.Set(
            LINKS_KEY,
            json.dumps(parent_links, separators=(",", ":"), sort_keys=True),
        )
    else:
        attributes.UserDictionary.Remove(LINKS_KEY)
    if child_refs:
        attributes.UserDictionary.Set(
            LINK_REFS_KEY,
            json.dumps(sorted(child_refs), separators=(",", ":")),
        )
    else:
        attributes.UserDictionary.Remove(LINK_REFS_KEY)
    return bool(doc.Objects.ModifyAttributes(obj.Id, attributes, True))


def object_update(doc, updates, object_id):
    key = object_key(object_id)
    if key not in updates:
        obj = find_object(doc, object_id)
        if obj is None:
            return None
        updates[key] = [obj, read_parent_links(obj), read_link_refs(obj)]
    return updates[key]


def apply_updates(doc, updates, description):
    undo_record = doc.BeginUndoRecord(description)
    try:
        return all(
            _set_object_metadata(doc, obj, parent_links, child_refs)
            for obj, parent_links, child_refs in updates.values()
        )
    finally:
        if undo_record:
            doc.EndUndoRecord(undo_record)


def object_key(object_id):
    return str(object_id).lower()
