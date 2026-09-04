"""Exercise analytic-plane maintenance through Rhino's EndCommand handler."""

import sys
import types

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, circular_plane_definition, cleanup, point_data, run_test



def _plane_origin(doc, definition):
    from tack import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None, "Analytic plane did not resolve"
    return Rhino.Geometry.Point3d(plane.Origin)


def _assert_close(actual, expected, tolerance, label):
    assert actual.DistanceTo(expected) <= tolerance, (
        "{}: expected {}, got {}".format(label, expected, actual)
    )


def verify_relationship_lifecycle():
    from tack import analytic_plane
    from tack import display
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    cleanup(doc)
    try:
        parent_id = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0))
        child_id = add_circle(doc, Rhino.Geometry.Point3d(10, 0, 0))
        parent_definition = circular_plane_definition(parent_id)
        child_definition = circular_plane_definition(child_id)
        parent_plane = analytic_plane.resolve_definition(doc, parent_definition)
        child_plane = analytic_plane.resolve_definition(doc, child_definition)
        assert parent_plane is not None and child_plane is not None
        aligned_child = plane_link.transform_object_in_place(
            doc,
            doc.Objects.Find(child_id),
            display.plane_to_plane_transform(parent_plane, child_plane),
        )
        assert aligned_child is not None, "Could not align child plane"

        link = plane_link_metadata.create(
            doc,
            parent_id,
            child_id,
            parent_definition,
            child_definition,
            False,
        )
        assert link is not None, "Could not create test relationship"
        state = plane_link.install(doc, link)
        assert state is not None, "Could not install test relationship"
        assert plane_link.display_enabled(doc)
        assert plane_link.set_display_enabled(doc, False)
        assert not plane_link.display_enabled(doc)
        assert plane_link.set_display_enabled(doc, True)

        move = Rhino.Geometry.Vector3d(5, 3, 0)
        child_before = _plane_origin(doc, child_definition)
        assert doc.Objects.Transform(
            parent_id,
            Rhino.Geometry.Transform.Translation(move),
            True,
        )
        plane_link.EndCommandHandler(
            None,
            types.SimpleNamespace(CommandEnglishName="Move"),
        )
        child_after_parent_move = _plane_origin(doc, child_definition)
        _assert_close(
            child_after_parent_move,
            child_before + move,
            tolerance,
            "child follows parent move",
        )

        assert doc.Objects.Transform(
            child_id,
            Rhino.Geometry.Transform.Translation(9, 0, 0),
            True,
        )
        plane_link.EndCommandHandler(
            None,
            types.SimpleNamespace(CommandEnglishName="Move"),
        )
        child_after_correction = _plane_origin(doc, child_definition)
        _assert_close(
            child_after_correction,
            child_after_parent_move,
            tolerance,
            "child correction",
        )

        original_alert = plane_link._show_broken_alert

        def mark_broken(broken_state):
            broken_state["broken"] = True
            broken_state["plane"] = None

        plane_link._show_broken_alert = mark_broken
        try:
            assert doc.Objects.Delete(child_id, True)
            plane_link.EndCommandHandler(
                None,
                types.SimpleNamespace(CommandEnglishName="Delete"),
            )
        finally:
            plane_link._show_broken_alert = original_alert
        assert state["broken"], "Deleting a child must break the relationship"

        return {
            "link_id": link["link_id"],
            "child_after_parent_move": point_data(child_after_parent_move),
            "child_after_correction": point_data(child_after_correction),
        }
    finally:
        cleanup(doc)


if __name__ == "__main__":
    run_test("relationship_lifecycle", verify_relationship_lifecycle)
