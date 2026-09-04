"""Resolve, validate, and draw analytic plane definitions."""

import Rhino
import System
import System.Drawing

from tack import anchor_definitions


CROSSHAIR_SIZE_MIN = 5
CROSSHAIR_SIZE_MAX = 20
CROSSHAIR_SIZE = float(CROSSHAIR_SIZE_MAX)
CROSSHAIR_COLOR = System.Drawing.Color.Orange
CROSSHAIR_THICKNESS = 2


def preview_half_extent(size=CROSSHAIR_SIZE):
    return float(size) * 0.5


def preview_circle_radius(size=CROSSHAIR_SIZE):
    return float(size) * 0.25


def _definition_object(doc, definition):
    try:
        object_id = System.Guid(str(definition["object_id"]))
    except Exception:
        return None
    return doc.Objects.FindId(object_id)


def _resolve_three_point_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    try:
        origin_definition = definition["origin_anchor"]
        x_definition = definition["x_axis_anchor"]
        y_definition = definition["y_axis_anchor"]
    except Exception:
        return None

    tolerance = max(doc.ModelAbsoluteTolerance, 1e-7)
    origin = anchor_definitions.resolve(obj, origin_definition, tolerance)
    x_point = anchor_definitions.resolve(obj, x_definition, tolerance)
    y_point = anchor_definitions.resolve(obj, y_definition, tolerance)
    if origin is None or x_point is None or y_point is None:
        return None

    plane = Rhino.Geometry.Plane(origin, x_point, y_point)
    return plane if plane.IsValid else None


def _plane_from_circular_curve(curve, circle):
    x_axis = curve.PointAtStart - circle.Center
    if not x_axis.Unitize():
        return None
    normal = Rhino.Geometry.Vector3d(circle.Normal)
    if not normal.Unitize():
        return None
    y_axis = Rhino.Geometry.Vector3d.CrossProduct(normal, x_axis)
    if not y_axis.Unitize():
        return None
    plane = Rhino.Geometry.Plane(circle.Center, x_axis, y_axis)
    return plane if plane.IsValid else None


def _resolve_circular_edge_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    try:
        center_definition = definition["edge_center_anchor"]
    except Exception:
        return None
    resolved = anchor_definitions.circular_edge(
        obj,
        center_definition,
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if resolved is None:
        return None
    return _plane_from_circular_curve(*resolved)


def _resolve_circular_curve_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    try:
        center_definition = definition["curve_center_anchor"]
    except Exception:
        return None
    resolved = anchor_definitions.circular_curve(
        obj,
        center_definition,
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if resolved is None:
        return None
    return _plane_from_circular_curve(*resolved)


_DEFINITION_RESOLVERS = {
    "three_point_plane": _resolve_three_point_plane,
    "circular_edge_plane": _resolve_circular_edge_plane,
    "circular_curve_plane": _resolve_circular_curve_plane,
}


def resolve_definition(doc, definition):
    if not isinstance(definition, dict):
        return None
    resolver = _DEFINITION_RESOLVERS.get(definition.get("type"))
    return None if resolver is None else resolver(doc, definition)


def _valid_three_point_plane(definition):
    return set(definition) == {
        "type",
        "object_id",
        "origin_anchor",
        "x_axis_anchor",
        "y_axis_anchor",
    } and all(
        anchor_definitions.validate(definition[name])
        for name in ("origin_anchor", "x_axis_anchor", "y_axis_anchor")
    )


def _valid_circular_plane(definition, definition_type, field, anchor_type):
    if set(definition) != {"type", "object_id", field}:
        return False
    anchor = definition[field]
    return (
        definition.get("type") == definition_type
        and anchor_definitions.validate(anchor)
        and anchor.get("type") == anchor_type
    )


def validate_definition(definition, expected_object_id=None):
    if not isinstance(definition, dict):
        return False
    definition_type = definition.get("type")
    valid = (
        _valid_three_point_plane(definition)
        if definition_type == "three_point_plane"
        else _valid_circular_plane(
            definition,
            "circular_edge_plane",
            "edge_center_anchor",
            anchor_definitions.CIRCULAR_EDGE_CENTER,
        )
        if definition_type == "circular_edge_plane"
        else _valid_circular_plane(
            definition,
            "circular_curve_plane",
            "curve_center_anchor",
            anchor_definitions.CURVE_CENTER,
        )
        if definition_type == "circular_curve_plane"
        else False
    )
    if not valid:
        return False
    try:
        object_id = System.Guid(str(definition["object_id"]))
    except Exception:
        return False
    return expected_object_id is None or str(object_id).lower() == str(
        expected_object_id
    ).lower()


def plane_border(origin, x_axis, y_axis, half_extent):
    if x_axis is None or y_axis is None:
        return []
    return [
        origin - x_axis * half_extent - y_axis * half_extent,
        origin + x_axis * half_extent - y_axis * half_extent,
        origin + x_axis * half_extent + y_axis * half_extent,
        origin - x_axis * half_extent + y_axis * half_extent,
    ]


def draw_preview(display, plane, size=CROSSHAIR_SIZE):
    if plane is None or not plane.IsValid:
        return
    origin = plane.Origin
    x_axis = plane.XAxis
    y_axis = plane.YAxis
    half_extent = preview_half_extent(size)
    appearance = Rhino.ApplicationSettings.AppearanceSettings

    display.DrawLine(
        origin,
        origin - x_axis * half_extent,
        CROSSHAIR_COLOR,
        CROSSHAIR_THICKNESS,
    )
    display.DrawLine(
        origin,
        origin - y_axis * half_extent,
        CROSSHAIR_COLOR,
        CROSSHAIR_THICKNESS,
    )
    display.DrawCircle(
        Rhino.Geometry.Circle(plane, preview_circle_radius(size)),
        CROSSHAIR_COLOR,
        CROSSHAIR_THICKNESS,
    )
    display.DrawLine(
        origin,
        origin + x_axis * half_extent,
        appearance.GridXAxisLineColor,
        CROSSHAIR_THICKNESS,
    )
    display.DrawLine(
        origin,
        origin + y_axis * half_extent,
        appearance.GridYAxisLineColor,
        CROSSHAIR_THICKNESS,
    )


def bounding_box(plane, size=CROSSHAIR_SIZE):
    return Rhino.Geometry.BoundingBox(
        plane_border(
            plane.Origin,
            plane.XAxis,
            plane.YAxis,
            preview_half_extent(size),
        )
    )
