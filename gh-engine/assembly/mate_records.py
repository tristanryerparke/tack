"""Mate record builders and validation.

The mate records are intentionally plain dictionaries so they can live in
``scriptcontext.sticky`` now and later be serialized into a Rhino document or a
sidecar JSON file without a translation layer.
"""

import uuid

from assembly.constants import MATE_TYPES


class MateRecordError(Exception):
    pass


def new_mate_record(mate_type, *, name=None, references=None, parameters=None, controls=None):
    """Create the source-of-truth record for one SolidWorks-style mate.

    ``references`` holds Rhino object/sub-object selections.
    ``parameters`` holds lengths, angles, strengths, limits, and solver options.
    ``controls`` declares which Rhino objects the generated GH definition writes
    back through Content Cache.
    """
    if mate_type not in MATE_TYPES:
        raise MateRecordError("Unsupported mate type: {}".format(mate_type))

    record = {
        "id": str(uuid.uuid4()),
        "type": mate_type,
        "name": name or mate_type.replace("_", " ").title(),
        "references": references or {},
        "parameters": parameters or {},
        "controls": controls or [],
    }
    validate_mate_record(record)
    return record


def validate_mate_record(record):
    required_keys = ("id", "type", "name", "references", "parameters", "controls")
    for key in required_keys:
        if key not in record:
            raise MateRecordError("Mate record missing key: {}".format(key))
    if record["type"] not in MATE_TYPES:
        raise MateRecordError("Unsupported mate type: {}".format(record["type"]))
    if not isinstance(record["references"], dict):
        raise MateRecordError("Mate references must be a dictionary.")
    if not isinstance(record["parameters"], dict):
        raise MateRecordError("Mate parameters must be a dictionary.")
    if not isinstance(record["controls"], list):
        raise MateRecordError("Mate controls must be a list.")
    return True


def object_reference(object_id, *, role, geometry_type=None, subobject=None):
    """Return a serializable reference to a Rhino object or sub-object."""
    return {
        "role": role,
        "object_id": str(object_id),
        "geometry_type": geometry_type,
        "subobject": subobject,
    }


def point_reference(point, *, role, source=None):
    """Return a serializable point/axis endpoint reference."""
    return {
        "role": role,
        "point": (float(point.X), float(point.Y), float(point.Z)),
        "source": source,
    }


def line_axis_reference(start, end, *, role, source=None):
    return {
        "role": role,
        "start": (float(start.X), float(start.Y), float(start.Z)),
        "end": (float(end.X), float(end.Y), float(end.Z)),
        "source": source,
    }


def content_cache_control(object_id, *, role, transform_source):
    """Declare that a Rhino object should be rewritten by Content Cache."""
    return {
        "role": role,
        "object_id": str(object_id),
        "writeback": "content_cache",
        "transform_source": transform_source,
    }


def eccentric_joint_record(
    *,
    shaft_axis,
    eccentric_pin_start=None,
    piston_axis,
    piston_pin_start=None,
    piston_object_id=None,
    rod_length,
    eccentric_object_id=None,
    rod_object_id=None,
    rotator_shaft_edge=None,
    eccentric_pin_edge=None,
    rod_big_edge=None,
    rod_small_edge=None,
    piston_pin_edge=None,
    name="Eccentric Joint",
):
    """Build the crank-slider/eccentric-joint mate record.

    Preferred metadata uses Brep object ids + circular edge indices. Point-based
    arguments remain accepted for early proof-of-concept files.
    """
    controls = []

    if rotator_shaft_edge is not None:
        eccentric_object_id = rotator_shaft_edge["object_id"]
        rod_object_id = rod_big_edge["object_id"] if rod_big_edge is not None else rod_object_id
        piston_object_id = piston_pin_edge["object_id"] if piston_pin_edge is not None else piston_object_id
        references = {
            "rotator_shaft_edge": rotator_shaft_edge,
            "shaft_axis": shaft_axis,
            "eccentric_pin_edge": eccentric_pin_edge,
            "rod_big_edge": rod_big_edge,
            "rod_small_edge": rod_small_edge,
            "piston_pin_edge": piston_pin_edge,
            "piston_axis": piston_axis,
            "eccentric_object": object_reference(eccentric_object_id, role="eccentric_rotator"),
            "rod_object": object_reference(rod_object_id, role="connecting_rod"),
            "piston_object": object_reference(piston_object_id, role="piston"),
        }
    else:
        references = {
            "shaft_axis": shaft_axis,
            "eccentric_pin_start": eccentric_pin_start,
            "piston_axis": piston_axis,
            "piston_pin_start": piston_pin_start,
            "piston_object": object_reference(piston_object_id, role="piston"),
        }
        if eccentric_object_id is not None:
            references["eccentric_object"] = object_reference(eccentric_object_id, role="eccentric_rotator")
        if rod_object_id is not None:
            references["rod_object"] = object_reference(rod_object_id, role="connecting_rod")

    if eccentric_object_id is not None:
        controls.append(
            content_cache_control(
                eccentric_object_id,
                role="eccentric_rotator",
                transform_source="shaft_angle_rotation",
            )
        )
    if piston_object_id is not None:
        controls.append(
            content_cache_control(
                piston_object_id,
                role="piston",
                transform_source="solved_piston_pin_translation",
            )
        )
    if rod_object_id is not None:
        controls.append(
            content_cache_control(
                rod_object_id,
                role="connecting_rod",
                transform_source="solved_rod_endpoint_orient",
            )
        )

    return new_mate_record(
        "eccentric_joint",
        name=name,
        references=references,
        parameters={
            "rod_length": float(rod_length),
            "angle_driver": {
                "type": "slider",
                "initial_degrees": 0.0,
            },
            "strengths": {
                "rod_length": 1000.0,
                "slider_axis": 10000.0,
                "shaft_anchor": 10000.0,
            },
        },
        controls=controls,
    )
