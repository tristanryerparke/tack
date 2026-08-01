import Rhino
import rhinoscriptsyntax as rs
from Rhino.Commands import Result

from tack import handlers
from tack import metadata
from tack import runtime
from tack import tack_frame_picker
from tack import utils


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    handlers.unsubscribe()
    runtime.stop_runtime()

    mode = tack_frame_picker.pick_link_mode()
    if mode is None:
        return Result.Cancel
    if mode == "PickVertices":
        print("Pick Vertices is not implemented yet.")
        return Result.Cancel

    parent_id = rs.GetObject(
        "Select parent polysurface",
        filter=Rhino.DocObjects.ObjectType.Brep,
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
            "Select child polysurface",
            filter=Rhino.DocObjects.ObjectType.Brep,
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
    matches = utils.coincident_vertices(parent, child, tolerance)
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
    if not metadata.write_link(
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

    if not runtime.start_runtime(parent_id, child_id):
        print("Could not start coincident vertex relationship.")
        return Result.Failure
    handlers.subscribe()
    print("Coincident vertex relationship active.")
    print("Parent GUID: {}".format(parent_id))
    print("Child GUID: {}".format(child_id))
    return Result.Success


if __name__ == "__main__":
    from rhino_watcher import websocket_output_sync

    with websocket_output_sync():
        RunCommand(True)
    # send_done_sync()
