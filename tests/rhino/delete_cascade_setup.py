"""Create one parent/child Tack and reset undo history for the cascade flow."""

import sys

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, run_flow_step

STICKY_KEY = "Tack.DeleteCascade"


def setup_delete_cascade():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    cleanup(doc)
    parent_id = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
    child_id = add_circle(doc, Rhino.Geometry.Point3d(10, 0, 0))
    link = plane_link_metadata.create(
        doc,
        parent_id,
        child_id,
        circular_plane_definition(parent_id),
        circular_plane_definition(child_id),
        False,
    )
    assert link is not None, "Could not create test relationship"
    assert plane_link.install(doc, link) is not None, "Could not install"
    doc.ClearUndoRecords(True)
    sc.sticky[STICKY_KEY] = {
        "link_id": link["link_id"],
        "parent_id": str(parent_id),
        "child_id": str(child_id),
    }
    import rhinoscriptsyntax as rs

    rs.UnselectAllObjects()
    assert rs.SelectObject(str(child_id)), "Could not select child"
    return {"link_id": link["link_id"]}


run_flow_step("delete_cascade_setup", setup_delete_cascade)
