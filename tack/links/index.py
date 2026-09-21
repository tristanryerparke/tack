"""Per-document runtime index for active and recently invalid Tacks."""

import Rhino
import System

from tack.core import documents
from tack.core.objects import find_object
from tack.links import object_store

INDEX_KEY = "Tack.Link.MetadataIndex"
INVALID_TACK_MAX_AGE = 200


def _next_runtime_serial():
    return int(Rhino.DocObjects.RhinoObject.NextRuntimeSerialNumber)


def _scan_objects(objects):
    parents = {}
    parent_conflicts = set()
    child_owners = {}

    for obj in objects:
        if obj is None or obj.IsDeleted:
            continue

        for link_id, link in object_store.read_parent_links(obj).items():
            saved = parents.get(link_id)
            if saved is not None and saved != link:
                parent_conflicts.add(link_id)
            else:
                parents[link_id] = link

        for link_id in object_store.read_link_refs(obj):
            child_owners.setdefault(link_id, set()).add(object_store.object_key(obj.Id))

    for link_id in parent_conflicts:
        parents.pop(link_id, None)
    return parents, child_owners


def _valid_observed_links(parents, child_owners):
    return {
        link_id: link
        for link_id, link in parents.items()
        if object_store.object_key(link["child_id"]) in child_owners.get(link_id, ())
    }


def _initialize(doc):
    parents, child_owners = _scan_objects(doc.Objects)
    valid = _valid_observed_links(parents, child_owners)
    return {
        "valid": valid,
        "invalid": {},
        "culled": set(),
        "object_ids": {
            object_store.object_key(link[role + "_id"])
            for link in valid.values()
            for role in ("parent", "child")
        },
        "next_runtime_serial": _next_runtime_serial(),
    }


def runtime_index(doc):
    return documents.get_value(doc, INDEX_KEY, _initialize)


def _find_runtime_object(doc, serial):
    obj = doc.Objects.Find(System.UInt32(serial))
    return None if obj is None or obj.IsDeleted else obj


def _candidate_objects(doc, saved_index):
    objects = {}
    for object_id in saved_index["object_ids"]:
        obj = find_object(doc, object_id)
        if obj is not None:
            objects[object_store.object_key(obj.Id)] = obj

    previous_serial = saved_index["next_runtime_serial"]
    current_serial = _next_runtime_serial()
    if current_serial >= previous_serial:
        for serial in range(previous_serial, current_serial):
            obj = _find_runtime_object(doc, serial)
            if obj is not None:
                objects[object_store.object_key(obj.Id)] = obj
    saved_index["next_runtime_serial"] = current_serial
    return objects


def refresh(doc, advance_invalid_age=False):
    saved_index = runtime_index(doc)
    objects = _candidate_objects(doc, saved_index)
    parents, child_owners = _scan_objects(objects.values())

    for link in parents.values():
        for role in ("parent", "child"):
            obj = find_object(doc, link[role + "_id"])
            if obj is not None:
                objects[object_store.object_key(obj.Id)] = obj
    parents, child_owners = _scan_objects(objects.values())

    previous_links = dict(saved_index["valid"])
    previous_links.update(
        {link_id: entry["link"] for link_id, entry in saved_index["invalid"].items()}
    )
    candidate_links = dict(previous_links)
    candidate_links.update(parents)

    observed_valid = _valid_observed_links(parents, child_owners)
    valid = {}
    invalid = {}
    culled = saved_index["culled"]
    for link_id, previous_link in candidate_links.items():
        if link_id in culled:
            continue
        current_link = observed_valid.get(link_id)
        if current_link is not None:
            valid[link_id] = current_link
            continue

        link = parents.get(link_id, previous_link)
        previous_invalid = saved_index["invalid"].get(link_id)
        age = 0 if previous_invalid is None else int(previous_invalid["age"])
        if advance_invalid_age:
            age += 1
        if age > INVALID_TACK_MAX_AGE:
            culled.add(link_id)
            continue
        invalid[link_id] = {"link": link, "age": age}

    saved_index["valid"] = valid
    saved_index["invalid"] = invalid
    saved_index["object_ids"] = {
        object_store.object_key(link[role + "_id"])
        for link in list(valid.values()) + [entry["link"] for entry in invalid.values()]
        for role in ("parent", "child")
    }
    return saved_index


def remember_valid(doc, link):
    saved_index = runtime_index(doc)
    link_id = link["link_id"]
    saved_index["valid"][link_id] = link
    saved_index["invalid"].pop(link_id, None)
    saved_index["culled"].discard(link_id)
    saved_index["object_ids"].update(
        object_store.object_key(link[role + "_id"]) for role in ("parent", "child")
    )


def remember_invalid(doc, links):
    saved_index = runtime_index(doc)
    for link in links:
        link_id = link["link_id"]
        saved_index["valid"].pop(link_id, None)
        saved_index["invalid"][link_id] = {"link": link, "age": 0}
        saved_index["culled"].discard(link_id)
        saved_index["object_ids"].update(
            object_store.object_key(link[role + "_id"]) for role in ("parent", "child")
        )


def valid_links(doc):
    return runtime_index(doc)["valid"]


def invalid_links(doc):
    return dict(runtime_index(doc)["invalid"])
