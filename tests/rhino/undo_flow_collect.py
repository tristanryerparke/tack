"""Collect saved parent and child plane origins between native undo-flow commands."""

import sys

import System
import scriptcontext as sc

sys.modules.pop("common", None)
from common import point_data, run_flow_step


def _origin(doc, definition):
    from tack import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return plane.Origin


def collect_undo_flow():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    plane_link._remove_runtime(doc)
    assert plane_link.restore_document(doc, default_display_enabled=False) == 1
    link = plane_link_metadata.all_links(doc)[0]
    parent = doc.Objects.Find(System.Guid.Parse(link["parent_id"]))
    child = doc.Objects.Find(System.Guid.Parse(link["child_id"]))
    assert parent is not None and child is not None
    return {
        "parent": point_data(_origin(doc, link["parent_plane"])),
        "child": point_data(_origin(doc, link["child_plane"])),
    }


run_flow_step("undo_flow_collect", collect_undo_flow)
