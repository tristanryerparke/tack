"""Verify persisted analytic anchors resolve directly in real Rhino geometry."""

import sys

import Rhino
import rhinoscriptsyntax as rs
import scriptcontext as sc

sys.modules.pop("common", None)
from common import cleanup, mark_test_object, run_test



def _assert_resolves(obj, feature_type, tolerance):
    from tack import anchor_definitions

    candidates = anchor_definitions.candidates(obj, feature_type, tolerance)
    assert candidates, "No {} candidates".format(feature_type)
    for definition, point in candidates:
        resolved = anchor_definitions.resolve(obj, definition, tolerance)
        assert resolved is not None, "Could not resolve {}".format(definition)
        assert resolved.DistanceTo(point) <= tolerance, (
            "Resolved point differs for {}".format(definition)
        )
    return len(candidates)


def verify_anchor_definitions():
    from tack import anchor_definitions

    doc = sc.doc
    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    cleanup(doc)
    try:
        box_id = rs.AddBox(
            [
                (0, 0, 0),
                (4, 0, 0),
                (4, 3, 0),
                (0, 3, 0),
                (0, 0, 2),
                (4, 0, 2),
                (4, 3, 2),
                (0, 3, 2),
            ]
        )
        mark_test_object(doc, box_id)
        box = doc.Objects.Find(box_id)

        circle_id = doc.Objects.AddCircle(
            Rhino.Geometry.Circle(Rhino.Geometry.Plane.WorldXY, 2.0)
        )
        mark_test_object(doc, circle_id)
        circle = doc.Objects.Find(circle_id)

        line_id = doc.Objects.AddLine(
            Rhino.Geometry.Point3d(10, 0, 0),
            Rhino.Geometry.Point3d(14, 0, 0),
        )
        mark_test_object(doc, line_id)
        line = doc.Objects.Find(line_id)

        polyline_id = doc.Objects.AddPolyline(
            [
                Rhino.Geometry.Point3d(10, 2, 0),
                Rhino.Geometry.Point3d(12, 4, 0),
                Rhino.Geometry.Point3d(14, 2, 0),
            ]
        )
        mark_test_object(doc, polyline_id)
        polyline = doc.Objects.Find(polyline_id)

        cylinder = Rhino.Geometry.Cylinder(
            Rhino.Geometry.Circle(Rhino.Geometry.Plane.WorldXY, 1.5),
            4.0,
        )
        cylinder_id = doc.Objects.AddBrep(cylinder.ToBrep(True, True))
        mark_test_object(doc, cylinder_id)
        cylinder_object = doc.Objects.Find(cylinder_id)

        counts = {
            "brep_vertex": _assert_resolves(
                box,
                anchor_definitions.BREP_VERTEX,
                tolerance,
            ),
            "brep_edge_midpoint": _assert_resolves(
                box,
                anchor_definitions.BREP_EDGE_MIDPOINT,
                tolerance,
            ),
            "brep_face_center": _assert_resolves(
                box,
                anchor_definitions.BREP_FACE_CENTER,
                tolerance,
            ),
            "curve_center": _assert_resolves(
                circle,
                anchor_definitions.CURVE_CENTER,
                tolerance,
            ),
            "curve_midpoint": _assert_resolves(
                circle,
                anchor_definitions.CURVE_MIDPOINT,
                tolerance,
            ),
            "curve_quadrant": _assert_resolves(
                circle,
                anchor_definitions.CURVE_QUADRANT,
                tolerance,
            ),
            "curve_start": _assert_resolves(
                line,
                anchor_definitions.CURVE_START,
                tolerance,
            ),
            "curve_end": _assert_resolves(
                line,
                anchor_definitions.CURVE_END,
                tolerance,
            ),
            "polyline_vertex": _assert_resolves(
                polyline,
                anchor_definitions.POLYLINE_VERTEX,
                tolerance,
            ),
            "polyline_segment_midpoint": _assert_resolves(
                polyline,
                anchor_definitions.POLYLINE_SEGMENT_MIDPOINT,
                tolerance,
            ),
            "circular_edge_center": _assert_resolves(
                cylinder_object,
                anchor_definitions.CIRCULAR_EDGE_CENTER,
                tolerance,
            ),
            "brep_edge_quadrant": _assert_resolves(
                cylinder_object,
                anchor_definitions.BREP_EDGE_QUADRANT,
                tolerance,
            ),
        }
        return {"candidate_counts": counts}
    finally:
        cleanup(doc)


if __name__ == "__main__":
    run_test("anchor_definitions", verify_anchor_definitions)
