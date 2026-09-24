"""Temporary per-document state for Links active in this Rhino session."""

from collections import deque
from dataclasses import dataclass

import Rhino

from tack.anchors import analytic_plane
from tack.core import documents
from tack.core.objects import find_object, object_key

STATES_KEY = "Tack.LinkStates"
RECENT_OBJECTS_KEY = "Tack.RecentTackObjectIds"
RECENT_OBJECT_MAX_AGE = 200


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


def states(doc, create=True):
    if create:
        return documents.get_value(doc, STATES_KEY, lambda _: {})
    return documents.try_get_value(doc, STATES_KEY) or {}


def recent_object_ids(doc, create=True):
    """Return recently removed/broken Tack endpoint IDs and their ages."""
    if create:
        return documents.get_value(doc, RECENT_OBJECTS_KEY, lambda _: {})
    return documents.try_get_value(doc, RECENT_OBJECTS_KEY) or {}


def remember_object_ids(doc, *object_ids, reset=True):
    recent = recent_object_ids(doc)
    for object_id in object_ids:
        if object_id is None:
            continue
        key = object_key(object_id)
        if reset or key not in recent:
            recent[key] = 0


def remember_state(doc, link_state, reset=True):
    """Discard one LinkState but retain its endpoint IDs for native Undo."""
    states(doc, create=False).pop(link_state.link_id, None)
    remember_object_ids(
        doc,
        link_state.parent_id,
        link_state.child_id,
        reset=reset,
    )


def set_state(doc, link_state):
    states(doc)[link_state.link_id] = link_state
    return link_state


def clear_states(doc):
    states(doc, create=False).clear()
    recent_object_ids(doc, create=False).clear()


def has_active_states():
    return documents.has_nonempty_value(STATES_KEY)


def has_tracked_states():
    return documents.has_nonempty_value(STATES_KEY) or documents.has_nonempty_value(
        RECENT_OBJECTS_KEY
    )


def candidate_objects(doc):
    """Return active endpoints plus recently associated objects still present."""
    object_ids = set(recent_object_ids(doc, create=False))
    for link_state in states(doc, create=False).values():
        object_ids.update(
            (object_key(link_state.parent_id), object_key(link_state.child_id))
        )
    objects = {}
    for object_id in object_ids:
        obj = find_object(doc, object_id)
        if obj is not None:
            objects[object_key(obj.Id)] = obj
    return objects


def age_recent_object_ids(doc):
    """Forget stale endpoint IDs after 200 EndCommand reconciliations."""
    recent = recent_object_ids(doc, create=False)
    for object_id, age in list(recent.items()):
        age += 1
        if age >= RECENT_OBJECT_MAX_AGE:
            recent.pop(object_id, None)
        else:
            recent[object_id] = age


def ordered_states(link_states):
    """Return parent-to-child LinkStates in stable topological order."""
    items = list(
        link_states.values() if hasattr(link_states, "values") else link_states
    )
    children = {}
    indegree = {}
    node_order = []
    for link_state in items:
        parent_id = object_key(link_state.parent_id)
        child_id = object_key(link_state.child_id)
        for object_id in (parent_id, child_id):
            if object_id not in indegree:
                indegree[object_id] = 0
                node_order.append(object_id)
        children.setdefault(parent_id, []).append(link_state)
        indegree[child_id] += 1

    pending = deque(object_id for object_id in node_order if indegree[object_id] == 0)
    ordered = []
    emitted = set()
    while pending:
        parent_id = pending.popleft()
        for link_state in children.get(parent_id, ()):
            if link_state.link_id in emitted:
                continue
            emitted.add(link_state.link_id)
            ordered.append(link_state)
            child_id = object_key(link_state.child_id)
            indegree[child_id] -= 1
            if indegree[child_id] == 0:
                pending.append(child_id)

    ordered.extend(item for item in items if item.link_id not in emitted)
    return ordered


def object_serial(obj):
    return None if obj is None else int(obj.RuntimeSerialNumber)


def refresh_serials(doc, link_state):
    link_state.parent_serial = object_serial(find_object(doc, link_state.parent_id))
    link_state.child_serial = object_serial(find_object(doc, link_state.child_id))


def changed(doc, link_state):
    if link_state.busy:
        return False
    return (
        object_serial(find_object(doc, link_state.parent_id))
        != link_state.parent_serial
        or object_serial(find_object(doc, link_state.child_id))
        != link_state.child_serial
    )


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
