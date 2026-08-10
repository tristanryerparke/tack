import Rhino
import scriptcontext as sc

from common import STATE_KEY
from common import assert_close
from common import point_data
from common import point_from_data
from common import pause
from common import rs
from common import run_step
from common import tack_modules


def test_child_move_updates_offset():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    fixture = sc.sticky.get(STATE_KEY)
    assert fixture is not None
    utils.set_setting("allow_child_movement", True)

    state_before = runtime.states(doc)[fixture["link_id"]]
    child_before = utils.find_object(doc, state_before["child_id"])
    assert child_before is not None
    anchor_index = fixture["child_anchor"][1]
    before_anchor = dict(bbox_analysis.anchors(child_before))[anchor_index]
    before_offset = list(metadata.read_link(child_before, fixture["link_id"])["offset"])

    rs.UnselectAllObjects()
    assert rs.SelectObject(state_before["child_id"])
    assert rs.Command("_Move 0,0,0 10,0,0", echo=False)
    pause("after allowed child move")

    state_after = runtime.states(doc)[fixture["link_id"]]
    assert not state_after["broken"]
    child_after = utils.find_object(doc, state_after["child_id"])
    assert child_after is not None
    after_anchor = dict(bbox_analysis.anchors(child_after))[anchor_index]
    assert_close(
        after_anchor,
        before_anchor + Rhino.Geometry.Vector3d(10, 0, 0),
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "allowed child movement",
    )
    saved_link = metadata.read_link(child_after, fixture["link_id"])
    assert saved_link is not None
    assert saved_link["offset"] != before_offset
    assert saved_link["offset"][0] == before_offset[0] + 10

    return {
        "name": "child_move_updates_offset_when_allowed",
        "offset_before": before_offset,
        "offset_after": saved_link["offset"],
        "child_anchor": point_data(after_anchor),
        "expected_child_anchor": point_data(
            point_from_data(point_data(before_anchor))
            + Rhino.Geometry.Vector3d(10, 0, 0)
        ),
    }


run_step("test_child_move_updates_offset", test_child_move_updates_offset)
