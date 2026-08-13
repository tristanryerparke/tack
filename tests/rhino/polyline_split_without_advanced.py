import scriptcontext as sc

from common import assert_close
from common import point_from_data
from common import run_step
from common import tack_modules


POLYLINE_SPLIT_STATE_KEY = "Tack.IntegrationTest.PolylineSplit"
STEP_KEY = "Tack.IntegrationTest.PolylineSplitWithoutAdvanced"


def arm_split_without_advanced():
    _, _, _, utils = tack_modules()
    from tack import link

    fixture = sc.sticky[POLYLINE_SPLIT_STATE_KEY]
    utils.ADVANCED_RECONCILIATION = False
    breaks = []
    original_break_link = link.break_link

    def record_break(state, reason):
        state["broken"] = True
        breaks.append(reason)

    link.break_link = record_break
    sc.sticky[STEP_KEY] = {
        "breaks": breaks,
        "original_break_link": original_break_link,
        "state": fixture,
    }


def collect_split_without_advanced():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis
    from tack import link
    from tack import scheduler

    step = sc.sticky.pop(STEP_KEY)
    fixture = step["state"]
    try:
        scheduler.solve_now(sc.doc)
    finally:
        link.break_link = step["original_break_link"]

    state = runtime.states(sc.doc)[fixture["link_id"]]
    assert state["broken"], "Split did not break Tack"
    assert step["breaks"], "Split did not invoke the Tack break alert"
    assert "linked parent" in step["breaks"][0]

    child = utils.find_object(sc.doc, state["child_id"])
    assert child is not None
    saved_link = metadata.read_link(child, fixture["link_id"])
    assert saved_link is not None
    child_anchor = dict(bbox_analysis.anchors(child))[
        saved_link["child_anchor"]["index"]
    ]
    assert_close(
        child_anchor,
        point_from_data(fixture["child_anchor"]),
        max(sc.doc.ModelAbsoluteTolerance, 1e-7),
        "split child remained in place",
    )


action = (
    collect_split_without_advanced
    if STEP_KEY in sc.sticky
    else arm_split_without_advanced
)
run_step(action.__name__, action)
