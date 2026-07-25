import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "glue"))

import Rhino
import rhinoscriptsyntax as rs
from Rhino.Commands import Result

import glue_frame_picker
import glue_link

importlib.reload(glue_frame_picker)
importlib.reload(glue_link)
from glue_frame_picker import pick_frame


def _point_data(point):
    return [point.X, point.Y, point.Z]


def _plane_data(plane):
    return {
        "origin": _point_data(plane.Origin),
        "x_axis": _point_data(plane.XAxis),
        "y_axis": _point_data(plane.YAxis),
        "z_axis": _point_data(plane.ZAxis),
    }


def _matrix_data(xform):
    return [
        xform.M00, xform.M01, xform.M02, xform.M03,
        xform.M10, xform.M11, xform.M12, xform.M13,
        xform.M20, xform.M21, xform.M22, xform.M23,
        xform.M30, xform.M31, xform.M32, xform.M33,
    ]


def _print_frame(name, object_id, result):
    spec, plane = result
    print("--- {} frame ---".format(name))
    print("object_id: {}".format(object_id))
    print("vertex: {} index={}".format(spec["vertex_type"], spec["vertex_index"]))
    print(
        "edge_1: {} index={} (red / X axis)".format(
            spec["edge_1_type"], spec["edge_1"]
        )
    )
    print(
        "edge_2: {} index={} (green / Y axis)".format(
            spec["edge_2_type"], spec["edge_2"]
        )
    )
    print("plane: {}".format(_plane_data(plane)))
    return plane


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

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
    parent_plane = _print_frame("parent", parent_id, parent_result)

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

    child_obj = doc.Objects.Find(child_id)
    print("child geometry: {}".format(child_obj.Geometry.GetType().FullName))
    child_result = pick_frame(child_id, "child")
    if child_result is None:
        return Result.Cancel
    child_plane = _print_frame("child", child_id, child_result)

    parent_to_child = Rhino.Geometry.Transform.PlaneToPlane(
        parent_plane,
        child_plane,
    )
    print("--- setup relationship ---")
    print("parent_to_child: {}".format(_matrix_data(parent_to_child)))
    if glue_link.write_link(
        doc,
        parent_id,
        child_id,
        parent_result[0],
        child_result[0],
        parent_plane,
        child_plane,
        parent_to_child,
    ):
        print("metadata: child link and parent child GUID written")
        print("child metadata: {}".format(glue_link.read_link(doc.Objects.Find(child_id))))
    else:
        print("metadata: write failed")
    print("--------------------------")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
