import sys

import Rhino

sys.modules.pop("common", None)

from common import STATE_KEY
from common import assert_close
from common import point_data
from common import point_from_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules
from common import translated


MOVE = Rhino.Geometry.Vector3d(0, 10, 0)


def test_multiple_tacks():
    _, _, runtime, _ = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    state = sc.sticky.get(STATE_KEY)
    assert state is not None, "Missing fixture; run setup_bbox_circles first"
    assert len(runtime.states()) == 2

    first_child_before = [
        point_data(point)
        for _, point in bbox_analysis.anchors(
            doc.Objects.Find(state["child_id"])
        )
    ]

    rs.UnselectAllObjects()
    assert rs.SelectObject(
        state["second_parent_id"]
    ), "Could not select the second parent"
    assert rs.Command("_Move 0,0,0 0,10,0", echo=False), "Rhino Move command failed"

    second_child = doc.Objects.Find(state["second_child_id"])
    second_child_after = bbox_analysis.anchors(second_child)
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    for (_, before), (_, after) in zip(
        state["second_child_before"],
        second_child_after,
    ):
        assert_close(
            after,
            translated(point_from_data(before), MOVE),
            tolerance,
            "second Tack child anchor",
        )

    first_child_after = [
        point_data(point)
        for _, point in bbox_analysis.anchors(
            doc.Objects.Find(state["child_id"])
        )
    ]
    assert first_child_after == first_child_before
    return {
        "name": "multiple_tacks_are_independent",
        "second_child_anchors": [
            point_data(point) for _, point in second_child_after
        ],
        "expected_second_child_anchors": [
            point_data(translated(point_from_data(point), MOVE))
            for _, point in state["second_child_before"]
        ],
    }


run_step("test_multiple_tacks", test_multiple_tacks)
