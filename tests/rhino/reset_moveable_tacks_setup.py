"""Create a deviated child-movable Tack for the reset-command undo flow."""

import sys
import types

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import (
    add_circle,
    circular_plane_definition,
    cleanup,
    point_data,
    run_flow_step,
)


def _origin(doc, definition):
    from tack.anchors import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return plane.Origin


def setup_reset_moveable_tacks():
    from tack.anchors import analytic_plane
    from tack.links import lifecycle, repository, runtime, transforms

    doc = sc.doc
    cleanup(doc)
    try:
        parent_id = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
        child_id = add_circle(doc, Rhino.Geometry.Point3d(10, 0, 0))
        parent_definition = circular_plane_definition(parent_id)
        child_definition = circular_plane_definition(child_id)
        parent_plane = analytic_plane.resolve_definition(doc, parent_definition)
        child_plane = analytic_plane.resolve_definition(doc, child_definition)
        assert parent_plane is not None and child_plane is not None
        assert transforms.transform_object_in_place(
            doc,
            doc.Objects.Find(child_id),
            transforms.plane_to_plane_transform(parent_plane, child_plane),
        ) is not None
        link = repository.create(
            doc,
            parent_id,
            child_id,
            parent_definition,
            child_definition,
            allow_child_movement=True,
        )
        assert link is not None
        assert runtime.install(doc, link) is not None
        assert doc.Objects.Transform(
            child_id,
            Rhino.Geometry.Transform.Translation(9, 0, 0),
            True,
        )
        lifecycle.end_command_handler(
            None,
            types.SimpleNamespace(CommandEnglishName="Move"),
        )
        moved_child = _origin(doc, child_definition)
        assert runtime.resettable_links(doc)
        doc.ClearUndoRecords(True)
        return {
            "child_moved": point_data(moved_child),
            "link_id": link.link_id,
        }
    except Exception:
        cleanup(doc)
        raise


run_flow_step("reset_moveable_tacks_setup", setup_reset_moveable_tacks)
