import scriptcontext as sc
from rhino_watcher import send_data_sync
from rhino_watcher import websocket_output_sync

from common import TEST_OBJECT_KEY
from common import assert_close
from common import point_from_data
from common import tack_modules


STATE_KEY = "Tack.IntegrationTest.PolylineSplit"


def _is_marked(obj):
    try:
        return bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
    except Exception:
        return False


def collect():
    _, metadata, runtime, utils = tack_modules()
    import tack.analysis.polyline_vertex as polyline_vertex_analysis
    from tack import link

    doc = sc.doc
    fixture = sc.sticky[STATE_KEY]
    state = runtime.states(doc)[fixture["link_id"]]
    assert not state["broken"]
    assert not utils.same_id(state["parent_id"], fixture["parent_id"])

    parent = utils.find_object(doc, state["parent_id"])
    child = utils.find_object(doc, state["child_id"])
    assert parent is not None and child is not None
    assert type(parent.Geometry).__name__ == "PolylineCurve"

    saved_link = metadata.read_link(child, fixture["link_id"])
    assert saved_link is not None
    assert utils.same_id(saved_link["parent_id"], parent.Id)
    assert saved_link["parent_anchor"]["anchor_type"] == (
        polyline_vertex_analysis.ANCHOR_TYPE
    )

    expected_parent_anchor = point_from_data(fixture["parent_anchor"])
    expected_child_anchor = point_from_data(fixture["child_anchor"])
    parent_anchor = polyline_vertex_analysis.resolve(
        parent,
        saved_link["parent_anchor"],
    )
    child_anchor = polyline_vertex_analysis.resolve(
        child,
        saved_link["child_anchor"],
    )
    assert_close(
        parent_anchor,
        expected_parent_anchor,
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "split parent anchor",
    )
    assert_close(
        child_anchor,
        expected_child_anchor,
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "split child anchor",
    )

    inspection = link.inspect_link(doc, state)
    assert inspection is not None
    assert_close(
        inspection["target_child_anchor"],
        inspection["child_anchor"],
        max(doc.ModelAbsoluteTolerance, 1e-7),
        "split Tack offset",
    )

    split_candidates = [
        obj
        for obj in doc.Objects
        if obj is not None
        and _is_marked(obj)
        and not utils.same_id(obj.Id, fixture["child_id"])
        and not utils.same_id(obj.Id, fixture["cutter_id"])
    ]
    matching_candidates = [
        obj
        for obj in split_candidates
        if any(
            point.DistanceTo(expected_parent_anchor)
            <= max(doc.ModelAbsoluteTolerance, 1e-7)
            for _, point in polyline_vertex_analysis.anchors(obj)
        )
    ]
    assert len(split_candidates) >= 2
    assert len(matching_candidates) == 1
    assert utils.same_id(matching_candidates[0].Id, parent.Id)

    return {
        "name": "polyline_split_preserves_tack",
        "old_parent_id": fixture["parent_id"],
        "new_parent_id": str(parent.Id),
        "split_candidate_count": len(split_candidates),
        "matching_candidate_count": len(matching_candidates),
    }


with websocket_output_sync():
    send_data_sync(collect())
    print("PASS polyline_split_preserves_tack")
