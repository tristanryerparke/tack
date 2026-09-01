"""Clear the active and saved analytic-plane relationships.

Run with:

    uv run rhino-watch demos/clear_analytic_plane.py --debug
"""

import importlib
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

from tack import plane_link
from tack import plane_link_metadata


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        print("No active Rhino document.")
        return Result.Cancel

    saved = plane_link_metadata.all_links(doc)
    if not saved:
        print("No saved analytic-plane relationships were found.")
        return Result.Cancel

    plane_link.clear_document(doc)
    remaining = plane_link_metadata.all_links(doc)
    if remaining:
        print(
            "Cleared {} analytic-plane relationship(s); {} could not be "
            "removed.".format(len(saved), len(remaining))
        )
        return Result.Failure

    print("Cleared {} analytic-plane relationship(s).".format(len(saved)))
    return Result.Success


if __name__ == "__main__":
    connection = SocketConnection()
    install_os_environment(connection)
    with OutputParasite(connection, done_msg=True):
        RunCommand(True)
