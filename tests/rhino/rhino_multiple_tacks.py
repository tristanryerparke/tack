import sys

import Rhino

sys.modules.pop("common", None)

from common import STATE_KEY
from common import assert_close
from common import pause
from common import point_data
from common import point_from_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules
from common import translated


MOVE = Rhino.Geometry.Vector3d(0, 10, 0)
STEP_KEY = "multiple_tacks_move"


def arm_multiple_tacks_move():
    _, _, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    state = sc.sticky[STATE_KEY]
    assert len(runtime.states(sc.doc)) == 2
    first_child = utils.find_object(sc.doc, state["child_id"])
    state[STEP_KEY] = [
        (index, point_data(point))
        for index, point in bbox_analysis.anchors(first_child)
    ]

    rs.UnselectAllObjects()
    assert rs.SelectObject(state["parent_id"]), "Could not select the first parent"
    assert rs.SelectObject(
        state["second_parent_id"]
    ), "Could not select the second parent"


def collect_multiple_tacks_move():
    _, metadata, _, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    state = sc.sticky[STATE_KEY]
    first_child_before = state.pop(STEP_KEY)
    pause("after simultaneous move")

    first_child = utils.find_object(doc, state["child_id"])
    second_child = utils.find_object(doc, state["second_child_id"])
    first_child_after = bbox_analysis.anchors(first_child)
    second_child_after = bbox_analysis.anchors(second_child)
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    for (_, before), (_, after) in zip(first_child_before, first_child_after):
        assert_close(
            after,
            translated(point_from_data(before), MOVE),
            tolerance,
            "first Tack child anchor after simultaneous move",
        )
    for (_, before), (_, after) in zip(
        state["second_child_before"],
        second_child_after,
    ):
        assert_close(
            after,
            translated(point_from_data(before), MOVE),
            tolerance,
            "second Tack child anchor after simultaneous move",
        )

    expected_ids = {state["link_id"], state["second_link_id"]}
    saved_links = {
        saved_link["link_id"]: saved_link
        for saved_link in metadata.all_links(doc)
    }
    assert expected_ids <= set(saved_links), (
        "One or more Tacks lost child metadata after moving both parents"
    )
    for link_id, parent_id, child_id in (
        (state["link_id"], state["parent_id"], state["child_id"]),
        (
            state["second_link_id"],
            state["second_parent_id"],
            state["second_child_id"],
        ),
    ):
        child = utils.find_object(doc, child_id)
        parent = utils.find_object(doc, parent_id)
        assert metadata.read_link(child, link_id) is not None
        assert metadata.read_parent_links(parent).get(link_id) == str(child.Id)


action = (
    collect_multiple_tacks_move
    if STEP_KEY in sc.sticky.get(STATE_KEY, {})
    else arm_multiple_tacks_move
)
run_step(action.__name__, action)
