import sys

sys.modules.pop("common", None)

from common import TEST_OBJECT_KEY
from common import pause
from common import point_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules


UNDO_STATE_KEY = "Tack.IntegrationTest.UndoBundling"


def _anchor(bbox_analysis, obj):
    return (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        dict(bbox_analysis.anchors(obj))[bbox_analysis.CENTER_INDEX],
    )


def setup():
    handlers, metadata, runtime, utils = tack_modules(reload_modules=True)
    import tack.analysis.bbox as bbox_analysis

    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    handlers.unsubscribe()
    runtime.stop_runtime(doc)

    parent_id = rs.AddCircle((0, 0, 0), 2)
    child_id = rs.AddCircle((10, 0, 0), 2)
    assert parent_id and child_id, "Could not create the test objects"
    for object_id in (parent_id, child_id):
        obj = doc.Objects.Find(object_id)
        attrs = obj.Attributes.Duplicate()
        attrs.UserDictionary.Set(TEST_OBJECT_KEY, True)
        assert doc.Objects.ModifyAttributes(obj.Id, attrs, True)

    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    link_id = metadata.write_link(
        doc,
        parent_id,
        child_id,
        _anchor(bbox_analysis, parent),
        _anchor(bbox_analysis, child),
    )
    assert link_id is not None, "Could not write the Tack link"
    assert runtime.start_runtime(doc, parent_id, child_id, link_id)
    handlers.subscribe()

    sc.sticky[UNDO_STATE_KEY] = {
        "link_id": link_id,
        "parent_id": parent_id,
        "child_id": child_id,
        "original_parent": point_data(
            dict(bbox_analysis.anchors(parent))[bbox_analysis.CENTER_INDEX]
        ),
        "original_child": point_data(
            dict(bbox_analysis.anchors(child))[bbox_analysis.CENTER_INDEX]
        ),
    }

    rs.UnselectAllObjects()
    assert rs.SelectObject(parent_id), "Could not select the parent"
    pause("before parent move")

    return {
        "parent_id": str(parent_id),
        "child_id": str(child_id),
    }


run_step("undo_bundling_setup", setup)
