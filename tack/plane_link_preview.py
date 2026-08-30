"""Display conduits used while creating an analytic-plane relationship."""

import Rhino

from tack import three_point_plane
from tack import utils


LOCKED_WIRE_THICKNESS = 1


def inverted_plane(plane):
    """Return the same origin/X axis with the Y and normal directions flipped."""
    return Rhino.Geometry.Plane(plane.Origin, plane.XAxis, -plane.YAxis)


def plane_to_plane_transform(parent_plane, child_plane, inverted=False):
    source = inverted_plane(child_plane) if inverted else child_plane
    return Rhino.Geometry.Transform.PlaneToPlane(source, parent_plane)


class PlaneDisplayConduit(Rhino.Display.DisplayConduit):
    def __init__(self, plane):
        super(PlaneDisplayConduit, self).__init__()
        self.plane = plane

    def CalculateBoundingBox(self, event):
        points = three_point_plane.plane_border(
            self.plane.Origin,
            self.plane.XAxis,
            self.plane.YAxis,
            three_point_plane.PLANE_HALF_EXTENT,
        )
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points))

    def DrawOverlay(self, event):
        three_point_plane.draw_preview(
            event.Display,
            self.plane.Origin,
            self.plane.XAxis,
            self.plane.YAxis,
            three_point_plane.PLANE_HALF_EXTENT,
            grid_spacing=three_point_plane.GRID_SPACING,
            major_frequency=(
                event.Viewport.GetConstructionPlane().ThickLineFrequency
            ),
        )


def _draw_bounding_box(display, geometry, color):
    bounding_box = geometry.GetBoundingBox(True)
    if not bounding_box.IsValid:
        return
    for line in Rhino.Geometry.Box(bounding_box).GetEdges():
        display.DrawLine(line, color, LOCKED_WIRE_THICKNESS)


def _draw_locked_wireframe(display, geometry):
    color = Rhino.ApplicationSettings.AppearanceSettings.LockedObjectColor
    if isinstance(geometry, Rhino.Geometry.Brep):
        display.DrawBrepWires(geometry, color, 1)
    elif isinstance(geometry, Rhino.Geometry.Extrusion):
        display.DrawExtrusionWires(geometry, color, 1)
    elif isinstance(geometry, Rhino.Geometry.Mesh):
        display.DrawMeshWires(geometry, color, LOCKED_WIRE_THICKNESS)
    elif isinstance(geometry, Rhino.Geometry.Curve):
        display.DrawCurve(geometry, color, LOCKED_WIRE_THICKNESS)
    elif isinstance(geometry, Rhino.Geometry.SubD):
        display.DrawSubDWires(geometry, color, float(LOCKED_WIRE_THICKNESS))
    elif isinstance(geometry, Rhino.Geometry.Surface):
        display.DrawSurface(geometry, color, 1)
    elif isinstance(geometry, Rhino.Geometry.Point):
        display.DrawPoint(geometry.Location, color)
    elif isinstance(geometry, Rhino.Geometry.PointCloud):
        display.DrawPointCloud(geometry, 2, color)
    else:
        _draw_bounding_box(display, geometry, color)


class TransformPreviewConduit(Rhino.Display.DisplayConduit):
    """Show the old child as locked wires and its transformed copy normally."""

    def __init__(self, child, parent_plane, child_plane, inverted=False):
        super(TransformPreviewConduit, self).__init__()
        self.child = child
        self.parent_plane = parent_plane
        self.child_plane = child_plane
        self.inverted = bool(inverted)
        self._drawing_child = False

    @property
    def transform(self):
        return plane_to_plane_transform(
            self.parent_plane,
            self.child_plane,
            self.inverted,
        )

    def CalculateBoundingBox(self, event):
        bounding_box = self.child.Geometry.GetBoundingBox(True)
        if not bounding_box.IsValid:
            return
        points = list(bounding_box.GetCorners())
        transform = self.transform
        transformed_points = []
        for point in points:
            transformed = Rhino.Geometry.Point3d(point)
            transformed.Transform(transform)
            transformed_points.append(transformed)
        event.IncludeBoundingBox(Rhino.Geometry.BoundingBox(points + transformed_points))

    def PreDrawObject(self, event):
        if self._drawing_child:
            return
        obj = event.RhinoObject
        if obj is not None and utils.same_id(obj.Id, self.child.Id):
            event.DrawObject = False

    def PostDrawObjects(self, event):
        child = self.child
        if child is None or child.Geometry is None:
            return
        _draw_locked_wireframe(event.Display, child.Geometry)
        self._drawing_child = True
        try:
            event.Display.DrawObject(child, self.transform)
        finally:
            self._drawing_child = False
