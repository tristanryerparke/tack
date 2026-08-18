import sys

sys.modules.pop("common", None)

from common import run_step
from common import sc

from ondsel.assembly import assembly_common


STATE_KEY = "Ondsel.IntegrationTest.UndoBundling"


def _center(doc, object_id):
    obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    if obj is None:
        return None
    center = obj.Geometry.GetBoundingBox(True).Center
    return [center.X, center.Y, center.Z]


def collect():
    doc = sc.doc
    state = sc.sticky[STATE_KEY]

    # No pump: with the synchronous scheduler there is nothing to pump.
    # If the child is back at its original position already, the solve
    # demonstrably ran inside the Move command's EndCommand.
    child_before_pump = _center(doc, state["child_object_id"])
    base_after_move = _center(doc, state["base_object_id"])

    return {
        "child_center_before_pump": child_before_pump,
        "base_center_after_move": base_after_move,
        "original_base": state["original_base"],
        "original_child": state["original_child"],
    }


run_step("ondsel_undo_after_move", collect)
