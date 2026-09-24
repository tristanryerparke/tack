"""Collect saved parent and child plane origins between native undo-flow commands."""

import sys

import scriptcontext as sc
import System

sys.modules.pop("common", None)
from common import point_data, run_flow_step


def _origin(doc, definition):
    from tack.anchors import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return plane.Origin


def collect_undo_flow():
    from tack.links import (
        repository,
        runtime,
    )

    doc = sc.doc
    runtime.remove_runtime(doc)
    assert runtime.restore_document(doc, default_display_enabled=False) == 1
    link = repository.all_links(doc)[0]
    parent = doc.Objects.Find(System.Guid.Parse(link["parent_id"]))
    child = doc.Objects.Find(System.Guid.Parse(link["child_id"]))
    assert parent is not None and child is not None
    return {
        "parent": point_data(_origin(doc, link["parent_plane_def"])),
        "child": point_data(_origin(doc, link["child_plane_def"])),
    }


run_flow_step("undo_flow_collect", collect_undo_flow)
