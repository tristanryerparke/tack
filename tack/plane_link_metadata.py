"""Persist Tack relationships in the Tack plug-in's private document data."""

import json
import uuid

from tack import analytic_plane
from tack import utils


# These names identify Tack's pre-plugin-data format and are retained only to
# migrate existing .3dm files when they are first opened with the plug-in.
LINKS_KEY = "Tack.PlaneLinks.v1"
INDEX_SECTION = "Tack"
INDEX_ENTRY = "PlaneLinkIndex.v1"
INDEX_VERSION = 1


def _plugin_data():
    try:
        from RhinoCodePlatform.Rhino3D.Projects.Plugin import TackDocumentData
    except ImportError:
        return None
    return TackDocumentData


def _set_legacy_links(doc, obj, links):
    if obj is None:
        return False
    attributes = obj.Attributes.Duplicate()
    if links:
        attributes.UserDictionary.Set(
            LINKS_KEY,
            json.dumps(links, sort_keys=True),
        )
    elif attributes.UserDictionary.ContainsKey(LINKS_KEY):
        attributes.UserDictionary.Remove(LINKS_KEY)
    return doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def _raw_legacy_links(obj):
    if (
        obj is None
        or not obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY)
    ):
        return {}
    try:
        data = json.loads(str(obj.Attributes.UserDictionary[LINKS_KEY]))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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


def _plugin_payload(index):
    return json.dumps(
        {"version": INDEX_VERSION, "links": index},
        sort_keys=True,
    )


def _clear_legacy(doc, index):
    links_by_object = {}
    for link_id, link in index.items():
        for object_id in (link["parent_id"], link["child_id"]):
            links_by_object.setdefault(object_id, set()).add(link_id)

    success = True
    for object_id, link_ids in links_by_object.items():
        obj = utils.find_object(doc, object_id)
        if obj is None:
            continue
        remaining = {
            link_id: link
            for link_id, link in read_links(obj).items()
            if link_id not in link_ids
        }
        success = _set_legacy_links(doc, obj, remaining) and success
    return _write_legacy_index(doc, {}) and success


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
            _clear_legacy(doc, legacy_index)
        else:
            return {}

    try:
        payload = json.loads(str(plugin_data.GetLinksJson(doc.RuntimeSerialNumber)))
    except Exception:
        return {}
    return _validated_index(payload)


def _write_index(doc, index):
    plugin_data = _plugin_data()
    if plugin_data is None:
        return _write_legacy_index(doc, index)
    return bool(
        plugin_data.SetLinksJson(
            doc.RuntimeSerialNumber,
            _plugin_payload(index),
        )
    )


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


def read_links(obj):
    """Read legacy per-object records during migration or standalone Python use."""
    result = {}
    for link_id, link in _raw_legacy_links(obj).items():
        if validate(link, expected_link_id=link_id):
            result[str(link_id)] = link
    return result


def read_link(doc, link_id):
    if not hasattr(doc, "Strings") and _plugin_data() is None:
        return next(
            (
                link
                for saved_id, link in read_links(doc).items()
                if utils.same_id(saved_id, link_id)
            ),
            None,
        )
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
    index[link["link_id"]] = link
    return _write_index(doc, index)


def clear(doc):
    """Clear every persisted Tack relationship in this document."""
    index = _read_index(doc)
    success = _write_index(doc, {})
    if _plugin_data() is not None:
        success = _clear_legacy(doc, _read_legacy_index(doc)) and success
        return success

    return _clear_legacy(doc, index) and success


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
