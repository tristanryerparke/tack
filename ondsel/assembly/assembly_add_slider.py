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


def _send_setup_record(record):
    from run_in_rhino.rhino_env.client import SocketConnection

    SocketConnection().send_data(record)


def _prompt_for_part_axis_edge(prompt, slider_object, doc):
    edge_data = assembly_common.prompt_for_one_brep_edge(prompt)
    if edge_data is None:
        return None
    if edge_data["object_id"] != slider_object.Id:
        print("Select an edge on the slider object.")
        return None
    circle = assembly_common.circle_from_edge(edge_data["edge"], doc.ModelAbsoluteTolerance)
    if circle is None:
        print("Edge must be circular.")
        return None
    return {"edge_index": int(edge_data["edge_index"]), "circle": circle}


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    obj = assembly_common.prompt_for_one_object("Select object to constrain as a slider")
    if obj is None:
        return Result.Cancel

    first_edge = _prompt_for_part_axis_edge(
        "Select first circular edge on the slider axis", obj, doc
    )
    if first_edge is None:
        return Result.Cancel

    second_edge = _prompt_for_part_axis_edge(
        "Select second circular edge on the slider axis", obj, doc
    )
    if second_edge is None:
        return Result.Cancel
    first_circle = first_edge["circle"]
    second_circle = second_edge["circle"]

    part_axis_direction = second_circle.Center - first_circle.Center
    if not part_axis_direction.Unitize() or part_axis_direction.IsTiny():
        print("The two circular edge centers must be distinct.")
        return Result.Cancel
    part_axis_origin = first_circle.Center

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
    _send_setup_record(
        {
            "type": "slider",
            "object_id": str(obj.Id),
            "edge_indexes": [first_edge["edge_index"], second_edge["edge_index"]],
            "world_axis_origin": [
                world_axis_origin.X,
                world_axis_origin.Y,
                world_axis_origin.Z,
            ],
            "world_axis_direction": [
                world_axis_direction.X,
                world_axis_direction.Y,
                world_axis_direction.Z,
            ],
        }
    )
    assembly_scheduler.expire_document(doc, reason="add slider {}".format(str(obj.Id)[:8]))
    print("[Ondsel assembly] slider set for {} and solved.".format(str(obj.Id)[:8]))
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
