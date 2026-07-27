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

from glue_frame_picker import (
    FrameSelectionConduit,
    _incident_edge_endpoints,
    _lock_objects_except,
    _select_edge,
    _unlock_changed,
    coincident_vertices,
    edge_endpoints,
    frame_from_spec,
)


def _point_text(point):
    return "({:.6f}, {:.6f}, {:.6f})".format(point.X, point.Y, point.Z)


def _edge_prompt(obj, object_id, label):
    return _select_edge(obj, object_id, label)


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
    shared_point = Rhino.Geometry.Point3d(parent_point)
    print(
        "Shared vertex: parent={} {} / child={} {} / point={}".format(
            parent_vertex_type,
            parent_vertex_index,
            child_vertex_type,
            child_vertex_index,
            _point_text(shared_point),
        )
    )

    parent_conduit = FrameSelectionConduit()
    child_conduit = FrameSelectionConduit()
    parent_conduit.set_highlighted_vertex(shared_point)
    child_conduit.set_highlighted_vertex(shared_point)
    parent_conduit.set_incident_edges(
        _incident_edge_endpoints(
            parent,
            parent_vertex_type,
            parent_vertex_index,
        )
    )
    child_conduit.set_incident_edges(
        _incident_edge_endpoints(
            child,
            child_vertex_type,
            child_vertex_index,
        )
    )

    parent_was_locked = rs.IsObjectLocked(parent_id)
    child_was_locked = rs.IsObjectLocked(child_id)
    if parent_was_locked:
        rs.UnlockObject(parent_id)
    if child_was_locked:
        rs.UnlockObject(child_id)
    locked_by_picker = _lock_objects_except(doc, [parent_id, child_id])
    parent_conduit.Enabled = True
    child_conduit.Enabled = True
    doc.Views.Redraw()

    try:
        parent_x = _edge_prompt(
            parent,
            parent_id,
            "Select parent X edge (red)",
        )
        if parent_x is None:
            return Result.Cancel
        parent_conduit.set_edge(
            1,
            edge_endpoints(parent, parent_x[0], parent_x[1]),
        )
        doc.Views.Redraw()

        child_x = _edge_prompt(
            child,
            child_id,
            "Select child X edge (red)",
        )
        if child_x is None:
            return Result.Cancel
        child_conduit.set_edge(
            1,
            edge_endpoints(child, child_x[0], child_x[1]),
        )
        doc.Views.Redraw()

        parent_y = _edge_prompt(
            parent,
            parent_id,
            "Select parent Y edge (green)",
        )
        if parent_y is None:
            return Result.Cancel
        parent_conduit.set_edge(
            2,
            edge_endpoints(parent, parent_y[0], parent_y[1]),
        )
        doc.Views.Redraw()

        child_y = _edge_prompt(
            child,
            child_id,
            "Select child Y edge (green)",
        )
        if child_y is None:
            return Result.Cancel
        child_conduit.set_edge(
            2,
            edge_endpoints(child, child_y[0], child_y[1]),
        )
        doc.Views.Redraw()
    finally:
        _unlock_changed(locked_by_picker)
        parent_conduit.Enabled = False
        child_conduit.Enabled = False
        if parent_was_locked:
            rs.LockObject(parent_id)
        if child_was_locked:
            rs.LockObject(child_id)
        doc.Views.Redraw()

    parent_spec = {
        "vertex_type": parent_vertex_type,
        "vertex_index": parent_vertex_index,
        "edge_1_type": parent_x[0],
        "edge_1": parent_x[1],
        "edge_2_type": parent_y[0],
        "edge_2": parent_y[1],
    }
    child_spec = {
        "vertex_type": child_vertex_type,
        "vertex_index": child_vertex_index,
        "edge_1_type": child_x[0],
        "edge_1": child_x[1],
        "edge_2_type": child_y[0],
        "edge_2": child_y[1],
    }
    parent_plane = frame_from_spec(parent, parent_spec)
    child_plane = frame_from_spec(child, child_spec)
    if parent_plane is None or child_plane is None:
        print("The selected edges cannot define planes.")
        return Result.Failure

    parent_to_child = Rhino.Geometry.Transform.PlaneToPlane(
        parent_plane,
        child_plane,
    )
    if not glue_link.write_link(
        doc,
        parent_id,
        child_id,
        parent_spec,
        child_spec,
        parent_plane,
        child_plane,
        parent_to_child,
    ):
        print("Could not write plane relationship metadata.")
        return Result.Failure

    glue_link.start_runtime(parent_id, child_id)
    print("Coincident plane relationship active.")
    print("Parent GUID: {}".format(parent_id))
    print("Child GUID: {}".format(child_id))
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
