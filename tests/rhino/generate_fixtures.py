"""Generate committed analytic-plane test fixtures in an open blank Rhino doc."""

import sys
from pathlib import Path

import Rhino
import scriptcontext as sc

sys.modules.pop("common", None)
from common import add_circle, cleanup, mark_test_object, run_test


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
HOLE_COUNT = 100
HOLE_RADIUS = 1.0
CYLINDER_RADIUS = 0.6
HEIGHT = 10.0
SPACING = 4.0


def _curve_plane(object_id):
    return {
        "type": "circular_curve_plane",
        "object_id": str(object_id),
        "curve_center_anchor": {"type": "curve_center"},
    }


def _circular_edge_plane(doc, obj, target, tolerance):
    from tack import anchor_definitions

    candidates = anchor_definitions.candidates(
        obj,
        anchor_definitions.CIRCULAR_EDGE_CENTER,
        tolerance,
    )
    anchor, center = min(candidates, key=lambda item: item[1].DistanceTo(target))
    assert center.DistanceTo(target) <= tolerance, (
        "No circular edge center at {}".format(target)
    )
    return {
        "type": "circular_edge_plane",
        "object_id": str(obj.Id),
        "edge_center_anchor": anchor,
    }


def _add_cylinder(doc, center, radius=CYLINDER_RADIUS):
    circle = Rhino.Geometry.Circle(
        Rhino.Geometry.Plane(center, Rhino.Geometry.Vector3d.ZAxis),
        radius,
    )
    cylinder = Rhino.Geometry.Cylinder(circle, HEIGHT)
    object_id = doc.Objects.AddBrep(cylinder.ToBrep(True, True))
    mark_test_object(doc, object_id)
    return object_id


def _write(doc, name):
    path = FIXTURES / name
    options = Rhino.FileIO.FileWriteOptions()
    options.SuppressDialogBoxes = True
    assert doc.Write3dmFile(str(path), options), "Could not write {}".format(path)
    return path


def _create_restore_fixture(doc):
    from tack import plane_link_metadata

    parent = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0), radius=4.0)
    child = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0), radius=2.0)
    link = plane_link_metadata.create(
        doc,
        parent,
        child,
        _curve_plane(parent),
        _curve_plane(child),
        False,
    )
    assert link is not None
    return _write(doc, "analytic_plane_restore.3dm"), link["link_id"]


def _create_nested_fixture(doc):
    from tack import plane_link_metadata

    grandparent = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0), radius=6.0)
    parent = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0), radius=4.0)
    child = add_circle(doc, Rhino.Geometry.Point3d(0, 0, 0), radius=2.0)
    first = plane_link_metadata.create(
        doc,
        grandparent,
        parent,
        _curve_plane(grandparent),
        _curve_plane(parent),
        False,
    )
    second = plane_link_metadata.create(
        doc,
        parent,
        child,
        _curve_plane(parent),
        _curve_plane(child),
        False,
    )
    assert first is not None and second is not None
    return _write(doc, "nested_analytic_planes.3dm"), [
        first["link_id"],
        second["link_id"],
    ]


def _create_perforated_fixture(doc):
    from tack import plane_link_metadata

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    length = (HOLE_COUNT + 1) * SPACING
    perforated = Rhino.Geometry.Brep.CreateFromBox(
        Rhino.Geometry.BoundingBox(
            Rhino.Geometry.Point3d(0, -5, 0),
            Rhino.Geometry.Point3d(length, 5, HEIGHT),
        )
    )
    for index in range(HOLE_COUNT):
        center = Rhino.Geometry.Point3d((index + 1) * SPACING, 0, -1)
        cutter = Rhino.Geometry.Cylinder(
            Rhino.Geometry.Circle(
                Rhino.Geometry.Plane(center, Rhino.Geometry.Vector3d.ZAxis),
                HOLE_RADIUS,
            ),
            HEIGHT + 2,
        ).ToBrep(True, True)
        result = Rhino.Geometry.Brep.CreateBooleanDifference(
            perforated,
            cutter,
            tolerance,
        )
        assert result and len(result) == 1, "Could not cut hole {}".format(index)
        perforated = result[0]

    parent_id = doc.Objects.AddBrep(perforated)
    mark_test_object(doc, parent_id)
    parent = doc.Objects.Find(parent_id)
    link_ids = []
    for index in range(HOLE_COUNT):
        x = (index + 1) * SPACING
        center = Rhino.Geometry.Point3d(x, 0, 0)
        child_id = _add_cylinder(doc, center)
        child = doc.Objects.Find(child_id)
        top_center = Rhino.Geometry.Point3d(x, 0, HEIGHT)
        link = plane_link_metadata.create(
            doc,
            parent_id,
            child_id,
            _circular_edge_plane(doc, parent, top_center, tolerance),
            _circular_edge_plane(doc, child, top_center, tolerance),
            False,
        )
        assert link is not None, "Could not create hole Tack {}".format(index)
        link_ids.append(link["link_id"])
    return _write(doc, "perforated_100_holes.3dm"), link_ids


def generate_fixtures():
    doc = sc.doc
    FIXTURES.mkdir(exist_ok=True)
    created = {}
    try:
        cleanup(doc)
        path, links = _create_restore_fixture(doc)
        created[path.name] = {"link_count": 1, "link_ids": [links]}
        cleanup(doc)

        path, links = _create_nested_fixture(doc)
        created[path.name] = {"link_count": len(links), "link_ids": links}
        cleanup(doc)

        path, links = _create_perforated_fixture(doc)
        created[path.name] = {"link_count": len(links), "link_ids": links}
        return {"fixtures": created}
    finally:
        cleanup(doc)


run_test("generate_analytic_plane_fixtures", generate_fixtures)
