import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "glue"))

import Rhino
from Rhino.Commands import Result

import glue_frame_picker
import glue_link

importlib.reload(glue_frame_picker)
importlib.reload(glue_link)


def _point_text(point):
    return "({:.9g}, {:.9g}, {:.9g})".format(point.X, point.Y, point.Z)


def _plane_text(plane):
    return "origin={}, x={}, y={}".format(
        _point_text(plane.Origin),
        _point_text(plane.XAxis),
        _point_text(plane.YAxis),
    )


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    runtime = glue_link.sc.sticky.get(glue_link.RUNTIME_KEY)
    if runtime is None:
        print("No active plane link runtime found.")
        return Result.Failure

    parent_id = runtime["parent_id"]
    result = glue_link.inspect_link(doc, parent_id)
    if result is None:
        print("No valid plane link found.")
        return Result.Failure

    correction = result["correction"]
    print("--- plane link analysis ---")
    print("parent: {}".format(result["parent_id"]))
    print("child: {}".format(result["child_id"]))
    print("current parent: {}".format(_plane_text(result["parent_plane"])))
    print("current child: {}".format(_plane_text(result["child_plane"])))
    print("target child: {}".format(_plane_text(result["target_child_plane"])))
    print("correction: {}".format(glue_link.transform_data(correction)))
    print("aligned: {}".format(glue_link._identity(correction)))
    print("---------------------------")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
