import importlib
import os
import sys

import Rhino
from Rhino.Commands import Result

TACK_ROOT = "/Users/tristanryerparke/projects-local/tack"
if TACK_ROOT not in sys.path:
    sys.path.insert(0, TACK_ROOT)

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model

assembly_model = importlib.reload(assembly_model)

assembly_common = importlib.reload(assembly_common) if "assembly_common" in globals() else assembly_common
assembly_model = importlib.reload(assembly_model)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    obj = assembly_common.prompt_for_one_object("Select object to anchor rigidly in world")
    if obj is None:
        return Result.Cancel

    part = assembly_model.add_world_anchor(doc, obj)
    if part is None:
        return Result.Failure
    result = assembly_model.solve_and_propagate(doc)
    print("[Ondsel assembly] anchored {} moved {} object(s).".format(str(obj.Id)[:8], len(result["moved"])))
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
