import Rhino
import scriptcontext as sc

from common import STATE_KEY
from common import assert_close
from common import pause
from common import rs
from common import run_step
from common import tack_modules


MOVE = Rhino.Geometry.Vector3d(10, 0, 0)
MOVE_STATE_KEY = "allowed_child_move"


def arm_child_move():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    fixture = sc.sticky[STATE_KEY]
    utils.set_setting("allow_child_movement", True)

    state = runtime.states(sc.doc)[fixture["link_id"]]
    child = utils.find_object(sc.doc, state["child_id"])
    assert child is not None
    anchor_index = fixture["child_anchor"][1]
    fixture[MOVE_STATE_KEY] = {
        "anchor_index": anchor_index,
        "before_anchor": dict(bbox_analysis.anchors(child))[anchor_index],
        "before_offset": list(metadata.read_link(child, fixture["link_id"])["offset"]),
    }

    rs.UnselectAllObjects()
    assert rs.SelectObject(state["child_id"])


def collect_child_move():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    fixture = sc.sticky[STATE_KEY]
    before = fixture.pop(MOVE_STATE_KEY)
    pause("after allowed child move")

    state = runtime.states(doc)[fixture["link_id"]]
    assert not state["broken"]
    child = utils.find_object(doc, state["child_id"])
    assert child is not None
    after_anchor = dict(bbox_analysis.anchors(child))[before["anchor_index"]]
    assert_close(
        after_anchor,
        before["before_anchor"] + MOVE,
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "allowed child movement",
    )

    saved_link = metadata.read_link(child, fixture["link_id"])
    assert saved_link is not None
    assert saved_link["offset"][0] == before["before_offset"][0] + MOVE.X


action = (
    collect_child_move
    if MOVE_STATE_KEY in sc.sticky.get(STATE_KEY, {})
    else arm_child_move
)
run_step(action.__name__, action)
