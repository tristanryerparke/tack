import sys

sys.modules.pop("common", None)

from common import STATE_KEY
from common import box
from common import pause
from common import point_data
from common import run_step
from common import sc
from common import tack_modules


def setup():
    handlers, metadata, runtime, utils = tack_modules(reload_modules=True)
    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    handlers.unsubscribe()
    runtime.stop_runtime()

    parent_id = box((0, 0, 0), (2, 2, 2))
    child_id = box((10, 0, 0), (12, 2, 2))
    assert parent_id and child_id, "Could not create the test boxes"

    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    parent_vertex_type = child_vertex_type = "BrepVertex"
    parent_vertex_index = child_vertex_index = 0
    parent_point = utils.get_vertex_from_brep(parent, parent_vertex_index)
    child_point = utils.get_vertex_from_brep(child, child_vertex_index)
    assert metadata.write_link(
        doc,
        parent_id,
        child_id,
        (parent_vertex_type, parent_vertex_index),
        (child_vertex_type, child_vertex_index),
        parent_point,
        child_point,
    )
    assert runtime.start_runtime(parent_id, child_id), "Could not start Tack"
    handlers.subscribe()

    sc.sticky[STATE_KEY] = {
        "parent_id": parent_id,
        "child_id": child_id,
        "child_before": [
            point_data(point) for point in utils.vertices_as_points(child)
        ],
        "child_vertex": (child_vertex_type, child_vertex_index, point_data(child_point)),
    }
    pause("fixture installed")


run_step("setup_coincident_pair", setup)
