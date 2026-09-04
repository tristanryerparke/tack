"""Persist Tack relationships in the Tack plug-in's private document data."""

import json
import uuid

from tack import analytic_plane
from tack import utils


# These names identify Tack's pre-plugin-data document-index format and are
# retained only to migrate existing .3dm files when first opened with the plug-in.
INDEX_SECTION = "Tack"
INDEX_ENTRY = "PlaneLinkIndex.v1"
INDEX_VERSION = 1
PLUGIN_INDEX_VERSION = 2


def _plugin_data():
    try:
        from RhinoCodePlatform.Rhino3D.Projects.Plugin import TackDocumentData
    except ImportError:
        return None
    return TackDocumentData


def _read_legacy_index(doc):
    try:
        payload = json.loads(str(doc.Strings.GetValue(INDEX_SECTION, INDEX_ENTRY)))
    except Exception:
        return {}
    return _validated_index(payload)


def _write_legacy_index(doc, index):
    try:
        doc.Strings.SetString(
            INDEX_SECTION,
            INDEX_ENTRY,
            json.dumps(
                {
                    "version": INDEX_VERSION,
                    "links": index,
                },
                sort_keys=True,
            ),
        )
        return True
    except Exception:
        return False


def _validated_index(payload):
    if not isinstance(payload, dict) or payload.get("version") != INDEX_VERSION:
        return {}
    entries = payload.get("links")
    if not isinstance(entries, dict):
        return {}
    return {
        str(link_id): link
        for link_id, link in entries.items()
        if validate(link, expected_link_id=link_id)
    }


def _compact_link(link):
    compact = dict(link)
    compact.pop("link_id", None)
    for role in ("parent", "child"):
        definition = dict(compact[role + "_plane"])
        definition.pop("object_id", None)
        compact[role + "_plane"] = definition
    return compact


def _inflate_link(link, expected_link_id=None):
    if not isinstance(link, dict) or expected_link_id is None:
        return None
    expanded = dict(link)
    saved_link_id = expanded.pop("link_id", None)
    if saved_link_id is not None and not utils.same_id(
        saved_link_id,
        expected_link_id,
    ):
        return None
    expanded["link_id"] = str(expected_link_id)
    for role in ("parent", "child"):
        definition = expanded.get(role + "_plane")
        if not isinstance(definition, dict) or "object_id" in definition:
            return None
        definition = dict(definition)
        definition["object_id"] = expanded.get(role + "_id")
        expanded[role + "_plane"] = definition
    return (
        expanded
        if validate(expanded, expected_link_id=expected_link_id)
        else None
    )


def _validated_plugin_index(payload):
    if not isinstance(payload, dict):
        return {}, False
    if payload.get("version") == INDEX_VERSION:
        return _validated_index(payload), True
    if payload.get("version") != PLUGIN_INDEX_VERSION:
        return {}, False
    entries = payload.get("links")
    if not isinstance(entries, dict):
        return {}, False

    index = {}
    needs_upgrade = False
    for link_id, saved_link in entries.items():
        link = _inflate_link(saved_link, expected_link_id=link_id)
        if link is None:
            continue
        index[str(link_id)] = link
        needs_upgrade = needs_upgrade or "link_id" in saved_link
    return index, needs_upgrade


def _plugin_payload(index, display_enabled=None):
    payload = {
        "version": PLUGIN_INDEX_VERSION,
        "links": {
            link_id: _compact_link(link)
            for link_id, link in index.items()
        },
    }
    if isinstance(display_enabled, bool):
        payload["display_enabled"] = display_enabled
    return json.dumps(payload, sort_keys=True)


def _read_index(doc):
    plugin_data = _plugin_data()
    if plugin_data is None:
        return _read_legacy_index(doc)

    if not plugin_data.HasDocumentData(doc.RuntimeSerialNumber):
        legacy_index = _read_legacy_index(doc)
        if legacy_index:
            if not plugin_data.ImportLinksJson(
                doc.RuntimeSerialNumber,
                _plugin_payload(legacy_index),
            ):
                return legacy_index
            _write_legacy_index(doc, {})
        else:
            return {}

    try:
        payload = json.loads(str(plugin_data.GetLinksJson(doc.RuntimeSerialNumber)))
    except Exception:
        return {}
    index, needs_upgrade = _validated_plugin_index(payload)
    if needs_upgrade:
        display_enabled = payload.get("display_enabled")
        plugin_data.ImportLinksJson(
            doc.RuntimeSerialNumber,
            _plugin_payload(
                index,
                display_enabled if isinstance(display_enabled, bool) else None,
            ),
        )
    return index


def _stored_display_enabled(doc):
    plugin_data = _plugin_data()
    if plugin_data is None or not plugin_data.HasDocumentData(
        doc.RuntimeSerialNumber
    ):
        return None
    try:
        payload = json.loads(str(plugin_data.GetLinksJson(doc.RuntimeSerialNumber)))
    except Exception:
        return None
    value = payload.get("display_enabled") if isinstance(payload, dict) else None
    return value if isinstance(value, bool) else None


def display_enabled(doc, default_enabled=True):
    """Return this document's saved Tack visibility, or its initial default."""
    saved = _stored_display_enabled(doc)
    return bool(default_enabled) if saved is None else saved


def _write_index(doc, index, display_enabled=None):
    plugin_data = _plugin_data()
    if plugin_data is None:
        return _write_legacy_index(doc, index)
    if display_enabled is None:
        display_enabled = _stored_display_enabled(doc)
    return bool(
        plugin_data.SetLinksJson(
            doc.RuntimeSerialNumber,
            _plugin_payload(index, display_enabled),
        )
    )


def set_display_enabled(doc, enabled):
    """Persist this document's Tack visibility with its relationship data."""
    return _write_index(doc, _read_index(doc), bool(enabled))


def validate(link, expected_link_id=None):
    if not isinstance(link, dict) or set(link) != {
        "version",
        "link_id",
        "parent_id",
        "child_id",
        "parent_plane",
        "child_plane",
        "inverted",
    }:
        return False
    link_id = str(link.get("link_id") or "")
    if (
        link.get("version") != 1
        or not link_id
        or (
            expected_link_id is not None
            and not utils.same_id(link_id, expected_link_id)
        )
        or not link.get("parent_id")
        or not link.get("child_id")
        or not isinstance(link.get("inverted"), bool)
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
            for saved_id, link in _read_index(doc).items()
            if utils.same_id(saved_id, link_id)
        ),
        None,
    )


def all_links(doc):
    """Read complete links from Tack's document-level relationship store."""
    links = []
    for link in _read_index(doc).values():
        parent = utils.find_object(doc, link["parent_id"])
        child = utils.find_object(doc, link["child_id"])
        if parent is not None and child is not None:
            links.append(link)
    return links


def save(doc, link):
    if not validate(link):
        return False
    parent = utils.find_object(doc, link["parent_id"])
    child = utils.find_object(doc, link["child_id"])
    if parent is None or child is None:
        return False

    index = _read_index(doc)
    for saved_link_id, saved_link in list(index.items()):
        if same_object_pair(saved_link, link):
            index.pop(saved_link_id)
    index[link["link_id"]] = link
    return _write_index(doc, index)


def clear(doc):
    """Clear every persisted Tack relationship in this document."""
    return _write_index(doc, {})


def create(doc, parent_id, child_id, parent_plane, child_plane, inverted):
    link = {
        "version": 1,
        "link_id": str(uuid.uuid4()),
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "parent_plane": parent_plane,
        "child_plane": child_plane,
        "inverted": bool(inverted),
    }
    return link if save(doc, link) else None
