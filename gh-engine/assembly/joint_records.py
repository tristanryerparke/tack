"""Fusion-style joint records for AssemblyGH.

Joints are the public API we want users to think in: revolute, slider, rigid,
planar, ball, etc. Internally, a joint references metadata-backed features on
assembly bodies and later emits lower-level Kangaroo goals.
"""

import uuid

from assembly.features import circular_edge_feature, feature_ref


class JointRecordError(Exception):
    pass


JOINT_TYPES = (
    "rigid",
    "revolute",
    "slider",
    "cylindrical",
    "pin_slot",
    "planar",
    "ball",
)


def new_joint_record(joint_type, *, name=None, references=None, parameters=None, controls=None):
    if joint_type not in JOINT_TYPES:
        raise JointRecordError("Unsupported joint type: {}".format(joint_type))
    record = {
        "id": str(uuid.uuid4()),
        "type": joint_type,
        "name": name or joint_type.replace("_", " ").title(),
        "references": references or {},
        "parameters": parameters or {},
        "controls": controls or [],
    }
    validate_joint_record(record)
    return record


def validate_joint_record(record):
    for key in ("id", "type", "name", "references", "parameters", "controls"):
        if key not in record:
            raise JointRecordError("Joint record missing key: {}".format(key))
    if record["type"] not in JOINT_TYPES:
        raise JointRecordError("Unsupported joint type: {}".format(record["type"]))
    if not isinstance(record["references"], dict):
        raise JointRecordError("Joint references must be a dictionary.")
    if not isinstance(record["parameters"], dict):
        raise JointRecordError("Joint parameters must be a dictionary.")
    if not isinstance(record["controls"], list):
        raise JointRecordError("Joint controls must be a list.")
    return True


def content_cache_control(object_id, *, role="moving_body", transform_source="solved_body_pose"):
    return {
        "role": role,
        "object_id": str(object_id),
        "writeback": "content_cache",
        "transform_source": transform_source,
    }


def revolute_joint_record(*, edge_a, edge_b, name="Revolute Joint", controls="both"):
    """Create a revolute joint between two circular edge features.

    This is Fusion-like: align circular centers/axes and leave one rotational DOF.
    """
    feature_a = circular_edge_feature(edge_a, role="revolute_a")
    feature_b = circular_edge_feature(edge_b, role="revolute_b")
    record_controls = []
    if controls in ("both", "a"):
        record_controls.append(content_cache_control(edge_a["object_id"], role="body_a"))
    if controls in ("both", "b"):
        record_controls.append(content_cache_control(edge_b["object_id"], role="body_b"))

    return new_joint_record(
        "revolute",
        name=name,
        references={
            "a": feature_ref(feature_a),
            "b": feature_ref(feature_b),
            "features": {
                feature_a["id"]: feature_a,
                feature_b["id"]: feature_b,
            },
        },
        parameters={
            "mode": "body_to_body",
            "degrees_of_freedom": ["rotation_about_joint_axis"],
            "strengths": {
                "center_coincident": 10000.0,
                "axis_aligned": 10000.0,
            },
        },
        controls=record_controls,
    )


def revolute_to_axis_joint_record(*, body_edge, axis, name="Revolute To Fixed Axis", controls="body"):
    """Create a revolute joint between one body edge and a fixed world axis."""
    feature = circular_edge_feature(body_edge, role="revolute_body")
    record_controls = []
    if controls == "body":
        record_controls.append(content_cache_control(body_edge["object_id"], role="revolute_body"))

    return new_joint_record(
        "revolute",
        name=name,
        references={
            "body": feature_ref(feature),
            "axis": axis,
            "features": {
                feature["id"]: feature,
            },
        },
        parameters={
            "mode": "body_to_world_axis",
            "degrees_of_freedom": ["rotation_about_joint_axis"],
            "strengths": {
                "center_on_axis": 10000.0,
                "axis_aligned": 10000.0,
            },
        },
        controls=record_controls,
    )


def slider_joint_record(*, body_edge, axis, name="Slider Joint", controls="body"):
    """Create a slider joint between a body feature center and a fixed world axis."""
    feature = circular_edge_feature(body_edge, role="slider_body")
    record_controls = []
    if controls == "body":
        record_controls.append(content_cache_control(body_edge["object_id"], role="slider_body"))

    return new_joint_record(
        "slider",
        name=name,
        references={
            "body": feature_ref(feature),
            "axis": axis,
            "features": {
                feature["id"]: feature,
            },
        },
        parameters={
            "mode": "body_to_world_axis",
            "degrees_of_freedom": ["translation_along_axis"],
            "strengths": {
                "point_on_axis": 10000.0,
            },
        },
        controls=record_controls,
    )
