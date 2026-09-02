"""Move one perforated parent Brep and verify its 100 cylinder Tacks follow."""

import sys
import time
import types

import System
import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import point_data, run_test


RELATIONSHIP_COUNT = 100
MOVE = Rhino.Geometry.Vector3d(12, 5, 0)


def _origin(doc, definition):
    from tack import analytic_plane

    plane = analytic_plane.resolve_definition(doc, definition)
    assert plane is not None
    return Rhino.Geometry.Point3d(plane.Origin)


def verify_stress_fixture():
    from tack import anchor_definitions
    from tack import plane_link
    from tack import plane_link_metadata

    doc = sc.doc
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    plane_link._remove_runtime(doc)
    assert (
        plane_link.restore_document(doc, default_display_enabled=False)
        == RELATIONSHIP_COUNT
    )
    links = plane_link_metadata.all_links(doc)
    assert len(links) == RELATIONSHIP_COUNT
    parent_ids = {link["parent_id"] for link in links}
    assert len(parent_ids) == 1
    parent = doc.Objects.Find(System.Guid.Parse(next(iter(parent_ids))))
    assert isinstance(parent.Geometry, Rhino.Geometry.Brep)

    top_hole_centers = {
        round(point.X, 6)
        for _, point in anchor_definitions.candidates(
            parent,
            anchor_definitions.CIRCULAR_EDGE_CENTER,
            tolerance,
        )
        if abs(point.Z - 10.0) <= tolerance
    }
    assert len(top_hole_centers) == RELATIONSHIP_COUNT

    before = {
        link["link_id"]: _origin(doc, link["child_plane"])
        for link in links
    }
    started = time.perf_counter()
    transformed_parent = plane_link.transform_object_in_place(
        doc,
        parent,
        Rhino.Geometry.Transform.Translation(MOVE),
    )
    assert transformed_parent is not None
    plane_link.EndCommandHandler(
        None,
        types.SimpleNamespace(CommandEnglishName="Move"),
    )
    update_seconds = time.perf_counter() - started

    moved_child_count = 0
    for link in links:
        after = _origin(doc, link["child_plane"])
        expected = before[link["link_id"]] + MOVE
        assert after.DistanceTo(expected) <= tolerance, (
            "Child {} did not follow its hole".format(link["link_id"])
        )
        moved_child_count += 1

    return {
        "relationship_count": len(links),
        "moved_child_count": moved_child_count,
        "update_seconds": update_seconds,
        "first_child": point_data(next(iter(before.values())) + MOVE),
    }


run_test("stress_100_holes", verify_stress_fixture)
