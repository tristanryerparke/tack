import sys

sys.modules.pop("common", None)

import Rhino

from common import assert_close
from common import point_data
from common import rs
from common import run_step
from common import sc
from common import tack_modules


MOVE = Rhino.Geometry.Vector3d(5, 7, 0)
TEST_OBJECT_KEY = "Tack.IntegrationTest.NestedObject"


def test_nested_tack():
    handlers, metadata, runtime, utils = tack_modules(reload_modules=True)
    import tack.analysis.bbox as bbox
    from tack import document_runtime

    doc = sc.doc
    handlers.unsubscribe()
    runtime.stop_runtime(doc)
    object_ids = []

    def anchor(obj):
        return (
            bbox.ANCHOR_TYPE,
            bbox.CENTER_INDEX,
            dict(bbox.anchors(obj))[bbox.CENTER_INDEX],
        )

    try:
        object_ids.extend(rs.AddCircle((x, 0, 0), 2) for x in (0, 10, 20))
        assert all(object_ids)
        for object_id in object_ids:
            obj = doc.Objects.Find(object_id)
            attributes = obj.Attributes.Duplicate()
            attributes.UserDictionary.Set(TEST_OBJECT_KEY, True)
            assert doc.Objects.ModifyAttributes(obj.Id, attributes, True)

        a, b, c = [doc.Objects.Find(object_id) for object_id in object_ids]
        ab = metadata.write_link(doc, a.Id, b.Id, anchor(a), anchor(b))
        bc = metadata.write_link(doc, b.Id, c.Id, anchor(b), anchor(c))
        assert ab and bc
        assert metadata.write_link(doc, c.Id, a.Id, anchor(c), anchor(a)) is None
        assert runtime.start_runtime(doc, a.Id, b.Id, ab)
        assert runtime.start_runtime(doc, b.Id, c.Id, bc)
        handlers.subscribe()

        rs.UnselectAllObjects()
        assert rs.SelectObject(a.Id)
        assert rs.Command("_Move 0,0,0 5,7,0", echo=False)

        states = runtime.states(doc)
        a = utils.find_object(doc, states[ab]["parent_id"])
        b = utils.find_object(doc, states[ab]["child_id"])
        c = utils.find_object(doc, states[bc]["child_id"])
        centers = [dict(bbox.anchors(obj))[bbox.CENTER_INDEX] for obj in (a, b, c)]
        tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
        for label, actual, before in zip("ABC", centers, (0, 10, 20)):
            assert_close(
                actual,
                Rhino.Geometry.Point3d(before, 0, 0) + MOVE,
                tolerance,
                "nested Tack object {}".format(label),
            )
        assert not (document_runtime.try_get_value(doc, utils.SCHEDULE_KEY) or set())
        assert not states[ab]["broken"] and not states[bc]["broken"]
        return {
            "name": "nested_tack_cascades_in_one_command",
            "centers": [point_data(center) for center in centers],
        }
    finally:
        handlers.unsubscribe()
        runtime.stop_runtime(doc)
        for obj in list(doc.Objects):
            try:
                tagged = bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
            except Exception:
                tagged = False
            if tagged:
                doc.Objects.Delete(obj.Id, True)
        for saved_link in metadata.all_links(doc):
            runtime.start_runtime(
                doc,
                saved_link["parent_id"],
                saved_link["child_id"],
                saved_link["link_id"],
                redraw=False,
            )
        if runtime.has_any_runtime():
            handlers.subscribe()
        doc.Views.Redraw()


run_step("nested_tack_cascades_in_one_command", test_nested_tack)
