"""Read and write persisted Links on their endpoint object metadata."""

from dataclasses import replace
from datetime import datetime, timezone

from tack.core.objects import find_object, object_key, same_id
from tack.links import graph, schema, transforms
from tack.links.schema import Link
from tack.object_metadata import child, parent


def _object_update(doc, updates, object_id):
    key = object_key(object_id)
    if key not in updates:
        obj = find_object(doc, object_id)
        if obj is None:
            return None
        updates[key] = [obj, parent.links(obj), child.link_ids(obj)]
    return updates[key]


def _set_object_metadata(doc, obj, parent_links, child_link_ids):
    if obj is None:
        return False
    if (
        not parent_links
        and not child_link_ids
        and not parent.has_links(obj)
        and not child.has_link_ids(obj)
    ):
        return True

    attributes = obj.Attributes.Duplicate()
    parent.set_links(attributes, parent_links)
    child.set_link_ids(attributes, child_link_ids)
    return bool(doc.Objects.ModifyAttributes(obj.Id, attributes, True))


def _apply_updates(doc, updates, description):
    undo_record = doc.BeginUndoRecord(description)
    try:
        return all(
            _set_object_metadata(doc, obj, parent_links, child_link_ids)
            for obj, parent_links, child_link_ids in updates.values()
        )
    finally:
        if undo_record:
            doc.EndUndoRecord(undo_record)


def observed_metadata(objects):
    """Read parent Links and child references from a selected object set."""
    parents = {}
    conflicts = set()
    child_owners = {}
    for obj in objects:
        if obj is None or obj.IsDeleted:
            continue
        for link_id, link in parent.links(obj).items():
            previous = parents.get(link_id)
            if previous is not None and previous != link:
                conflicts.add(link_id)
            else:
                parents[link_id] = link
        for link_id in child.link_ids(obj):
            child_owners.setdefault(link_id, set()).add(object_key(obj.Id))
    for link_id in conflicts:
        parents.pop(link_id, None)
    return parents, child_owners


def active_observed_links(parents, child_owners, include_invalid=False):
    """Return Links whose parent record and child reference agree."""
    return {
        link_id: link
        for link_id, link in parents.items()
        if (include_invalid or link.valid)
        and object_key(link.child_id) in child_owners.get(link_id, ())
    }


def _stored_links(doc):
    """Return every well-formed Link stored by a present parent object."""
    return observed_metadata(doc.Objects)[0]


def _child_owners(doc):
    return observed_metadata(doc.Objects)[1]


def _is_active(doc, link, child_owners=None):
    owners = _child_owners(doc) if child_owners is None else child_owners
    return object_key(link.child_id) in owners.get(link.link_id, ())


def all_links(doc, include_invalid=False):
    """Return Links with both endpoint metadata entries currently present."""
    parents, children = observed_metadata(doc.Objects)
    return list(active_observed_links(parents, children, include_invalid).values())


def read_link(doc, link_id, parent_id=None, include_invalid=False):
    """Read one active Link directly from its parent object metadata."""
    if parent_id is not None:
        owner = find_object(doc, parent_id)
        link = None if owner is None else parent.links(owner).get(str(link_id))
        if link is not None and (include_invalid or link.valid) and _is_active(doc, link):
            return link
        return None
    return next(
        (
            link
            for link in all_links(doc, include_invalid=include_invalid)
            if same_id(link.link_id, link_id)
        ),
        None,
    )


def _stored_link(doc, link_id):
    return next(
        (
            link
            for saved_id, link in _stored_links(doc).items()
            if same_id(saved_id, link_id)
        ),
        None,
    )


def save(doc, link, replaced=None):
    """Write a Link and its child reference in one undoable metadata update.

    Callers updating a known Link pass it in ``replaced`` so command-end
    maintenance does not rescan the document.
    """
    if not isinstance(link, Link) or not schema.validate(link):
        return False
    if find_object(doc, link.parent_id) is None or find_object(doc, link.child_id) is None:
        return False

    if replaced is None:
        replaced = [
            saved_link
            for saved_link in _stored_links(doc).values()
            if saved_link.link_id == link.link_id or schema.same_object_pair(saved_link, link)
        ]
    updates = {}
    for saved_link in replaced:
        parent_update = _object_update(doc, updates, saved_link.parent_id)
        child_update = _object_update(doc, updates, saved_link.child_id)
        if parent_update is None or child_update is None:
            return False
        parent_update[1].pop(saved_link.link_id, None)
        child_update[2].discard(saved_link.link_id)

    parent_update = _object_update(doc, updates, link.parent_id)
    child_update = _object_update(doc, updates, link.child_id)
    if parent_update is None or child_update is None:
        return False
    parent_update[1][link.link_id] = link
    child_update[2].add(link.link_id)
    return _apply_updates(doc, updates, "Tack links")


