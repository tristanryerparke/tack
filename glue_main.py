import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
from Rhino.Commands import Result
from System import Guid

from glue_constants import AFTER_HANDLER_KEY, CONDUIT_KEY, HANDLER_KEY, REPLACE_HANDLER_KEY
from glue_debug import log
from glue_display import GlueConduit
from glue_events import after_transform, before_transform, replace_rhino_object, reset_runtime_objects
from glue_metadata import write_metadata
from glue_state import get_state
from glue_transforms import choose_reference_plane


def RunCommand(is_interactive):
    reset_runtime_objects()
    state = get_state()
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    parent_id = rs.GetObject(
        "Select Parent object",
        preselect=False,
        select=False,
    )
    if not parent_id:
        return Result.Cancel

    parent_result = choose_reference_plane(parent_id, "Parent")
    if parent_result is None:
        return Result.Cancel
    parent_spec, parent_plane = parent_result

    child_ids = rs.GetObjects(
        "Select Child object(s)",
        preselect=False,
        select=False,
    )
    if not child_ids or parent_id in child_ids:
        print("Select one Parent object that is not a Child.")
        return Result.Cancel

    for child_id in child_ids:
        child_result = choose_reference_plane(child_id, "Child")
        if child_result is None:
            return Result.Cancel
        child_spec, child_plane = child_result
        relationship_id = str(Guid.NewGuid())
        parent_to_child = Rhino.Geometry.Transform.PlaneToPlane(
            parent_plane,
            child_plane,
        )
        relationship_data = {
            "parent_spec": parent_spec,
            "child_spec": child_spec,
            "parent_plane": GlueConduit.plane_data(parent_plane),
            "child_plane": GlueConduit.plane_data(child_plane),
            "parent_to_child": GlueConduit.transform_data(parent_to_child),
        }
        relationship = {
            "document_serial": doc.RuntimeSerialNumber,
            "follower_id": child_id,
            "driver_id": parent_id,
            "parent_spec": parent_spec,
            "child_spec": child_spec,
            "parent_to_child": parent_to_child,
            "parent_initial_plane": parent_plane,
            "child_initial_plane": child_plane,
            "current_parent_plane": parent_plane,
            "current_child_plane": child_plane,
        }
        state["relationships"][relationship_id] = relationship
        write_metadata(
            doc,
            child_id,
            relationship_id,
            "follower",
            parent_id,
            relationship_data,
        )
        write_metadata(
            doc,
            parent_id,
            relationship_id,
            "driver",
            child_id,
            relationship_data,
        )
        log(
            "created plane relationship {}: Child={}, Parent={}, parent_to_child={}".format(
                relationship_id,
                child_id,
                parent_id,
                GlueConduit.transform_data(parent_to_child),
            )
        )

    sc.sticky[HANDLER_KEY] = before_transform
    Rhino.RhinoDoc.BeforeTransformObjects += before_transform
    sc.sticky[AFTER_HANDLER_KEY] = after_transform
    Rhino.RhinoDoc.AfterTransformObjects += after_transform
    sc.sticky[REPLACE_HANDLER_KEY] = replace_rhino_object
    Rhino.RhinoDoc.ReplaceRhinoObject += replace_rhino_object

    conduit = GlueConduit(state)
    conduit.Enabled = True
    sc.sticky[CONDUIT_KEY] = conduit
    doc.Views.Redraw()
    print("Glue active: {} plane relationship(s).".format(len(state["relationships"])))
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
