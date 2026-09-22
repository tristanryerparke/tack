"""Remove a Tack without changing geometry and leave one undo record."""

import sys

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, run_flow_step

STICKY_KEY = "Tack.ObjectMetadataUndo"


def setup_object_metadata_undo():
    from tack.links import (
        repository,
        runtime,
        state,
    )

    doc = sc.doc
    cleanup(doc)
    parent_id = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
    child_id = add_circle(doc, Rhino.Geometry.Point3d(10, 0, 0))
    link = repository.create(
        doc,
        parent_id,
        child_id,
        circular_plane_definition(parent_id),
        circular_plane_definition(child_id),
    )
    assert link is not None
    assert runtime.install(doc, link) is not None
    doc.ClearUndoRecords(True)

    assert runtime.remove_link(doc, link["link_id"])
    assert repository.read_link(doc, link["link_id"]) is None
    assert not state.states(doc, create=False)
    sc.sticky[STICKY_KEY] = {"link_id": link["link_id"]}
    return {"link_id": link["link_id"], "removed": True}


run_flow_step("object_metadata_undo_setup", setup_object_metadata_undo)
