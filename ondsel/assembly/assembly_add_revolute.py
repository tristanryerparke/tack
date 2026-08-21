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


def _send_setup_record(record):
    from run_in_rhino.rhino_env.client import SocketConnection

    SocketConnection().send_data(record)

assembly_common = importlib.reload(assembly_common) if "assembly_common" in globals() else assembly_common
assembly_model = importlib.reload(assembly_model)
assembly_scheduler = importlib.reload(assembly_scheduler)


def RunCommand(is_interactive):
    doc = Rhino.RhinoDoc.ActiveDoc
    if doc is None:
        return Result.Cancel

    side_a = assembly_common.prompt_for_one_brep_edge(
        "Select circular edge on first object (parent)"
    )
    if side_a is None:
        return Result.Cancel

    side_b = assembly_common.prompt_for_one_brep_edge(
        "Select circular edge on second object (child to move)"
    )
    if side_b is None:
        return Result.Cancel

    if str(side_a["object_id"]) == str(side_b["object_id"]):
        print("Pick edges on two different objects.")
        return Result.Cancel

    if assembly_common.circle_from_edge(side_a["edge"], doc.ModelAbsoluteTolerance) is None:
        print("First edge is not circular.")
        return Result.Cancel
    if assembly_common.circle_from_edge(side_b["edge"], doc.ModelAbsoluteTolerance) is None:
        print("Second edge is not circular.")
        return Result.Cancel

    joint = assembly_model.add_revolute(doc, side_a, side_b)
    if joint is None:
        return Result.Failure
    _send_setup_record(
        {
            "type": "revolute",
            "a": {
                "object_id": str(side_a["object_id"]),
                "edge_index": int(side_a["edge_index"]),
            },
            "b": {
                "object_id": str(side_b["object_id"]),
                "edge_index": int(side_b["edge_index"]),
            },
        }
    )
    assembly_scheduler.expire_document(doc, reason="add revolute {}".format(joint["id"][:8]))
    print("[Ondsel assembly] added revolute {} and solved.".format(joint["id"][:8]))
    return Result.Success


if __name__ == "__main__":
    from tack.watcher import run_entrypoint

    run_entrypoint(lambda: RunCommand(True), True)
