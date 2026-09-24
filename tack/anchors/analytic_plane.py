"""Resolve, validate, and draw analytic plane definitions."""

import Rhino
import System
import System.Drawing

from tack.anchors import definitions

CROSSHAIR_SIZE_MIN = 1
CROSSHAIR_SIZE_MAX = 20
CROSSHAIR_SIZE = float(CROSSHAIR_SIZE_MAX)
PARENT_COLOR = System.Drawing.Color.Red
CHILD_COLOR = System.Drawing.Color.Orange
CROSSHAIR_COLOR = CHILD_COLOR
CROSSHAIR_THICKNESS_MIN = 1
CROSSHAIR_THICKNESS_MAX = 5
CROSSHAIR_THICKNESS = 2


def preview_half_extent(size=CROSSHAIR_SIZE):
    return float(size) * 0.5


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
    origin = definitions.resolve(obj, origin_definition, tolerance)
    x_point = definitions.resolve(obj, x_definition, tolerance)
    y_point = definitions.resolve(obj, y_definition, tolerance)
    if origin is None or x_point is None or y_point is None:
        return None

    plane = Rhino.Geometry.Plane(origin, x_point, y_point)
    return plane if plane.IsValid else None


def _resolve_world_axes_plane(doc, definition):
    obj = _definition_object(doc, definition)
    if obj is None:
        return None
    origin = definitions.resolve(
        obj,
        definition.get("origin_anchor"),
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if origin is None:
        return None
    plane = Rhino.Geometry.Plane(
        origin,
        Rhino.Geometry.Vector3d.XAxis,
        Rhino.Geometry.Vector3d.YAxis,
    )
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
    resolved = definitions.circular_edge(
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
    resolved = definitions.circular_curve(
        obj,
        center_definition,
        max(doc.ModelAbsoluteTolerance, 1e-7),
    )
    if resolved is None:
        return None
    return _plane_from_circular_curve(*resolved)


_DEFINITION_RESOLVERS = {
    "three_point_plane": _resolve_three_point_plane,
    "world_axes_plane": _resolve_world_axes_plane,
    "circular_edge_plane": _resolve_circular_edge_plane,
    "circular_curve_plane": _resolve_circular_curve_plane,
}


def _flipped_plane(plane):
    return Rhino.Geometry.Plane(plane.Origin, plane.XAxis, -plane.YAxis)


def flipped_definition(definition):
    """Return the same saved plane selection with its Z orientation reversed."""
    if not isinstance(definition, dict):
        return None
    flipped = dict(definition)
    flipped["flipped"] = not bool(flipped.get("flipped", False))
    return flipped


def resolve_definition(doc, definition):
    if not isinstance(definition, dict):
        return None
    resolver = _DEFINITION_RESOLVERS.get(definition.get("type"))
    plane = None if resolver is None else resolver(doc, definition)
    return (
        _flipped_plane(plane)
        if plane is not None and definition.get("flipped")
        else plane
    )


def _has_fields(definition, fields):
    return (
        set(definition).issubset(set(fields) | {"flipped"})
        and set(fields).issubset(definition)
        and isinstance(definition.get("flipped", False), bool)
    )


def _valid_three_point_plane(definition):
    return _has_fields(
        definition,
        {
            "type",
            "object_id",
            "origin_anchor",
            "x_axis_anchor",
            "y_axis_anchor",
        },
    ) and all(
        definitions.validate(definition[name])
        for name in ("origin_anchor", "x_axis_anchor", "y_axis_anchor")
    )


def _valid_world_axes_plane(definition):
    return _has_fields(definition, {"type", "object_id", "origin_anchor"}) and (
        definitions.validate(definition["origin_anchor"])
    )


def _valid_circular_plane(definition, definition_type, field, anchor_type):
    if not _has_fields(definition, {"type", "object_id", field}):
        return False
    anchor = definition[field]
    return (
        definition.get("type") == definition_type
        and definitions.validate(anchor)
        and anchor.get("type") == anchor_type
    )


def validate_definition(definition, expected_object_id=None):
    if not isinstance(definition, dict):
        return False
    definition_type = definition.get("type")
    valid = (
        _valid_three_point_plane(definition)
        if definition_type == "three_point_plane"
        else _valid_world_axes_plane(definition)
        if definition_type == "world_axes_plane"
        else _valid_circular_plane(
            definition,
            "circular_edge_plane",
            "edge_center_anchor",
            definitions.CIRCULAR_EDGE_CENTER,
        )
        if definition_type == "circular_edge_plane"
        else _valid_circular_plane(
            definition,
            "circular_curve_plane",
            "curve_center_anchor",
            definitions.CURVE_CENTER,
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
    return (
        expected_object_id is None
        or str(object_id).lower() == str(expected_object_id).lower()
    )


def draw_preview(
    display,
    plane,
    size=CROSSHAIR_SIZE,
    thickness=CROSSHAIR_THICKNESS,
):
    """Draw the three oriented axes used while choosing a Tack plane."""
    if plane is None or not plane.IsValid:
        return
    origin = plane.Origin
    half_extent = preview_half_extent(size)
    appearance = Rhino.ApplicationSettings.AppearanceSettings
    for axis, color in (
        (plane.XAxis, appearance.GridXAxisLineColor),
        (plane.YAxis, appearance.GridYAxisLineColor),
        (plane.ZAxis, appearance.GridZAxisLineColor),
    ):
        display.DrawLine(origin, origin + axis * half_extent, color, thickness)


def bounding_box(plane, size=CROSSHAIR_SIZE):
    half_extent = preview_half_extent(size)
    return Rhino.Geometry.BoundingBox(
        [
            plane.Origin,
            plane.Origin + plane.XAxis * half_extent,
            plane.Origin + plane.YAxis * half_extent,
            plane.Origin + plane.ZAxis * half_extent,
        ]
    )
