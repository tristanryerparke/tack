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
    handlers, metadata, runtime, _, utils = tack_modules()
    doc = sc.doc
    assert doc is not None, "Open a Rhino document before running this test"

    handlers.unsubscribe()
    runtime.stop_runtime()

    parent_id = box((0, 0, 0), (2, 2, 2))
    child_id = box((-2, -2, -2), (0, 0, 0))
    assert parent_id and child_id, "Could not create the test boxes"

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    parent = doc.Objects.Find(parent_id)
    child = doc.Objects.Find(child_id)
    matches = utils.coincident_vertices(parent, child, tolerance)
    assert len(matches) == 1, "Expected one shared vertex, got {}".format(len(matches))

    (
        parent_vertex_type,
        parent_vertex_index,
        child_vertex_type,
        child_vertex_index,
        parent_point,
        child_point,
    ) = matches[0]
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
