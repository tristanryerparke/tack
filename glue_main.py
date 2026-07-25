import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "glue"))

import Rhino
import rhinoscriptsyntax as rs
from Rhino.Commands import Result

import glue_frame_picker
import glue_link

importlib.reload(glue_frame_picker)
importlib.reload(glue_link)
from glue_frame_picker import pick_frame


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    glue_link.stop_runtime()

    parent_id = rs.GetObject(
        "Select parent object",
        preselect=False,
        select=False,
    )
    if not parent_id:
        return Result.Cancel

    parent_result = pick_frame(parent_id, "parent")
    if parent_result is None:
        return Result.Cancel

    parent_was_locked = rs.IsObjectLocked(parent_id)
    if not parent_was_locked:
        rs.LockObject(parent_id)
    try:
        child_id = rs.GetObject(
            "Select child object",
            preselect=False,
            select=False,
        )
    finally:
        if not parent_was_locked:
            rs.UnlockObject(parent_id)

    if not child_id or str(child_id).lower() == str(parent_id).lower():
        print("Select a different child object.")
        return Result.Cancel

    child_result = pick_frame(child_id, "child")
    if child_result is None:
        return Result.Cancel

    parent_plane = parent_result[1]
    child_plane = child_result[1]
    parent_to_child = Rhino.Geometry.Transform.PlaneToPlane(
        parent_plane,
        child_plane,
    )
    if not glue_link.write_link(
        doc,
        parent_id,
        child_id,
        parent_result[0],
        child_result[0],
        parent_plane,
        child_plane,
        parent_to_child,
    ):
        print("Could not write plane relationship metadata.")
        return Result.Failure

    glue_link.start_runtime(parent_id, child_id)
    print("Plane relationship active.")
    print("Parent GUID: {}".format(parent_id))
    print("Child GUID: {}".format(child_id))
    print("Move, rotate, or scale the parent to test the link.")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
