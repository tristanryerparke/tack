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


MOVE = Rhino.Geometry.Vector3d(10, 0, 0)


def test_child_move():
    _, _, _, utils = tack_modules()
    doc = sc.doc
    state = sc.sticky.get(STATE_KEY)
    assert state is not None, "Missing fixture; run setup_coincident_pair first"

    rs.UnselectAllObjects()
    assert rs.SelectObject(state["child_id"]), "Could not select the child"
    pause("before child move")
    assert rs.Command("_Move 0,0,0 10,0,0", echo=False), "Rhino Move command failed"
    pause("after child move")

    tack_state = sc.sticky[utils.RUNTIME_KEY]
    child = doc.Objects.Find(tack_state["child_id"])
    assert child is not None, "Tack lost the child object"
    child_after = utils.vertices_as_points(child)
    assert len(child_after) == len(state["child_before"]), "Child topology changed unexpectedly"
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    for index, (before, after) in enumerate(zip(state["child_before"], child_after)):
        assert_close(
            after,
            point_from_data(before),
            tolerance,
            "child vertex {}".format(index),
        )

    _, vertex_index, child_point = state["child_vertex"]
    linked_child = utils.get_vertex_from_brep(child, vertex_index)
    assert_close(
        linked_child,
        point_from_data(child_point),
        tolerance,
        "linked child vertex",
    )
    return {
        "name": "child_move_restores_child",
        "child_vertices": [point_data(point) for point in child_after],
        "expected_child_vertices": list(state["child_before"]),
    }


run_step("test_child_move_restores_child", test_child_move)
