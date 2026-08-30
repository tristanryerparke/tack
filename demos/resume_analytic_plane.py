"""Restore a saved analytic plane's sticky conduit and EndCommand handler.

Run after opening a 3dm file that was saved after defining the plane:

    uv run rhino-watch demos/resume_analytic_plane.py --debug
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


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    saved = three_point_plane_metadata.all_definitions(doc)
    if not saved:
        print("No valid saved analytic plane metadata was found.")
        return Result.Cancel
    if len(saved) != 1:
        print(
            "Expected one saved analytic plane definition, found {}.".format(
                len(saved)
            )
        )
        return Result.Failure

    obj, definition = saved[0]
    state = three_point_plane.install(doc, definition)
    if state is None:
        print(
            "Saved analytic plane on object {} could not be resolved.".format(
                obj.Id
            )
        )
        return Result.Failure

    print(
        "Restored analytic plane: {}".format(
            json.dumps(definition, sort_keys=True)
        )
    )
    return Result.Success


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True):
        RunCommand(True)
