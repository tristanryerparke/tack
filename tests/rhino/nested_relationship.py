"""Verify a parent-to-parent-to-child chain settles in one EndCommand."""

import sys
import types

import System
import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import point_data, run_test


MOVE = Rhino.Geometry.Vector3d(4, 6, 0)


def _origin(doc, definition):
    from tack import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return Rhino.Geometry.Point3d(plane.Origin)


def _assert_close(actual, expected, tolerance):
    assert actual.DistanceTo(expected) <= tolerance, (
        "Expected {}, got {}".format(expected, actual)
    )


def verify_nested_relationship():
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    plane_link._remove_runtime(doc)
    assert plane_link.restore_document(doc, default_display_enabled=False) == 2
    links = plane_link_metadata.all_links(doc)
    parent_ids = {link["parent_id"] for link in links}
    child_ids = {link["child_id"] for link in links}
    grandparent_id = next(iter(parent_ids - child_ids))
    middle_id = next(iter(parent_ids & child_ids))
    child_id = next(iter(child_ids - parent_ids))
    by_parent = {link["parent_id"]: link for link in links}
    first = by_parent[grandparent_id]
    second = by_parent[middle_id]
    before = _origin(doc, second["child_plane"])

    transformed_grandparent = plane_link.transform_object_in_place(
        doc,
        doc.Objects.Find(System.Guid.Parse(grandparent_id)),
        Rhino.Geometry.Transform.Translation(MOVE),
    )
    assert transformed_grandparent is not None
    plane_link.EndCommandHandler(
        None,
        types.SimpleNamespace(CommandEnglishName="Move"),
    )

    middle = _origin(doc, first["child_plane"])
    child = _origin(doc, second["child_plane"])
    _assert_close(middle, before + MOVE, tolerance)
    _assert_close(child, before + MOVE, tolerance)
    assert str(second["child_id"]).lower() == child_id.lower()
    return {
        "middle": point_data(middle),
        "child": point_data(child),
    }


run_test("nested_relationship", verify_nested_relationship)
