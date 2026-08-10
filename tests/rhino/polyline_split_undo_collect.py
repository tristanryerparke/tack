import time

import scriptcontext as sc
from rhino_watcher import send_data_sync
from rhino_watcher import websocket_output_sync

from common import assert_close
from common import point_from_data
from common import tack_modules


STATE_KEY = "Tack.IntegrationTest.PolylineSplit"


def collect():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.polyline_vertex as polyline_vertex_analysis
    from tack import link
    from tack import scheduler

    doc = sc.doc
    assert doc.Undo()
    time.sleep(1)
    scheduler.solve_now(doc)
    fixture = sc.sticky[STATE_KEY]
    state = runtime.states(doc)[fixture["link_id"]]
    assert not state["broken"]
    assert utils.same_id(state["parent_id"], fixture["parent_id"])

    parent = utils.find_object(doc, fixture["parent_id"])
    child = utils.find_object(doc, fixture["child_id"])
    assert parent is not None and child is not None
    assert type(parent.Geometry).__name__ == "PolylineCurve"

    saved_link = metadata.read_link(child, fixture["link_id"])
    assert saved_link is not None
    assert utils.same_id(saved_link["parent_id"], parent.Id)
    assert saved_link["parent_anchor"] == {
        "anchor_type": polyline_vertex_analysis.ANCHOR_TYPE,
        "index": 0,
    }

    expected_parent_anchor = point_from_data(fixture["parent_anchor"])
    expected_child_anchor = point_from_data(fixture["child_anchor"])
    inspection = link.inspect_link(doc, state)
    assert inspection is not None
    assert_close(
        inspection["parent_anchor"],
        expected_parent_anchor,
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "restored split parent anchor",
    )
    assert_close(
        inspection["child_anchor"],
        expected_child_anchor,
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "restored split child anchor",
    )
    assert_close(
        inspection["target_child_anchor"],
        inspection["child_anchor"],
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "restored split Tack offset",
    )

    return {
        "name": "polyline_split_undo_restores_tack",
        "restored_parent_id": str(parent.Id),
        "link_parent_id": saved_link["parent_id"],
    }


with websocket_output_sync():
    send_data_sync(collect())
    print("PASS polyline_split_undo_restores_tack")
