"""Prepare the saved-link fixture for native Move, Undo, and Redo commands."""

import sys

import rhinoscriptsyntax as rs
import scriptcontext as sc
import System

sys.modules.pop("common", None)
from common import point_data, run_flow_step


def _origin(doc, definition):
    from tack.anchors import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return plane.Origin


def setup_undo_flow():
    from tack.links import (
        repository,
        runtime,
    )

    doc = sc.doc
    runtime.remove_runtime(doc)
    assert runtime.restore_document(doc, default_display_enabled=False) == 1
    link = repository.all_links(doc)[0]
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
