"""High-level persistence operations for Tack relationships."""

from datetime import datetime, timezone

from tack.core.objects import find_object, same_id
from tack.links import graph, index, object_store, schema


def read_link(doc, link_id):
    return next(
        (
            link
            for saved_id, link in index.valid_links(doc).items()
            if same_id(saved_id, link_id)
        ),
        None,
    )


def all_links(doc):
    """Return cached links with matching live parent data and child references."""
    return list(index.valid_links(doc).values())


def reconcile_links(doc):
    """Refresh the index and age links that remain incomplete."""
    return list(index.refresh(doc, advance_invalid_age=True)["valid"].values())


def save(doc, link):
    if not schema.validate(link):
        return False
    parent = find_object(doc, link["parent_id"])
    child = find_object(doc, link["child_id"])
    if parent is None or child is None:
        return False

    valid = index.valid_links(doc)
    replaced = [
        saved_link
        for saved_link in valid.values()
        if same_id(saved_link["link_id"], link["link_id"])
        or schema.same_object_pair(saved_link, link)
    ]
    updates = {}
    for saved_link in replaced:
        parent_update = object_store.object_update(
            doc,
            updates,
            saved_link["parent_id"],
        )
        child_update = object_store.object_update(
            doc,
            updates,
            saved_link["child_id"],
        )
        if parent_update is None or child_update is None:
            return False
        parent_update[1].pop(saved_link["link_id"], None)
        child_update[2].discard(saved_link["link_id"])

    parent_update = object_store.object_update(doc, updates, link["parent_id"])
    child_update = object_store.object_update(doc, updates, link["child_id"])
    if parent_update is None or child_update is None:
        return False
    parent_update[1][link["link_id"]] = link
    child_update[2].add(link["link_id"])

    if not object_store.apply_updates(doc, updates, "Tack links"):
        return False
    index.remember_invalid(
        doc,
        [
            saved_link
            for saved_link in replaced
            if not same_id(saved_link["link_id"], link["link_id"])
        ],
    )
    index.remember_valid(doc, link)
    return True


def remove_many(doc, link_ids):
    """Remove one or more relationships from their endpoint objects."""
    requested = tuple(link_ids)
    if not requested:
        return False
    removed = [
        link
        for saved_id, link in index.valid_links(doc).items()
        if any(same_id(saved_id, link_id) for link_id in requested)
    ]
    if not removed:
        return False

    updates = {}
    for link in removed:
        parent_update = object_store.object_update(doc, updates, link["parent_id"])
        child_update = object_store.object_update(doc, updates, link["child_id"])
        if parent_update is None or child_update is None:
            return False
        parent_update[1].pop(link["link_id"], None)
        child_update[2].discard(link["link_id"])
    if not object_store.apply_updates(doc, updates, "Remove Tack links"):
        return False
    index.remember_invalid(doc, removed)
    return True


def remove(doc, link_id):
    return remove_many(doc, (link_id,))


def clear(doc):
    """Strip every Tack metadata entry from this document."""
    saved_index = index.runtime_index(doc)
    removed = list(saved_index["valid"].values())
    updates = {}
    for obj in doc.Objects:
        if obj is not None and object_store.has_metadata(obj):
            updates[object_store.object_key(obj.Id)] = [obj, {}, set()]
    if updates and not object_store.apply_updates(doc, updates, "Clear Tack links"):
        return False
    index.remember_invalid(doc, removed)
    for link_id in list(saved_index["invalid"]):
        if link_id not in saved_index["valid"]:
            saved_index["invalid"].pop(link_id, None)
    saved_index["object_ids"] = {
        object_store.object_key(link[role + "_id"])
        for link in list(saved_index["valid"].values())
        + [entry["link"] for entry in saved_index["invalid"].values()]
        for role in ("parent", "child")
    }
    return True


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
    valid = index.valid_links(doc)
    replacing_pair = {
        "parent_id": str(parent_id),
        "child_id": str(child_id),
    }
    replacing = any(
        schema.same_object_pair(saved_link, replacing_pair)
        for saved_link in valid.values()
    )
    if not replacing and graph.would_create_cycle(
        valid.values(),
        parent_id,
        child_id,
    ):
        return None
    link = {
        "link_id": schema.new_link_id(valid),
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
