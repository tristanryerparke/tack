"""Persist a planar-face offset constraint in the active Ondsel assembly.

Run from the Tack repository root:

    uv run rhino-watch ondsel/assembly/assembly_add_planar_offset.py --debug --nostop

The first selected face is anchored in world space. The second can slide in
that face plane and spin about its normal, but its signed normal offset and
parallelism are maintained after subsequent Rhino commands.
"""
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

assembly_common = importlib.reload(assembly_common)
assembly_model = importlib.reload(assembly_model)
assembly_scheduler = importlib.reload(assembly_scheduler)


def _send_setup_record(record):
    from run_in_rhino.rhino_env.client import SocketConnection

    SocketConnection().send_data(record)


def _prompt_for_offset(initial_offset):
    getter = Rhino.Input.Custom.GetOption()
    getter.SetCommandPrompt(
        "Set signed planar-face offset ({:.4f}); press Enter to accept".format(
            initial_offset
        )
    )
    getter.AcceptNothing(True)
    offset = Rhino.Input.Custom.OptionDouble(initial_offset)
    getter.AddOptionDouble("Offset", offset)
    while True:
        result = getter.Get()
        if result == Rhino.Input.GetResult.Cancel:
            return None
        if result == Rhino.Input.GetResult.Nothing:
            return float(offset.CurrentValue)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    side_a = assembly_common.prompt_for_one_planar_brep_face(
        "Select planar face on FIXED parent object"
    )
    if side_a is None:
        return Result.Cancel

    side_b = assembly_common.prompt_for_one_planar_brep_face(
        "Select planar face on child object to MOVE"
    )
    if side_b is None:
        return Result.Cancel
    if str(side_a["object_id"]) == str(side_b["object_id"]):
        print("Select faces on two different objects.")
        return Result.Cancel

    initial_offset = (side_b["plane"].Origin - side_a["plane"].Origin) * side_a[
        "plane"
    ].ZAxis
    offset = _prompt_for_offset(initial_offset)
    if offset is None:
        return Result.Cancel

    constraint = assembly_model.add_planar_offset(doc, side_a, side_b, offset)
    if constraint is None:
        print("Could not create planar-face markers.")
        return Result.Failure

    assembly_model.subscribe()
    _send_setup_record(
        {
            "type": "planar_offset",
            "offset": offset,
            "a": {
                "object_id": str(side_a["object_id"]),
                "face_index": side_a["face_index"],
            },
            "b": {
                "object_id": str(side_b["object_id"]),
                "face_index": side_b["face_index"],
            },
        }
    )
    assembly_scheduler.expire_document(
        doc,
        reason="add planar offset {}".format(constraint["id"][:8]),
    )
    print(
        "[Ondsel assembly] planar offset {} added; parent anchored and "
        "EndCommand handler subscribed.".format(constraint["id"][:8])
    )
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
