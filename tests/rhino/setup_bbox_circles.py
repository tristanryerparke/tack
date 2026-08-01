import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import pause
from common import point_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules


def setup():
    handlers, metadata, runtime, _ = tack_modules(reload_modules=True)
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    handlers.unsubscribe()
    runtime.stop_runtime()

    fixture = {}
    sc.sticky[STATE_KEY] = fixture
    parent_id = rs.AddCircle((0, 0, 0), 2)
    fixture["parent_id"] = parent_id
    child_id = rs.AddCircle((10, 0, 0), 2)
    fixture["child_id"] = child_id
    assert parent_id and child_id, "Could not create the test circles"

    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    parent_anchor = (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        dict(bbox_analysis.anchors(parent))[bbox_analysis.CENTER_INDEX],
    )
    child_anchor = (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        dict(bbox_analysis.anchors(child))[bbox_analysis.CENTER_INDEX],
    )
    assert metadata.write_link(
        doc,
        parent_id,
        child_id,
        parent_anchor,
        child_anchor,
    )
    saved_link = metadata.read_link(doc.Objects.Find(child_id))
    assert saved_link["parent_anchor"]["anchor_type"] == bbox_analysis.ANCHOR_TYPE
    assert saved_link["child_anchor"]["anchor_type"] == bbox_analysis.ANCHOR_TYPE
    assert set(saved_link) == {
        "version",
        "parent_id",
        "child_id",
        "parent_anchor",
        "child_anchor",
        "offset",
    }
    assert runtime.start_runtime(parent_id, child_id), "Could not start Tack"
    handlers.subscribe()

    fixture["child_before"] = [
        (index, point_data(point))
        for index, point in bbox_analysis.anchors(child)
    ]
    fixture["child_anchor"] = (
        child_anchor[0],
        child_anchor[1],
        point_data(child_anchor[2]),
    )
    pause("fixture installed")


run_step("setup_bbox_circles", setup)
