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
    return "({:.6f}, {:.6f}, {:.6f})".format(point.X, point.Y, point.Z)


def _box_key(obj):
    box = obj.Geometry.GetBoundingBox(True)
    return (
        type(obj.Geometry).__name__,
        round(box.Min.X, 6), round(box.Min.Y, 6), round(box.Min.Z, 6),
        round(box.Max.X, 6), round(box.Max.Y, 6), round(box.Max.Z, 6),
    )


def _same_geometry(left, right):
    try:
        return Rhino.Geometry.GeometryBase.GeometryEquals(
            left.Geometry,
            right.Geometry,
        )
    except Exception:
        try:
            return left.Geometry.GeometryEquals(right.Geometry)
        except Exception:
            return False


def _metadata(obj):
    keys = []
    for key in (glue_link.LINK_KEY, glue_link.CHILD_KEY):
        try:
            if obj.Attributes.UserDictionary.ContainsKey(key):
                keys.append(key)
        except Exception:
            pass
    return ", ".join(keys) or "-"


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    objects = [obj for obj in doc.Objects if obj is not None]
    groups = {}
    for obj in objects:
        groups.setdefault(_box_key(obj), []).append(obj)

    print("--- duplicate analysis ---")
    print("object count: {}".format(len(objects)))
    for obj in objects:
        box = obj.Geometry.GetBoundingBox(True)
        print(
            "object={} type={} min={} max={} metadata={}".format(
                obj.Id,
                type(obj.Geometry).__name__,
                _point_text(box.Min),
                _point_text(box.Max),
                _metadata(obj),
            )
        )

    candidates = [group for group in groups.values() if len(group) > 1]
    print("same-bounds groups: {}".format(len(candidates)))
    for group in candidates:
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                print(
                    "duplicate candidate: {} / {} geometry_equal={}".format(
                        left.Id,
                        right.Id,
                        _same_geometry(left, right),
                    )
                )
    print("---------------------------")
    return Result.Success


if __name__ == "__main__":
    RunCommand(True)
