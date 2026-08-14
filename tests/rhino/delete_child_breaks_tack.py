import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import run_step
from common import sc
from common import tack_modules


def test_delete_child_breaks_tack():
    handlers, _, runtime, _ = tack_modules()
    from tack import link
    from tack import scheduler

    doc = sc.doc
    fixture = sc.sticky.get(STATE_KEY)
    assert fixture is not None, "Missing fixture; run setup_bbox_circles first"

    link_state = runtime.states(doc)[fixture["link_id"]]
    reasons = []
    original_break_link = link.break_link

    def record_break(state, reason):
        reasons.append(reason)
        state["broken"] = True

    link.break_link = record_break
    try:
        assert doc.Objects.Delete(fixture["child_id"], True), "Could not delete child"
        handlers.EndCommandHandler(None, None)
        scheduler.solve_now(doc)
    finally:
        link.break_link = original_break_link

    assert reasons, "Deleting a Tack child did not break its relationship"
    assert link_state["broken"], "Deleting a Tack child did not mark it broken"
    return {
        "name": "delete_child_breaks_tack",
        "reason": reasons[0],
    }


run_step("delete_child_breaks_tack", test_delete_child_breaks_tack)
