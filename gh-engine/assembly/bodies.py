"""Assembly body registry.

A body is a Rhino object participating in mates. Its relationships are expressed
through feature metadata (for example circular Brep edge indices), not by baked
geometry snapshots.
"""

from assembly.features import circular_edge_feature, feature_ref, validate_feature


class BodyRecordError(Exception):
    pass


def new_body_record(object_id, *, role=None):
    return {
        "id": str(object_id),
        "object_id": str(object_id),
        "role": role,
        "features": {},
        "controls": {},
    }


def add_feature(body, feature):
    validate_feature(feature)
    if str(feature["object_id"]) != str(body["object_id"]):
        raise BodyRecordError("Feature object_id does not match body object_id.")
    body["features"][feature["id"]] = feature
    return feature_ref(feature)


def add_control(body, control):
    object_id = control.get("object_id")
    if str(object_id) != str(body["object_id"]):
        raise BodyRecordError("Control object_id does not match body object_id.")
    role = control.get("role") or "default"
    body["controls"][role] = dict(control)


def ensure_body(registry, object_id, *, role=None):
    object_id = str(object_id)
    body = registry.get(object_id)
    if body is None:
        body = new_body_record(object_id, role=role)
        registry[object_id] = body
    elif role and not body.get("role"):
        body["role"] = role
    return body


def _add_edge_feature_from_reference(registry, edge_reference, *, role, body_role=None):
    body = ensure_body(registry, edge_reference["object_id"], role=body_role or role)
    return add_feature(body, circular_edge_feature(edge_reference, role=role))


def eccentric_joint_feature_refs(record):
    """Return semantic feature refs for an eccentric-joint mate record."""
    refs = record.get("references", {})
    if "rotator_shaft_edge" not in refs:
        return {}

    registry = {}
    feature_refs = {
        "rotator_shaft": _add_edge_feature_from_reference(
            registry,
            refs["rotator_shaft_edge"],
            role="rotator_shaft",
        ),
        "eccentric_pin": _add_edge_feature_from_reference(
            registry,
            refs["eccentric_pin_edge"],
            role="eccentric_pin",
        ),
        "rod_big": _add_edge_feature_from_reference(
            registry,
            refs["rod_big_edge"],
            role="rod_big",
        ),
        "rod_small": _add_edge_feature_from_reference(
            registry,
            refs["rod_small_edge"],
            role="rod_small",
        ),
        "piston_pin": _add_edge_feature_from_reference(
            registry,
            refs["piston_pin_edge"],
            role="piston_pin",
        ),
    }
    return feature_refs


def apply_mate_to_registry(registry, record):
    """Merge one mate's bodies/features/controls into the session registry."""
    refs = record.get("references", {})
    if record.get("type") == "eccentric_joint" and "rotator_shaft_edge" in refs:
        for body_role, key in (
            ("eccentric_rotator", "rotator_shaft_edge"),
            ("eccentric_rotator", "eccentric_pin_edge"),
            ("connecting_rod", "rod_big_edge"),
            ("connecting_rod", "rod_small_edge"),
            ("piston", "piston_pin_edge"),
        ):
            _add_edge_feature_from_reference(
                registry,
                refs[key],
                role=refs[key].get("role", key),
                body_role=body_role,
            )

    driver_mode = record.get("parameters", {}).get("driver_mode", "live_driver")
    for control in record.get("controls", []):
        if record.get("type") == "eccentric_joint" and control.get("role") == "eccentric_rotator" and driver_mode != "slider":
            continue
        object_id = control.get("object_id")
        if object_id:
            body = ensure_body(registry, object_id, role=control.get("role"))
            add_control(body, control)
    return registry


def body_registry_from_mates(records):
    registry = {}
    for record in records:
        apply_mate_to_registry(registry, record)
    return registry
