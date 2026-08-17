import sys

sys.modules.pop("common", None)

from common import pause
from common import point_data
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
    fixture = sc.sticky.pop(UNDO_STATE_KEY, None)
    assert fixture is not None, "Undo-bundling fixture missing"
    parent_before_pump = point_data(
        _center(bbox_analysis, utils.find_object(doc, fixture["parent_id"]))
    )
    link_state = runtime.states(doc, create=False).get(fixture["link_id"])
    child_before_pump = None
    if link_state is not None:
        child_obj = utils.find_object(doc, link_state["child_id"])
        if child_obj is not None:
            child_before_pump = point_data(_center(bbox_analysis, child_obj))

    pause("after single undo")

    child = None
    if link_state is not None:
        child = utils.find_object(doc, link_state["child_id"])
    if child is None:
        child = utils.find_object(doc, fixture["child_id"])
    parent = utils.find_object(doc, fixture["parent_id"])

    if child is None or parent is None:
        return {
            "parent_center_before_undo_pump": parent_before_pump,
            "child_center_before_undo_pump": child_before_pump,
            "missing_objects": True,
            "parent_center_after_move": fixture["parent_center_after_move"],
            "child_center_after_move": fixture["child_center_after_move"],
            "original_parent": fixture["original_parent"],
            "original_child": fixture["original_child"],
        }

    return {
        "parent_center_before_undo_pump": parent_before_pump,
        "child_center_before_undo_pump": child_before_pump,
        "parent_center_after_undo": point_data(_center(bbox_analysis, parent)),
        "child_center_after_undo": point_data(_center(bbox_analysis, child)),
        "parent_center_after_move": fixture["parent_center_after_move"],
        "child_center_after_move": fixture["child_center_after_move"],
        "original_parent": fixture["original_parent"],
        "original_child": fixture["original_child"],
    }


run_step("undo_bundling_after_undo", collect, send_done=True)
