"""Define a persistent plane from one circular edge/curve center snap.

The plane origin is the circle center. Its X axis points from the center to the
edge or curve start, and its XY plane is coplanar with the circle.

Run from the parent terminal:

    uv run rhino-watch demos/circular_center_plane.py --debug
"""

import importlib
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import Rhino
from Rhino.Commands import Result
from run_in_rhino.rhino_env.client import SocketConnection
from run_in_rhino.rhino_env.env import install_os_environment
from run_in_rhino.rhino_env.parasite import OutputParasite

import tack

importlib.reload(tack).reload()

from tack import three_point_plane
from tack import three_point_plane_metadata
from tack.prompting import analytic_plane_picker
from tack.prompting.osnap_anchor_picker import select_object


PICKER_CALLBACK = "circular_center_plane"


def _point_data(point):
    return [point.X, point.Y, point.Z]


def _emit_callback(connection, parasite, event, **data):
    payload = {"callback": PICKER_CALLBACK, "event": event}
    payload.update(data)
    encoded = json.dumps(payload, sort_keys=True)
    print("CALLBACK {}".format(encoded))
    parasite.flush()
    connection.send_data(encoded)


def RunCommand(is_interactive, connection, parasite):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        _emit_callback(connection, parasite, "cancelled", reason="no_active_doc")
        return Result.Cancel

    obj = select_object(doc, "Select object with a circular edge or curve")
    if obj is None:
        _emit_callback(connection, parasite, "cancelled", stage="object")
        return Result.Cancel

    picked = analytic_plane_picker.pick_circular_plane(doc, obj)
    if picked is None:
        _emit_callback(connection, parasite, "cancelled", stage="circle_center")
        return Result.Cancel

    accepted = picked["picks"][0]
    center = accepted["point"]
    definition = picked["definition"]
    if not three_point_plane_metadata.save_definition(doc, definition):
        print("The circular plane metadata could not be saved.")
        _emit_callback(connection, parasite, "save_failed", definition=definition)
        return Result.Failure

    state = three_point_plane.install(doc, definition)
    if state is None:
        print("The circular edge or curve could not be resolved into a plane.")
        _emit_callback(connection, parasite, "resolve_failed", definition=definition)
        return Result.Failure

    plane = state["plane"]
    print(
        "Circular plane definition: {}".format(
            json.dumps(definition, sort_keys=True)
        )
    )
    _emit_callback(
        connection,
        parasite,
        "completed",
        definition=definition,
        picked_center=_point_data(center),
        resolved_plane={
            "origin": _point_data(plane.Origin),
            "x_axis": _point_data(plane.XAxis),
            "y_axis": _point_data(plane.YAxis),
            "z_axis": _point_data(plane.ZAxis),
        },
    )
    return Result.Success


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True) as parasite:
        RunCommand(True, connection, parasite)
