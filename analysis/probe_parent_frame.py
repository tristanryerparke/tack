import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "glue"))

import Rhino
import rhinoscriptsyntax as rs
from Rhino.Commands import Result

import glue_frame_picker

importlib.reload(glue_frame_picker)
from glue_frame_picker import pick_parent_frame


def _point_data(point):
    return [point.X, point.Y, point.Z]


def _plane_data(plane):
    return {
        "origin": _point_data(plane.Origin),
        "x_axis": _point_data(plane.XAxis),
        "y_axis": _point_data(plane.YAxis),
        "z_axis": _point_data(plane.ZAxis),
    }


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

    result = pick_parent_frame(parent_id)
    if result is None:
        print("Parent frame selection cancelled.")
        return Result.Cancel

    spec, plane = result
    print("--- parent frame result ---")
    print("object_id: {}".format(parent_id))
    print("vertex_type: {}".format(spec["vertex_type"]))
    print("vertex_index: {}".format(spec["vertex_index"]))
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
    print("---------------------------")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
