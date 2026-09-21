"""Shared low-level Rhino display drawing helpers."""

import Rhino

LOCKED_WIRE_THICKNESS = 1


def _draw_bounding_box(display, geometry, color, thickness):
    bounding_box = geometry.GetBoundingBox(True)
    if bounding_box.IsValid:
        display.DrawBox(bounding_box, color, thickness)


def _draw_brep_edges(display, brep, color, thickness):
    if brep is None:
        return
    for edge in brep.Edges:
        display.DrawCurve(edge, color, thickness)


def draw_wireframe(display, geometry, color, thickness):
    if isinstance(geometry, Rhino.Geometry.Brep):
        _draw_brep_edges(display, geometry, color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        _draw_brep_edges(display, geometry.ToBrep(), color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        display.DrawMeshWires(geometry, color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Curve):
        display.DrawCurve(geometry, color, thickness)
    elif isinstance(geometry, Rhino.Geometry.SubD):
        display.DrawSubDWires(geometry, color, float(thickness))
    elif isinstance(geometry, Rhino.Geometry.Surface):
        _draw_brep_edges(display, geometry.ToBrep(), color, thickness)
    elif isinstance(geometry, Rhino.Geometry.Point):
        display.DrawPoint(geometry.Location, color)
    elif isinstance(geometry, Rhino.Geometry.PointCloud):
        display.DrawPointCloud(geometry, 2, color)
    else:
        _draw_bounding_box(display, geometry, color, thickness)


def draw_locked_wireframe(display, geometry):
    draw_wireframe(
        display,
        geometry,
        Rhino.ApplicationSettings.AppearanceSettings.LockedObjectColor,
        LOCKED_WIRE_THICKNESS,
    )


def draw_transformed_object(display, obj, transform):
    """Draw an object with Tack's filtered dynamic transform."""
    geometry = obj.Geometry
    if isinstance(geometry, Rhino.Geometry.TextEntity):
        display.PushModelTransform(transform)
        try:
            display.DrawText(
                geometry,
                obj.Attributes.DrawColor(obj.Document),
            )
        finally:
            display.PopModelTransform()
        return
    display.DrawObject(obj, transform)


def draw_dotted_line(display, start, end, color, thickness, spacing):
    direction = end - start
    length = direction.Length
    if length <= 1e-7:
        return
    dot_count = min(200, max(1, int(length / max(spacing, 1e-7))))
    step = length / dot_count
    direction.Unitize()
    for index in range(dot_count):
        dot_start = start + direction * (index * step)
        dot_end = start + direction * (index * step + step * 0.35)
        display.DrawLine(dot_start, dot_end, color, thickness)
