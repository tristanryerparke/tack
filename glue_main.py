import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
import glue_display
import glue_events
import glue_metadata
import glue_state
import glue_transforms

import rhinoscriptsyntax as rs
import scriptcontext as sc
from Rhino.Commands import Result
from System import Guid

from glue_constants import (
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
from glue_metadata import write_metadata
from glue_state import get_state
from glue_transforms import choose_transform_types


def RunCommand(is_interactive):
    # Drop old event/conduit instances, but preserve current relationship data.
    reset_runtime_objects()
    state = get_state()

    parent_id = rs.GetObject(
        "Select Parent object",
        preselect=False,
        select=False,
    )
    if not parent_id:
        return Result.Cancel

    child_ids = rs.GetObjects(
        "Select Child object(s)",
        preselect=False,
        select=False,
    )
    if not child_ids or parent_id in child_ids:
        print("Select one Parent object that is not a Child.")
        return Result.Cancel

    transform_types = choose_transform_types(parent_id)
    if transform_types is None:
        return Result.Cancel

    (
        allow_translation,
        allow_rotation,
        allow_scale,
        reference,
        vertex_index,
        vertex_type,
    ) = transform_types
    if reference == "vertex":
        allow_scale = False
        log("vertex reference: forcing scale off; rotation={}".format(allow_rotation))

    log(
        "relationship options: reference={}, vertex_type={}, vertex_index={}".format(
            reference,
            vertex_type,
            vertex_index,
        )
    )

    doc = Rhino.RhinoDoc.ActiveDoc

    for child_id in child_ids:
        relationship_id = str(Guid.NewGuid())
        relationship = {
            "document_serial": doc.RuntimeSerialNumber,
            "follower_id": child_id,
            "driver_id": parent_id,
            "translation": allow_translation,
            "rotation": allow_rotation,
            "scale": allow_scale,
            "reference": reference,
            "vertex_index": vertex_index,
            "vertex_type": vertex_type,
        }
        offset = None
        frame_indices = None
        initial_frame = None
        if reference == "vertex":
            parent = doc.Objects.Find(parent_id)
            child = doc.Objects.Find(child_id)
            parent_point = GlueConduit.reference_point(
                parent,
                relationship,
                fallback=False,
            ) if parent is not None else None
            if child is None or parent_point is None:
                print("Could not resolve the selected Parent vertex.")
                return Result.Cancel
            offset = GlueConduit.centroid(child) - parent_point
            if allow_rotation:
                frame_indices = GlueConduit.frame_vertex_indices(parent, relationship)
                if frame_indices is None:
                    print("The selected Parent vertex has no usable rotation frame.")
                    return Result.Cancel
                relationship["frame_index_1"] = frame_indices[0]
                relationship["frame_index_2"] = frame_indices[1]
                initial_frame = GlueConduit.reference_frame(parent, relationship)
                if initial_frame is None:
                    print("Could not create a rotation frame for the Parent vertex.")
                    return Result.Cancel
            log("stored Child {} vertex offset={}".format(child_id, offset))
        relationship["offset"] = offset
        relationship["frame_index_1"] = frame_indices[0] if frame_indices else -1
        relationship["frame_index_2"] = frame_indices[1] if frame_indices else -1
        relationship["initial_frame"] = initial_frame
        state["relationships"][relationship_id] = relationship
        log(
            "created relationship {}: child={}, parent={}, reference={}, vertex_type={}, vertex_index={}".format(
                relationship_id,
                child_id,
                parent_id,
                reference,
                vertex_type,
                vertex_index,
            )
        )

        write_metadata(
            doc,
            child_id,
            relationship_id,
            "follower",
            parent_id,
            allow_translation,
            allow_rotation,
            allow_scale,
            reference,
            vertex_index,
            vertex_type,
            offset,
            frame_indices,
            initial_frame,
        )
        write_metadata(
            doc,
            parent_id,
            relationship_id,
            "driver",
            child_id,
            allow_translation,
            allow_rotation,
            allow_scale,
            reference,
            vertex_index,
            vertex_type,
            offset,
            frame_indices,
            initial_frame,
        )

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
        "Glue active: {} child relationship(s); translation={}, rotation={}, scale={}.".format(
            len(state["relationships"]),
            allow_translation,
            allow_rotation,
            allow_scale,
        )
    )
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
