"""Persist Tack relationships on their parent and child Rhino objects."""

import json
import math
import uuid
from datetime import datetime, timezone

from tack import analytic_plane
from tack import link_graph
from tack import utils


LINKS_KEY = "Tack.Link"


def _plugin_data():
    from tack import plugin_data

    return plugin_data


def _document_state(display_enabled=None):
    payload = {}
    if isinstance(display_enabled, bool):
        payload["display_enabled"] = display_enabled
    return payload


def _stored_display_enabled(doc):
    value = _plugin_data().document_data(doc).get("display_enabled")
    return value if isinstance(value, bool) else None


def _write_document_state(doc, display_enabled=None):
    return bool(
        _plugin_data().set_document_data(
            doc,
            _document_state(display_enabled),
        )
    )


def _raw_links(obj):
    if obj is None or not obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY):
        return {}
    try:
        value = json.loads(str(obj.Attributes.UserDictionary[LINKS_KEY]))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def read_links(obj):
    """Return valid links whose saved endpoint IDs include ``obj``."""
    result = {}
    for link_id, link in _raw_links(obj).items():
        if not validate(link, expected_link_id=link_id):
            continue
        if not (
            utils.same_id(obj.Id, link["parent_id"])
            or utils.same_id(obj.Id, link["child_id"])
        ):
            continue
        result[str(link_id)] = link
    return result


def _set_links(doc, obj, links):
    if obj is None:
        return False
    has_saved_links = obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY)
    if not links and not has_saved_links:
        return True
    attributes = obj.Attributes.Duplicate()
    if links:
        attributes.UserDictionary.Set(
            LINKS_KEY,
            json.dumps(links, separators=(",", ":"), sort_keys=True),
        )
    else:
        attributes.UserDictionary.Remove(LINKS_KEY)
    return bool(doc.Objects.ModifyAttributes(obj.Id, attributes, True))


def _object_update(doc, updates, object_id):
    key = str(object_id).lower()
    if key not in updates:
        obj = utils.find_object(doc, object_id)
        if obj is None:
            return None
        updates[key] = [obj, read_links(obj)]
    return updates[key][1]


def _apply_updates(doc, updates, description):
    undo_record = doc.BeginUndoRecord(description)
    try:
        return all(
            _set_links(doc, obj, links)
            for obj, links in updates.values()
        )
    finally:
        if undo_record:
            doc.EndUndoRecord(undo_record)


def _object_index(doc):
    candidates = {}
    for obj in doc.Objects:
        if obj is None:
            continue
        for link_id, link in read_links(obj).items():
            candidate = candidates.setdefault(
                link_id,
                {"link": link, "owners": [], "conflict": False},
            )
            if candidate["link"] != link:
                candidate["conflict"] = True
            candidate["owners"].append(obj.Id)

    index = {}
    for link_id, candidate in candidates.items():
        link = candidate["link"]
        owners = candidate["owners"]
        if candidate["conflict"]:
            continue
        if not any(utils.same_id(owner, link["parent_id"]) for owner in owners):
            continue
        if not any(utils.same_id(owner, link["child_id"]) for owner in owners):
            continue
        index[link_id] = link
    return index


def display_enabled(doc, default_enabled=True):
    """Return this document's saved Tack visibility, or its initial default."""
    saved = _stored_display_enabled(doc)
    return bool(default_enabled) if saved is None else saved


def set_display_enabled(doc, enabled):
    """Persist this document's Tack visibility outside the relationship graph."""
    return _write_document_state(doc, bool(enabled))


def _valid_transform(data):
    return (
        isinstance(data, list)
        and len(data) == 16
        and all(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            for value in data
        )
    )


def link_mode(link):
    """Return a Tack mode, defaulting to attached."""
    return link.get("mode", "attached")


def translation_enabled(link):
    """Return whether a Tack inherits its parent's translation."""
    return link.get("translation", True)


def rotation_enabled(link):
    """Return whether a Tack inherits its parent's rotation."""
    return link.get("rotation", True)


def _valid_link_id(link_id):
    if not isinstance(link_id, str) or len(link_id) != 8:
        return False
    try:
        return "{:08x}".format(int(link_id, 16)) == link_id
    except ValueError:
        return False


def _new_link_id(index):
    while True:
        link_id = uuid.uuid4().hex[:8]
        if link_id not in index:
            return link_id


