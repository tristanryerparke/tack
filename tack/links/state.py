"""Temporary per-document state for Links active in this Rhino session."""

from dataclasses import dataclass

import Rhino

from tack.anchors import analytic_plane
from tack.core import documents
from tack.core.objects import find_object, object_key

STATES_KEY = "Tack.LinkStates"
INVALID_STATES_KEY = "Tack.InvalidLinkStates"
INVALID_LINK_MAX_AGE = 200


@dataclass
class LinkState:
    """Runtime data derived from one persisted Link; never written to a file."""

    link_id: str
    parent_id: str
    child_id: str
    parent_plane: object
    child_plane: object
    parent_serial: int
    child_serial: int
    busy: bool = False


@dataclass
class InvalidLinkState:
    """A removed LinkState kept briefly so native Undo can restore it."""

    state: LinkState
    age: int = 0


def states(doc, create=True):
    if create:
        return documents.get_value(doc, STATES_KEY, lambda _: {})
    return documents.try_get_value(doc, STATES_KEY) or {}


def invalid_states(doc, create=True):
    if create:
        return documents.get_value(doc, INVALID_STATES_KEY, lambda _: {})
    return documents.try_get_value(doc, INVALID_STATES_KEY) or {}


def _tracked_object_ids(doc):
    return {
        object_key(object_id)
        for link_state in list(states(doc, create=False).values())
        + [entry.state for entry in invalid_states(doc, create=False).values()]
        for object_id in (link_state.parent_id, link_state.child_id)
    }


def set_state(doc, link_state):
    states(doc)[link_state.link_id] = link_state
    invalid_states(doc).pop(link_state.link_id, None)
    return link_state


def cache_state(doc, link_state, age=0):
    """Keep only runtime data for a missing Link, never its definition."""
    states(doc, create=False).pop(link_state.link_id, None)
    invalid_states(doc)[link_state.link_id] = InvalidLinkState(link_state, age)


def remove_state(doc, link_id):
    removed = states(doc, create=False).pop(link_id, None)
    invalid_states(doc, create=False).pop(link_id, None)
    return removed


def clear_states(doc):
    states(doc, create=False).clear()
    invalid_states(doc, create=False).clear()


def has_active_states():
    return documents.has_nonempty_value(STATES_KEY)


def has_tracked_states():
    return documents.has_matching_value(
        STATES_KEY,
        bool,
    ) or documents.has_matching_value(INVALID_STATES_KEY, bool)


def candidate_objects(doc):
    """Return only endpoints that have an active or cached Tack state."""
    objects = {}
    for object_id in _tracked_object_ids(doc):
        obj = find_object(doc, object_id)
        if obj is not None:
            objects[object_key(obj.Id)] = obj
    return objects


def keep_invalid_for_undo(doc):
    """Age missing states and discard only entries older than 200 commands."""
    invalid = invalid_states(doc, create=False)
    for link_id, entry in list(invalid.items()):
        entry.age += 1
        if entry.age >= INVALID_LINK_MAX_AGE:
            invalid.pop(link_id, None)


def object_serial(obj):
    return None if obj is None else int(obj.RuntimeSerialNumber)


def refresh_serials(doc, link_state):
    link_state.parent_serial = object_serial(find_object(doc, link_state.parent_id))
    link_state.child_serial = object_serial(find_object(doc, link_state.child_id))


def new_state(doc, link):
    parent = find_object(doc, link.parent_id)
    child = find_object(doc, link.child_id)
    if parent is None or child is None:
        return None
    parent_plane = analytic_plane.resolve_definition(doc, link.parent_plane_def)
    child_plane = analytic_plane.resolve_definition(doc, link.child_plane_def)
    if parent_plane is None or child_plane is None:
        return None
    return LinkState(
        link_id=link.link_id,
        parent_id=link.parent_id,
        child_id=link.child_id,
        parent_plane=Rhino.Geometry.Plane(parent_plane),
        child_plane=Rhino.Geometry.Plane(child_plane),
        parent_serial=object_serial(parent),
        child_serial=object_serial(child),
    )
