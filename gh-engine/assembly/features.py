"""Mate feature metadata.

AssemblyGH follows the Tack ethos: relationships are defined by Rhino metadata
(object ids + sub-object indices), and live geometry is resolved only when a
solution is generated or evaluated.
"""


class FeatureRecordError(Exception):
    pass


def circular_edge_feature(edge_reference, *, role=None):
    """Create a stable-ish feature record from a circular Brep edge reference.

    The stored center/radius/normal are fingerprints and debugging aids. The
    source of truth is still ``object_id`` + ``edge_indices``.
    """
    object_id = str(edge_reference["object_id"])
    edge_indices = edge_reference.get("edge_indices") or [edge_reference.get("edge_index")]
    edge_indices = [int(index) for index in edge_indices]
    if not edge_indices:
        raise FeatureRecordError("Circular edge feature requires at least one edge index.")

    return {
        "id": circular_edge_feature_id(object_id, edge_indices, role or edge_reference.get("role")),
        "kind": "circular_edge",
        "role": role or edge_reference.get("role"),
        "object_id": object_id,
        "edge_indices": edge_indices,
        "fingerprint": {
            "center": edge_reference.get("center"),
            "radius": edge_reference.get("radius"),
            "normal": edge_reference.get("normal"),
            "circle_kind": edge_reference.get("circle_kind"),
            "adjacent_face_indices": edge_reference.get("adjacent_face_indices", []),
        },
    }


def circular_edge_feature_id(object_id, edge_indices, role=None):
    index_part = ",".join(str(int(index)) for index in edge_indices)
    if role:
        return "{}:circular_edge:{}:{}".format(object_id, role, index_part)
    return "{}:circular_edge:{}".format(object_id, index_part)


def feature_ref(feature):
    return {
        "body_id": str(feature["object_id"]),
        "feature_id": feature["id"],
        "kind": feature["kind"],
        "role": feature.get("role"),
    }


def validate_feature(feature):
    for key in ("id", "kind", "object_id"):
        if key not in feature:
            raise FeatureRecordError("Feature missing key: {}".format(key))
    if feature["kind"] == "circular_edge" and not feature.get("edge_indices"):
        raise FeatureRecordError("Circular edge feature missing edge_indices.")
    return True
