import sys

import Rhino

sys.modules.pop("common", None)

from common import assert_close
from common import run_step
from common import tack_modules


def test_bbox_analysis():
    tack_modules(reload_modules=True)
    import tack.analysis.bbox as bbox_analysis
    import tack.analysis.polyline_vertex as polyline_vertex_analysis
    import tack.analysis.vertex as vertex_analysis
    from tack import link
    from tack import metadata
    from tack.prompting import command_menu

    osnap_was_enabled = Rhino.ApplicationSettings.ModelAidSettings.Osnap
    original_pick_link = command_menu._pick_link
    original_disable_osnaps = command_menu.DISABLE_NORMAL_OSNAPS

    def osnap_probe(doc):
        assert not Rhino.ApplicationSettings.ModelAidSettings.Osnap
        return "osnap-disabled"

    try:
        command_menu.DISABLE_NORMAL_OSNAPS = True
        command_menu._pick_link = osnap_probe
        assert command_menu.pick_link(None) == "osnap-disabled"
        assert Rhino.ApplicationSettings.ModelAidSettings.Osnap == osnap_was_enabled
    finally:
        command_menu._pick_link = original_pick_link
        command_menu.DISABLE_NORMAL_OSNAPS = original_disable_osnaps
        Rhino.ApplicationSettings.ModelAidSettings.Osnap = osnap_was_enabled

    box = Rhino.Geometry.Box(
        Rhino.Geometry.Plane.WorldXY,
        Rhino.Geometry.Interval(0, 2),
        Rhino.Geometry.Interval(0, 2),
        Rhino.Geometry.Interval(0, 2),
    ).ToBrep()
    box_anchors = bbox_analysis.anchors(box)
    assert [index for index, _ in box_anchors] == list(range(9))

    extrusion = Rhino.Geometry.Extrusion.Create(
        Rhino.Geometry.Circle(
            Rhino.Geometry.Plane.WorldXY,
            1,
        ).ToNurbsCurve(),
        5,
        True,
    )
    assert extrusion is not None
    assert vertex_analysis.supports_vertex_anchors(extrusion)
    extrusion_anchors = vertex_analysis.anchors(extrusion)
    assert extrusion_anchors
    extrusion_index, extrusion_point = extrusion_anchors[0]
    assert_close(
        vertex_analysis.resolve(extrusion, {"index": extrusion_index}),
        extrusion_point,
        Rhino.RhinoMath.ZeroTolerance,
        "extrusion vertex anchor",
    )
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

    assert polyline_vertex_analysis.supports_vertex_anchors(rectangle)
    assert command_menu._vertex_analyzer(rectangle) is polyline_vertex_analysis
    polyline_anchors = polyline_vertex_analysis.anchors(rectangle)
    assert [index for index, _ in polyline_anchors] == [0, 1, 2, 3]
    assert_close(
        polyline_vertex_analysis.resolve(rectangle, {"index": 2}),
        Rhino.Geometry.Point3d(2, 3, 5),
        Rhino.RhinoMath.ZeroTolerance,
        "closed polyline vertex anchor",
    )
    assert polyline_vertex_analysis.resolve(rectangle, {"index": 4}) is None

    open_polyline = Rhino.Geometry.PolylineCurve(
        [
            Rhino.Geometry.Point3d(0, 0, 0),
            Rhino.Geometry.Point3d(1, 0, 0),
            Rhino.Geometry.Point3d(1, 1, 0),
        ]
    )
    assert [
        index for index, _ in polyline_vertex_analysis.anchors(open_polyline)
    ] == [0, 1, 2]
    assert metadata._parse_anchor(
        {"anchor_type": polyline_vertex_analysis.ANCHOR_TYPE, "index": 2}
    ) == {
        "anchor_type": polyline_vertex_analysis.ANCHOR_TYPE,
        "index": 2,
    }

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
    assert not polyline_vertex_analysis.supports_vertex_anchors(line)

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

    polyline_parent_anchor = dict(polyline_anchors)[2]
    polyline_offset = child_anchor - polyline_parent_anchor
    polyline_link = {
        "version": 3,
        "link_id": "polyline-link",
        "parent_id": "polyline-parent",
        "child_id": "child",
        "parent_anchor": {
            "anchor_type": polyline_vertex_analysis.ANCHOR_TYPE,
            "index": 2,
        },
        "child_anchor": {
            "anchor_type": vertex_analysis.ANCHOR_TYPE,
            "index": 0,
        },
        "offset": [polyline_offset.X, polyline_offset.Y, polyline_offset.Z],
    }
    polyline_result = link.inspect_link(
        None,
        {
            "link_id": "polyline-link",
            "parent_id": "polyline-parent",
            "child_id": "child",
            "link": polyline_link,
        },
        parent_obj=rectangle,
        child_obj=child_box,
    )
    assert polyline_result is not None
    assert_close(
        polyline_result["parent_anchor"],
        polyline_parent_anchor,
        Rhino.RhinoMath.ZeroTolerance,
        "mixed parent polyline vertex anchor",
    )


run_step("test_bbox_analysis", test_bbox_analysis)
