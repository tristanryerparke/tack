import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
import scriptcontext as sc
from Rhino.Commands import Result

import glue_display
import glue_events
import glue_metadata
import glue_state

from glue_constants import (
    ALLOW_ROTATION,
    ALLOW_SCALE,
    ALLOW_TRANSLATION,
    CONDUIT_KEY,
    HANDLER_KEY,
    REPLACE_HANDLER_KEY,
)
from glue_debug import log
from glue_display import GlueConduit
from glue_events import (
    before_transform,
    replace_rhino_object,
    reset_runtime_objects,
)
from glue_metadata import (
    META_OFFSET_X,
    META_OFFSET_Y,
    META_OFFSET_Z,
    META_FRAME_INDEX_1,
    META_FRAME_INDEX_2,
    META_FRAME_ORIGIN_X,
    META_FRAME_ORIGIN_Y,
    META_FRAME_ORIGIN_Z,
    META_FRAME_X_X,
    META_FRAME_X_Y,
    META_FRAME_X_Z,
    META_FRAME_Y_X,
    META_FRAME_Y_Y,
    META_FRAME_Y_Z,
    META_PEER,
    META_RELATION,
    META_ROLE,
    META_REFERENCE,
    META_ROTATION,
    META_SCALE,
    META_TRANSLATION,
    META_VERTEX_INDEX,
    META_VERTEX_TYPE,
    user_value,
)
from glue_state import get_state


def _metadata_bool(obj, key, default):
    value = user_value(obj, key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "on", "yes")


def _metadata_int(obj, key, default):
    value = user_value(obj, key)
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _metadata_float(obj, key):
    value = user_value(obj, key)
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _metadata_frame(obj):
    values = [
        _metadata_float(obj, key)
        for key in (
            META_FRAME_ORIGIN_X,
            META_FRAME_ORIGIN_Y,
            META_FRAME_ORIGIN_Z,
            META_FRAME_X_X,
            META_FRAME_X_Y,
            META_FRAME_X_Z,
            META_FRAME_Y_X,
            META_FRAME_Y_Y,
            META_FRAME_Y_Z,
        )
    ]
    if any(value is None for value in values):
        return None
    return Rhino.Geometry.Plane(
        Rhino.Geometry.Point3d(*values[0:3]),
        Rhino.Geometry.Vector3d(*values[3:6]),
        Rhino.Geometry.Vector3d(*values[6:9]),
    )


def _load_relationships(doc):
    objects_by_id = {}
    for obj in doc.Objects:
        if obj is not None:
            objects_by_id[str(obj.Id).lower()] = obj

    relationships = {}
    for child in objects_by_id.values():
        relation_id = user_value(child, META_RELATION)
        role = user_value(child, META_ROLE)
        peer_id = user_value(child, META_PEER)
        if relation_id is None or role is None or peer_id is None:
            log("skipping object {}: incomplete relationship metadata".format(child.Id))
            continue
        if str(role).lower() != "follower":
            continue

        parent = objects_by_id.get(str(peer_id).lower())
        if parent is None:
            log("skipping Child {}: Parent {} not found".format(child.Id, peer_id))
            continue

        reference = str(
            user_value(child, META_REFERENCE) or "centroid"
        ).lower()
        vertex_index = _metadata_int(child, META_VERTEX_INDEX, -1)
        vertex_type = str(user_value(child, META_VERTEX_TYPE) or "")
        if reference == "vertex" and (vertex_index < 0 or not vertex_type):
            log(
                "skipping relationship {}: invalid vertex metadata type={}, index={}".format(
                    relation_id,
                    vertex_type,
                    vertex_index,
                )
            )
            continue
        if reference != "vertex":
            reference = "centroid"
            vertex_index = -1
            vertex_type = ""

        offset = None
        if reference == "vertex":
            offset_values = (
                _metadata_float(child, META_OFFSET_X),
                _metadata_float(child, META_OFFSET_Y),
                _metadata_float(child, META_OFFSET_Z),
            )
            if all(value is not None for value in offset_values):
                offset = Rhino.Geometry.Vector3d(*offset_values)
            else:
                parent_point = GlueConduit.reference_point(
                    parent,
                    {
                        "reference": reference,
                        "vertex_index": vertex_index,
                        "vertex_type": vertex_type,
                    },
                    fallback=False,
                )
                if parent_point is None:
                    log("skipping relationship {}: could not reconstruct vertex offset".format(relation_id))
                    continue
                offset = GlueConduit.centroid(child) - parent_point
                log("reconstructed missing vertex offset for {}: {}".format(relation_id, offset))

        frame_indices = (
            _metadata_int(child, META_FRAME_INDEX_1, -1),
            _metadata_int(child, META_FRAME_INDEX_2, -1),
        )
        initial_frame = _metadata_frame(child) if reference == "vertex" else None
        if initial_frame is None:
            frame_indices = (-1, -1)

        relation_id = str(relation_id)
        relationships[relation_id] = {
            "document_serial": doc.RuntimeSerialNumber,
            "follower_id": child.Id,
            "driver_id": parent.Id,
            "translation": _metadata_bool(
                child, META_TRANSLATION, ALLOW_TRANSLATION
            ),
            "rotation": (
                False
                if reference == "vertex"
                else _metadata_bool(child, META_ROTATION, ALLOW_ROTATION)
            ),
            "scale": (
                False
                if reference == "vertex"
                else _metadata_bool(child, META_SCALE, ALLOW_SCALE)
            ),
            "reference": reference,
            "vertex_index": vertex_index,
            "vertex_type": vertex_type,
            "offset": offset,
            "frame_index_1": frame_indices[0],
            "frame_index_2": frame_indices[1],
            "initial_frame": initial_frame,
        }
        log(
            "loaded relationship {}: Child={}, Parent={}, reference={}, vertex_type={}, vertex_index={}, offset={}".format(
                relation_id,
                child.Id,
                parent.Id,
                reference,
                vertex_type,
                vertex_index,
                offset,
            )
        )

    return relationships


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    reset_runtime_objects()

    state = get_state()
    state["relationships"] = _load_relationships(doc)
    state["busy"] = False

    if not state["relationships"]:
        print("No saved glue relationships found.")
        return Result.Cancel

    sc.sticky[HANDLER_KEY] = before_transform
    Rhino.RhinoDoc.BeforeTransformObjects += before_transform
    sc.sticky[REPLACE_HANDLER_KEY] = replace_rhino_object
    Rhino.RhinoDoc.ReplaceRhinoObject += replace_rhino_object
    log("registered transform and replacement handlers")

    conduit = GlueConduit(state)
    conduit.Enabled = True
    sc.sticky[CONDUIT_KEY] = conduit
    doc.Views.Redraw()

    print(
        "Glue restored: {} relationship(s).".format(
            len(state["relationships"])
        )
    )
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
