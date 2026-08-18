import sys

sys.modules.pop("common", None)

from common import run_step
from common import sc

from ondsel.assembly import assembly_common
from ondsel.assembly import assembly_model


STATE_KEY = "Ondsel.IntegrationTest.UndoBundling"


def _center(doc, object_id):
    obj = doc.Objects.FindId(assembly_common.parse_guid(object_id))
    if obj is None:
        return None
    center = obj.Geometry.GetBoundingBox(True).Center
    return [center.X, center.Y, center.Z]


def collect():
    doc = sc.doc
    state = sc.sticky.pop(STATE_KEY, None)
    assert state is not None, "Undo-bundling fixture missing"

    data = assembly_model.read_data(doc)
    parts = list(data["parts"].values())
    live_ids = {part["name"]: part["object_id"] for part in parts}

    return {
        "base_center_after_undo": _center(doc, state["base_object_id"]),
        "child_center_after_undo": _center(doc, state["child_object_id"]),
        "original_base": state["original_base"],
        "original_child": state["original_child"],
        "live_ids": {name: str(value) for name, value in live_ids.items()},
    }


run_step("ondsel_undo_after_undo", collect, send_done=True)
