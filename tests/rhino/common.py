"""Shared helpers executed inside the disposable Rhino test document."""

import json
import sys
from pathlib import Path

import System
import Rhino
import scriptcontext as sc

from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.parasite import OutputParasite


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

TEST_KEY = "Tack.AnalyticPlaneTests"


def mark_test_object(doc, object_id):
    obj = doc.Objects.Find(object_id)
    if obj is None:
        raise RuntimeError("Test object is unavailable: {}".format(object_id))
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Set(TEST_KEY, True)
    if not doc.Objects.ModifyAttributes(object_id, attributes, True):
        raise RuntimeError("Could not mark test object: {}".format(object_id))


def cleanup(doc):
    from tack import plane_link

    plane_link.clear_document(doc)
    object_ids = []
    for obj in doc.Objects:
        if obj is None:
            continue
        try:
            if obj.Attributes.UserDictionary.ContainsKey(TEST_KEY):
                object_ids.append(obj.Id)
        except Exception:
            pass
    for object_id in object_ids:
        doc.Objects.Delete(object_id, True)
    doc.Views.Redraw()


def circular_plane_definition(object_id):
    return {
        "type": "circular_curve_plane",
        "object_id": str(object_id),
        "curve_center_anchor": {"type": "curve_center"},
    }


def add_circle(doc, center, radius=2.0):
    plane = Rhino.Geometry.Plane(center, Rhino.Geometry.Vector3d.ZAxis)
    object_id = doc.Objects.AddCircle(Rhino.Geometry.Circle(plane, radius))
    if object_id == System.Guid.Empty:
        raise RuntimeError("Could not add test circle")
    mark_test_object(doc, object_id)
    return object_id


def point_data(point):
    return [point.X, point.Y, point.Z]


def run_test(name, action):
    connection = SocketConnection()
    with OutputParasite(connection, done_msg=True):
        payload = action()
        payload["name"] = name
        connection.send_data(json.dumps(payload))
