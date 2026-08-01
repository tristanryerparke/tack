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


MOVE = Rhino.Geometry.Vector3d(10, 0, 0)


def test_parent_move():
    _, _, _, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    state = sc.sticky.get(STATE_KEY)
    assert state is not None, "Missing fixture; run setup_bbox_circles first"

    rs.UnselectAllObjects()
    assert rs.SelectObject(state["parent_id"]), "Could not select the parent"
    pause("before parent move")
    assert rs.Command("_Move 0,0,0 10,0,0", echo=False), "Rhino Move command failed"
    pause("after parent move")

    tack_state = sc.sticky[utils.RUNTIME_KEY]
    child = doc.Objects.Find(tack_state["child_id"])
    assert child is not None, "Tack lost the child object"
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
            translated(point_from_data(before), MOVE),
            tolerance,
            "child bounding-box anchor {}".format(index),
        )

    _, anchor_index, anchor_point = state["child_anchor"]
    linked_child = dict(child_after)[anchor_index]
    assert_close(
        linked_child,
        translated(point_from_data(anchor_point), MOVE),
        tolerance,
        "child anchor",
    )
    return {
        "name": "parent_move_translates_child",
        "child_anchors": [point_data(point) for _, point in child_after],
        "expected_child_anchors": [
            point_data(translated(point_from_data(point), MOVE))
            for _, point in state["child_before"]
        ],
    }


run_step("test_parent_move_translates_child", test_parent_move)
