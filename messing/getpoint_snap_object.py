import importlib

import Rhino
from Rhino.Commands import Result

import derivation
import getpoint_support

importlib.reload(derivation)
importlib.reload(getpoint_support)

from derivation import derive_snap_data
from getpoint_support import get_point
from getpoint_support import print_pick_debug
from getpoint_support import run_with_watcher


def get_point_and_snap_object():
    picked = get_point("Pick a point")
    if picked is None:
        return None

    derived = derive_snap_data(
        picked["object_ref"],
        picked["point"],
        picked["osnap_type"],
    )
    return {**picked, **derived}


def RunCommand(is_interactive):
    picked = get_point_and_snap_object()
    if picked is None:
        return Result.Cancel

    print_pick_debug(picked, picked, point_label="Point")
    return Result.Success


if __name__ == "__main__":
    run_with_watcher(lambda: RunCommand(True))
