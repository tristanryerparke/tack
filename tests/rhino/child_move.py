import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import assert_close
from common import pause
from common import point_from_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules


STEP_KEY = "child_move_armed"


def arm_child_move():
    state = sc.sticky[STATE_KEY]
    rs.UnselectAllObjects()
    assert rs.SelectObject(state["child_id"]), "Could not select the child"
    state[STEP_KEY] = True
    pause("before child move")


def collect_child_move():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    state = sc.sticky[STATE_KEY]
    state.pop(STEP_KEY)
    pause("after child move")

    tack_state = runtime.states(doc)[state["link_id"]]
    child = utils.find_object(doc, tack_state["child_id"])
    assert child is not None, "Tack lost the child object"
    saved_link = metadata.read_link(child, state["link_id"])
    assert saved_link is not None, "Child lost Tack metadata after its first move"
    parent = utils.find_object(doc, saved_link["parent_id"])
    assert parent is not None, "Tack lost the parent object"
    assert metadata.read_parent_links(parent).get(state["link_id"]) == str(
        child.Id
    ), "Parent lost its matching Tack link ID"
    child_after = bbox_analysis.anchors(child)
    assert [index for index, _ in child_after] == [
        index for index, _ in state["child_before"]
    ]
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    for index, ((_, before), (_, after)) in enumerate(
        zip(state["child_before"], child_after)
    ):
        assert_close(
            after,
            point_from_data(before),
            tolerance,
            "child bounding-box anchor {}".format(index),
        )

    _, anchor_index, anchor_point = state["child_anchor"]
    assert_close(
        dict(child_after)[anchor_index],
        point_from_data(anchor_point),
        tolerance,
        "child anchor",
    )


action = (
    collect_child_move
    if sc.sticky.get(STATE_KEY, {}).get(STEP_KEY)
    else arm_child_move
)
run_step(action.__name__, action)
