import importlib

import Rhino
from Rhino.Commands import Result

import derivation
import getpoint_support

importlib.reload(derivation)
importlib.reload(getpoint_support)

from derivation import derive_snap_data
from getpoint_support import TARGET_OBJECT_ID
from getpoint_support import pick_point_on_object
from getpoint_support import print_pick_debug
from getpoint_support import run_with_watcher


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        print("No active Rhino document.")
        return Result.Cancel

    target_object = doc.Objects.Find(TARGET_OBJECT_ID)
    if target_object is None:
        print("Target object was not found: {}".format(TARGET_OBJECT_ID))
        return Result.Cancel

    picked = pick_point_on_object(
        TARGET_OBJECT_ID,
        "Pick a point on the target Brep",
    )
    if picked is None:
        return Result.Cancel

    derived = derive_snap_data(
        picked["object_ref"],
        picked["point"],
        picked["osnap_type"],
    )
    print_pick_debug(
        picked,
        derived,
        point_label="Accepted point on target Brep",
    )
    return Result.Success


if __name__ == "__main__":
    run_with_watcher(lambda: RunCommand(True))
