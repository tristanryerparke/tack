"""Per-document runtime state for active Tack relationships."""

import Rhino

from tack.anchors import analytic_plane
from tack.core import documents
from tack.core.objects import find_object

STATES_KEY = "Tack.Link.States"


def states(doc, create=True):
    if create:
        return documents.get_value(doc, STATES_KEY, lambda _: {})
    return documents.try_get_value(doc, STATES_KEY) or {}


def object_serial(obj):
    return None if obj is None else int(obj.RuntimeSerialNumber)


def refresh_serials(doc, link_state):
    for role in ("parent", "child"):
        link_state[role + "_runtime_serial"] = object_serial(
            find_object(doc, link_state[role + "_id"])
        )


def new_state(doc, link):
    parent = find_object(doc, link["parent_id"])
    child = find_object(doc, link["child_id"])
    if parent is None or child is None:
        return None
    parent_plane = analytic_plane.resolve_definition(doc, link["parent_plane"])
    child_plane = analytic_plane.resolve_definition(doc, link["child_plane"])
    if parent_plane is None or child_plane is None:
        return None
    link_state = {
        "link_id": link["link_id"],
        "parent_id": link["parent_id"],
        "child_id": link["child_id"],
        "link": link,
        "plane": Rhino.Geometry.Plane(parent_plane),
        "child_plane": Rhino.Geometry.Plane(child_plane),
        "broken": False,
        "busy": False,
        "dynamic_preview_active": False,
    }
    refresh_serials(doc, link_state)
    return link_state
