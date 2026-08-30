"""Pick an analytic plane with smart circular-center reconciliation.

At the origin prompt, a circular edge/curve center displays and accepts its
one-click analytic plane. Any other anchor continues to X/Y three-point
selection. Use ``3Point`` to force custom X/Y directions from a circular
center.

Run from the parent terminal:

    uv run rhino-watch demos/analytic_plane_picker.py --debug
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


PICKER_CALLBACK = "analytic_plane_picker"


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
    view = doc.Views.ActiveView if doc is not None else None
    if view is None:
        _emit_callback(connection, parasite, "cancelled", reason="no_active_view")
        return Result.Cancel

    obj = select_object(doc, "Select object that will define the plane")
    if obj is None:
        _emit_callback(connection, parasite, "cancelled", stage="object")
        return Result.Cancel

    picked = analytic_plane_picker.pick_plane(
        doc,
        obj,
        view.ActiveViewport.ConstructionPlane(),
    )
    if picked is None:
        _emit_callback(connection, parasite, "cancelled", stage="plane")
        return Result.Cancel

    definition = picked["definition"]
    for accepted in picked["picks"]:
        _emit_callback(
            connection,
            parasite,
            accepted["role"],
            mode=picked["mode"],
            point=_point_data(accepted["point"]),
            anchor=accepted["anchor"],
        )

    if not three_point_plane_metadata.save_definition(doc, definition):
        print("The analytic plane metadata could not be saved.")
        _emit_callback(connection, parasite, "save_failed", definition=definition)
        return Result.Failure

    state = three_point_plane.install(doc, definition)
    if state is None:
        print("The analytic plane definition could not be resolved.")
        _emit_callback(connection, parasite, "resolve_failed", definition=definition)
        return Result.Failure

    plane = state["plane"]
    print(
        "Analytic plane definition: {}".format(
            json.dumps(definition, sort_keys=True)
        )
    )
    _emit_callback(
        connection,
        parasite,
        "completed",
        mode=picked["mode"],
        definition=definition,
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
