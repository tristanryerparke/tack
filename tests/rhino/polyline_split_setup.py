import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc
from rhino_watcher import send_data_sync
from rhino_watcher import websocket_output_sync

sys.modules.pop("common", None)

from common import TEST_OBJECT_KEY
from common import tack_modules


STATE_KEY = "Tack.IntegrationTest.PolylineSplit"


def _mark(doc, object_id):
    obj = doc.Objects.Find(object_id)
    assert obj is not None
    attributes = obj.Attributes.Duplicate()
    attributes.UserDictionary.Set(TEST_OBJECT_KEY, True)
    assert doc.Objects.ModifyAttributes(obj.Id, attributes, True)


def _is_marked(obj):
    try:
        return bool(obj.Attributes.UserDictionary[TEST_OBJECT_KEY])
    except Exception:
        return False


def _delete_marked(doc):
    for obj in list(doc.Objects):
        if obj is not None and _is_marked(obj):
            doc.Objects.Delete(obj.Id, True)


def setup():
    handlers, metadata, runtime, utils = tack_modules(reload_modules=True)
    import tack.analysis.polyline_vertex as polyline_vertex_analysis

    utils.ADVANCED_RECONCILIATION = True
    doc = sc.doc
    assert doc is not None
    handlers.unsubscribe()
    runtime.stop_runtime(doc)
    _delete_marked(doc)

    parent_id = rs.AddPolyline(
        [
            (-5, -5, 0),
            (5, -5, 0),
            (5, 5, 0),
            (-5, 5, 0),
            (-5, -5, 0),
        ]
    )
    child_id = rs.AddPolyline(
        [
            (15, -5, 0),
            (25, -5, 0),
            (25, 5, 0),
            (15, 5, 0),
            (15, -5, 0),
        ]
    )
    assert parent_id is not None and child_id is not None
    _mark(doc, parent_id)
    _mark(doc, child_id)

    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    parent_anchor = dict(polyline_vertex_analysis.anchors(parent))[0]
    child_anchor = dict(polyline_vertex_analysis.anchors(child))[0]
    link_id = metadata.write_link(
        doc,
        parent_id,
        child_id,
        (
            polyline_vertex_analysis.ANCHOR_TYPE,
            0,
            parent_anchor,
        ),
        (
            polyline_vertex_analysis.ANCHOR_TYPE,
            0,
            child_anchor,
        ),
    )
    assert link_id is not None
    assert runtime.start_runtime(doc, parent_id, child_id, link_id)

    cutter_id = rs.AddCircle((4, 0, 0), 4)
    assert cutter_id is not None
    _mark(doc, cutter_id)

    sc.sticky[STATE_KEY] = {
        "parent_id": str(parent_id),
        "child_id": str(child_id),
        "cutter_id": str(cutter_id),
        "link_id": link_id,
        "parent_anchor": [
            parent_anchor.X,
            parent_anchor.Y,
            parent_anchor.Z,
        ],
        "child_anchor": [child_anchor.X, child_anchor.Y, child_anchor.Z],
    }

    handlers.subscribe()
    rs.UnselectAllObjects()
    return {
        "parent_id": str(parent_id),
        "cutter_id": str(cutter_id),
    }


with websocket_output_sync():
    setup_data = setup()
    send_data_sync(setup_data)
    print(
        "Polyline split fixture ready parent={} cutter={}".format(
            setup_data["parent_id"],
            setup_data["cutter_id"],
        )
    )
