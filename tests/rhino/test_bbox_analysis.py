import sys

import Rhino

sys.modules.pop("common", None)

from common import assert_close
from common import run_step
from common import tack_modules


def test_bbox_analysis():
    tack_modules(reload_modules=True)
    import tack.analysis.bbox as bbox_analysis
    import tack.analysis.vertex as vertex_analysis
    from tack import link

    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(0, 2),
        Rhino.Geometry.Interval(0, 2),
        Rhino.Geometry.Interval(0, 2),
    ).ToBrep()
    box_anchors = bbox_analysis.anchors(box)
    assert [index for index, _ in box_anchors] == list(range(9))
    assert len(bbox_analysis.wire_segments(box)) == 12
    assert_close(
        dict(box_anchors)[bbox_analysis.CENTER_INDEX],
        Rhino.Geometry.Point3d(1, 1, 1),
        Rhino.RhinoMath.ZeroTolerance,
        "box center anchor",
    )

    rectangle = Rhino.Geometry.PolylineCurve(
        [
            Rhino.Geometry.Point3d(0, 0, 5),
            Rhino.Geometry.Point3d(2, 0, 5),
            Rhino.Geometry.Point3d(2, 3, 5),
            Rhino.Geometry.Point3d(0, 3, 5),
            Rhino.Geometry.Point3d(0, 0, 5),
        ]
    )
    assert [index for index, _ in bbox_analysis.anchors(rectangle)] == [
        0,
        1,
        2,
        3,
        bbox_analysis.CENTER_INDEX,
    ]
    assert len(bbox_analysis.wire_segments(rectangle)) == 4

    line = Rhino.Geometry.LineCurve(
        Rhino.Geometry.Point3d(0, 0, 0),
        Rhino.Geometry.Point3d(2, 0, 0),
    )
    assert [index for index, _ in bbox_analysis.anchors(line)] == [
        0,
        1,
        bbox_analysis.CENTER_INDEX,
    ]
    assert len(bbox_analysis.wire_segments(line)) == 1

    point = Rhino.Geometry.Point(Rhino.Geometry.Point3d(4, 5, 6))
    assert [index for index, _ in bbox_analysis.anchors(point)] == [
        bbox_analysis.CENTER_INDEX
    ]
    assert bbox_analysis.wire_segments(point) == []

    child_box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(10, 12),
        Rhino.Geometry.Interval(0, 2),
        Rhino.Geometry.Interval(0, 2),
    ).ToBrep()
    parent_anchor = dict(box_anchors)[bbox_analysis.CENTER_INDEX]
    child_anchor = dict(vertex_analysis.anchors(child_box))[0]
    offset = child_anchor - parent_anchor
    mixed_link = {
        "version": 3,
        "link_id": "mixed-link",
        "parent_id": "parent",
        "child_id": "child",
        "parent_anchor": {
            "anchor_type": bbox_analysis.ANCHOR_TYPE,
            "index": bbox_analysis.CENTER_INDEX,
        },
        "child_anchor": {
            "anchor_type": vertex_analysis.ANCHOR_TYPE,
            "index": 0,
        },
        "offset": [offset.X, offset.Y, offset.Z],
    }
    result = link.inspect_link(
        None,
        {
            "link_id": "mixed-link",
            "parent_id": "parent",
            "child_id": "child",
            "link": mixed_link,
        },
        parent_obj=box,
        child_obj=child_box,
    )
    assert result is not None
    assert_close(
        result["parent_anchor"],
        parent_anchor,
        Rhino.RhinoMath.ZeroTolerance,
        "mixed parent bounding-box anchor",
    )
    assert_close(
        result["child_anchor"],
        child_anchor,
        Rhino.RhinoMath.ZeroTolerance,
        "mixed child vertex anchor",
    )


run_step("test_bbox_analysis", test_bbox_analysis)
