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
        middle_id = add_circle(doc, Rhino.Geometry.Point3d(10, 0, 0))
        child_id = add_circle(doc, Rhino.Geometry.Point3d(20, 0, 0))
        parent_definition = circular_plane_definition(parent_id)
        middle_definition = circular_plane_definition(middle_id)
        child_definition = circular_plane_definition(child_id)
        parent_plane = analytic_plane.resolve_definition(doc, parent_definition)
        middle_plane = analytic_plane.resolve_definition(doc, middle_definition)
        assert parent_plane is not None and middle_plane is not None
        assert transforms.transform_object_in_place(
            doc,
            doc.Objects.Find(middle_id),
            transforms.plane_to_plane_transform(parent_plane, middle_plane),
        ) is not None
        parent_link = repository.create(
            doc,
            parent_id,
            middle_id,
            parent_definition,
            middle_definition,
            allow_child_movement=True,
        )
        assert parent_link is not None
        assert runtime.install(doc, parent_link) is not None

        middle_plane = analytic_plane.resolve_definition(doc, middle_definition)
        child_plane = analytic_plane.resolve_definition(doc, child_definition)
        assert middle_plane is not None and child_plane is not None
        assert transforms.transform_object_in_place(
            doc,
            doc.Objects.Find(child_id),
            transforms.plane_to_plane_transform(middle_plane, child_plane),
        ) is not None
        child_link = repository.create(
            doc,
            middle_id,
            child_id,
            middle_definition,
            child_definition,
            allow_child_movement=True,
        )
        assert child_link is not None
        assert runtime.install(doc, child_link) is not None

        assert doc.Objects.Transform(
            middle_id,
            Rhino.Geometry.Transform.Translation(5, 0, 0),
            True,
        )
        lifecycle.end_command_handler(
            None,
            types.SimpleNamespace(CommandEnglishName="Move"),
        )
        assert doc.Objects.Transform(
            child_id,
            Rhino.Geometry.Transform.Translation(4, 0, 0),
            True,
        )
        lifecycle.end_command_handler(
            None,
            types.SimpleNamespace(CommandEnglishName="Move"),
        )
        moved_middle = _origin(doc, middle_definition)
        moved_child = _origin(doc, child_definition)
        assert len(runtime.resettable_links(doc)) == 2
        doc.ClearUndoRecords(True)
        return {
            "middle_moved": point_data(moved_middle),
            "child_moved": point_data(moved_child),
            "link_ids": [parent_link.link_id, child_link.link_id],
        }
    except Exception:
        cleanup(doc)
        raise


run_flow_step("reset_moveable_tacks_setup", setup_reset_moveable_tacks)
