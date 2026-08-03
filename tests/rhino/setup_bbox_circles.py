import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import TEST_OBJECT_KEY
from common import pause
from common import point_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules


def _anchor(bbox_analysis, obj):
    return (
        bbox_analysis.ANCHOR_TYPE,
        bbox_analysis.CENTER_INDEX,
        dict(bbox_analysis.anchors(obj))[bbox_analysis.CENTER_INDEX],
    )


def _mark_test_object(doc, object_id):
    obj = doc.Objects.Find(object_id)
    assert obj is not None, "Could not find test object {}".format(object_id)
    attrs = obj.Attributes.Duplicate()
    attrs.UserDictionary.Set(TEST_OBJECT_KEY, True)
    assert doc.Objects.ModifyAttributes(obj.Id, attrs, True), (
        "Could not mark test object {}".format(object_id)
    )


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
    child_id = rs.AddCircle((10, 0, 0), 2)
    second_parent_id = rs.AddPolyline(
        [
            (-2, 18, 0),
            (2, 18, 0),
            (2, 22, 0),
            (-2, 22, 0),
            (-2, 18, 0),
        ]
    )
    second_child_id = rs.AddText("Tack child", (10, 20, 0), height=1.0)
    fixture.update(
        {
            "parent_id": parent_id,
            "child_id": child_id,
            "second_parent_id": second_parent_id,
            "second_child_id": second_child_id,
        }
    )
    object_ids = (parent_id, child_id, second_parent_id, second_child_id)
    assert all(object_ids), "Could not create the test objects"
    for object_id in object_ids:
        _mark_test_object(doc, object_id)

    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    parent_anchor = _anchor(bbox_analysis, parent)
    child_anchor = _anchor(bbox_analysis, child)
    link_id = metadata.write_link(
        doc,
        parent_id,
        child_id,
        parent_anchor,
        child_anchor,
    )
    assert link_id is not None
    fixture["link_id"] = link_id

    second_parent = doc.Objects.Find(second_parent_id)
    second_child = doc.Objects.Find(second_child_id)
    second_link_id = metadata.write_link(
        doc,
        second_parent_id,
        second_child_id,
        _anchor(bbox_analysis, second_parent),
        _anchor(bbox_analysis, second_child),
    )
    assert second_link_id is not None
    fixture["second_link_id"] = second_link_id

    saved_link = metadata.read_link(child, link_id)
    assert saved_link["link_id"] == link_id
    assert saved_link["parent_anchor"] == {
        "anchor_type": bbox_analysis.ANCHOR_TYPE,
        "index": bbox_analysis.CENTER_INDEX,
    }
    assert saved_link["child_anchor"] == {
        "anchor_type": bbox_analysis.ANCHOR_TYPE,
        "index": bbox_analysis.CENTER_INDEX,
    }
    assert set(saved_link) == {
        "version",
        "link_id",
        "parent_id",
        "child_id",
        "parent_anchor",
        "child_anchor",
        "offset",
    }
    assert metadata.read_parent_links(parent)[link_id] == str(child_id)

    assert runtime.start_runtime(parent_id, child_id, link_id), "Could not start Tack"
    assert runtime.start_runtime(
        second_parent_id,
        second_child_id,
        second_link_id,
    ), "Could not start second Tack"
    assert len(runtime.states()) == 2
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
    fixture["second_child_before"] = [
        (index, point_data(point))
        for index, point in bbox_analysis.anchors(second_child)
    ]
    pause("fixture installed")


run_step("setup_bbox_circles", setup)
