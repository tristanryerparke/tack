"""Versioned metadata for parent/child analytic-plane relationships."""

import json
import uuid

from tack import three_point_plane_metadata
from tack import utils


LINKS_KEY = "Tack.AnalyticPlaneLinks.v1"


def _set_links(doc, obj, links):
    if obj is None:
        return False
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Set(LINKS_KEY, json.dumps(links, sort_keys=True))
    return doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def _raw_links(obj):
    if obj is None:
        return {}
    try:
        data = json.loads(str(obj.Attributes.UserDictionary[LINKS_KEY]))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


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
        three_point_plane_metadata.validate_definition(link["parent_plane"])
        and three_point_plane_metadata.validate_definition(link["child_plane"])
    )


def read_links(obj):
    result = {}
    for link_id, link in _raw_links(obj).items():
        if validate(link, expected_link_id=link_id):
            result[str(link_id)] = link
    return result


def read_link(obj, link_id):
    return next(
        (
            link
            for saved_id, link in read_links(obj).items()
            if utils.same_id(saved_id, link_id)
        ),
        None,
    )


def all_links(doc):
    """Return one canonical copy of every saved relationship in ``doc``."""
    links = {}
    for obj in doc.Objects:
        if obj is None:
            continue
        for link_id, link in read_links(obj).items():
            if utils.same_id(obj.Id, link["child_id"]):
                links[link_id] = link
            elif link_id not in links:
                links[link_id] = link
    return list(links.values())


def save(doc, link):
    if not validate(link):
        return False
    parent = utils.find_object(doc, link["parent_id"])
    child = utils.find_object(doc, link["child_id"])
    if parent is None or child is None:
        return False

    parent_links = read_links(parent)
    child_links = read_links(child)
    parent_links[link["link_id"]] = link
    child_links[link["link_id"]] = link
    return _set_links(doc, parent, parent_links) and _set_links(
        doc,
        child,
        child_links,
    )


def clear(doc):
    """Remove every analytic-plane relationship payload in one document."""
    success = True
    for obj in list(doc.Objects):
        if obj is None or not obj.Attributes.UserDictionary.ContainsKey(LINKS_KEY):
            continue
        attributes = obj.Attributes.Duplicate()
        attributes.UserDictionary.Remove(LINKS_KEY)
        success = doc.Objects.ModifyAttributes(obj.Id, attributes, True) and success
    return success


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
