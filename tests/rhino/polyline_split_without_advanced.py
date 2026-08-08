import scriptcontext as sc

from common import assert_close
from common import point_from_data
from common import rs
from common import run_step
from common import suppress_break_alerts
from common import tack_modules


POLYLINE_SPLIT_STATE_KEY = "Tack.IntegrationTest.PolylineSplit"


def split_without_advanced_reconciliation():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    fixture = sc.sticky[POLYLINE_SPLIT_STATE_KEY]
    utils.ADVANCED_RECONCILIATION = False
    link_id = fixture["link_id"]
    state = runtime.states(doc)[link_id]
    parent_id = fixture["parent_id"]
    cutter_id = fixture["cutter_id"]

    with suppress_break_alerts() as breaks:
        rs.UnselectAllObjects()
        command_result = rs.Command(
            "_Split _SelID {} _Enter _SelID {} _Enter".format(
                parent_id,
                cutter_id,
            ),
            echo=False,
        )
        from tack import scheduler

        scheduler.solve_now(doc)

    assert command_result, "Rhino Split command failed"
    assert state["broken"], "Split did not break Tack"
    assert breaks, "Split did not invoke the Tack break alert"

    child = utils.find_object(doc, state["child_id"])
    assert child is not None
    saved_link = metadata.read_link(child, link_id)
    assert saved_link is not None
    expected_child_anchor = point_from_data(fixture["child_anchor"])
    child_anchor = dict(bbox_analysis.anchors(child))[
        saved_link["child_anchor"]["index"]
    ]
    assert_close(
        child_anchor,
        expected_child_anchor,
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "split child remained in place",
    )

    return {
        "name": "polyline_split_breaks_without_advanced_reconciliation",
        "reason": breaks[0],
        "child_id": str(child.Id),
    }


run_step(
    "polyline_split_without_advanced_reconciliation",
    split_without_advanced_reconciliation,
)
