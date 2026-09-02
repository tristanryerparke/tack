"""Prepare the saved-link fixture for native Move, Undo, and Redo commands."""

import sys

import System
import rhinoscriptsyntax as rs
import scriptcontext as sc

sys.modules.pop("common", None)
from common import point_data, run_flow_step


def _origin(doc, definition):
    from tack import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return plane.Origin


def setup_undo_flow():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    plane_link._remove_runtime(doc)
    assert plane_link.restore_document(doc, default_display_enabled=False) == 1
    link = plane_link_metadata.all_links(doc)[0]
    parent_id = System.Guid.Parse(link["parent_id"])
    child_before = _origin(doc, link["child_plane"])
    parent_before = _origin(doc, link["parent_plane"])
    doc.ClearUndoRecords(True)
    rs.UnselectAllObjects()
    assert rs.SelectObject(parent_id)
    return {
        "parent_id": str(parent_id),
        "parent_before": point_data(parent_before),
        "child_before": point_data(child_before),
    }


run_flow_step("undo_flow_setup", setup_undo_flow)