def validate(link, expected_link_id=None):
    required_fields = {
        "link_id",
        "parent_id",
        "child_id",
        "parent_plane",
        "child_plane",
        "inverted",
    }
    if not isinstance(link, dict):
        return False
    fields = set(link)
    allowed_fields = required_fields | {
        "created_at",
        "mode",
        "original_transform",
        "current_transform",
        "translation",
        "rotation",
    }
    if not required_fields.issubset(fields) or not fields.issubset(allowed_fields):
        return False
    link_id = link.get("link_id")
    created_at = link.get("created_at")
    if (
        not _valid_link_id(link_id)
        or (
            created_at is not None
            and (not isinstance(created_at, str) or not created_at.strip())
        )
        or (
            expected_link_id is not None
            and not utils.same_id(link_id, expected_link_id)
        )
        or not link.get("parent_id")
        or not link.get("child_id")
        or not isinstance(link.get("inverted"), bool)
    ):
        return False
    mode = link_mode(link)
    if mode not in ("attached", "inherit_only") or not all(
        isinstance(link.get(field, True), bool)
        for field in ("translation", "rotation")
    ):
        return False
    if mode == "inherit_only" and not (
        _valid_transform(link.get("original_transform"))
        and _valid_transform(link.get("current_transform"))
    ):
        return False
    return (
        analytic_plane.validate_definition(link["parent_plane"])
        and analytic_plane.validate_definition(link["child_plane"])
    )


def same_object_pair(left, right):
    return (
        utils.same_id(left["parent_id"], right["parent_id"])
        and utils.same_id(left["child_id"], right["child_id"])
    ) or (
        utils.same_id(left["parent_id"], right["child_id"])
        and utils.same_id(left["child_id"], right["parent_id"])
    )


def read_link(doc, link_id):
    return next(
        (
            link
            for saved_id, link in _object_index(doc).items()
            if utils.same_id(saved_id, link_id)
        ),
        None,
    )


def all_links(doc):
    """Return links with matching metadata on both live endpoint objects."""
    return list(_object_index(doc).values())


def save(doc, link):
    if not validate(link):
        return False
    parent = utils.find_object(doc, link["parent_id"])
    child = utils.find_object(doc, link["child_id"])
    if parent is None or child is None:
        return False

    index = _object_index(doc)
    replaced = [
        saved_link
        for saved_link in index.values()
        if utils.same_id(saved_link["link_id"], link["link_id"])
        or same_object_pair(saved_link, link)
    ]
    updates = {}
    for saved_link in replaced:
        for role in ("parent", "child"):
            links = _object_update(doc, updates, saved_link[role + "_id"])
            if links is None:
                return False
            links.pop(saved_link["link_id"], None)
    for role in ("parent", "child"):
        links = _object_update(doc, updates, link[role + "_id"])
        if links is None:
            return False
        links[link["link_id"]] = link
    return _apply_updates(doc, updates, "Tack links")


def remove_many(doc, link_ids):
    """Remove one or more relationships from both endpoint objects."""
    requested = tuple(link_ids)
    if not requested:
        return False
    removed = [
        link
        for saved_id, link in _object_index(doc).items()
        if any(utils.same_id(saved_id, link_id) for link_id in requested)
    ]
    if not removed:
        return False

    updates = {}
    for link in removed:
        for role in ("parent", "child"):
            links = _object_update(doc, updates, link[role + "_id"])
            if links is None:
                return False
            links.pop(link["link_id"], None)
    return _apply_updates(doc, updates, "Remove Tack links")


def remove(doc, link_id):
    return remove_many(doc, (link_id,))


def clear(doc):
    """Remove all Tack relationship metadata."""
    updates = {
        str(obj.Id).lower(): [obj, {}]
        for obj in doc.Objects
        if obj is not None and obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY)
    }
    if not updates:
        return True
    return _apply_updates(doc, updates, "Clear Tack links")


def create(
    doc,
    parent_id,
    child_id,
    parent_plane,
    child_plane,
    inverted,
    mode="attached",
    original_transform=None,
    current_transform=None,
    translation=True,
    rotation=True,
):
    index = _object_index(doc)
    replacing_pair = {
        "parent_id": str(parent_id),
        "child_id": str(child_id),
    }
    replacing = any(
        same_object_pair(saved_link, replacing_pair)
        for saved_link in index.values()
    )
    if not replacing and link_graph.would_create_cycle(
        index.values(),
        parent_id,
        child_id,
    ):
        return None
    link = {
        "link_id": _new_link_id(index),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_plane": parent_plane,
        "child_plane": child_plane,
        "inverted": bool(inverted),
        "mode": mode,
        "translation": bool(translation),
        "rotation": bool(rotation),
    }
    if mode == "inherit_only":
        link["original_transform"] = original_transform
        link["current_transform"] = current_transform
    return link if save(doc, link) else None
