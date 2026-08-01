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
    _, _, _, _, utils = tack_modules()
    doc = sc.doc
    state = sc.sticky.get(STATE_KEY)
    assert state is not None, "Missing fixture; run setup_coincident_pair first"

    rs.UnselectAllObjects()
    assert rs.SelectObject(state["parent_id"]), "Could not select the parent"
    pause("before parent move")
    assert rs.Command("_Move 0,0,0 10,0,0", echo=False), "Rhino Move command failed"
    pause("after parent move")

    tack_state = sc.sticky[utils.RUNTIME_KEY]
    child = doc.Objects.Find(tack_state["child_id"])
    assert child is not None, "Tack lost the child object"
    child_after = utils.vertices_as_points(child)
    assert len(child_after) == len(state["child_before"]), "Child topology changed unexpectedly"
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    for index, (before, after) in enumerate(zip(state["child_before"], child_after)):
        assert_close(
            after,
            translated(point_from_data(before), MOVE),
            tolerance,
            "child vertex {}".format(index),
        )

    _, vertex_index, child_point = state["child_vertex"]
    linked_child = utils.get_vertex_from_brep(child, vertex_index)
    assert_close(
        linked_child,
        translated(point_from_data(child_point), MOVE),
        tolerance,
        "linked child vertex",
    )
    return {
        "name": "parent_move_translates_child",
        "child_vertices": [point_data(point) for point in child_after],
        "expected_child_vertices": [
            point_data(translated(point_from_data(point), MOVE))
            for point in state["child_before"]
        ],
    }


run_step("test_parent_move_translates_child", test_parent_move)