def set_valid(doc, link_id, valid, parent_id=None):
    """Persist a Link's resolution status without retaining an in-memory copy."""
    if parent_id is None:
        link = _stored_link(doc, link_id)
    else:
        parent_object = find_object(doc, parent_id)
        link = None if parent_object is None else parent.links(parent_object).get(link_id)
    if link is None or link.valid == bool(valid):
        return link is not None
    return save(doc, replace(link, valid=bool(valid)), replaced=(link,))


def remove_many(doc, link_ids):
    """Remove one or more Links from whichever endpoint metadata remains."""
    requested = tuple(link_ids)
    if not requested:
        return False
    removed = [
        link
        for saved_id, link in _stored_links(doc).items()
        if any(same_id(saved_id, link_id) for link_id in requested)
    ]
    if not removed:
        return False

    updates = {}
    for link in removed:
        parent_update = _object_update(doc, updates, link.parent_id)
        if parent_update is None:
            return False
        parent_update[1].pop(link.link_id, None)
        child_update = _object_update(doc, updates, link.child_id)
        if child_update is not None:
            child_update[2].discard(link.link_id)
    return _apply_updates(doc, updates, "Remove Tack links")


def remove(doc, link_id):
    return remove_many(doc, (link_id,))


def clear(doc):
    """Strip every Tack metadata entry from this document."""
    updates = {}
    for obj in doc.Objects:
        if obj is not None and (parent.has_links(obj) or child.has_link_ids(obj)):
            updates[object_key(obj.Id)] = [obj, {}, set()]
    return not updates or _apply_updates(doc, updates, "Clear Tack links")


def _replacement_links(doc, parent_id, child_id):
    """Read only the two prospective endpoint parents for replacement metadata."""
    replacing_pair = {"parent_id": str(parent_id), "child_id": str(child_id)}
    result = {}
    for object_id in (parent_id, child_id):
        obj = find_object(doc, object_id)
        if obj is None:
            continue
        for link in parent.links(obj).values():
            if schema.same_object_pair(link, replacing_pair):
                result[link.link_id] = link
    return tuple(result.values())


def _active_pairs(doc):
    """Use LinkState identities for graph checks; Link definitions stay on objects."""
    from tack.links import state

    return [
        {"parent_id": link_state.parent_id, "child_id": link_state.child_id}
        for link_state in state.states(doc, create=False).values()
    ]


def would_create_cycle(doc, parent_id, child_id):
    return not _replacement_links(doc, parent_id, child_id) and graph.would_create_cycle(
        _active_pairs(doc),
        parent_id,
        child_id,
    )


def create(
    doc,
    parent_id,
    child_id,
    parent_plane,
    child_plane,
    translation=True,
    rotation=True,
    allow_child_movement=False,
    relationship_transform=None,
):
    """Persist a Tack's current or explicitly supplied plane relationship."""
    replaced = _replacement_links(doc, parent_id, child_id)
    if not replaced and graph.would_create_cycle(_active_pairs(doc), parent_id, child_id):
        return None
    from tack.anchors import analytic_plane
    from tack.links import state

    resolved_parent = analytic_plane.resolve_definition(doc, parent_plane)
    resolved_child = analytic_plane.resolve_definition(doc, child_plane)
    if resolved_parent is None or resolved_child is None:
        return None
    if relationship_transform is None:
        relationship_transform = transforms.inherit_transform_data(
            resolved_parent,
            resolved_child,
        )
    elif not schema.valid_transform(relationship_transform):
        return None
    original_transform = list(relationship_transform)
    known_ids = {
        *_stored_links(doc),
        *state.states(doc, create=False),
        *(link.link_id for link in replaced),
    }
    link = Link(
        link_id=schema.new_link_id({link_id: None for link_id in known_ids}),
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        parent_id=str(parent_id),
        child_id=str(child_id),
        parent_plane_def=parent_plane,
        child_plane_def=child_plane,
        translation=bool(translation),
        rotation=bool(rotation),
        allow_child_movement=bool(allow_child_movement),
        original_transform=original_transform,
        current_transform=list(original_transform),
    )
    return link if save(doc, link, replaced=replaced) else None
