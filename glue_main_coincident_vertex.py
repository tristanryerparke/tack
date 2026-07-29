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

from glue_frame_picker import coincident_vertices


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    glue_link.stop_runtime()
    glue_link.stop_coincident_runtime()

    parent_id = rs.GetObject(
        "Select parent object",
        preselect=False,
        select=False,
    )
    if not parent_id:
        return Result.Cancel
    parent = doc.Objects.Find(parent_id)
    if parent is None:
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
    child = doc.Objects.Find(child_id)
    if child is None:
        return Result.Cancel

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    matches = coincident_vertices(parent, child, tolerance)
    if not matches:
        print("Parent and child do not share a coincident vertex.")
        return Result.Cancel
    if len(matches) > 1:
        print(
            "Found {} coincident vertices; automatic selection is ambiguous.".format(
                len(matches)
            )
        )
        return Result.Cancel

    (
        parent_vertex_type,
        parent_vertex_index,
        child_vertex_type,
        child_vertex_index,
        parent_point,
        child_point,
    ) = matches[0]
    if not glue_link.write_coincident_link(
        doc,
        parent_id,
        child_id,
        (parent_vertex_type, parent_vertex_index),
        (child_vertex_type, child_vertex_index),
        parent_point,
        child_point,
    ):
        print("Could not write coincident vertex relationship metadata.")
        return Result.Failure

    if not glue_link.start_coincident_runtime(parent_id, child_id):
        print("Could not start coincident vertex relationship.")
        return Result.Failure
    print("Coincident vertex relationship active.")
    print("Parent GUID: {}".format(parent_id))
    print("Child GUID: {}".format(child_id))
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
