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
from ondsel.assembly import assembly_scheduler

assembly_common = importlib.reload(assembly_common) if "assembly_common" in globals() else assembly_common
assembly_model = importlib.reload(assembly_model)
assembly_scheduler = importlib.reload(assembly_scheduler)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    obj = assembly_common.prompt_for_one_object("Select object to constrain as a slider")
    if obj is None:
        return Result.Cancel

    part_axis = assembly_common.prompt_for_axis(
        "Pick first point on the slider axis on the selected object",
        "Pick second point on the slider axis on the selected object",
    )
    if part_axis is None:
        return Result.Cancel
    part_axis_origin, part_axis_direction = part_axis

    world_axis = assembly_common.prompt_for_axis(
        "Pick first point on fixed world slider axis",
        "Pick second point on fixed world slider axis",
    )
    if world_axis is None:
        return Result.Cancel
    world_axis_origin, world_axis_direction = world_axis

    assembly_model._set_command_busy(doc, True)
    try:
        assembly_model.prealign_slider_child(
            doc,
            obj,
            part_axis_origin,
            part_axis_direction,
            world_axis_origin,
            world_axis_direction,
        )
        part = assembly_model.add_slider_axis(
            doc,
            obj,
            world_axis_origin,
            world_axis_direction,
            world_axis_origin,
            world_axis_direction,
        )
    finally:
        assembly_model._set_command_busy(doc, False)
    if part is None:
        return Result.Failure
    assembly_scheduler.expire_document(doc, reason="add slider {}".format(str(obj.Id)[:8]))
    print("[Ondsel assembly] slider set for {} and queued solve.".format(str(obj.Id)[:8]))
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
