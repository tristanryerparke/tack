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

    side = assembly_common.prompt_for_one_brep_edge(
        "Select circular edge on the piston head (reference point for slider)"
    )
    if side is None:
        return Result.Cancel
    if assembly_common.circle_from_edge(side["edge"], doc.ModelAbsoluteTolerance) is None:
        print("Selected edge is not circular.")
        return Result.Cancel

    axis = assembly_common.prompt_for_axis(
        "Pick first point on fixed slider axis",
        "Pick second point on fixed slider axis",
    )
    if axis is None:
        return Result.Cancel
    axis_origin, axis_direction = axis

    assembly_model.prealign_slider_child(doc, side, axis_origin, axis_direction)
    part = assembly_model.add_slider_axis(doc, side, axis_origin, axis_direction)
    if part is None:
        return Result.Failure
    result = assembly_model.solve_and_propagate(doc)
    print("[Ondsel assembly] slider set for {} moved {} object(s).".format(str(side["object_id"])[:8], len(result["moved"])))
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
