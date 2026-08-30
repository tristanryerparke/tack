"""Persist supported analytic plane definitions on Rhino objects."""

import copy
import json

import System

from tack import anchor_definitions


USER_DATA_KEY = "Tack.AnalyticPlane.v1"
METADATA_VERSION = 1


def _valid_three_point_plane(definition):
    expected_fields = {
        "type",
        "object_id",
        "origin_anchor",
        "x_axis_anchor",
        "y_axis_anchor",
    }
    return set(definition) == expected_fields and all(
        anchor_definitions.validate(definition[name])
        for name in ("origin_anchor", "x_axis_anchor", "y_axis_anchor")
    )


def _valid_circular_edge_plane(definition):
    expected_fields = {"type", "object_id", "edge_center_anchor"}
    if set(definition) != expected_fields:
        return False
    anchor = definition["edge_center_anchor"]
    return (
        anchor_definitions.validate(anchor)
        and anchor.get("type") == anchor_definitions.CIRCULAR_EDGE_CENTER
    )


def _valid_circular_curve_plane(definition):
    expected_fields = {"type", "object_id", "curve_center_anchor"}
    if set(definition) != expected_fields:
        return False
    anchor = definition["curve_center_anchor"]
    return (
        anchor_definitions.validate(anchor)
        and anchor.get("type") == anchor_definitions.CURVE_CENTER
    )


_DEFINITION_VALIDATORS = {
    "three_point_plane": _valid_three_point_plane,
    "circular_edge_plane": _valid_circular_edge_plane,
    "circular_curve_plane": _valid_circular_curve_plane,
}


def validate_definition(definition, expected_object_id=None):
    """Validate a plane definition and all of its new-model anchors."""
    if not isinstance(definition, dict):
        return False
    validator = _DEFINITION_VALIDATORS.get(definition.get("type"))
    if validator is None or not validator(definition):
        return False
    try:
        object_id = System.Guid(str(definition["object_id"]))
    except Exception:
        return False
    return expected_object_id is None or str(object_id).lower() == str(
        expected_object_id
    ).lower()


def _payload(definition):
    return {
        "version": METADATA_VERSION,
        "definition": copy.deepcopy(definition),
    }


def _set_payload(doc, obj, payload):
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Set(
        USER_DATA_KEY,
        json.dumps(payload, sort_keys=True),
    )
    return doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def _remove_payload(doc, obj):
    if not obj.Attributes.UserDictionary.ContainsKey(USER_DATA_KEY):
        return True
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Remove(USER_DATA_KEY)
    return doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def read_definition(obj):
    """Read and validate a plane definition stored on its defining object."""
    if obj is None or not obj.Attributes.UserDictionary.ContainsKey(USER_DATA_KEY):
        return None
    try:
        payload = json.loads(str(obj.Attributes.UserDictionary[USER_DATA_KEY]))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("version") != METADATA_VERSION:
        return None
    definition = payload.get("definition")
    if not validate_definition(definition, expected_object_id=obj.Id):
        return None
    return copy.deepcopy(definition)


def all_definitions(doc):
    """Return valid saved definitions with their host objects."""
    return [
        (obj, definition)
        for obj in doc.Objects
        if obj is not None
        for definition in (read_definition(obj),)
        if definition is not None
    ]


def save_definition(doc, definition):
    """Save one document-wide plane definition on its defining object.

    The persistent display is currently a singleton, so a successful save
    removes this metadata key from all other objects in the document.
    """
    if not validate_definition(definition):
        return False
    try:
        object_id = System.Guid(str(definition["object_id"]))
    except Exception:
        return False
    obj = doc.Objects.FindId(object_id)
    if obj is None:
        return False
    if not _set_payload(doc, obj, _payload(definition)):
        return False

    cleared = True
    for candidate in doc.Objects:
        if candidate is None or str(candidate.Id).lower() == str(obj.Id).lower():
            continue
        if not _remove_payload(doc, candidate):
            cleared = False
    return cleared


def clear(doc):
    """Remove saved plane metadata from every object in the document."""
    changed = False
    succeeded = True
    for obj in doc.Objects:
        if obj is None or not obj.Attributes.UserDictionary.ContainsKey(USER_DATA_KEY):
            continue
        changed = True
        if not _remove_payload(doc, obj):
            succeeded = False
    return changed and succeeded
