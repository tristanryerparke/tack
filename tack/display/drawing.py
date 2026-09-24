"""Shared low-level Rhino display drawing helpers."""

import Rhino
import System.Drawing

LOCKED_WIRE_THICKNESS = 1
POINT_BACKING_COLOR = System.Drawing.Color.White
POINT_CORE_COLOR = System.Drawing.Color.White
SNAP_POINT_BACKING_COLOR = System.Drawing.Color.Black
SNAP_POINT_COLOR = System.Drawing.Color.White


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


def draw_endpoint_point(display, point, ring_color):
    """Draw a Rhino-style colored-ring point with a white core."""
    display.DrawPoint(
        point,
        Rhino.Display.PointStyle.Circle,
        6,
        POINT_BACKING_COLOR,
    )
    display.DrawPoint(
        point,
        Rhino.Display.PointStyle.Circle,
        4,
        ring_color,
    )
    display.DrawPoint(
        point,
        Rhino.Display.PointStyle.Circle,
        2,
        POINT_CORE_COLOR,
    )


def draw_center_snap_point(display, point):
    """Draw the object-center snap as a 2 px white circle with black backing."""
    display.DrawPoint(
        point,
        Rhino.Display.PointStyle.Circle,
        4,
        SNAP_POINT_BACKING_COLOR,
    )
    display.DrawPoint(
        point,
        Rhino.Display.PointStyle.Circle,
        2,
        SNAP_POINT_COLOR,
    )


def draw_dotted_line(display, start, end, color, thickness):
    """Draw one native dotted line between Tack endpoints."""
    if start.DistanceTo(end) <= 1e-7:
        return
    # Two drawn pixels and six gap pixels, repeating: double the dotted pattern.
    display.DrawPatternedLine(start, end, color, 0x0303, thickness)
