import sys

sys.modules.pop("common", None)

from common import pause
from common import point_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules


UNDO_STATE_KEY = "Tack.IntegrationTest.UndoBundling"


def _center(bbox_analysis, obj):
    return dict(bbox_analysis.anchors(obj))[bbox_analysis.CENTER_INDEX]


def collect():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    fixture = sc.sticky[UNDO_STATE_KEY]

    # Position BEFORE any pump: proves whether the solve ran inside the
    # Move command's EndCommand or only later (idle / manual pump).
    link_state = runtime.states(doc, create=False).get(fixture["link_id"])
    child_before_pump = None
    if link_state is not None:
        child_obj = utils.find_object(doc, link_state["child_id"])
        if child_obj is not None:
            child_before_pump = point_data(_center(bbox_analysis, child_obj))

    pause("after parent move")

    link_state = runtime.states(doc, create=False).get(fixture["link_id"])
    assert link_state is not None, "Tack runtime lost the link after the move"
    child = utils.find_object(doc, link_state["child_id"])
    parent = utils.find_object(doc, fixture["parent_id"])
    assert child is not None, "Tack lost the child after the move"
    assert parent is not None, "Tack lost the parent after the move"

    fixture["child_id"] = child.Id
    fixture["parent_center_after_move"] = point_data(
        _center(bbox_analysis, parent)
    )
    fixture["child_center_after_move"] = point_data(
        _center(bbox_analysis, child)
    )
    rs.UnselectAllObjects()

    return {
        "child_center_before_pump": child_before_pump,
        "parent_center_after_move": fixture["parent_center_after_move"],
        "child_center_after_move": fixture["child_center_after_move"],
        "original_parent": fixture["original_parent"],
        "original_child": fixture["original_child"],
    }


run_step("undo_bundling_after_move", collect)
